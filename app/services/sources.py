"""Sources behind the site: every external link and every "not verified" marker, offline (no network).

- ``links()``: each external URL in data/**/*.yaml, the report and background templates, the engineering notes and
  visuals, the library notes and the competitor profiles, with where it is used (file, line, entry id and the page on
  the site where one is known). Part catalogues (datasheet and product links) are tier 2, so the weekly link check
  (scripts/check_links.py) gets to the cited sources first.
- ``markers()``: phrases that say a figure or a source was not checked: "from memory", "not read" / "not re-read",
  "est" attached to a number, "approx." before a number, "Not Enough Data", low confidence (also the ``confidence:
  low`` / ``conf: low`` fields), ``verified: false``, a check status "unconfirmed" and a link noted as dead. The part
  catalogues, the price model's own estimate pages, format templates (files starting with "_") and YAML comments are
  left out, so the list stays short enough to act on.
- ``latest_problems()``: the dead or moved links of the latest link check (data/manage/link_check.yaml, written by
  scripts/check_links.py; the full results stay in var/links/).

The weekly "Link and source check" puts both into Data management › Site data › Verify next (kind "Sources").
"""

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from app import yamlio
from app.config import PROJECT_ROOT

TEMPLATES = "app/web/templates"
# Where links and markers are looked for (globs relative to the project root).
SCAN = (
    "data/**/*.yaml",
    "data/library/notes/*.md",
    f"{TEMPLATES}/business/reports/*.html",
    f"{TEMPLATES}/engineering/notes/*.html",
    f"{TEMPLATES}/engineering/visuals/*.html",
)
# Part catalogues: thousands of datasheet and product links, checked after the cited sources (tier 2); their notes
# ("pinout not read from the datasheet") are part-data backlog (docs/pinout_backlog.md), not markers.
CATALOGUE = ("data/catalog/", "data/real/", "data/reference_designs/", "data/mechanical", "data/sources/",
             "data/synthetic/", "data/appnotes")  # fmt: skip
# The price model's own estimates are what those pages are for; they are not unverified sources.
NO_MARKERS = ("data/business/price_model.yaml", "data/business/list_prices.yaml", "data/business/scoring.yaml",
              "data/business/explanations.yaml")  # fmt: skip
LINK_CHECK = PROJECT_ROOT / "data" / "manage" / "link_check.yaml"

URL_RE = re.compile(r"https?://[^\s\"'<>`)\]}\\,|]+")
_NUM = r"[−\-–~≈$€£¥]?\s?\d"
# (kind, label, pattern). Order is the priority in Verify next: the weakest evidence first.
MARKERS = (
    ("from_memory", "From memory", re.compile(r"\bfrom memory\b|\btextbook background\b", re.I)),
    ("not_read", "Not read", re.compile(r"\bnot (?:re-?)?read\b", re.I)),
    ("dead_link", "Link noted as dead", re.compile(r"\blink is dead\b|\bdead link\b", re.I)),
    ("not_verified", "Marked not verified", re.compile(r"\bverified:\s*false\b|\bstatus:\s*unconfirmed\b", re.I)),
    ("no_data", "Not Enough Data", re.compile(r"\bNot Enough Data\b")),
    ("low_confidence", "Low confidence", re.compile(r"\blow confidence\b|\b(?:confidence|conf):\s*['\"]?low\b", re.I)),
    # "est" only right after a number or a limit in the same clause: "16 kA ..., est", "$1.5 (est)", "est. 2 W"
    (
        "estimate",
        "Estimate without a source",
        re.compile(rf"\d[^\n;:.!?<>\"]{{0,60}}?[\s(,]est\b\.?\)?|\(est\)|\best\.?\s{_NUM}|\bapprox\.\s?{_NUM}", re.I),
    ),
)
KIND_LABELS = {k: label for k, label, _ in MARKERS}
LINK_PROBLEMS = {"dead": "Dead link", "moved": "Moved link"}


@dataclass(frozen=True)
class Use:
    file: str  # relative to the project root
    line: int
    entry: str | None  # id, slug, key or part number of the entry, or the heading in a page template
    page: str | None  # the page on the site, e.g. /business/reports/auto-hv-hot-swap


@dataclass
class Link:
    url: str
    host: str
    tier: int  # 1 cited source, 2 part catalogue
    uses: list[Use] = field(default_factory=list)


@dataclass(frozen=True)
class Marker:
    kind: str
    file: str
    line: int
    entry: str | None
    page: str | None
    text: str  # the sentence around the marker, plain text
    key: str  # stable across edits elsewhere in the file: file, entry and the text, not the line

    @property
    def label(self) -> str:
        return KIND_LABELS[self.kind]


