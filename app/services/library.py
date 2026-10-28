"""Systems library: deep dives per topic (data/library/topics/<key>.yaml) with references, a block diagram drawn
by us, design rules, research trends and where our parts sit; and the background list of every source assessed
(data/library/sources.yaml). Only our own summaries and short quotes with citations are stored. Each topic links to
the General knowledge pages and the Interactive visuals it builds on, found by keyword (see `related`)."""

import re
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FOLDER = PROJECT_ROOT / "data" / "library"
FEASIBILITY = {"high": "High", "medium": "Medium", "low": "Low", "blocked": "Blocked"}
HORIZON = {"now": "Now", "2-3y": "2–3 years", "5y+": "5+ years"}
_KEY = re.compile(r"^[a-z0-9_]+$")


@lru_cache
def sources() -> tuple[dict, ...]:
    return tuple((yamlio.load((FOLDER / "sources.yaml").read_text()) or {}).get("sources") or [])


@lru_cache
def topic(key: str) -> dict | None:
    path = FOLDER / "topics" / f"{key}.yaml"
    if not _KEY.match(key) or not path.exists():
        return None
    return yamlio.load(path.read_text()) or {}


def topics() -> list[dict]:
    """Every topic, by its optional `order:` field, then by key."""
    out = [t | {"key": p.stem} for p in sorted((FOLDER / "topics").glob("*.yaml")) if (t := topic(p.stem))]
    return sorted(out, key=lambda t: (t.get("order", 99), t["key"]))


def refs_by_id(t: dict) -> dict[str, dict]:
    return {r["id"]: r for r in t.get("references") or []}


# ---- use across the site -------------------------------------------------------------------------------------------
def fns(t: dict) -> tuple[set[str], set[str]]:
    """(functions where we name parts, every function in the topic's block diagram), canonical ids."""
    from app.services import vocab

    fit = {vocab.canonical(s["fn"]) for s in t.get("skyworks_fit") or []}
    drawn = {vocab.canonical(b["fn"] if isinstance(b, dict) else b)
             for g in (t.get("block_diagram") or {}).get("groups") or [] for b in g.get("blocks") or []}  # fmt: skip
    return fit, drawn


def for_function(fn: str) -> list[dict]:
    """Topics that cover a function: first those that name our parts for it, then those that only draw it."""
    out = []
    for t in topics():
        fit, drawn = fns(t)
        if fn in fit or fn in drawn:
            note = next((s.get("note") for s in t.get("skyworks_fit") or [] if s["fn"] == fn), "")
            out.append({"key": t["key"], "title": t["title"], "ours": fn in fit, "note": note,
                        "trends": t.get("trends") or [], "n_rules": len(t.get("design_rules") or [])})  # fmt: skip
    return sorted(out, key=lambda x: not x["ours"])


def items(keys: list[str]) -> list[dict]:
    """Named topics in the shape for_function returns (for a case's `library:` list)."""
    out = []
    for k in keys or []:
        t = topic(k)
        if t:
            out.append({"key": k, "title": t["title"], "ours": False, "note": "", "trends": t.get("trends") or [],
                        "n_rules": len(t.get("design_rules") or [])})  # fmt: skip
    return out


def cases_using(key: str) -> list[dict]:
    """Preliminary cases that name the topic in their `library:` list."""
    from app.services import prelim
    from app.services import reports as rp

    return [{"slug": r["slug"], "title": r["title"]} for r in rp.reports()
            if key in ((prelim.raw(r["slug"]) or {}).get("library") or [])]  # fmt: skip


def notes(key: str) -> str:
    path = FOLDER / "notes" / f"{key}.md"
    return path.read_text() if _KEY.match(key) and path.exists() else ""


# ---- reviewers' assessment of rules and trends (DataReview rows, dataset "library:<key>", latest verdict counts) -----
VERDICTS = {"agree": "correct", "disagree": "wrong", "reset": "unsure"}
_LOWER = {"high": "med", "med": "low", "medium": "low", "low": "low"}


def dataset(key: str) -> str:
    return f"library:{key}"[:40]


