"""Biweekly TAM check (the evening run of every second Sunday): does each source of data/business/tam.yaml still state
its figure?

    uv run python scripts/check_tam.py [--limit 25] [--max-minutes 20] [--dry-run]

For up to ``--limit`` estimates per run (rotating: the ones checked longest ago first; state in var/tam/state.json)
the source page is fetched once, politely, with the rules and the fetcher of the weekly link check
(scripts/check_links.py): robots.txt first, GET only, one request at a time, at least 10 s per host, a host stopped
at the first 403 / 429 or bot check, and never a policy host (qorvo.com, www.qualcomm.com, distributors, iso.org,
archives, the hosts blocked in data/library/sources.yaml). Page text is untrusted: it is only searched, never run.

Result per estimate (data/business/tam_checks.yaml, committed, so the live site shows it on TAM estimates):
- verified      the page states the value with its year in US dollars and names the market;
- changed       the same page shows a newer figure (a later base year) or a different value for a later year;
- unverifiable  no link, page gone, robots / policy / block, or the figure is not on the page (paywall, script);
- disqualified  the page gives a different figure for the same year (or another currency), or the source is not a
                market-research or company publication (a blog, wiki, forum or summary site).
Nothing is ever deleted: app/services/tam.py leaves a disqualified estimate out of the market size, unless the
owner agreed with it, in which case it stays and the owner is asked to look again. Estimates added on the site
(database rows) are not checked here.
"""

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_links as cl  # noqa: E402

from app import yamlio  # noqa: E402
from app.services import sources, tam  # noqa: E402

OUT = ROOT / "var" / "tam"
STATE = OUT / "state.json"
TAM_YAML = ROOT / "data" / "business" / "tam.yaml"
CHECKS = ROOT / "data" / "business" / "tam_checks.yaml"
USER_AGENT = "BizDevTamCheck/1.0 (biweekly check that a private site's cited market figures are still stated)"
MAX_BYTES = 3_000_000
# Not a market-research or company publication: summaries, blogs, wikis and forums.
NOT_PUBLISHER = ("fintool.com", "wikipedia.org", "medium.com", "reddit.com", "quora.com", "seekingalpha.com",
                 "linkedin.com", "blogspot.com", "wordpress.com", "substack.com", "scribd.com", "slideshare.net")
GENERIC = {"automotive", "market", "markets", "system", "systems", "chip", "chips", "global", "products", "other",
           "types", "share", "largest", "methods", "sensing", "isolated", "all", "the", "and", "for"}  # fmt: skip
_MONEY = re.compile(r"(USD|US\$|\$|EUR|€)?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(billion|bn|b|million|mn|m)\b",
                    re.I)  # fmt: skip
_FORECAST = re.compile(r"\b(by|reach|reaching|projected|expected|forecast|will|grow to|to)\s*(?:\w+\s){0,3}$", re.I)
_VALUED = re.compile(r"(valued|size|worth|estimated|stood|was|accounted|generated|amounted|reached)", re.I)


def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", raw)
    return " ".join(html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw)).split())


def mentions(text: str) -> list[dict]:
    """Every money figure in the text: {usd, cur, pos, before, after}."""
    out = []
    for m in _MONEY.finditer(text):
        num = float(m.group(2).replace(",", ""))
        unit = m.group(3).lower()
        before = text[max(0, m.start() - 60): m.start()]
        cur = (m.group(1) or "").upper().replace("US$", "$")
        if not cur:
            usd, eur = re.search(r"(USD|US\$|\$)\s*$", before), re.search(r"(EUR|€)\s*$", before)
            cur = "USD" if usd else "EUR" if eur else ""
        if not cur and unit in ("b", "m"):  # "5 m" without a currency is not money
            continue
        mult = 1e9 if unit in ("billion", "bn", "b") else 1e6
        out.append({"usd": num * mult, "cur": "EUR" if cur in ("EUR", "€") else "USD" if cur else "",
                    "pos": m.start(), "end": m.end(), "before": text[max(0, m.start() - 120): m.start()],
                    "after": text[m.end(): m.end() + 60]})  # fmt: skip
    return out


def _year_after(m: dict) -> int | None:
    """The year a figure is for: "USD 2.3 billion in 2024", or a table cell "2024 Market Size $ 2.31 Billion"."""
    y = re.search(r"\b(20\d\d)\s*(?:market size|market value|value|revenue)\s*:?\s*(?:USD|US\$|\$)?\s*$", m["before"],
                  re.I)  # fmt: skip
    if y:
        return int(y.group(1))
    y = re.match(r"\W{0,3}(?:in|for|during|as of)\s*(?:the year\s*)?(20\d\d)\b", m["after"], re.I)
    return int(y.group(1)) if y else None


