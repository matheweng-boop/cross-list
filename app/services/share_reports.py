"""Shareable reports for management (owner, 25 Oct 2026): "Skyworks + Qorvo synergies" (/shareable/synergies) and its
extension "Automotive: technologies and applications" (/shareable/automotive), plus Create PDF and PowerPoint.

The words come from data/business/share_reports.yaml; every count is built here from the site's data (the same
catalogue rows, families and platforms as the Technology overview, app/services/tech_overview.py; the synergy pairs of
app/services/portfolio.py) and shown rounded (text.round_count). Editing, storage, comments and the word check are the
Technology overview's (tech_overview_edit.Report), each report under its own storage key.
"""

import importlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import share_slides as ss
from app.services import tech_overview as to
from app.services import tech_overview_edit as te
from app.services.text import round_count, whole_words

FILE = PROJECT_ROOT / "data" / "business" / "share_reports.yaml"
LINES = to.LINES
PARA = (2, 420)  # at most 2 paragraphs per section, 420 characters together (what one A4 page holds)
PARA_SHORT = {"technologies": (1, 160), "overlap": (2, 260), "combine": (2, 260), "applications": (1, 160),
              "pairs": (1, 200)}  # fmt: skip


@lru_cache
def curated() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


# ---- share safety: the synergies page also guards where and how parts are made (owner, 25 Oct 2026) -----------------
# The manufacturing section stays at capability level: no site, city or named partner. A generic capability sentence
# ("silicon from foundry partners") is allowed; "fab", "wafer fab", a named foundry or a site name is not.
GENERIC_OK = ("foundry partners", "foundry partner")
NAMED_PARTNERS = ("TSMC", "GlobalFoundries", "UMC", "TowerJazz", "Tower Semiconductor", "SMIC", "Vanguard", "X-FAB",
                  "WIN Semiconductors", "AWSC", "Luxshare", "Amkor", "ASE", "JCET")  # fmt: skip
MAKING_WORDS = ("fab", "wafer fab", "foundry", "foundries", "wafer")


def site_names() -> tuple[str, ...]:
    """Manufacturing site names the synergies page must never name: the site-wide list in app/services/site_guard.py."""
    from app.services import site_guard

    return tuple(s for s in site_guard.SITES if s.isalpha() or " " in s)


def making_problems(text: str) -> list[str]:
    """Words on where or how parts are made, after taking out the allowed generic capability phrases."""
    t = text
    for ok in GENERIC_OK:
        t = re.sub(rf"\b{re.escape(ok)}\b", " ", t, flags=re.I)
    hits = whole_words(t, MAKING_WORDS, plural=True)
    hits += [n for n in NAMED_PARTNERS if re.search(rf"\b{re.escape(n)}\b", t)]
    from app.services import site_guard

    hits += site_guard.hits(t)
    return [f"“{w}” is about where or how parts are made; this page names capabilities only." for w in hits]


def synergy_problems(text: str, allow: tuple[str, ...] = ()) -> list[str]:
    t = text
    for ok in GENERIC_OK:
        t = re.sub(rf"\b{re.escape(ok)}\b", " ", t, flags=re.I)
    base = [p for p in to.share_problems(t, allow) if "where or how parts are made" not in p]
    return base + making_problems(text)


# ---- patents: one tag per platform, when W's public patent summary is there (owner, 25 Oct 2026) ------------------
PATENTS_FILE = PROJECT_ROOT / "data" / "business" / "evidence" / "patents_platforms.yaml"
PATENT_NOTE = "IP: indicative US patent families, public USPTO data, not legal advice."