def item_ids(key: str) -> set[str]:
    t = topic(key) or {}
    return {str(x["id"]) for x in [*(t.get("design_rules") or []), *(t.get("trends") or [])] if x.get("id")}


def reviewed(session, key: str) -> dict:
    """The topic with each rule and trend carrying its feedback; a disputed item's confidence drops one step."""
    from sqlalchemy import select

    from app.models import DataReview

    fb: dict[str, dict] = {}
    q = select(DataReview).where(DataReview.dataset == dataset(key)).order_by(DataReview.id)
    for r in session.scalars(q):
        f = fb.setdefault(r.key, {"verdict": None, "comments": []})
        f["verdict"] = None if r.verdict == "unsure" else r.verdict
        if r.comment:
            f["comments"].append({"text": r.comment, "author": r.author, "date": r.created_at})

    def attach(rows):
        out = []
        for x in rows or []:
            f = fb.get(str(x.get("id")), {})
            if f.get("verdict") == "wrong" and x.get("conf"):
                x = {**x, "conf_was": x["conf"], "conf": _LOWER.get(x["conf"], "low")}
            out.append({**x, "fb": f})
        return out

    t = topic(key) or {}
    n = sum(1 for f in fb.values() if f["verdict"] or f["comments"])
    return {**t, "design_rules": attach(t.get("design_rules")), "trends": attach(t.get("trends")), "n_feedback": n}


def react(session, key: str, item: str, verdict: str, comment: str = "", author: str = "") -> None:
    from app.models import DataReview

    if item not in item_ids(key) or verdict not in VERDICTS:
        raise ValueError("unknown item or verdict")
    session.add(DataReview(dataset=dataset(key), key=item[:120], verdict=VERDICTS[verdict],
                           comment=comment.strip()[:2000] or None, author=author.strip()[:100] or None))  # fmt: skip
    session.commit()


