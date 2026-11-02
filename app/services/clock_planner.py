"""Clock planner (owner, 2 Nov 2026, item 18): a browser aid in the spirit of Skyworks ClockBuilder Pro.

From one or two input clocks (or a crystal), a list of outputs (frequency, count, format, supply), a jitter target, a
PCIe generation and automotive yes/no, it works out:

- which of our timing parts fit, with the reason for each check, and the closest TI and SiTime parts, using the
  timing cross rules (rules/timing.yaml, ``compare_param``) on the request as if it were a reference part;
- a frequency plan for the chosen part (planning estimate, est): the VCO frequency, which outputs get an integer
  divider and which a fractional one, and the divider values;
- the jitter against the target (datasheet typ first, max next to it);
- a clock-tree diagram (SVG).

It is not a register-exact plan: ClockBuilder Pro gives the final settings and programming files.
"""

import copy
import math
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from xml.sax.saxutils import escape

from app import yamlio
from app.matching.engine import BETTER, EQUAL, WORSE, compare_param
from app.matching.rules import get_rules

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "data" / "clocks" / "planner.yaml"
PART_FILES = ("skyworks_timing", "ti_timing", "sitime_timing")
FUNCTION_LABELS = {
    "clock_generator": "Clock generator",
    "jitter_attenuator": "Jitter attenuator",
    "clock_buffer": "Clock buffer",
    "pcie_buffer": "PCIe buffer",
    "crystal_oscillator": "Oscillator (XO)",
}
MAX_OUTPUT_ROWS = 16
MAX_OUTPUTS = 64


# ---------------------------------------------------------------- data


@lru_cache
def data() -> dict:
    return yamlio.load(DATA_FILE.read_text()) or {}


def presets() -> list[dict]:
    return data().get("presets") or []


def clockbuilder() -> dict:
    return data().get("clockbuilder") or {}


@lru_cache
def parts() -> tuple[dict, ...]:
    """Every timing part in the data files, ``like`` resolved as the loader does (app/services/seed.py), with the
    parameter values the cross rules read (defaults filled in)."""
    rules = get_rules("timing")
    out = []
    for name in PART_FILES:
        path = ROOT / "data" / "real" / f"{name}.yaml"
        if not path.exists():
            continue
        resolved: dict[str, dict] = {}
        for raw in (yamlio.load(path.read_text()) or {}).get("parts", []):
            spec = copy.deepcopy(resolved[raw["like"]]) if "like" in raw else {}
            params = {**spec.get("params", {}), **raw.get("params", {})}
            spec.update({k: v for k, v in raw.items() if k not in ("like", "params")})
            spec["params"] = params
            resolved[spec["mpn"]] = spec
            if spec.get("family") != "timing":
                continue
            values = dict(params)
            for p in rules.params:
                if p.default is not None and values.get(p.key) in (None, "", []):
                    values[p.key] = p.default
            out.append({"mpn": spec["mpn"], "manufacturer": spec["manufacturer"],
                        "description": spec.get("description", ""), "values": values,
                        "product_url": spec.get("product_url"),
                        "datasheet_url": spec.get("datasheet_url")})  # fmt: skip
    return tuple(out)


def architecture(mpn: str) -> dict | None:
    """How the part makes its outputs (data/clocks/planner.yaml), by the longest matching part-number start."""
    archs = data().get("architectures") or {}
    key = max((k for k in archs if mpn.upper().startswith(k.upper())), key=len, default=None)
    if key is None:
        return None
    return _resolve_arch(key)


def _resolve_arch(key: str) -> dict:
    archs = data()["architectures"]
    raw = dict(archs[key])
    if "like" in raw:
        base = _resolve_arch(raw.pop("like"))
        raw = {**base, **raw}
    raw["key"] = key
    return raw


# ---------------------------------------------------------------- the request


def parse_mhz(text) -> Fraction | None:
    """A frequency in MHz as typed: ``156.25``, ``100/3`` or ``33,333``. None when blank or not a positive number."""
    s = str(text or "").strip().replace(" ", "").replace(",", ".").removesuffix("MHz").removesuffix("mhz")
    if not s:
        return None
    try:
        v = Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None
    return v if v > 0 else None


def _num(text, lo: float, hi: float) -> float | None:
    try:
        v = float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi and math.isfinite(v) else None


def _int(text, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(float(str(text).strip()))))
    except (TypeError, ValueError):
        return default


def fmt_mhz(v: Fraction | float | None) -> str:
    if v is None:
        return "—"
    f = Fraction(v)
    if f.denominator == 1:
        return f"{f.numerator}"
    if f.denominator in (2, 4, 5, 8, 10, 16, 20, 25, 40, 50, 80, 100, 125, 200, 250, 400, 500, 1000):
        return f"{float(f):g}"
    return f"{float(f):.6g}"