def _patent_source():
    """The patent summary per platform: the helper patent_summary() when a module has it, else the YAML file, else
    nothing. Read defensively: a missing or odd source gives no tags, never an error."""
    for mod in ("app.services.patents", "app.services.patent_summary", "app.services.evidence"):
        try:
            fn = getattr(importlib.import_module(mod), "patent_summary", None)
        except Exception:  # noqa: BLE001 - another worker's module; never break the page over it
            fn = None
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                return None
    try:
        return yamlio.load(PATENTS_FILE.read_text()) if PATENTS_FILE.exists() else None
    except Exception:  # noqa: BLE001
        return None


def patent_marks() -> dict[str, dict]:
    """platform or capability key -> {"leader": "Skyworks" | "Qorvo" | "Both", "automotive": bool}."""
    data = _patent_source()
    if isinstance(data, dict) and isinstance(data.get("platforms"), (dict, list)):
        data = data["platforms"]
    items = data.items() if isinstance(data, dict) else (
        ((x.get("key") or x.get("platform"), x) for x in data if isinstance(x, dict)) if isinstance(data, list) else ())
    out = {}
    for k, v in items:
        if not k or not isinstance(v, dict):
            continue
        lead = str(v.get("leader") or "").strip().lower()
        leader = {"skyworks": "Skyworks", "qorvo": "Qorvo", "both": "Both"}.get(lead)
        if leader:
            out[str(k)] = {"leader": leader, "automotive": bool(v.get("automotive"))}
    return out


def patent_tag(platform: dict, marks: dict, automotive_only: bool = False) -> str:
    """The tag of one platform row ("IP: Qorvo-led", "IP: both"), "" when there is no mark."""
    keys = [platform.get("key"), *(platform.get("caps") or [])]
    m = next((marks[k] for k in keys if k in marks), None)
    if not m or (automotive_only and not m["automotive"]):
        return ""
    return "IP: both" if m["leader"] == "Both" else f"IP: {m['leader']}-led"


# ---- what each synergy is good for (owner, 25 Oct 2026: "how are these synergies useful?") -------------------------
# A fixed set of benefit types (data/business/share_reports.yaml, synergies.benefit_types); cost savings always say
# "assumed". One type per pair, a default for a pair the file does not list.
BENEFIT_KEYS = ("manufacturing", "shared_tech", "new_tech", "cost", "market")


def benefit_labels() -> dict[str, str]:
    words = (curated().get("synergies") or {}).get("benefit_types") or {}
    return {k: str(words.get(k) or k) for k in BENEFIT_KEYS}


def benefit_of(pair_key: str) -> str:
    """The benefit label of one pair ("<Skyworks function> + <Qorvo function>")."""
    cur = curated().get("synergies") or {}
    kind = (cur.get("benefits") or {}).get(pair_key) or cur.get("benefit_default") or "shared_tech"
    labels = benefit_labels()
    return labels.get(kind, labels["shared_tech"])


def overlap_benefits() -> dict[str, dict]:
    """Skyworks | Both | Qorvo -> {"benefit": label, "line": one line} for the overlap view."""
    labels = benefit_labels()
    rows = (curated().get("synergies") or {}).get("overlap_benefits") or {}
    return {side: {"benefit": labels.get((rows.get(side) or {}).get("type"), labels["market"]),
                   "line": str((rows.get(side) or {}).get("line") or "")}
            for side in ("Skyworks", "Both", "Qorvo")}  # fmt: skip


# ---- the numbers and lists of each report --------------------------------------------------------------------------
def _qualified(r: dict) -> bool:
    """AEC-Q qualified: the one site-wide test (app.services.autograde.is_aec), as on Cross-sell and the overview."""
    from app.services import autograde

    return r.get("automotive") is True or autograde.is_aec(r)


def series_rows(series: str) -> list[dict]:
    pre = to.series_prefix(series).upper()
    return [r for r in to.active_rows() if r["mpn"].upper().startswith(pre)]


def qualified_series(series: str) -> bool:
    return any(_qualified(r) for r in series_rows(series))


