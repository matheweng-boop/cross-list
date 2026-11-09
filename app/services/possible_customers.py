"""Possible customers per sub-system and region (owner, 9 Nov 2026: "Include possible customers for each region
(Americas, EMEA and Asia). If customers overlap between regions, add them for all regions.")

Companies that publicly build the systems of a Systems library sub-system, grouped by region: the checked companies
of the Markets & customers segments (data/business/customers.yaml) that data/business/possible_customers.yaml maps
to the sub-system, plus the companies that file adds from association lists and specifications. Every company comes
with its source link, the date the source was read and the source type. A company present in several regions (its
headquarters plus the regions its own public pages show) is listed in each of them. Possible customers only: never a
customer list, never a claim that they buy from Skyworks or Qorvo."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import data_flow
from app.services import opportunity as op

FILE = PROJECT_ROOT / "data" / "business" / "possible_customers.yaml"
CUSTOMERS = PROJECT_ROOT / "data" / "business" / "customers.yaml"  # Markets & customers (opportunity.customers)
REGIONS = ("Americas", "EMEA", "Asia")
UNPLACED = "Region not checked"
NOTE = "Companies that publicly build these systems (possible customers); not a customer list."


@lru_cache
def data() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


def _type_of(url: str) -> str:
    low = url.lower()
    if any(w in low for w in ("/press", "/news", "newsroom", "press-release")):
        return "press release"
    if "annual" in low and "report" in low:
        return "public annual report"
    return "company page"


def _src(key: str) -> dict:
    s = (data().get("sources") or {}).get(key) or {}
    return {"title": s.get("title", key), "url": s.get("url", ""), "date": str(s.get("date", "")),
            "type": s.get("type", "")}  # fmt: skip


@lru_cache
def segments() -> dict[str, dict]:
    """The Markets & customers segments, with those no library diagram matches yet (e.g. hearing aids)."""
    raw = yamlio.load(CUSTOMERS.read_text()) or {}
    return {**op.customers(), **(raw.get("unmatched_segments") or {})}


@lru_cache
def _hq() -> dict[str, str]:
    """Each checked company's headquarters region label from customers.yaml (first mention)."""
    out: dict[str, str] = {}
    for seg in segments().values():
        for c in seg.get("customers") or []:
            out.setdefault(c.get("name", ""), c.get("region", ""))
    return out


def regions_of(name: str, own: list | None = None) -> tuple[list[str], str, list[dict]]:
    """(regions, where line, presence sources) of a company: its headquarters region plus the regions its own pages
    show (`presence`); an extra entry's own `regions` when it has no headquarters on record."""
    hq_map = data().get("hq_region") or {}
    pres = (data().get("presence") or {}).get(name) or {}
    hq = _hq().get(name, "")
    regions = [hq_map[hq]] if hq in hq_map else []
    for r in list(own or []) + list(pres.get("regions") or []):
        if r in REGIONS and r not in regions:
            regions.append(r)
    where = pres.get("where") or ""
    if not where and hq and len(regions) == 1:
        where = f"HQ: {hq}"
    return regions, where, [_src(k) for k in pres.get("sources") or []]


def _entry(c: dict, srcs: list[dict], own_regions: list | None = None, own_where: str = "") -> dict:
    regions, where, pres = regions_of(c["name"], own_regions)
    return {"name": c["name"], "type": c.get("type", ""), "note": c.get("note", ""), "sources": srcs,
            "regions": regions, "where": own_where or where, "presence": pres}  # fmt: skip


def _from_segments(keys: list[str]) -> list[dict]:
    """Checked companies of the segments, interleaved so each segment shows its most relevant first."""
    lists = []
    for k in keys:
        seg = segments().get(k) or {}
        date = str((seg.get("check") or {}).get("date", ""))
        checked = [c for c in seg.get("customers") or [] if c.get("evidence") and c.get("check") != "unconfirmed"]
        title = seg.get("label", k)
        lists.append([(c, {"title": title, "url": c["evidence"], "date": date, "type": _type_of(c["evidence"])})
                      for c in checked])  # fmt: skip
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        out += [x[i] for x in lists if i < len(x)]
    return out


@lru_cache(maxsize=256)
def for_sub(system: str, sub: str) -> dict:
    """{regions: {Americas: [...], EMEA: [...], Asia: [...]}, unplaced: [...], more: {region: n}, few, n}."""
    spec = (data().get("subsystems") or {}).get(f"{system}/{sub}") or {}
    by: dict[str, dict] = {}
    for c, src in _from_segments(list(spec.get("segments") or [])):
        if c["name"] not in by:
            by[c["name"]] = _entry(c, [src])
    for x in spec.get("extra") or []:
        srcs = [_src(k) for k in x.get("sources") or []]
        if x["name"] in by:  # a second public source for a company already listed
            by[x["name"]]["sources"] += [
                s for s in srcs if s["url"] not in {y["url"] for y in by[x["name"]]["sources"]}
            ]
            continue
        by[x["name"]] = _entry(x, srcs, x.get("regions"), x.get("where", ""))
    return _group(list(by.values()), spec.get("few_sources", ""))


def _group(companies: list[dict], few: str = "") -> dict:
    cap = int(data().get("max_per_region") or 8)
    regions = {r: [c for c in companies if r in c["regions"]] for r in REGIONS}
    return {"regions": {r: v[:cap] for r, v in regions.items()},
            "more": {r: [c["name"] for c in v[cap:]] for r, v in regions.items()},
            "unplaced": [c for c in companies if not c["regions"]], "few": few, "n": len(companies),
            "note": data().get("note") or NOTE}  # fmt: skip


@lru_cache(maxsize=32)
def for_system(system: str) -> dict:
    """All sub-systems of a system together, each company once (first sub-system's line)."""
    from app.services import systems as sy

    s = sy.get(system)
    by: dict[str, dict] = {}
    for x in (s or {}).get("subsystems") or []:
        g = for_sub(system, x["key"])
        for c in [c for v in g["regions"].values() for c in v] + g["unplaced"]:
            by.setdefault(c["name"], c)
    return _group(list(by.values()))


def all_texts() -> list[str]:
    """Every text this feature shows (names, lines, where, source titles): for the data-protection screen."""
    out = []
    for key in data().get("subsystems") or {}:
        system, _, sub = key.partition("/")
        g = for_sub(system, sub)
        out.append(g["few"])
        for c in [c for v in g["regions"].values() for c in v] + g["unplaced"]:
            out += [c["name"], c["note"], c["where"]] + [s["title"] for s in c["sources"] + c["presence"]]
    return [t for t in out if t]


def screen() -> list[tuple[str, list[str]]]:
    """Texts the data-protection screen (data_flow.screen: sites, e-mails, phones, "confidential" ...) flags."""
    return [(t, why) for t in dict.fromkeys(all_texts()) if (why := data_flow.screen(t))]