def fmt_low(mhz: float) -> str:
    """The low end of a frequency range, readable below 1 MHz (100 Hz, not 1e-04): '0.5 Hz', '100 Hz', '24 kHz'."""
    v = float(mhz)
    if v >= 1:
        return fmt_mhz(Fraction(str(v)))
    if v >= 0.001:
        return f"{v * 1000:g} kHz"
    return f"{v * 1e6:g} Hz"


def build_request(form: dict) -> dict:
    """The planner request from the form (or a saved plan), every field optional: blank or unreadable values are
    dropped with a plain message, never an error page. ``form`` maps names to a value or a list of values."""

    def one(key, default=""):
        v = form.get(key, default)
        return (v[0] if v else default) if isinstance(v, list | tuple) else v

    def many(key):
        v = form.get(key, [])
        return list(v) if isinstance(v, list | tuple) else [v]

    notes: list[str] = []
    preset = next((p for p in presets() if p["key"] == one("preset")), None)
    if preset and not one("in1") and not any(many("f")):
        form = _preset_form(preset)
    req: dict = {"notes": notes, "preset": one("preset") if preset else ""}
    req["in1_kind"] = "crystal" if one("in1_kind") == "crystal" else "clock"
    req["in1"] = parse_mhz(one("in1"))
    req["in2"] = parse_mhz(one("in2"))
    if one("in1") and req["in1"] is None:
        notes.append(f"Input 1 “{one('in1')}” is not a frequency in MHz; left out.")
    if one("in2") and req["in2"] is None:
        notes.append(f"Input 2 “{one('in2')}” is not a frequency in MHz; left out.")
    fs, ns, fmts, vs = many("f"), many("n"), many("fmt"), many("v")
    outputs = []
    for i, f in enumerate(fs[:MAX_OUTPUT_ROWS]):
        if not str(f or "").strip():
            continue
        mhz = parse_mhz(f)
        if mhz is None:
            notes.append(f"Output “{f}” is not a frequency in MHz; left out.")
            continue
        fmt = str(fmts[i] if i < len(fmts) else "").upper()
        fmt = fmt if fmt in data().get("formats", []) else "LVDS"
        v = _num(vs[i] if i < len(vs) else "", 1.0, 3.6)
        outputs.append({"f": mhz, "n": _int(ns[i] if i < len(ns) else 1, 1, MAX_OUTPUTS, 1), "fmt": fmt, "v": v})
    req["outputs"] = outputs
    jit = _num(one("jit"), 0.001, 1_000_000)
    req["jitter_fs"] = None if jit is None else (jit * 1000 if one("jit_unit") == "ps" else jit)
    req["jit_unit"] = "ps" if one("jit_unit") == "ps" else "fs"
    pcie = str(one("pcie") or "none").lower()
    req["pcie"] = pcie if pcie in ("gen1", "gen2", "gen3", "gen4", "gen5", "gen6") else "none"
    req["automotive"] = str(one("auto") or "").lower() in ("1", "on", "true", "yes")
    t = one("type")
    req["type"] = t if t in FUNCTION_LABELS else ""
    req["part"] = str(one("part") or "").strip()[:60]
    return req


def _preset_form(p: dict) -> dict:
    outs = p.get("outputs") or []
    return {"preset": p["key"], "in1": str(p.get("in1", "")), "in1_kind": p.get("in1_kind", "clock"),
            "in2": str(p.get("in2", "") or ""), "f": [str(o["f"]) for o in outs], "n": [str(o["n"]) for o in outs],
            "fmt": [o["fmt"] for o in outs], "v": [str(o["v"]) for o in outs], "jit": str(p.get("jitter", "")),
            "jit_unit": "fs", "pcie": p.get("pcie", "none"), "auto": "1" if p.get("automotive") else "",
            "type": p.get("type", "")}  # fmt: skip


def to_form(req: dict) -> dict:
    """The request as form values (to fill the form, build links and save a plan): plain strings, JSON-safe."""
    jit = req.get("jitter_fs")
    if jit is not None and req.get("jit_unit") == "ps":
        jit = jit / 1000
    return {"in1": _frac_text(req.get("in1")), "in1_kind": req.get("in1_kind", "clock"),
            "in2": _frac_text(req.get("in2")),
            "f": [_frac_text(o["f"]) for o in req.get("outputs", [])],
            "n": [str(o["n"]) for o in req.get("outputs", [])],
            "fmt": [o["fmt"] for o in req.get("outputs", [])],
            "v": ["" if o["v"] is None else f"{o['v']:g}" for o in req.get("outputs", [])],
            "jit": "" if jit is None else f"{jit:g}", "jit_unit": req.get("jit_unit", "fs"),
            "pcie": req.get("pcie", "none"), "auto": "1" if req.get("automotive") else "",
            "type": req.get("type", ""), "part": req.get("part", ""), "preset": req.get("preset", "")}  # fmt: skip