@lru_cache
def build_synergies() -> dict:
    from app.services import portfolio as pf

    cur = curated().get("synergies") or {}
    b = to.build()
    rows = to.active_rows()
    fams = [f for f in b["families"] if f["label"] != pf.OTHER_CATEGORY]
    both = [f for f in fams if f["Skyworks"] and f["Qorvo"]]
    sky = [f for f in fams if f["Skyworks"] and not f["Qorvo"]]
    qor = [f for f in fams if f["Qorvo"] and not f["Skyworks"]]
    marks = patent_marks()
    plats = [{**p, "ip": patent_tag(p, marks)} for p in b["platforms"]]
    tech = {side: [p for p in plats if p["owner"] == side] for side in ("Skyworks", "Both", "Qorvo")}
    # no AEC-Q part count (owner, 25 Oct 2026: "I just want AEC-Q part counts out, filters and designations remain")
    nums = {"parts": len(rows), "families": len(fams), "shared": len(both), "platforms": len(plats)}
    words = cur.get("facts") or {}
    facts = [{"key": k, "num": f"{n:,}", "label": (words.get(k) or {}).get("label", "")} for k, n in nums.items()]
    notes, lines = pf.synergy_notes(), cur.get("pairs") or {}
    pairs = []
    for x in pf.synergies(limit=12):
        key = f"{x['skyworks']} + {x['qorvo']}"
        note = notes.get(key) or {}
        if note.get("weak"):
            continue  # a supply link only: not a management-level synergy
        line = lines.get(key) or note.get("reason") or f"Used together in {round_count(x['n'])} reference designs."
        pairs.append({"key": key.replace(" + ", "-"), "skyworks": x["skyworks_label"], "qorvo": x["qorvo_label"],
                      "line": " ".join(str(line).split()), "n": x["n"], "benefit": benefit_of(key),
                      "s_ex": x["skyworks_parts"][0]["mpn"] if x["skyworks_parts"] else "",
                      "q_ex": x["qorvo_parts"][0]["mpn"] if x["qorvo_parts"] else ""})  # fmt: skip
        if len(pairs) >= 6:
            break
    return {"cur": cur, "facts": facts, "tech": tech, "both": both, "sky": sky, "qor": qor, "pairs": pairs,
            "mfg": list(cur.get("manufacturing") or []), "ip": any(p["ip"] for p in plats),
            "overlap": overlap_benefits(),
            "catalogue_date": b["catalogue_date"]}  # fmt: skip


@lru_cache
def build_automotive() -> dict:
    from app.services import portfolio as pf
    from app.services import systems

    cur = curated().get("automotive") or {}
    rows = [r for r in to.active_rows() if _qualified(r)]
    aecq = {r["mpn"] for r in rows}  # AEC-Q-qualified active parts: the only examples named
    plats = {p["key"]: p for p in to.build()["platforms"]}
    marks = patent_marks()
    tech = [{**plats[k], "car": line, "ip": patent_tag(plats[k], marks, automotive_only=True)}
            for k, line in (cur.get("technologies") or {}).items() if k in plats]  # fmt: skip
    words = cur.get("subsystems") or {}
    sys = systems.get("automotive") or {"subsystems": []}
    subs = []
    for s in sys["subsystems"]:
        w = words.get(s["key"]) or {}
        series = [x for x in w.get("series") or [] if qualified_series(x)]
        subs.append({"key": s["key"], "title": s["title"], "line": w.get("line") or s.get("summary", ""),
                     "series": series})  # fmt: skip
    idx = systems.selection("automotive")["idx"]
    lines = (curated().get("synergies") or {}).get("pairs") or {}
    pairs = []
    for x in pf.together_in(idx)["synergies"] if idx else []:
        if x["weak"]:
            continue
        key = f"{x['skyworks']} + {x['qorvo']}"
        s_ex = next((p["mpn"] for p in x["skyworks_parts"] if p["mpn"] in aecq), "")
        q_ex = next((p["mpn"] for p in x["qorvo_parts"] if p["mpn"] in aecq), "")
        pairs.append({"key": key.replace(" + ", "-"), "skyworks": x["skyworks_label"], "qorvo": x["qorvo_label"],
                      "line": " ".join(str(lines.get(key) or x["reason"] or "").split()), "s_ex": s_ex,
                      "benefit": benefit_of(key),
                      "q_ex": q_ex})  # fmt: skip
        if len(pairs) >= 6:
            break
    fams = {r["family"] for r in rows} - {pf.OTHER_CATEGORY}
    # owner, 25 Oct 2026: no "from Skyworks" tile, and no AEC-Q part count at all ("I just want AEC-Q part counts
    # out, filters and designations should remain"): which series are AEC-Q qualified is still shown
    nums = {"platforms": len(tech), "subsystems": len(subs), "families": len(fams)}
    fw = cur.get("facts") or {}
    facts = [{"key": k, "num": f"{n:,}", "label": (fw.get(k) or {}).get("label", "")} for k, n in nums.items()]
    return {"cur": cur, "facts": facts, "tech": tech, "subsystems": subs, "pairs": pairs,
            "standards": list(cur.get("standards") or []), "ip": any(t["ip"] for t in tech)}  # fmt: skip


