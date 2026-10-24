"""Weekly link check (the Sunday evening run): are the external links of the site still alive?

    uv run python scripts/check_links.py [--limit 40] [--max-minutes 30] [--dry-run]

Reads the offline inventory (app/services/sources.py) and checks up to ``--limit`` links per run, the ones checked
longest ago first (never-checked cited sources before part catalogues). Polite, like tools/research/fetch.sh:
- robots.txt of each host first, and only the paths it allows; one request at a time; at least 10 s between requests
  to a host (5 s for skyworksinc.com and ti.com); each URL at most once per run;
- one GET per link, streamed and closed after the headers (no body is read); redirects are not followed;
- a host is stopped at the first 403 / 429 or bot check, for this run and the next 30 days;
- never requested ("not checked (policy)"): any qorvo.com host, www.qualcomm.com, distributors, iso.org, web
  archives and the hosts blocked in data/library/sources.yaml.

State (when each link was last checked, stopped hosts) is var/links/state.json; each run writes
var/links/<date>.json and var/links/<date>.md (var/ is never committed). The dead or moved links (all, not only
tonight's) go to data/manage/link_check.yaml, which the site reads for Verify next › Sources: commit that file with
the run's branch. Uses HTTPS_PROXY and SSL_CERT_FILE from the environment.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.robotparser
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import yamlio  # noqa: E402
from app.services import sources  # noqa: E402

OUT = ROOT / "var" / "links"
STATE = OUT / "state.json"
LINK_CHECK = ROOT / "data" / "manage" / "link_check.yaml"
SOURCES_YAML = ROOT / "data" / "library" / "sources.yaml"
USER_AGENT = "BizDevLinkCheck/1.0 (weekly link check of a private site's cited sources; one request per link)"
ROBOTS_AGENT = "BizDevLinkCheck"
STOP_DAYS = 30
# Never requested. A host matches when it is the domain or a subdomain of it.
NEVER = ("qorvo.com", "www.qualcomm.com", "mouser.com", "mouser.de", "digikey.com", "digikey.de", "arrow.com",
         "octopart.com", "richardsonrfpd.com", "richardson.com", "everythingrf.com", "alldatasheet.com",
         "findchips.com", "iso.org", "archive.org", "archive.ph", "archive.today")  # fmt: skip
FAST = ("skyworksinc.com", "ti.com")
GAP, GAP_FAST = 10.0, 5.0
BOT_HEADERS = ("cf-mitigated", "x-amzn-waf-action")


def _under(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def blocked_hosts(path: Path = SOURCES_YAML) -> set[str]:
    """Hosts of the sources marked blocked in the technical library (their URL and any host named in their access
    note), so a block found once is never worked around."""
    rows = (yamlio.load(path.read_text()) or {}).get("sources") or [] if path.exists() else []
    out = set()
    for r in rows:
        if r.get("feasibility") != "blocked":
            continue
        if r.get("url"):
            out.add(sources.host_of(r["url"]))
        out.update(h.lower() for h in re.findall(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|de|edu|gov)\b",
                                                 str(r.get("access") or ""), re.I))  # fmt: skip
    return {h.removeprefix("www.") for h in out if h}


def policy_block(url: str, blocked: set[str]) -> str | None:
    """Why a link is never requested, or None."""
    host = sources.host_of(url)
    if _under(host, NEVER):
        return "policy"
    if _under(host, blocked) or _under(host.removeprefix("www."), blocked):
        return "policy (blocked in the library's source list)"
    if url.startswith("http://") and not os.environ.get("HTTP_PROXY") and not os.environ.get("http_proxy"):
        return "plain HTTP (not passed by the proxy)"
    return None


def gap_for(host: str) -> float:
    return GAP_FAST if _under(host, FAST) else GAP


def load_state(path: Path = STATE) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"urls": {}, "stopped": {}}


def pick(links: list, state: dict, limit: int, blocked: set[str], now: datetime) -> tuple[list, Counter]:
    """The links to check this run: longest ago first (never checked first), cited sources before catalogues.
    Returns (picked, skipped by reason)."""
    skipped: Counter = Counter()
    stopped = {h for h, s in state.get("stopped", {}).items()
               if now - datetime.fromisoformat(s["date"]) < timedelta(days=STOP_DAYS)}  # fmt: skip
    cands = []
    for lk in links:
        why = policy_block(lk.url, blocked)
        if why:
            skipped[why] += 1
            continue
        if lk.host in stopped:
            skipped["host stopped earlier"] += 1
            continue
        last = state.get("urls", {}).get(lk.url, {}).get("checked", "")[:10]  # the day of the last check
        cands.append((last, lk.tier, lk.url, lk))
    cands.sort(key=lambda c: c[:3])
    # within one day and tier, spread over the hosts (one link per host, then the next), so a run covers many sites
    seen: Counter = Counter()
    ranked = []
    for last, tier, url, lk in cands:
        seen[(last, tier, lk.host)] += 1
        ranked.append((last, tier, seen[(last, tier, lk.host)], url, lk))
    ranked.sort(key=lambda c: c[:4])
    return [c[4] for c in ranked[:limit]], skipped


def _trivial(url: str, target: str) -> bool:
    """A redirect to the same page: http -> https, a trailing slash, an added query, upper/lower case."""
    a, b = urlsplit(url), urlsplit(target)
    return (a.hostname or "").lower() == (b.hostname or "").lower() and \
        a.path.rstrip("/").lower() == b.path.rstrip("/").lower()  # fmt: skip


def classify(url: str, r: httpx.Response) -> dict:
    code = r.status_code
    out = {"code": code}
    if any(h in r.headers for h in BOT_HEADERS) or (code == 503 and "cloudflare" in r.headers.get("server", "")):
        return {**out, "status": "bot check"}
    if code in (403, 429):
        return {**out, "status": "blocked"}
    if 200 <= code < 300:
        return {**out, "status": "ok"}
    if 300 <= code < 400:
        target = urljoin(url, r.headers.get("location", ""))
        return {**out, "status": "ok" if _trivial(url, target) else "moved", "target": target}
    if code in (404, 410):
        return {**out, "status": "dead"}
    if code == 401:
        return {**out, "status": "needs login"}
    return {**out, "status": "error"}  # 5xx, 405 ...: tried again next run, not reported as dead


class Checker:
    """One request at a time, the per-host gap, robots.txt first, stop at the first block."""

    def __init__(self, client: httpx.Client, sleep=time.sleep, clock=time.monotonic):
        self.client, self.sleep, self.clock = client, sleep, clock
        self.last: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser | str] = {}
        self.stopped: dict[str, str] = {}
        self.requested: list[str] = []
        self._times: list[float] = []  # when each request was sent (for the tests of the gap)

    def _wait(self, host: str) -> None:
        if host in self.last:
            left = gap_for(host) - (self.clock() - self.last[host])
            if left > 0:
                self.sleep(left)

    def _mark(self, url: str) -> None:
        self.requested.append(url)
        self._times.append(self.clock())

    def _get(self, url: str) -> httpx.Response:
        host = sources.host_of(url)
        if url in self.requested:
            raise RuntimeError(f"already requested this run: {url}")
        self._wait(host)
        self._mark(url)
        try:
            with self.client.stream("GET", url) as r:  # headers only: closed without reading the body
                return r
        finally:
            self.last[host] = self.clock()

    def _robots(self, url: str) -> urllib.robotparser.RobotFileParser | str:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        if host in self.robots:
            return self.robots[host]
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        try:
            self._wait(host)
            self._mark(robots_url)
            r = self.client.get(robots_url)
            self.last[host] = self.clock()
            target = urljoin(robots_url, r.headers.get("location", ""))
            if r.is_redirect and sources.host_of(target) == host and target not in self.requested:
                self._wait(host)  # robots.txt moved on the same host (e.g. to https): follow once
                self._mark(target)
                r = self.client.get(target)
                self.last[host] = self.clock()
        except httpx.HTTPError as e:
            self.last[host] = self.clock()
            self.robots[host] = f"robots.txt unavailable ({type(e).__name__})"
            return self.robots[host]
        if r.status_code in (401, 403, 429) or any(h in r.headers for h in BOT_HEADERS):
            self.stopped[host] = f"robots.txt answered {r.status_code}"
            self.robots[host] = self.stopped[host]
        elif r.status_code in (404, 410):
            rp = urllib.robotparser.RobotFileParser()
            rp.parse([])  # no robots.txt: everything allowed
            self.robots[host] = rp
        elif r.status_code == 200:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(r.text.splitlines())
            self.robots[host] = rp
        else:
            self.robots[host] = f"robots.txt unavailable ({r.status_code}): treated as not crawlable"
        return self.robots[host]

    def check(self, url: str) -> dict:
        host = sources.host_of(url)
        if host in self.stopped:
            return {"status": "not checked (host stopped)", "error": self.stopped[host]}
        rp = self._robots(url)
        if isinstance(rp, str):
            return {"status": "not checked (robots)", "error": rp}
        if not rp.can_fetch(ROBOTS_AGENT, url):
            return {"status": "not checked (robots)", "error": "disallowed by robots.txt"}
        if host in self.stopped:
            return {"status": "not checked (host stopped)", "error": self.stopped[host]}
        try:
            r = self._get(url)
        except httpx.TimeoutException:
            return {"status": "error", "error": "timeout"}
        except httpx.HTTPError as e:
            msg = str(e)[:200]
            dns = re.search(r"name or service not known|nodename nor servname|getaddrinfo|no address", msg, re.I)
            return {"status": "dead" if dns else "error", "error": f"{type(e).__name__}: {msg}"}
        res = classify(url, r)
        if res["status"] in ("blocked", "bot check"):
            self.stopped[host] = f"{res['status']} ({res['code']}) on {url}"
        return res


def run(links: list, state: dict, limit: int, checker: Checker, blocked: set[str], now: datetime,
        deadline: float | None = None, clock=time.monotonic) -> dict:  # fmt: skip
    picked, skipped = pick(links, state, limit, blocked, now)
    results, pending = [], list(picked)
    while pending:
        if deadline is not None and clock() > deadline:
            skipped["time box reached"] += len(pending)
            break
        # the next link whose host is ready (others wait their gap); else the one that is ready first
        ready = [lk for lk in pending if lk.host not in checker.last
                 or clock() - checker.last[lk.host] >= gap_for(lk.host)]  # fmt: skip
        lk = ready[0] if ready else min(pending, key=lambda x: checker.last[x.host] + gap_for(x.host))
        pending.remove(lk)
        res = checker.check(lk.url)
        results.append({"url": lk.url, "host": lk.host, "tier": lk.tier, **res,
                        "uses": [{"file": u.file, "line": u.line, "entry": u.entry, "page": u.page}
                                 for u in lk.uses[:3]], "n_uses": len(lk.uses)})  # fmt: skip
        if not res["status"].startswith("not checked"):
            state.setdefault("urls", {})[lk.url] = {"checked": now.isoformat(timespec="seconds"), **res}
    for host, why in checker.stopped.items():
        state.setdefault("stopped", {})[host] = {"date": now.isoformat(timespec="seconds"), "why": why}
    return {"date": now.date().isoformat(), "limit": limit, "checked": results, "skipped": dict(skipped),
            "stopped": checker.stopped, "requests": len(checker.requested)}  # fmt: skip


def problems(state: dict, inventory: set[str]) -> list[dict]:
    """Every link whose latest check found it dead or moved and that is still on the site."""
    out = []
    for url, s in sorted(state.get("urls", {}).items()):
        if s.get("status") in sources.LINK_PROBLEMS and url in inventory:
            out.append({k: v for k, v in {"url": url, "status": s["status"], "code": s.get("code"),
                                          "target": s.get("target"), "error": s.get("error"),
                                          "date": s["checked"][:10]}.items() if v is not None})  # fmt: skip
    return out


def summary(report: dict, n_links: int, n_state: int) -> str:
    st = Counter(r["status"] for r in report["checked"])
    lines = [f"# Link check {report['date']}", "",
             f"{len(report['checked'])} links looked at (limit {report['limit']}), {report['requests']} requests "
             f"including robots.txt; {n_state} of {n_links} links checked at least once so far.", "",
             "Results: " + (", ".join(f"{n} {s}" for s, n in st.most_common()) or "none"),
             "Skipped: " + (", ".join(f"{n} {s}" for s, n in report["skipped"].items()) or "none")]  # fmt: skip
    if report["stopped"]:
        lines += ["", "Hosts stopped:"] + [f"- {h}: {w}" for h, w in report["stopped"].items()]
    bad = [r for r in report["checked"] if r["status"] in sources.LINK_PROBLEMS or r["status"] == "error"]
    if bad:
        lines += ["", "Dead, moved or failed:"]
        for r in bad:
            where = r["uses"][0]["page"] or r["uses"][0]["file"]
            lines.append(f"- {r['status']} {r.get('code') or ''} {r['url']}"
                         f"{' -> ' + r['target'] if r.get('target') else ''}"
                         f"{' (' + r['error'] + ')' if r.get('error') else ''} · {where}")  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--max-minutes", type=float, default=30)
    ap.add_argument("--dry-run", action="store_true", help="show what would be checked, request nothing")
    args = ap.parse_args(argv)
    now = datetime.now(UTC)
    links = sources.links()
    state = load_state()
    blocked = blocked_hosts()
    if args.dry_run:
        picked, skipped = pick(links, state, args.limit, blocked, now)
        print("\n".join(lk.url for lk in picked))
        print(dict(skipped), file=sys.stderr)
        return 0
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or True
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=False, verify=cafile,
                      trust_env=True) as client:  # fmt: skip
        report = run(links, state, args.limit, Checker(client), blocked, now,
                     deadline=time.monotonic() + args.max_minutes * 60)  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    (OUT / f"{report['date']}.json").write_text(json.dumps(report, indent=1))
    md = summary(report, len(links), len(state.get("urls", {})))
    (OUT / f"{report['date']}.md").write_text(md)
    found = problems(state, {lk.url for lk in links})
    head = (
        "# Dead or moved links found by the weekly link check (scripts/check_links.py writes this file; the site\n"
        "# shows them in Data management › Site data › Verify next › Sources). Full results: var/links/.\n"
    )
    LINK_CHECK.write_text(head + yaml.safe_dump({"checked": report["date"], "problems": found}, sort_keys=False,
                                                allow_unicode=True, width=120))  # fmt: skip
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