def _frac_text(v: Fraction | None) -> str:
    if v is None:
        return ""
    f = Fraction(v)
    as_float = f"{float(f):.10g}"
    return as_float if Fraction(as_float) == f else f"{f.numerator}/{f.denominator}"


def query(req: dict, **change) -> str:
    """The planner link for this request (``/clocks?...``), with some fields changed."""
    from urllib.parse import urlencode

    form = {**to_form(req), **change}
    pairs = []
    for k, v in form.items():
        if isinstance(v, list):
            pairs += [(k, x) for x in v]
        elif v not in ("", None, "none") or k == "pcie" and v != "none":
            pairs.append((k, v))
    return "/clocks?" + urlencode(pairs)


# ---------------------------------------------------------------- which parts fit


def _reference(req: dict) -> dict:
    """The request as a reference part's values, for the cross rules."""
    fr = [o["f"] for o in req["outputs"]]
    ref = {"outputs": sum(o["n"] for o in req["outputs"]),
           "output_formats": sorted({o["fmt"] for o in req["outputs"]}),
           "freq_range_mhz": [float(min(fr)), float(max(fr))] if fr else None,
           "jitter_fs": req.get("jitter_fs"), "pcie_gen": req.get("pcie", "none"),
           "qualification": "automotive" if req.get("automotive") else "industrial",
           "inputs": 2 if req.get("in2") else 1}  # fmt: skip
    return ref