# ---- the editable fields of each report ----------------------------------------------------------------------------
def _common(out: dict, cur: dict, add) -> None:
    hdr = cur.get("header") or {}
    add("hdr.title", "line", hdr.get("title", ""), 60, "Header title")
    add("hdr.subtitle", "line", hdr.get("subtitle", ""), 60, "Header subtitle (optional)")
    add("title", "line", cur.get("title", ""), 70, "Title")
    for s, v in (cur.get("sections") or {}).items():
        add(f"sec.{s}.heading", "line", v.get("heading", ""), 50, "Heading")
        add(f"slide.{s}", "text", v.get("slide", ""), te.SLIDE_MAX, "Slide text (PowerPoint)")


def _adder(out: dict):
    def add(fid, kind, default, mx=0, label="", options=()):
        exact = ""
        if kind == "data" and (r := to_rounded(default)) != default:
            exact, default = default, r
        out[fid] = te.Field(fid, kind, default, mx, label, tuple(options), exact)

    return add


def to_rounded(v: object) -> object:
    from app.services.text import rounded_count_text

    return rounded_count_text(v) if isinstance(v, str) else v


@lru_cache
def specs_synergies() -> dict:
    b = build_synergies()
    out: dict = {}
    add = _adder(out)
    _common(out, b["cur"], add)
    for f in b["facts"]:
        add(f"fact.{f['key']}.num", "data", f["num"], 14, "Number")
        add(f"fact.{f['key']}.label", "line", f["label"], 40, "Label")
    for i, m in enumerate(b["mfg"]):
        add(f"mfg.{i}.label", "line", m.get("label", ""), 48, "Capability")
        add(f"mfg.{i}.skyworks", "line", m.get("skyworks", ""), 24, "Skyworks")
        add(f"mfg.{i}.qorvo", "line", m.get("qorvo", ""), 24, "Qorvo")
    for p in b["pairs"]:
        add(f"pair.{p['key']}.benefit", "choice", p["benefit"], 0, "Benefit", tuple(benefit_labels().values()))
        add(f"pair.{p['key']}.line", "text", p["line"], 140, "What it is useful for")
    for side, o in b["overlap"].items():
        add(f"ovl.{side.lower()}.benefit", "choice", o["benefit"], 0, "Benefit", tuple(benefit_labels().values()))
        add(f"ovl.{side.lower()}.line", "text", o["line"], 80, "What it is useful for")
    for i, s in enumerate(b["cur"].get("sources") or []):
        add(f"src.{i}", "text", s, 200, "Source line")
    return out