def _snippet(text: str, pos: int, end: int) -> str:
    s = text[max(0, pos - 90): end + 90].strip()
    return (s[:197] + "…") if len(s) > 200 else s


def scope_words(product: str) -> list[str]:
    words = re.findall(r"[a-z][a-z\-]+", product.lower())
    return [w.rstrip("s") for w in words if w not in GENERIC and len(w) >= 4]


def classify(entry: dict, text: str, today: datetime | None = None) -> dict:
    """The result for one estimate from its page text (pure, for the tests)."""
    today = today or datetime.now(UTC)
    low, high = tam.parse_range(entry.get("value") or "")
    year = entry.get("year")
    if not low:
        return {"status": "unverifiable", "why": "the recorded value cannot be read as a figure"}
    ms = mentions(text)
    lower = text.lower()
    words = scope_words(entry.get("product") or "")
    names_market = not words or any(w in lower for w in words)

    def near(v: float, target: float) -> bool:
        return abs(v - target) <= 0.015 * target

    hits = [m for m in ms if near(m["usd"], low) or (high and near(m["usd"], high))]
    with_year = [m for m in hits if year and str(year) in text[max(0, m["pos"] - 150): m["end"] + 150]]
    # a newer base-year figure on the same page ("valued at USD 1.0 billion in 2025")
    newer = []
    for m in ms:
        y = _year_after(m)
        if m["cur"] == "USD" and y and year and year < y <= today.year and not _FORECAST.search(m["before"][-40:]) \
                and _VALUED.search(m["before"][-60:] + " " + m["after"][:12]):  # fmt: skip
            newer.append((y, m))
    same_year_other = [m for m in ms if _year_after(m) == year and _VALUED.search(m["before"][-60:])
                       and not _FORECAST.search(m["before"][-40:]) and m not in hits
                       and not (low * 0.85 <= m["usd"] <= (high or low) * 1.15)]  # fmt: skip
    if with_year and names_market:
        good = [m for m in with_year if m["cur"] != "EUR"]
        if not good:
            m = with_year[0]
            return {"status": "disqualified", "why": "the page states the figure in euros, not US dollars",
                    "evidence": _snippet(text, m["pos"], m["end"])}  # fmt: skip
        if newer:
            y, n = max(newer, key=lambda t: t[0])
            return {"status": "changed", "why": f"the page now gives a {y} figure", "new_value": tam.money(n["usd"]),
                    "new_year": y, "evidence": _snippet(text, n["pos"], n["end"])}  # fmt: skip
        m = good[0]
        return {"status": "verified", "why": f"the page states {entry.get('value')} for {year}",
                "evidence": _snippet(text, m["pos"], m["end"])}  # fmt: skip
    if newer and names_market:
        y, n = max(newer, key=lambda t: t[0])
        return {"status": "changed", "why": f"the figure for {year} is gone; the page gives a {y} figure",
                "new_value": tam.money(n["usd"]), "new_year": y,
                "evidence": _snippet(text, n["pos"], n["end"])}  # fmt: skip
    if same_year_other and names_market:
        m = same_year_other[0]
        return {"status": "disqualified", "why": f"the page gives {tam.money(m['usd'])} for {year}, not "
                f"{entry.get('value')}", "evidence": _snippet(text, m["pos"], m["end"])}  # fmt: skip
    if not names_market:
        return {"status": "unverifiable", "why": "the page does not name this market (moved or a different page)"}
    return {"status": "unverifiable", "why": "the figure is not in the page text (paywalled or loaded by script)"}


class PageChecker(cl.Checker):
    """The link check's polite fetcher, reading the page body (up to 3 MB) instead of only the headers."""

    def _get(self, url: str):
        host = sources.host_of(url)
        if url in self.requested:
            raise RuntimeError(f"already requested this run: {url}")
        self._wait(host)
        self._mark(url)
        try:
            with self.client.stream("GET", url) as r:
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                r._tam_text = body.decode(r.encoding or "utf-8", errors="replace")
                self._last_response = r
                return r
        finally:
            self.last[host] = self.clock()

    def page(self, url: str, hops: int = 1) -> tuple[dict, str]:
        """(link-check result, page text); text is "" unless the page answered 200."""
        self._last_response = None
        res = self.check(url)
        r = self._last_response
        if res["status"] == "moved" and hops and sources.host_of(res.get("target", "")) == sources.host_of(url):
            return self.page(res["target"], hops - 1)  # the publisher moved the page on its own site: follow once
        if res["status"] == "ok" and r is not None and 200 <= r.status_code < 300:
            return res, page_text(getattr(r, "_tam_text", ""))
        return res, ""