def check_part(part: dict, req: dict) -> dict:
    """Each check of the request against one part: (label, ok, text). ``ok`` is True, False or None (not known)."""
    rules = get_rules("timing")
    v = part["values"]
    ref = _reference(req)
    arch = architecture(part["mpn"]) if part["manufacturer"] == "Skyworks" else None
    ftype = v.get("function_type")
    checks: list[tuple[str, bool | None, str]] = []

    def add(label, ok, text):
        checks.append((label, ok, text))

    if req.get("type") and ftype != req["type"]:
        add("Part type", False, f"{FUNCTION_LABELS.get(ftype, ftype)}, not the {FUNCTION_LABELS[req['type']].lower()} "
                                "you asked for")  # fmt: skip
    status, _ = compare_param(rules.get("outputs"), ref["outputs"], v.get("outputs"))
    add("Outputs", status in (EQUAL, BETTER),
        f"{v.get('outputs')} outputs for your {ref['outputs']}" if status in (EQUAL, BETTER)
        else f"only {v.get('outputs')} outputs; you need {ref['outputs']}")  # fmt: skip
    status, _ = compare_param(rules.get("output_formats"), ref["output_formats"], v.get("output_formats") or [])
    missing = sorted(set(ref["output_formats"]) - {str(x).upper() for x in v.get("output_formats") or []})
    add("Formats", status in (EQUAL, BETTER), "all formats available" if not missing else f"no {', '.join(missing)}")
    rng = v.get("freq_range_mhz")
    if rng and ref["freq_range_mhz"]:
        outside = [o for o in req["outputs"] if not (rng[0] - 1e-9 <= float(o["f"]) <= rng[1] + 1e-9)]
        lim = (arch or {}).get("format_max_mhz") or {}
        over = [o for o in req["outputs"] if o["fmt"] in lim and float(o["f"]) > lim[o["fmt"]]]
        span = f"{fmt_low(rng[0])}–{fmt_mhz(Fraction(str(rng[1])))} MHz"
        if outside:
            add("Frequency", False, f"{', '.join(fmt_mhz(o['f']) for o in outside)} MHz outside {span}")
        elif over:
            add("Frequency", False, "; ".join(f"{o['fmt']} only to {lim[o['fmt']]} MHz" for o in over))
        else:
            add("Frequency", True, f"all within {span}")
    if ftype in ("clock_buffer", "pcie_buffer"):
        ins = {x for x in (req.get("in1"), req.get("in2")) if x}
        if req.get("in1_kind") == "crystal":
            add("Input", False, "a buffer needs an input clock, not a crystal")
        elif any(o["f"] not in ins for o in req["outputs"]):
            add("Input", False, "a buffer repeats its input: every output must equal an input frequency")
        else:
            add("Input", True, "outputs repeat the input clock")
    if ftype == "jitter_attenuator" and req.get("in1_kind") == "crystal":
        add("Input", None, "a jitter attenuator cleans an input clock; from a crystal alone a clock generator is the "
                           "usual choice")  # fmt: skip
    if ftype == "crystal_oscillator" and req.get("in1"):
        add("Input", None, "an oscillator has its own crystal; no input needed")
    if arch and arch.get("crystal_mhz") and req.get("in1_kind") == "crystal" and req.get("in1"):
        lo, hi = arch["crystal_mhz"]
        ok = lo <= float(req["in1"]) <= hi
        add("Crystal", ok, f"{fmt_mhz(req['in1'])} MHz {'within' if ok else 'outside'} {lo}–{hi} MHz")
    if req.get("in2") and ftype not in ("crystal_oscillator",):
        ok = (v.get("inputs") or 0) >= 2
        add("Inputs", ok, f"{v.get('inputs') or 'one'} input{'s' if (v.get('inputs') or 1) > 1 else ''}")
    supplies = (arch or {}).get("vddo_v")
    wanted = {o["v"] for o in req["outputs"] if o["v"] is not None}
    if supplies and wanted:
        bad = sorted(x for x in wanted if not any(abs(x - s) < 0.06 for s in supplies))
        add("Supply", not bad, "output supplies available" if not bad
            else f"no {', '.join(f'{x:g} V' for x in bad)} output supply")  # fmt: skip
    if req.get("jitter_fs") is not None:
        typ = v.get("jitter_fs")
        status, _ = compare_param(rules.get("jitter_fs"), req["jitter_fs"], typ)
        if typ is None:
            add("Jitter", None, "not stated")
        elif status == WORSE:
            add("Jitter", False, f"{typ:g} fs typ, above your {req['jitter_fs']:g} fs")
        elif typ > req["jitter_fs"]:
            add("Jitter", True, f"{typ:g} fs typ, within 10 % of your {req['jitter_fs']:g} fs")
        else:
            add("Jitter", True, f"{typ:g} fs typ against your {req['jitter_fs']:g} fs")
    if req.get("pcie", "none") != "none":
        status, _ = compare_param(rules.get("pcie_gen"), req["pcie"], v.get("pcie_gen", "none"))
        have = v.get("pcie_gen", "none")
        add(
            "PCIe",
            status in (EQUAL, BETTER),
            f"compliant to {'Gen ' + have[3:] if have != 'none' else 'no generation stated'}",
        )
    if req.get("automotive"):
        status, _ = compare_param(rules.get("qualification"), "automotive", v.get("qualification"))
        add(
            "Automotive",
            status in (EQUAL, BETTER),
            "AEC-Q100" if status in (EQUAL, BETTER) else f"{v.get('qualification')} grade, not AEC-Q100",
        )
    fails = sum(1 for _, ok, _ in checks if ok is False)
    over_spec = not req.get("automotive") and v.get("qualification") == "automotive"  # an industrial part does
    return {
        "part": part,
        "arch": arch,
        "checks": checks,
        "fails": fails,
        "fits": fails == 0,
        "over_spec": over_spec,
        "type_label": FUNCTION_LABELS.get(ftype, ftype),
    }


def _rank(r: dict):
    """Fits first; then parts without a caveat (None checks), the lowest jitter, the fewest outputs."""
    typ = r["part"]["values"].get("jitter_fs")
    caveats = sum(1 for _, ok, _ in r["checks"] if ok is None)
    outputs = r["part"]["values"].get("outputs") or 0
    return (r["fails"], caveats, r["over_spec"], typ if typ is not None else 1e9, outputs, r["part"]["mpn"])


def match(req: dict) -> dict:
    """Our parts that fit (fits first), the ones that do not with the reason, and the closest competitor parts."""
    if not req["outputs"]:
        return {"ours": [], "competitors": []}
    results = [check_part(p, req) for p in parts()]
    ours = sorted((r for r in results if r["part"]["manufacturer"] == "Skyworks"), key=_rank)
    types = {r["part"]["values"].get("function_type") for r in ours if r["fits"]} or {
        r["part"]["values"].get("function_type") for r in ours[:3]
    }
    others = sorted((r for r in results if r["part"]["manufacturer"] != "Skyworks"
                     and r["part"]["values"].get("function_type") in types), key=_rank)  # fmt: skip
    return {"ours": ours, "competitors": others[:4]}


def chosen(req: dict, matched: dict) -> dict | None:
    """The part the plan is for: the one picked, else the best fitting Skyworks part with a known architecture."""
    ours = matched["ours"]
    if req.get("part"):
        hit = next((r for r in ours if r["part"]["mpn"].lower() == req["part"].lower()), None)
        if hit:
            return hit
    return next((r for r in ours if r["fits"] and r["arch"]), None) or next((r for r in ours if r["arch"]), None)