@lru_cache
def specs_automotive() -> dict:
    b = build_automotive()
    out: dict = {}
    add = _adder(out)
    _common(out, b["cur"], add)
    for f in b["facts"]:
        add(f"fact.{f['key']}.num", "data", f["num"], 14, "Number")
        add(f"fact.{f['key']}.label", "line", f["label"], 44, "Label")
    for t in b["tech"]:
        add(f"tech.{t['key']}.car", "text", t["car"], 110, "In the car")
    for s in b["subsystems"]:
        add(f"sub.{s['key']}.title", "line", s["title"], 44, "Sub-system")
        add(f"sub.{s['key']}.line", "text", s["line"], 110, "What we bring")
    for p in b["pairs"]:
        add(f"pair.{p['key']}.benefit", "choice", p["benefit"], 0, "Benefit", tuple(benefit_labels().values()))
        add(f"pair.{p['key']}.line", "text", p["line"], 170, "Why they go together")
    add("standards", "chips", b["standards"], te.CHIP_MAX, "Standards (one per line)", (8,))
    for i, s in enumerate(b["cur"].get("sources") or []):
        add(f"src.{i}", "text", s, 200, "Source line")
    return out


def _sections(key: str):
    return lambda: tuple((curated().get(key) or {}).get("sections") or {})


def _paras(key: str):
    def default(section: str) -> list[dict]:
        sec = ((curated().get(key) or {}).get("sections") or {}).get(section) or {}
        return [{"id": p["id"], "text": " ".join(str(p["text"]).split())} for p in sec.get("paragraphs") or []]

    return default


def _limits(section: str) -> tuple[int, int]:
    return PARA_SHORT.get(section, PARA)


SYNERGIES = te.Report("synergies", "share_synergies", "Skyworks + Qorvo synergies", "/shareable/synergies",
                      lambda: specs_synergies(), _sections("synergies"), _paras("synergies"), _limits,
                      synergy_problems, "3 A4 pages")  # fmt: skip
AUTOMOTIVE = te.Report("automotive", "share_automotive", "Automotive: technologies and applications",
                       "/shareable/automotive", lambda: specs_automotive(), _sections("automotive"),
                       _paras("automotive"), _limits, to.share_problems, "3 A4 pages")  # fmt: skip


# ---- THE REGISTRY: every report on /shareable (owner, 25 Oct 2026) ---------------------------------------------------
# How to add a report (e.g. "Drones", built like Automotive):
#   1. Words: a new top-level section in data/business/share_reports.yaml (title, header, sections with paragraphs,
#      facts, sources), like "automotive:".
#   2. Data: a build_<key>() here returning what the page shows (facts, lists), a specs_<key>() for its editable
#      fields and a te.Report(...) for editing and storage, like AUTOMOTIVE above.
#   3. Page: a body template app/web/templates/shareable/_<key>.html (one <section class="to-page"> per A4 page),
#      like _automotive.html.
#   4. PDF and slides: a content-model function in app/services/share_doc.py (data, vals, today) -> the sections and
#      blocks, like automotive(); the A4 PDF (share_pdf.py) and the slides (share_slides.from_doc) are laid out from
#      it, so all three versions carry the same facts.
#   5. One ShareReport(...) entry in REGISTRY below. Nothing else: the report then shows on /shareable as a row (tap
#      to preview, tick, Edit for the owner), in Create PDF (/shareable/pdf), in Create PowerPoint (/shareable/pptx),
#      and at /shareable/<key> (+ /edit) under the menu's "Reports" entry.
#   tests/test_share_registry.py checks that an extra entry shows up in the list, the PDF and the PowerPoint.
@dataclass(frozen=True)
class ShareReport:
    key: str  # in addresses (?r=...) and /shareable/<key>
    label: str  # the name in the list
    line: str  # one short line under the name
    url: str
    pages: int  # printed A4 pages
    build: Callable[[], dict]  # the data the page renders
    slides: Callable[..., list[dict]]  # (data, vals, today, ip_note) -> PowerPoint slides (share_slides.py)
    body: str = ""  # the body template (its A4 pages); "" for the Technology overview, which has its own page
    edit: te.Report | None = None  # editing and stored values; None: the Technology overview's own
    pack_rank: int = 50  # place in the combined PDF (lower first); the list and PowerPoint follow REGISTRY's order
    doc: Callable[..., dict] | None = None  # (data, vals, today) -> content model; None: share_doc.BUILDERS[key]

    def content(self, data: dict, vals: dict, today=None) -> dict:
        """The content model the PDF and the slides are laid out from (app/services/share_doc.py)."""
        from app.services import share_doc as sd

        make = self.doc or sd.BUILDERS[self.key]
        return make({**data, "ip_note": PATENT_NOTE}, vals, today or date.today())