def _files() -> list[Path]:
    seen: dict[Path, None] = {}
    for g in SCAN:
        for p in sorted(PROJECT_ROOT.glob(g)):
            if p.is_file() and not p.is_symlink():
                seen[p] = None
    return list(seen)


def _rel(p: Path) -> str:
    return p.relative_to(PROJECT_ROOT).as_posix()


def is_catalogue(rel: str) -> bool:
    return rel.startswith(CATALOGUE)


def page_for(rel: str, entry: str | None = None) -> str | None:
    """The page on the site that shows this file (and entry), where one is known."""
    p = Path(rel)
    stem, parent = p.stem, p.parent.as_posix()
    e = entry or ""
    if rel == "data/business/reports.yaml":
        return f"/business/reports/{e}" if e else "/business/reports"
    if parent == "data/business/cases":
        return f"/business/reports/{stem}"
    if parent == f"{TEMPLATES}/business/reports":
        if stem.endswith(".background"):
            return f"/business/reports/{stem.removesuffix('.background')}/background"
        return f"/business/reports/{stem}"
    if parent == f"{TEMPLATES}/engineering/notes":
        return f"/engineering/{stem}"
    if parent == f"{TEMPLATES}/engineering/visuals":
        return "/visuals"
    if parent in ("data/business/evidence",) or rel == "data/business/competition.yaml":
        return f"/business/evidence/{e}" if e and re.fullmatch(r"[a-z0-9_]+", e) else None
    if parent == "data/business/competitors":
        return f"/business/competitors/{stem}"
    if parent in ("data/library/topics", "data/library/notes"):
        return f"/library/{stem}"
    if parent == "data/reviews":
        return f"/reviews/{stem}"
    if parent.startswith(("data/catalog", "data/real")) and e:
        return f"/find?q={e}"
    return {
        "data/library/sources.yaml": "/library/sources",
        "data/business/tam.yaml": "/business/tam",
        "data/business/risks.yaml": "/business/risks",
        "data/engineering_rf_notes.yaml": "/rf-notes",
        "data/engineering_rf_bands.yaml": "/rf-bands",
        "data/knowledge_by_product.yaml": "/knowledge",
        "data/blocks/templates.yaml": "/blocks",
        "data/business/customers.yaml": "/business/markets",
        "data/manage/schedule.yaml": "/manage/schedule",
    }.get(rel)


_ITEM = re.compile(r"^(\s*)- ")
_ID = re.compile(r"""^\s*(?:- )?\{?\s*(id|slug|key|mpn|fn)\s*:\s*['"]?([^'",}#\s][^'",}#]*?)['"]?\s*(?:[,}#]|$)""")
_TOP = re.compile(r"^([A-Za-z0-9_][\w\-]*):\s*(?:#.*)?$")
_HEADING = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def _yaml_entries(lines: list[str]) -> list[str | None]:
    """The entry each line belongs to: the id / slug / key / mpn / fn of the innermost list item that has one, else
    the top-level key (evidence files are keyed by function)."""
    out: list[str | None] = []
    stack: list[tuple[int, str | None]] = []  # (indent of "- ", its id)
    top = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            out.append(next((i for _, i in reversed(stack) if i), top))
            continue
        m = _TOP.match(raw)
        if m:
            top, stack = m.group(1), []
        item = _ITEM.match(raw)
        indent = len(raw) - len(raw.lstrip())
        if item:
            indent = len(item.group(1))
            stack = [s for s in stack if s[0] < indent]
            stack.append((indent, None))
        else:
            stack = [s for s in stack if s[0] < indent]
        idm = _ID.match(raw)
        if idm and stack and stack[-1][1] is None and (item or indent == stack[-1][0] + 2):
            stack[-1] = (stack[-1][0], idm.group(2).strip())
        out.append(next((i for _, i in reversed(stack) if i), top))
    return out


def _html_entries(text: str, lines: list[str]) -> list[str | None]:
    """The nearest heading above each line of a page template."""
    heads = sorted((text.count("\n", 0, m.start()), " ".join(_TAG.sub("", m.group(1)).split()))
                   for m in _HEADING.finditer(text))  # fmt: skip
    out, h, j = [], None, 0
    for n in range(len(lines)):
        while j < len(heads) and heads[j][0] <= n:
            h = heads[j][1][:120] or h
            j += 1
        out.append(h)
    return out


def _read(p: Path) -> tuple[str, list[str], list[str | None]]:
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    entries = _html_entries(text, lines) if p.suffix == ".html" else _yaml_entries(lines)
    return text, lines, entries


def _clean_url(u: str) -> str:
    return u.rstrip(".;:!?'\"*")


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