# ---------------------------------------------------------------- the frequency plan (est)


def lcm(values) -> Fraction:
    """The least common multiple of positive rational numbers (the smallest number every value divides into an
    integer): lcm of the numerators over gcd of the denominators, each value in lowest terms."""
    vals = [Fraction(v) for v in values]
    if not vals:
        raise ValueError("lcm of nothing")
    num, den = 1, 0
    for v in vals:
        num = num * v.numerator // math.gcd(num, v.numerator)
        den = math.gcd(den, v.denominator)
    return Fraction(num, den)


def first_multiple(base: Fraction, lo: Fraction, hi: Fraction) -> Fraction | None:
    """The smallest multiple of ``base`` within [lo, hi], or None."""
    k = math.ceil(Fraction(lo) / base)
    m = max(k, 1) * base
    return m if m <= hi else None


def group_outputs(freqs: list[Fraction], kind: str, r_max: int = 62) -> list[dict]:
    """Outputs that can share one divider before their own output divider R, highest first. A group's base is the
    frequency its shared divider makes; each output divides it by R. MultiSynth parts (R even, at least 2): base = 2 x
    the highest frequency. Si5332 (R = 1 or even up to 62): base = the highest frequency. Integer-only multi-PLL parts:
    one group per frequency (the PLL's VCO is chosen for them)."""
    groups: list[dict] = []
    for f in sorted(set(freqs), reverse=True):
        for g in groups:
            r = g["base"] / f
            if r.denominator == 1 and _r_ok(int(r), kind, r_max):
                g["members"].append(f)
                break
        else:
            base = 2 * f if kind == "multisynth" else f
            groups.append({"base": base, "members": [f]})
    return groups


def _r_ok(r: int, kind: str, r_max: int) -> bool:
    if kind == "multisynth":
        return r >= 2 and r % 2 == 0
    if kind == "si5332":
        return r == 1 or (r % 2 == 0 and r <= r_max)
    return r >= 1


def choose_vco(bases: list[Fraction], vco: tuple, ref: Fraction | None = None) -> dict:
    """The VCO frequency for these group bases within the VCO range: the smallest multiple of the bases' LCM in range
    makes every divider an integer. When no VCO does, the one that makes the most dividers integer (est); between
    equals, one that is also an integer multiple of the reference (integer feedback divider), then the lowest."""
    lo, hi = Fraction(str(vco[0])), Fraction(str(vco[1]))
    uniq = sorted(set(bases), reverse=True)
    best = None
    n = len(uniq)
    sizes = range(n, 0, -1)
    for size in sizes:
        subsets = combinations(uniq, size) if math.comb(n, size) <= 5000 else [tuple(uniq[:size])]
        for sub in subsets:
            for with_ref in (True, False) if ref else (False,):
                base = lcm([*sub, ref] if with_ref else sub)
                m = first_multiple(base, lo, hi)
                if m is None:
                    continue
                key = (size, with_ref, -m)
                if best is None or key > best[0]:
                    best = (key, m, set(sub))
        if best is not None:
            break
    if best is None:
        mid = (lo + hi) / 2
        mid = Fraction(round(mid))
        return {"vco": mid, "integer": set(), "feedback_integer": bool(ref and (mid / ref).denominator == 1)}
    _, m, sub = best
    return {"vco": m, "integer": sub, "feedback_integer": bool(ref and (m / ref).denominator == 1)}


def divider_text(d: Fraction) -> str:
    if d.denominator == 1:
        return str(d.numerator)
    whole, rest = divmod(d.numerator, d.denominator)
    if d.denominator <= 1_000_000:
        return f"{whole} + {rest}/{d.denominator} (≈ {float(d):.6f})"
    return f"≈ {float(d):.9f}"