# ---- links to General knowledge and Interactive visuals ------------------------------------------------------------
# target -> keywords. Capitalised keywords (PA, NF, LNA) match case-sensitively, others in any case; whole words.
RF_NOTES = {  # RF fundamentals note ids (data/engineering_rf_notes.yaml)
    "cascaded_noise_figure": ("noise figure", "NF", "LNA", "LNAs", "Friis", "low-noise amplifier"),
    "sensitivity_noise_floor": ("sensitivity", "noise floor", "C/N0", "SNR"),
    "linearity_p1db_ip3": ("linearity", "IP3", "IIP3", "OIP3", "P1dB", "compression", "intermodulation"),
    "dynamic_range_sfdr_blocking": ("blocking", "blocker", "blockers", "dynamic range", "desense", "reciprocal mixing"),
    "vswr_return_loss_mismatch": ("VSWR", "return loss", "impedance mismatch", "mismatch loss", "impedance matching"),
    "acoustic_filters_duplexers": ("BAW", "SAW", "duplexer", "duplexers", "multiplexer", "acoustic", "notch"),
    "filter_fundamentals": ("filter", "filters", "filtering", "band-pass", "low-pass", "rejection"),
    "txrx_isolation_options": ("T/R switch", "circulator", "diplexer", "TDD", "half-duplex"),
    "rf_switches": ("RF switch", "RF switches", "SPDT", "antenna switch"),
    "attenuators_fixed_and_step": ("attenuator", "attenuators", "step attenuator"),
    "directional_couplers": ("coupler", "couplers", "power detector"),
    "pa_linearization_dpd_doherty": ("PA", "PAs", "power amplifier", "DPD", "predistortion", "Doherty", "ACLR", "EVM",
                                     "back-off"),
    "semiconductor_technology_map": ("GaN", "GaAs", "SiGe", "SOI", "CMOS", "LDMOS", "InP"),
    "link_budget_mmwave_fwa": ("link budget", "path loss", "EIRP", "e.i.r.p.", "cable loss"),
    "receiver_architectures": ("superheterodyne", "zero-IF", "direct sampling", "receiver architecture"),
    "phase_noise_oscillators": ("phase noise", "oscillator", "jitter"),
    "pll_synthesis": ("PLL", "synthesizer", "synthesiser"),
    "beamforming_architectures": ("beamforming", "phased array", "beam steering", "antenna array"),
    "radar_fundamentals": ("radar", "FMCW", "Doppler"),
    "satcom_ground_segment": ("satellite", "satcom", "NTN"),
    "limiters_receiver_protection": ("limiter", "limiters", "receiver protection"),
    "mmwave_5g_front_ends": ("mmWave", "FR2"),
    "wifi_fem_and_triband_ap": ("Wi-Fi", "WLAN", "FEM", "FEMs"),
    "power_splitters_combiners": ("splitter", "combiner", "Wilkinson"),
    "rf_transformers_baluns": ("balun", "baluns"),
}  # fmt: skip
SPEC_GUIDES = {  # specification guide keys (app/services/engineering.py NOTES)
    "cmti_kv_us": ("CMTI", "dv/dt", "common-mode transient"),
    "isolation_rating_kvrms": ("isolation rating", "kVrms", "withstand"),
    "isolation_class": ("reinforced", "basic isolation"),
    "creepage_mm": ("creepage", "clearance"),
    "viorm_vpk": ("working voltage", "VIORM", "VIOWM"),
    "default_output": ("default output", "fail-safe", "safe state"),
    "qualification": ("AEC-Q100", "AEC-Q104", "AEC-Q", "automotive grade", "Grade 1", "Grade 2"),
    "prop_delay_ns": ("propagation delay", "latency"),
    "data_rate_mbps": ("data rate", "Mbps"),
    "temp_range_c": ("temperature range", "ambient temperature"),
    "pwd_ns": ("dead time", "skew", "pulse-width distortion"),
    "peak_source_a": ("gate drive", "gate driver", "gate drivers", "peak current", "gate charge"),
    "uvlo_v": ("UVLO", "undervoltage"),
    "certifications": ("UL 1577", "VDE", "IEC 60747-17", "certification", "certifications"),
    "integrated_power": ("isolated power", "isolated bias", "isolated supply", "isolated supplies"),
    "uwb_signal_path": ("group delay", "group-delay", "pre-echo", "precursor", "pulse fidelity", "phase linearity"),
    "emc_eft_cispr": ("EFT", "burst", "IEC 61000-4-4", "CISPR 25", "CISPR 32", "conducted emissions",
                      "radiated emissions"),
}  # fmt: skip
VISUALS = {  # interactive visual id (app/web/static/visuals.js or static/vz/<id>.js) -> (title, link, keywords)
    "dbm": ("dBm: the power ladder", "/visuals#dbm", ("dBm",)),
    "link": ("Link budget and range", "/visuals#link", ("link budget", "path loss", "EIRP", "e.i.r.p.", "cable loss")),
    "wave": ("Wavelength and antenna size", "/visuals#wave", ("antenna", "antennas", "wavelength")),
    "nf": ("Cascaded noise figure and sensitivity", "/visuals#nf",
           ("noise figure", "NF", "LNA", "LNAs", "sensitivity", "C/N0")),
    "ip3": ("IP3 and intermodulation", "/visuals#ip3", ("IP3", "IIP3", "OIP3", "intermodulation", "linearity", "P1dB")),
    "fmim": ("FM intermodulation: where interference can come from", "/visuals#fmim",
             ("FM intermodulation", "image frequency", "image rejection")),
    "vswr": ("Mismatch, VSWR and the standing wave", "/visuals#vswr",
             ("VSWR", "return loss", "impedance mismatch", "mismatch loss")),
    "filter": ("Band-pass filter: order, bandwidth, rejection", "/visuals#filter",
               ("filter", "filters", "filtering", "BAW", "SAW", "rejection", "notch")),
    "lc": ("LC resonance and Q", "/visuals#lc", ("resonance", "resonator", "Q factor")),
    "skin": ("Skin depth", "/visuals#skin", ("skin depth", "skin effect")),
    "cmti": ("CMTI against the switching edge", "/visuals#cmti", ("CMTI", "dv/dt")),
    "creep": ("Creepage against working voltage", "/visuals#creep", ("creepage", "working voltage", "clearance")),
    "gate": ("Gate-drive current and power", "/visuals#gate",
             ("gate drive", "gate driver", "gate drivers", "gate charge")),
    "thermal": ("Junction temperature", "/visuals#thermal", ("thermal", "junction temperature")),
    "bvd": ("Acoustic resonator (SAW / BAW)", "/visuals#bvd",
            ("acoustic resonator", "piezoelectric", "coupling factor")),
    "mod": ("AM vs FM modulation", "/visuals#mod", ("AM", "FM", "modulation", "superheterodyne")),
    "jitter": ("Phase noise to jitter", "/visuals#jitter", ("jitter", "phase noise", "jitter attenuator")),
    "emc": ("EFT and CISPR: setup and design what-if", "/visuals#emc",
            ("EFT", "burst", "CISPR", "Y capacitor", "common-mode current", "emissions")),
    "swloss": ("Switching loss vs frequency", "/visuals#swloss",
               ("switching loss", "switching losses", "conduction loss")),
    "uwb": ("UWB: power limit, range, time of flight, relay and first path", "/visuals#uwb",  # static/vz/uwb.js
            ("time of flight", "two-way ranging", "first path", "relay attack", "distance bounding", "STS", "ranging")),
    "dab": ("DAB: from I/Q samples to the ensemble and the audio", "/visuals#dab",  # static/vz/dab.js
            ("DAB", "DAB+", "ensemble", "multiplex", "I/Q", "OFDM")),
    "flow": ("Signal flow: from the antenna to the audio", "/visuals#flow",  # static/vz/flow.js
             ("signal flow", "signal chain", "FM stereo", "de-emphasis", "MPX", "envelope detector")),
    "rds": ("RDS: the data under FM (PS name, traffic, AF, clock)", "/visuals#rds",  # static/vz/rds.js
            ("RDS", "RBDS", "RadioText", "traffic announcement", "alternative frequency")),
    "turnon": ("Three-step turn-on: overshoot, ringing, EMI and the filter", "/visuals#turnon",  # static/vz/turnon.js
               ("turn-on", "overshoot", "ringing", "EMI filter", "ProVCD", "di/dt")),
    "hex": ("Hex, binary and registers", "/visuals#hex",  # static/vz/hex.js
            ("hexadecimal", "register map", "register maps", "bit field", "bit fields", "endianness")),
    # owner, 28 Oct 2026: GNSS in general (static/vz/gnss.js)
    "gnssbands": ("GNSS band plan and the interferers around it", "/visuals#gnssbands",
                  ("band plan", "GPS L1", "GPS L5", "E5a", "B1C", "GLONASS", "Galileo", "BeiDou")),
    "gnsstri": ("Pseudoranges: why the receiver clock needs one more satellite", "/visuals#gnsstri",
                ("pseudorange", "pseudoranges", "trilateration", "receiver clock")),
    "gnssdop": ("Satellite geometry: dilution of precision (DOP)", "/visuals#gnssdop",
                ("DOP", "dilution of precision", "HDOP", "satellite geometry")),
    "gnssiono": ("Ionosphere: why dual frequency removes the delay", "/visuals#gnssiono",
                 ("ionosphere", "ionospheric", "dual-frequency", "dual frequency", "TEC")),
    # owner, 28 Oct 2026: animated circuits, current shown moving along the wires (static/vz/circuit.js)
    "bootstrap": ("Gate driver and half-bridge: bootstrap, dead time, Miller plateau", "/visuals#bootstrap",
                  ("bootstrap", "half-bridge", "half bridge", "dead time", "Miller plateau", "shoot-through")),
    "bldc": ("BLDC motor: 6-step commutation, FOC and back-EMF", "/visuals#bldc",
             ("BLDC", "brushless", "6-step", "six-step", "commutation", "FOC", "field-oriented control", "back-EMF",
              "back EMF", "sensorless", "zero crossing")),
    "buck": ("Buck converter: on loop, freewheel loop, inductor current", "/visuals#buck",
             ("buck converter", "buck converters", "freewheel", "inductor ripple", "duty cycle")),
    "efuse": ("Hot-swap / eFuse: inrush, short and trip", "/visuals#efuse",
              ("eFuse", "eFuses", "hot-swap", "hot swap", "inrush", "soft start")),
    "isosense": ("Isolated current sensing: shunt to controller, error by error", "/visuals#isosense",
                 ("shunt", "isolated amplifier", "isolated amplifiers", "current sensing", "delta-sigma modulator")),
    "ook": ("Capacitive isolator: on-off keying and common-mode rejection", "/visuals#ook",
            ("on-off keying", "OOK", "digital isolator", "digital isolators", "common-mode transient")),
    "rf-bands": ("RF bands chart", "/rf-bands", ("GNSS", "LTE", "5G", "V2X", "UWB", "Wi-Fi", "NTN", "band", "bands")),
}  # fmt: skip
_NEVER = re.compile(r"(?!x)x")