def check_entry(e: dict, checker: PageChecker | None, blocked: set[str], today: datetime) -> dict:
    """One estimate: no request for an entry without a link, a policy host or a non-publisher source."""
    url = ((e.get("source") or {}).get("url") or "").strip()
    base = {"date": today.date().isoformat(), "url": url}
    if not url:
        return {**base, "status": "unverifiable", "why": "no link was recorded"}
    host = sources.host_of(url)
    if cl._under(host, NOT_PUBLISHER):
        return {**base, "status": "disqualified",
                "why": f"{host} is a summary site, not the market-research firm or the company itself"}  # fmt: skip
    why = cl.policy_block(url, blocked)
    if why:
        return {**base, "status": "unverifiable", "why": f"not requested ({why})"}
    if checker is None:
        return {**base, "status": "unverifiable", "why": "not checked"}
    res, text = checker.page(url)
    if not text:
        st = res["status"]
        what = {"dead": "page gone", "moved": f"moved to {res.get('target', '')}", "blocked": "blocked by the site",
                "bot check": "bot check", "needs login": "needs a login"}.get(st, st)  # fmt: skip
        code = f" ({res['code']})" if res.get("code") else ""
        err = f": {res['error']}" if res.get("error") else ""
        return {**base, "status": "unverifiable", "why": f"{what}{code}{err}"[:200]}
    return {**base, **classify(e, text, today)}


def load_entries(path: Path = TAM_YAML) -> list[dict]:
    return list((yamlio.load(path.read_text()) or {}).get("estimates") or [])


def pick(entries: list[dict], state: dict, limit: int) -> list[dict]:
    """Rotating order: never checked first, then the ones checked longest ago."""
    return sorted(entries, key=lambda e: (state.get(str(e["id"]), ""), str(e["id"])))[:limit]


def run(entries: list[dict], state: dict, limit: int, checker: PageChecker | None, blocked: set[str],
        today: datetime, deadline: float | None = None) -> dict:  # fmt: skip
    out = {}
    for e in pick(entries, state, limit):
        if deadline is not None and time.monotonic() > deadline:
            break
        res = check_entry(e, checker, blocked, today)
        if res.get("evidence"):
            res["evidence"] = res["evidence"][:200]
        out[str(e["id"])] = {k: v for k, v in res.items() if v not in (None, "")}
        state[str(e["id"])] = today.isoformat(timespec="seconds")
    return out


HEAD = """# Biweekly TAM check results (scripts/check_tam.py writes this file; do not edit by hand).
# One entry per data/business/tam.yaml id: the latest check of its source.
#   status    verified | changed | unverifiable | disqualified (see the script's docstring)
#   date      the day of the check; url = the page requested ("" = none recorded)
#   evidence  at most 200 characters of the page text around the figure (public page, quoted only as evidence)
#   why       one line; new_value / new_year when the same page shows a newer figure
# Nothing is deleted because of a check: a disqualified estimate is left out of the market size (tam.by_function)
# the same way an owner "disagree" is, unless the owner agreed with it (then it stays, flagged for the owner).
"""


def write_checks(results: dict, day: str, path: Path = CHECKS) -> dict:
    old = (yamlio.load(path.read_text()) or {}) if path.exists() else {}
    merged = {**(old.get("checks") or {}), **results}
    data = {"checked": day, "checks": dict(sorted(merged.items()))}
    path.write_text(HEAD + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--max-minutes", type=float, default=20)
    ap.add_argument("--dry-run", action="store_true", help="show what would be checked, request nothing")
    args = ap.parse_args(argv)
    today = datetime.now(UTC)
    entries = load_entries()
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    blocked = cl.blocked_hosts()
    if args.dry_run:
        for e in pick(entries, state, args.limit):
            url = (e.get("source") or {}).get("url") or ""
            print(e["id"], url or "(no link)", cl.policy_block(url, blocked) if url else "")
        return 0
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or True
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=False, verify=cafile,
                      trust_env=True) as client:  # fmt: skip
        checker = PageChecker(client)
        results = run(entries, state, args.limit, checker, blocked, today,
                      deadline=time.monotonic() + args.max_minutes * 60)  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    day = today.date().isoformat()
    (OUT / f"{day}.json").write_text(json.dumps({"results": results, "requests": checker.requested,
                                                 "stopped": checker.stopped}, indent=1))  # fmt: skip
    data = write_checks(results, day)
    counts = {s: sum(1 for r in data["checks"].values() if r.get("status") == s) for s in tam.CHECK_LABELS}
    print(f"TAM check {day}: {len(results)} checked, {len(checker.requested)} requests including robots.txt")
    print(", ".join(f"{n} {s}" for s, n in counts.items()))
    for k, r in results.items():
        print(f"- {k}: {r['status']} · {r.get('why', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