def plan(req: dict, arch: dict | None, part: dict | None = None) -> dict:
    """The frequency plan for one part (est): VCO, divider per output frequency (integer or fractional), whether the
    part has dividers enough, and the outputs outside its range. ``problems`` holds plain-English reasons it fails."""
    out = {"kind": (arch or {}).get("kind"), "problems": [], "rows": [], "plls": [], "notes": []}
    freqs = [o["f"] for o in req["outputs"]]
    if not freqs:
        out["problems"].append("Add at least one output.")
        return out
    if not arch:
        out["problems"].append("No frequency plan for this part: how it divides is not in our data yet.")
        return out
    kind = arch["kind"]
    rng = (part or {}).get("values", {}).get("freq_range_mhz")
    if rng:
        outside = sorted({f for f in freqs if not (rng[0] - 1e-9 <= float(f) <= rng[1] + 1e-9)})
        if outside:
            out["problems"].append(f"{', '.join(fmt_mhz(f) for f in outside)} MHz is outside this part's output "
                                   f"range ({fmt_low(rng[0])}–{rng[1]:g} MHz).")  # fmt: skip
            freqs = [f for f in freqs if f not in outside]
            if not freqs:
                return out
    ref = req.get("in1")
    if kind == "buffer":
        ins = [x for x in (req.get("in1"), req.get("in2")) if x]
        for f in sorted(set(freqs), reverse=True):
            out["rows"].append({"f": f, "divider": "1 (repeats the input)", "integer": f in ins, "group": "Fanout"})
        if any(f not in ins for f in freqs) or not ins:
            out["problems"].append("A buffer only repeats its input: every output must equal an input frequency.")
        out["all_integer"] = not out["problems"]
        return out
    if kind == "xo":
        uniq = sorted(set(freqs))
        out["rows"] = [{"f": f, "divider": "set at the factory (or over I2C)", "integer": True, "group": "XO"}
                       for f in uniq]  # fmt: skip
        if len(uniq) > 1 or sum(o["n"] for o in req["outputs"]) > 1:
            out["problems"].append("An oscillator has one output: use one per frequency, or a clock generator.")
        out["all_integer"] = True
        return out
    vco = arch["vco_mhz"]
    if kind == "multi_pll":
        return _plan_multi(out, freqs, arch, ref)
    groups = group_outputs(freqs, kind, arch.get("r_max", 62))
    choice = choose_vco([g["base"] for g in groups], vco, ref)
    v = choice["vco"]
    out["vco"] = v
    out["feedback_integer"] = choice["feedback_integer"]
    n_int = n_frac = 0
    for i, g in enumerate(groups):
        n = v / g["base"]
        integer = n.denominator == 1
        if kind == "si5332":
            label = f"INT{n_int}" if integer and n_int < arch.get("int_dividers", 0) else f"N{n_frac}"
            if label.startswith("INT"):
                n_int += 1
            else:
                n_frac += 1
        else:
            label = f"N{i}"
        g.update({"label": label, "n": n, "integer": integer})
        for f in g["members"]:
            r = g["base"] / f
            out["rows"].append({"f": f, "group": label, "n": n, "n_text": divider_text(n), "r": int(r),
                                "total": v / f, "total_text": divider_text(v / f), "integer": integer})  # fmt: skip
    out["groups"] = groups
    if kind == "si5332":
        frac_needed = sum(1 for g in groups if not g["integer"]) + max(0, sum(1 for g in groups if g["integer"])
                                                                       - arch.get("int_dividers", 0))  # fmt: skip
        if frac_needed > arch.get("frac_dividers", 0):
            out["problems"].append(f"Needs {frac_needed} fractional MultiSynth dividers; the part has "
                                   f"{arch.get('frac_dividers', 0)}.")  # fmt: skip
    elif len(groups) > arch.get("frac_dividers", 0):
        out["problems"].append(f"Needs {len(groups)} N dividers; the part has {arch.get('frac_dividers', 0)}.")
    out["all_integer"] = all(g["integer"] for g in groups)
    out["fractional"] = sorted({f for g in groups if not g["integer"] for f in g["members"]}, reverse=True)
    return out


def _plan_multi(out: dict, freqs: list[Fraction], arch: dict, ref: Fraction | None) -> dict:
    """Several PLLs with integer output dividers: put as many frequencies as possible on each PLL in turn (VCO = a
    multiple of the LCM of 2 x each frequency, R even), up to the number of PLLs."""
    lo, hi = Fraction(str(arch["vco_mhz"][0])), Fraction(str(arch["vco_mhz"][1]))
    left = sorted(set(freqs), reverse=True)
    for k in range(arch.get("plls", 1)):
        if not left:
            break
        choice = choose_vco([2 * f for f in left], (lo, hi), ref)
        on = sorted({f for f in left if 2 * f in choice["integer"]}, reverse=True)
        if not on:
            break
        v = choice["vco"]
        out["plls"].append({"label": f"PLL {chr(65 + k)}", "vco": v, "members": on})
        for f in on:
            out["rows"].append({"f": f, "group": f"PLL {chr(65 + k)}", "r": int(v / f), "total": v / f,
                                "total_text": divider_text(v / f), "integer": True})  # fmt: skip
        left = [f for f in left if f not in on]
    if left:
        out["problems"].append(f"{', '.join(fmt_mhz(f) for f in left)} MHz cannot be made with integer dividers on "
                               f"the {arch.get('plls', 1)} PLLs.")  # fmt: skip
    out["all_integer"] = True
    out["vco"] = out["plls"][0]["vco"] if out["plls"] else None
    return out


