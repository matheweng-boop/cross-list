"""Part descriptions, shown and searched one way. The source text stays in the data as the company published it;
pages show it cleaned (clean_description) next to a short description built from the part's structured fields
(short_description), and search matches both regardless of spacing, dashes and case (search_key)."""

import html
import re

from app.services import vocab

_UNITS = (
    (re.compile(r"kV\s*/\s*[uμµ]s\b", re.I), "kV/µs"),
    (re.compile(r"\bV\s*/\s*ns\b"), "V/ns"),
    (re.compile(r"kV\s*RMS\b", re.I), "kVrms"),
    (re.compile(r"(\d\s?)u(V|A|F|H|W|m|s)(rms)?\b"), r"\1µ\2\3"),
    (re.compile(r"(\d)\s*ohms?\b", re.I), r"\1 Ω"),
    (re.compile(r"(\d)\s*deg\.?\s*C\b"), r"\1 °C"),
    # a space between a number and its unit: 2.4GHz -> 2.4 GHz (not inside part numbers: the number stands alone)
    (
        re.compile(r"(?<![A-Za-z\d.\-])(\d+(?:\.\d+)?)(GHz|MHz|kHz|dBm|dBc|dB|kVrms|Vrms|kV|mA|ns|ps|mW|Mbps)\b"),
        r"\1 \2",
    ),
)


def units(text) -> str:
    """Units written one way: kV/us and kV/μs -> kV/µs, kVRMS -> kVrms, uV -> µV, 50 ohm -> 50 Ω, 2.4GHz -> 2.4 GHz."""
    s = "" if text is None else str(text)
    for rx, rep in _UNITS:
        s = rx.sub(rep, s)
    return s


_TAGS = re.compile(r"<[^>]+>")
_MARKS = re.compile(r"\s*(?:™|®|©|\((?:R|TM|C)\))", re.I)
# provenance the collectors appended: "(MACOM category: core chips)", "(listed under "Amplifiers")"
_PROVENANCE = re.compile(r"\s*\((?:[\w .-]+ category:|listed under)[^)]*\)", re.I)
_RANGE_DASH = re.compile(r"(\d)\s+[-–—]\s+(\d)|(\d)\s*[–—]\s*(\d)")
_DANGLING = re.compile(r"(?:\s*(?:\.\.\.|…)|[\s,;:–—-]+|\s+(?:for|with|and|or|in|of|to|the|a))+$")  # "a", not "5 A"
_PN_SEP = " -_/."
_LEAD = re.compile(r"^(?:the\s+)?(?:[\w-]+['’]s\s+)?", re.I)  # "The ", "Qorvo's " before a part number
_AFTER_PN = re.compile(r"^(?:\s*[:–-]\s+|\s+(?:is|are)\s+(?:an?\s+|the\s+)?)", re.I)


def _after_pn(s: str, mpn: str) -> int | None:
    """Index just past `mpn` at the start of `s`, ignoring separators and case (SI8641BD-IS = SI8641BD IS)."""
    want = [c for c in mpn.upper() if c not in _PN_SEP]
    i = j = 0
    while i < len(s) and j < len(want):
        c = s[i].upper()
        if c == want[j]:
            j += 1
        elif c not in _PN_SEP or j == 0:
            return None
        i += 1
    return i if j == len(want) and want else None


def _strip_pn(s: str, mpn: str) -> str:
    """Drop a leading part number: "ISO6441: Quad …", "The AG203-63 is a …", "Qorvo's QPA1234 is a …"."""
    lead = _LEAD.match(s).end()
    for start in dict.fromkeys((0, lead)):
        end = _after_pn(s[start:], mpn)
        if end is not None:
            m = _AFTER_PN.match(s[start + end :])
            if m:
                return s[start + end + m.end() :]
    return s