@lru_cache(maxsize=1)
def _links() -> tuple[Link, ...]:
    found: dict[str, Link] = {}
    for p in _files():
        rel = _rel(p)
        tier = 2 if is_catalogue(rel) else 1
        _, lines, entries = _read(p)
        for n, line in enumerate(lines):
            if "http" not in line or (p.suffix == ".yaml" and line.lstrip().startswith("#") and tier == 2):
                continue
            for m in URL_RE.finditer(line):
                url = _clean_url(m.group(0))
                host = host_of(url)
                if "{" in url or not host or "." not in host:
                    continue  # template expressions and placeholders
                lk = found.setdefault(url, Link(url, host, tier))
                lk.tier = min(lk.tier, tier)
                lk.uses.append(Use(rel, n + 1, entries[n], page_for(rel, entries[n])))
    return tuple(found.values())


def links() -> list[Link]:
    """Every external link with its uses (cached: the files change only with a deploy)."""
    return list(_links())


def _sentence(line: str, start: int, end: int, html: bool) -> str:
    """Plain text around a match: the clause it sits in, at most about 300 characters."""
    if html:
        before, mid, after = _TAG.sub("", line[:start]), line[start:end], _TAG.sub("", line[end:])
    else:
        before, mid, after = line[:start], line[start:end], line[end:]
    before = re.split(r"(?<=[.!?])\s+(?=[A-Z])", before)[-1][-200:]
    after = re.split(r"(?<=[.!?])\s+(?=[A-Z])", after)[0][:150]
    text = " ".join(f"{before}{mid}{after}".split())
    return text.strip(" -\"'{},") or mid


@lru_cache(maxsize=1)
def _markers() -> tuple[Marker, ...]:
    out: list[Marker] = []
    seen: set[str] = set()
    for p in _files():
        rel = _rel(p)
        if is_catalogue(rel) or rel in NO_MARKERS or p.name.startswith("_") and p.suffix == ".yaml":
            continue
        _, lines, entries = _read(p)
        html = p.suffix == ".html"
        for n, line in enumerate(lines):
            if not html and line.lstrip().startswith("#"):
                continue
            taken: list[tuple[int, int]] = []
            for kind, _, rx in MARKERS:
                for m in rx.finditer(line):
                    if any(a < m.end() and m.start() < b for a, b in taken):
                        continue  # one marker per spot, the strongest kind
                    taken.append((m.start(), m.end()))
                    text = _sentence(line, m.start(), m.end(), html)
                    if kind in ("not_verified", "low_confidence") and len(text) < 40:
                        text = f"{entries[n] or ''}: {text}".strip(": ")  # a bare field: name the entry
                    h = hashlib.sha1(f"{rel}|{entries[n]}|{kind}|{text}".encode()).hexdigest()[:12]
                    if f"marker:{rel}#{h}" in seen:
                        continue  # the same clause again in the same entry: one item
                    seen.add(f"marker:{rel}#{h}")
                    out.append(Marker(kind, rel, n + 1, entries[n], page_for(rel, entries[n]), text[:400],
                                      f"marker:{rel}#{h}"))  # fmt: skip
    return tuple(out)


def markers() -> list[Marker]:
    return list(_markers())


def by_page(items: list[Marker] | None = None) -> dict[str, list[Marker]]:
    """Markers grouped by the page they are on (the file when no page is known)."""
    groups: dict[str, list[Marker]] = defaultdict(list)
    for m in markers() if items is None else items:
        groups[m.page or m.file].append(m)
    return dict(sorted(groups.items()))


def counts() -> dict:
    """Inventory totals for the report and the tests."""
    ls, ms = links(), markers()
    return {"urls": len(ls), "cited": sum(lk.tier == 1 for lk in ls),
            "hosts": Counter(lk.host for lk in ls).most_common(), "markers": Counter(m.kind for m in ms),
            "pages": len(by_page(ms))}  # fmt: skip


def latest_problems(path: Path | None = None) -> list[dict]:
    """Dead or moved links of the latest link check, each with its uses (page, file, entry)."""
    path = path or LINK_CHECK
    if not path.exists():
        return []
    data = yamlio.load(path.read_text()) or {}
    if not data.get("problems"):
        return []
    uses = {lk.url: lk.uses for lk in links()}  # a few seconds once per deploy (the part catalogues are large)
    out = []
    for r in data["problems"]:
        if r.get("status") in LINK_PROBLEMS and r.get("url") in uses:  # a link removed since then is done
            out.append({**r, "checked": str(data.get("checked") or ""), "uses": uses[r["url"]]})
    return out


def clear_cache() -> None:
    _links.cache_clear()
    _markers.cache_clear()