# ---------------------------------------------------------------- jitter


def jitter(req: dict, arch: dict | None, the_plan: dict, part: dict | None = None) -> dict:
    """Datasheet jitter for the plan's mode (typ, max) against the target, and the PCIe-filtered jitter where the data
    has it. ``rows``: (what, typ fs, max fs, ok, source, est)."""
    rows = []
    target = req.get("jitter_fs")
    arch = arch or {}
    if arch.get("kind") == "buffer":
        typ, mx = arch.get("additive_fs") or [None, None]
        rows.append({"what": "Additive jitter (the buffer's own), 12 kHz–20 MHz", "typ": typ, "max": mx,
                     "source": arch.get("jitter_source", ""), "est": False})  # fmt: skip
        rows.append({"what": "Output = √(input² + additive²): your source's jitter decides", "typ": None, "max": None,
                     "source": "est (RMS sum)", "est": True})  # fmt: skip
    elif arch.get("jitter"):
        j = arch["jitter"]
        mode = "int" if the_plan.get("all_integer", True) else "frac"
        src = "xtal" if req.get("in1_kind") == "crystal" else "clock"
        key = next((k for k in (f"{src}_{mode}", f"clock_{mode}", f"xtal_{mode}", "xo", "clock_int", "xtal_int")
                    if k in j), None)  # fmt: skip
        if key:
            typ, mx = j[key]
            what = {"xo": "Phase jitter", "int": "Phase jitter, integer mode", "frac": "Phase jitter, fractional mode"}
            label = what["xo"] if key == "xo" else what[key.split("_")[1]]
            if key != "xo" and key.split("_")[1] != mode:
                label += " (the only value in our data; a fractional divider adds jitter, est)"
            elif key != "xo" and key != f"{src}_{mode}":
                label += f" ({'crystal' if key.startswith('xtal') else 'input clock'} values)"
            rows.append({"what": f"{label}, 12 kHz–20 MHz", "typ": typ, "max": mx, "source": arch.get("jitter_source"),
                         "est": key != f"{src}_{mode}" and key != "xo"})  # fmt: skip
    elif part:
        typ = part["values"].get("jitter_fs")
        if typ is not None:
            rows.append({"what": "Phase jitter, 12 kHz–20 MHz", "typ": typ, "max": None, "source": "part data",
                         "est": False})  # fmt: skip
    for r in rows:
        if target is None or (r["typ"] is None and r["max"] is None):
            r["ok"] = None
        else:
            r["ok"] = (r["typ"] if r["typ"] is not None else r["max"]) <= target
            r["max_ok"] = None if r["max"] is None else r["max"] <= target
    pcie = None
    if req.get("pcie", "none") != "none":
        limit = (data().get("pcie_limits_ps") or {}).get(req["pcie"])
        have = (arch.get("pcie_jitter_ps") or {}).get(req["pcie"])
        pcie = {"gen": req["pcie"], "limit": limit, "typ": have[0] if have else None, "max": have[1] if have else None,
                "source": arch.get("pcie_source", ""), "stated": bool(have)}  # fmt: skip
        value = pcie["max"] if pcie["max"] is not None else pcie["typ"]
        pcie["ok"] = None if value is None or limit is None else value <= limit
    notes = [(f, (arch.get("format_notes") or {})[f]) for f in sorted({o["fmt"] for o in req["outputs"]})
             if f in (arch.get("format_notes") or {})]  # fmt: skip
    return {"rows": rows, "target": target, "pcie": pcie, "format_notes": notes}


# ---------------------------------------------------------------- clock-tree diagram