def clean_description(text, mpn: str = "") -> str:
    """The source text without markup, trademark signs, collector notes, a leading part number ("ISO6441: …",
    "The AG203-63 is a …") or a cut-off ending; units and ranges written one way."""
    s = _TAGS.sub(" ", html.unescape(str(text or "")))
    s = _MARKS.sub("", s)
    s = _PROVENANCE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^MPN\s*:\s*", "", s, flags=re.I)
    if mpn:
        s = _strip_pn(s, mpn)
    s = _RANGE_DASH.sub(lambda m: f"{m.group(1) or m.group(3)}–{m.group(2) or m.group(4)}", s)
    s = units(s)
    s = _DANGLING.sub("", s).rstrip(".").strip()
    if mpn and _after_pn(s, mpn) == len(s):
        return ""  # the description was only the part number
    return s[:1].upper() + s[1:]


def search_key(*texts) -> str:
    """Lower case, no spaces, one kind of dash: "2.4 GHz" and "2.4GHz", "0.1–6" and "0.1-6" find each other."""
    s = " ".join(str(t or "") for t in texts)
    s = units(html.unescape(_TAGS.sub(" ", s))).casefold()
    return re.sub(r"\s+", "", re.sub(r"[–—]", "-", s))


# key-spec names as catalogues write them ("Gain Typ. (dB)", "Gain (dB)", "Insertion Loss Max (dB)") folded to one
# name per quantity, with the unit to show
_SPEC_NAMES = (
    ("config", re.compile(r"^(?:configuration|config|topology|switch type)$")),
    ("gain", re.compile(r"^(?:small signal )?gain")),
    ("nf", re.compile(r"^(?:nf|noise figure)")),
    ("psat", re.compile(r"^(?:psat|saturated|output power|pout)")),
    ("p1db", re.compile(r"^(?:op1db|p1db|output p1db)")),
    ("il", re.compile(r"^insertion loss")),
)


def _fold(key: str) -> str:
    k = re.sub(r"\([^)]*\)|\btyp\b\.?|\btypical\b", " ", str(key).lower())
    return re.sub(r"\s+", " ", k).strip(" .:")


def _first_number(v) -> str | None:
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(v))
    return m.group(0) if m else None


def _spec(specs: dict, name: str) -> str | None:
    for k, v in (specs or {}).items():
        rx = dict(_SPEC_NAMES)[name]
        if rx.search(_fold(k)) and str(v).strip():
            return str(v).strip()
    return None


# a switch or attenuator configuration as catalogues write it: SP4T, DPDT, 6-bit, 2x2
_CONFIG = re.compile(r"^(?:[SD]P\d*[SDT]T|SP\d+T|\d+\s*x\s*\d+|\d+[- ]bit|transfer)$", re.I)
_FREQ_EDGE = re.compile(r"^(?:frequency|freq\.?|rf frequency)\s*(min|max)", re.I)


def _ghz(lo: float, hi: float) -> str:
    def g(x):
        return f"{x:.3g}" if x >= 0.1 else f"{x:.2g}"

    if abs(hi - lo) < 1e-9:
        return f"{g(lo)} GHz"
    return f"DC–{g(hi)} GHz" if lo == 0 else f"{g(lo)}–{g(hi)} GHz"


def _dc_range(specs: dict) -> tuple[float, float] | None:
    """'Frequency Min (GHz): 0' with a maximum: a DC-coupled part (frequency_ranges() leaves 0 out)."""
    edge = {}
    for k, v in specs.items():
        m = _FREQ_EDGE.match(_fold(k))
        n = _first_number(v)
        if m and n:
            edge[m.group(1).lower()] = float(n) * (1e-3 if re.search(r"MHz", f"{k} {v}", re.I) else 1.0)
    return (0.0, edge["max"]) if edge.get("min") == 0 and edge.get("max") else None