@lru_cache
def _patterns(keywords: tuple[str, ...]) -> tuple[re.Pattern, re.Pattern]:
    """(pattern for the keywords in any case, case-sensitive pattern for the capitalised ones); whole words only."""

    def alt(ws: list[str], flags=0) -> re.Pattern:
        if not ws:
            return _NEVER
        body = "|".join(re.escape(w) for w in sorted(ws, key=len, reverse=True))
        return re.compile(r"(?<![\w/-])(?:" + body + r")(?![\w-])", flags)

    return alt([w for w in keywords if w != w.upper()], re.I), alt([w for w in keywords if w == w.upper()])


def _hits(text: str, keywords: tuple[str, ...]) -> int:
    loose, exact = _patterns(keywords)
    return len(loose.findall(text)) + len(exact.findall(text))


def _text(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " ".join(_text(v) for k, v in x.items() if k not in ("references", "refs", "id", "url"))
    if isinstance(x, list | tuple):
        return " ".join(_text(v) for v in x)
    return ""


def _short(title: str, n: int = 42) -> str:
    """A note title up to its first ' - ', ':' or ', ', cut at a word to about n characters (for compact links)."""
    t = re.split(r" - |: |, ", title)[0]
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


@lru_cache
def _targets() -> dict[str, tuple[dict, ...]]:
    from app.services import engineering, rf_notes

    titles = {t["id"]: _short(t["title"]) for t in rf_notes.topics()}
    rf = [{"title": titles[k], "href": f"/rf-notes#{k}", "kind": "RF fundamentals", "kw": kw}
          for k, kw in RF_NOTES.items() if k in titles]  # fmt: skip
    spec = [{"title": engineering.NOTES[k][0], "href": f"/engineering/{k}", "kind": "Specification guide", "kw": kw}
            for k, kw in SPEC_GUIDES.items() if k in engineering.NOTES]  # fmt: skip
    vis = [{"title": t, "href": h, "kind": "Interactive visual", "kw": kw} for t, h, kw in VISUALS.values()]
    return {"knowledge": tuple(rf + spec), "visuals": tuple(vis)}


def related_to(text: str, min_hits: int = 1, limit: int = 8) -> dict[str, list[dict]]:
    """General knowledge pages and interactive visuals whose keywords appear in the text, most mentioned first."""
    out = {}
    for group, targets in _targets().items():
        scored = sorted(((n, t) for t in targets if (n := _hits(text, t["kw"])) >= min_hits), key=lambda x: -x[0])
        out[group] = [{k: v for k, v in t.items() if k != "kw"} | {"hits": n} for n, t in scored[:limit]]
    return out


@lru_cache
def related(key: str) -> dict[str, list[dict]]:
    """What a topic builds on: the General knowledge pages (RF fundamentals, specification guides) and the
    Interactive visuals its text mentions at least twice."""
    t = topic(key)
    return related_to(_text(t), min_hits=2, limit=8) if t else {"knowledge": [], "visuals": []}


def rule_links(rule: dict) -> dict | None:
    """The General knowledge page and the visual a design rule leans on most (either may be None)."""
    r = related_to(_text({k: rule.get(k) for k in ("area", "rule", "why")}), limit=1)
    k, v = (r["knowledge"] or [None])[0], (r["visuals"] or [None])[0]
    return {"knowledge": k, "visual": v} if k or v else None