def diagram(req: dict, the_plan: dict, part_label: str) -> str:
    """The clock tree as SVG: input(s) → PLL / VCO → dividers → outputs with frequency, count and format. Drawn on a
    fixed 640-unit-wide canvas; the page shows it in its own scrolling box on a phone."""
    outs = req["outputs"]
    if not outs:
        return ""
    row_h, top = 34, 30
    by_f: dict[Fraction, list[dict]] = {}
    for o in outs:
        by_f.setdefault(o["f"], []).append(o)
    rows = the_plan.get("rows") or []
    group_of = {r["f"]: r.get("group", "") for r in rows}
    integer_of = {r["f"]: r.get("integer", True) for r in rows}
    # outputs in the order of their groups, so a divider's outputs sit together
    order = sorted(outs, key=lambda o: (str(group_of.get(o["f"], "~")), -o["f"]))
    h = top + max(len(order), 2) * row_h + 20
    w = 640
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" class="cp-svg" '
         f'aria-label="Clock tree for {escape(part_label)}">']  # fmt: skip
    p.append('<g font-size="12" fill="currentColor">')
    p.append(f'<text x="8" y="16" class="cp-svg-h">Inputs</text><text x="150" y="16" class="cp-svg-h">'
             f'{escape(part_label)}</text><text x="440" y="16" class="cp-svg-h">Outputs</text>')  # fmt: skip
    mid = top + (len(order) * row_h) / 2
    ins = [(req.get("in1"), "crystal" if req.get("in1_kind") == "crystal" else "clock")]
    if req.get("in2"):
        ins.append((req["in2"], "clock"))
    for i, (f, kind) in enumerate(ins):
        y = mid - 24 + i * 40 if len(ins) > 1 else mid - 12
        txt = f"{fmt_mhz(f)} MHz {kind}" if f else "no input given"
        p.append(f'<rect x="4" y="{y:.0f}" width="112" height="26" rx="6" class="cp-in"/>'
                 f'<text x="10" y="{y + 17:.0f}">{escape(txt)}</text>')  # fmt: skip
        p.append(f'<line x1="116" y1="{y + 13:.0f}" x2="150" y2="{mid:.0f}" class="cp-wire"/>')
    kind = the_plan.get("kind")
    core = {"buffer": "Fanout buffer", "xo": "Crystal + PLL inside"}.get(kind or "", "PLL")
    vco = the_plan.get("vco")
    p.append(f'<rect x="150" y="{mid - 26:.0f}" width="120" height="52" rx="8" class="cp-pll"/>'
             f'<text x="160" y="{mid - 6:.0f}" font-weight="600">{escape(core)}</text>')  # fmt: skip
    if vco and kind not in ("buffer", "xo"):
        label = "VCO " + (f"{float(vco) / 1000:.6g} GHz" if vco >= 1000 else f"{fmt_mhz(vco)} MHz")
        if the_plan.get("plls") and len(the_plan["plls"]) > 1:
            label = f"{len(the_plan['plls'])} PLLs"
        p.append(f'<text x="160" y="{mid + 12:.0f}">{escape(label)}</text>')
    divs_drawn: dict[str, float] = {}
    for i, o in enumerate(order):
        y = top + i * row_h + 4
        g = group_of.get(o["f"], "")
        dx = 300
        if g and g not in divs_drawn and kind not in ("buffer", "xo"):
            divs_drawn[g] = y
            cls = "cp-div" if integer_of.get(o["f"], True) else "cp-div cp-frac"
            p.append(f'<line x1="270" y1="{mid:.0f}" x2="{dx}" y2="{y + 13}" class="cp-wire"/>'
                     f'<rect x="{dx}" y="{y}" width="108" height="26" rx="6" class="{cls}"/>'
                     f'<text x="{dx + 6}" y="{y + 17}">{escape(g)} '
                     f'{"integer" if integer_of.get(o["f"], True) else "fractional"}</text>')  # fmt: skip
        src_x, src_y = (dx + 108, divs_drawn.get(g, y) + 13) if g in divs_drawn else (270, mid)
        r = next((x.get("r") for x in rows if x["f"] == o["f"]), None)
        p.append(f'<line x1="{src_x}" y1="{src_y:.0f}" x2="440" y2="{y + 13}" class="cp-wire"/>')
        if r and kind not in ("buffer", "xo"):
            p.append(f'<text x="{(src_x + 440) / 2 - 10:.0f}" y="{y + 10}" font-size="10">÷{r}</text>')
        v = f" {o['v']:g} V" if o["v"] else ""
        p.append(
            f'<rect x="440" y="{y}" width="196" height="26" rx="6" class="cp-out"/>'
            f'<text x="446" y="{y + 17}">{escape(fmt_mhz(o["f"]))} MHz {escape(o["fmt"])} ×{o["n"]}{v}</text>'
        )
    p.append("</g></svg>")
    return "".join(p)


# ---------------------------------------------------------------- everything for the page


def run(req: dict) -> dict:
    matched = match(req)
    pick = chosen(req, matched)
    the_plan = plan(req, pick["arch"] if pick else None, pick["part"] if pick else None) if pick else None
    jit = jitter(req, pick["arch"], the_plan, pick["part"]) if pick and the_plan else None
    svg = diagram(req, the_plan, pick["part"]["mpn"]) if pick and the_plan else ""
    return {"matched": matched, "pick": pick, "plan": the_plan, "jitter": jit, "svg": svg}