# the figure that says most about a part, by function: output power for PAs, gain then noise for LNAs
_FIGURES = {"power_amplifier": ("psat", "p1db", "gain"), "rf_predriver": ("p1db", "psat", "gain"),
            "rf_power_transistor": ("psat", "p1db", "gain"), "pa_module": ("psat", "p1db", "gain"),
            "lna": ("gain", "nf"), "gnss_lna": ("gain", "nf")}  # fmt: skip
_FIGURE_UNIT = {"psat": "dBm Psat", "p1db": "dBm P1dB", "gain": "dB gain", "nf": "dB NF"}


def _rf_spec(fn: str, specs: dict, description: str, params: dict) -> list[str]:
    from app.services.rf_coverage import frequency_ranges

    out = []
    cfg = str(params.get("configuration") or _spec(specs, "config") or "")
    if _CONFIG.match(cfg):
        out.append(cfg.upper() if cfg[:2].lower() in ("sp", "dp") else cfg)
    rng = params.get("freq_range_ghz")
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        out.append(_ghz(float(rng[0]), float(rng[1])))
    else:
        found = frequency_ranges(specs, description)
        ranges = [r for r in found if r[1] > r[0]] or found or [r for r in [_dc_range(specs)] if r]
        if ranges:
            out.append(_ghz(min(r[0] for r in ranges), max(r[1] for r in ranges)))
    for name in _FIGURES.get(vocab.canonical(fn) or "", ("gain", "p1db")):
        n = _first_number(_spec(specs, name) or "")
        if n:
            out.append(f"{n} {_FIGURE_UNIT[name]}")
            break
    return out


def _n(v) -> str:
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _isolation_params(specs: dict) -> dict:
    """Catalogue key specs of isolation parts in BizDev parameter terms (Forward / Reverse Channels -> '2/2')."""
    by = {_fold(k): v for k, v in specs.items() if str(v).strip()}
    out = {}
    fwd, rev = by.get("forward channels"), by.get("reverse channels")
    if fwd is not None:
        out["channel_config"] = f"{_n(fwd)}/{_n(rev or 0)}"
    elif by.get("driver channels"):
        out["driver_channels"] = by["driver channels"]
    for key, name in (("peak_source_a", "peak output current"), ("isolation_rating_kvrms", "isolation rating")):
        n = _first_number(by.get(name) or "")
        if n:
            out[key] = n
    return out


def _isolation_spec(params: dict) -> list[str]:
    out = []
    if params.get("driver_channels"):
        ch = _n(params["driver_channels"])
        out.append(f"{ch} channel{'s' if ch != '1' else ''}")
    if params.get("channel_config"):
        out.append(f"{params['channel_config']} channels")
    if params.get("peak_source_a"):
        sink = params.get("peak_sink_a")
        out.append(f"{_n(params['peak_source_a'])}/{_n(sink)} A" if sink else f"{_n(params['peak_source_a'])} A")
    if params.get("isolation_rating_kvrms"):
        out.append(f"{_n(params['isolation_rating_kvrms'])} kVrms")
    return out


def short_description(
    fn: str | None, package: str = "", grade: str | None = None, specs: dict | None = None, params: dict | None = None,
    description: str = "",
) -> str:  # fmt: skip
    """'RF switch · SP4T · 0.1–6 GHz · QFN-16 3x3 · AEC-Q100': function, key specs, package, grade. Any part that is
    not known is left out, never shown as n/a. `specs` are catalogue key specs (free text), `params` BizDev
    parameters (typed); `description` is only read for a frequency range when no spec states one."""
    params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    bits = [vocab.fn_label(fn)] if fn else []
    f = vocab.functions().get(vocab.canonical(fn) or "") or {}
    if f.get("category") == "rf" or "freq_range_ghz" in params:
        bits += _rf_spec(fn or "", specs or {}, description, params)
    else:
        bits += _isolation_spec({**_isolation_params(specs or {}), **params})
    if package:
        bits.append(str(package))
    if grade == "automotive":
        bits.append("AEC-Q100")
    return " · ".join(b for b in bits if b)