REGISTRY: list[ShareReport] = [
    ShareReport("synergies", "Skyworks + Qorvo synergies", "For management: capabilities, overlap, where they combine.",
                SYNERGIES.url, 3, build_synergies, ss.synergies, "shareable/_synergies.html", SYNERGIES, 10),
    ShareReport("automotive", "Automotive", "Extension of the synergies: technologies and applications in the car.",
                AUTOMOTIVE.url, 3, build_automotive, ss.automotive, "shareable/_automotive.html", AUTOMOTIVE, 20),
    ShareReport("overview", "Technology overview", "The Skyworks + Qorvo portfolio: platforms, markets, families.",
                "/shareable/technology-overview", 4, to.build, ss.overview, pack_rank=0),
]  # fmt: skip


def _system_briefs() -> list[ShareReport]:
    """The four system briefs (owner, 27 Oct 2026: UWB, V2X, GNSS, car radio), app/services/share_systems.py: block
    diagram, core and peripheral parts, talking points. One body template for all four."""
    from app.services import share_systems as sy

    out = []
    for i, k in enumerate(sy.KEYS):
        c, rep = sy.cur(k), sy.REPORTS[k]
        out.append(ShareReport(k, str(c.get("label") or k), str(c.get("line") or ""), rep.url, 3, sy.builder(k),
                               sy.slides_of(k), "shareable/_system.html", rep, 30 + i, sy.content(k)))  # fmt: skip
    return out


REGISTRY += _system_briefs()


def registry() -> dict[str, ShareReport]:
    """key -> report, in the list's order (read at call time, so a test can add an entry)."""
    return {r.key: r for r in REGISTRY}


def reports() -> dict[str, te.Report]:
    """The report pages with their own editing (/shareable/<key>)."""
    return {r.key: r.edit for r in REGISTRY if r.edit is not None}


def pages() -> dict[str, int]:
    return {r.key: r.pages for r in REGISTRY}


def pack_order() -> tuple[str, ...]:
    return tuple(r.key for r in sorted(REGISTRY, key=lambda r: r.pack_rank))


def list_order(keys) -> list[str]:
    """The known keys among the given ones, in the list's order, each once (Download as PowerPoint)."""
    asked = {str(k).strip() for k in keys}
    return [r.key for r in REGISTRY if r.key in asked]


# the same, as fixed values for older callers (the inbox, tests); new code calls the functions above
REPORTS, PAGES, PACK_ORDER = reports(), pages(), pack_order()


def pack_selection(raw: str) -> list[str]:
    """?r=overview,synergies,automotive -> the known reports in the combined PDF's order, each once."""
    asked = {x.strip() for x in (raw or "").split(",")}
    return [k for k in pack_order() if k in asked]


def sources(keys: list[str], vals_by: dict[str, dict]) -> list[str]:
    """The sources lines of the selected reports, each line once, in order."""
    out: list[str] = []
    for k in keys:
        vals = vals_by[k]
        n = 0
        while f"src.{n}" in vals:
            line = str(vals[f"src.{n}"]).strip()
            if line and line not in out:
                out.append(line)
            n += 1
    return out
