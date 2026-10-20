"""Data for Engineering knowledge > Interactive visuals: values from the cross lists that the visuals draw as
reference lines (package creepage, isolator CMTI)."""

import re
from collections import Counter, defaultdict
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Package, ParamValue, Part
from app.services import blocks

_CACHE: dict = {}


def package_creepage(session: Session, limit: int = 8) -> list[dict]:
    """Creepage per package as the data sheets state it: the most common value of each package used by at least
    20 isolation parts, widest spread of values first chosen by use."""
    v = (blocks._data_version(session), limit)
    if v in _CACHE:
        return _CACHE[v]
    q = (
        select(Package.code, ParamValue.value)
        .join(Part, Part.package_id == Package.id)
        .join(ParamValue, ParamValue.part_id == Part.id)
        .where(ParamValue.key == "creepage_mm")
    )
    by: dict[str, Counter] = defaultdict(Counter)
    for code, val in session.execute(q):
        try:
            by[code][round(float(val), 1)] += 1
        except (TypeError, ValueError):
            continue
    rows = [{"code": c, "mm": cnt.most_common(1)[0][0], "parts": sum(cnt.values())} for c, cnt in by.items()]
    rows = [r for r in rows if r["parts"] >= 20]
    # one package per distinct creepage value, the most used one, so the reference lines do not pile up
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: -r["parts"]):
        if r["mm"] not in seen:
            seen.add(r["mm"])
            out.append(r)
    out = sorted(out[:limit], key=lambda r: r["mm"])
    _CACHE.clear()
    _CACHE[v] = out
    return out


# reference parts drawn as lines in the CMTI and gate-drive visuals: (label, exact part number, ours)
CMTI_REFS = (
    ("Si86xx", "SI8641BD-IS", True), ("Si86S", "SI86S641BE-IS2", True), ("Si82Ex", "SI82E39BEE-IS3", True),
    ("TI ISO6441", "ISO6441FDWR", False), ("Chipanalog CA-IS37", "CA-IS3741HW", False),
    ("Novosense NSI8241", "NSI8241W0-DSWR", False),
)  # fmt: skip
DRIVER_REFS = (
    ("Si8233 (source)", "SI8233BB-D-IS", True), ("Si82Ex", "SI82E39BEE-IS3", True),
    ("TI UCC21520 (source)", "UCC21520DWR", False), ("Infineon 2EDR8259H (source)", "2EDR8259HXUMA1", False),
)  # fmt: skip


def reference_values(session: Session) -> dict:
    """CMTI (kV/us) and peak source current (A) of the reference parts, as the cross lists hold them."""
    mpns = {m for _, m, _ in CMTI_REFS + DRIVER_REFS}
    q = (
        select(Part.mpn, ParamValue.key, ParamValue.value)
        .join(ParamValue, ParamValue.part_id == Part.id)
        .where(Part.mpn.in_(mpns), ParamValue.key.in_(("cmti_kv_us", "peak_source_a")))
    )
    vals: dict[tuple[str, str], float] = {}
    for mpn, key, val in session.execute(q):
        try:
            vals[(mpn, key)] = float(val)
        except (TypeError, ValueError):
            continue
    cmti = [{"name": n, "mpn": m, "kvus": vals[(m, "cmti_kv_us")], "ours": o} for n, m, o in CMTI_REFS
            if (m, "cmti_kv_us") in vals]  # fmt: skip
    drv = [{"name": n, "mpn": m, "a": vals[(m, "peak_source_a")], "ours": o} for n, m, o in DRIVER_REFS
           if (m, "peak_source_a") in vals]  # fmt: skip
    return {"cmti": cmti, "drivers": drv}


# --- RF catalogue numbers for the receiver visuals (cascaded NF part suggestions, blocker scenario) -------------------
_STAGE = {"lna": "lna", "gnss_lna": "lna", "rf_gain_block": "gain", "rf_predriver": "gain", "rf_mixer": "mixer",
          "rf_switch": "switch", "filter_saw_baw": "filter"}  # fmt: skip
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_SKIP = re.compile(r"flatness|control|step|return|\bLO\b|^IF\b|IF Freq", re.I)


def _nums(v) -> list[float]:
    text = re.sub(r"(\d)\s*(?:[-–]|to)\s*(?=\d)", r"\1 ", str(v).replace(",", ""))  # "0.4-3.0", "1 to 3": a range
    return [float(x) for x in _NUM.findall(text)]


def _ghz(key: str, val) -> list[float]:
    """Frequencies in GHz from a key/value pair, using the unit in the key or the value; [] when there is none."""
    unit = re.search(r"\b([GMk])Hz", f"{key} {val}")
    n = [x for x in _nums(val) if x >= 0]
    f = {"G": 1.0, "M": 1e-3, "k": 1e-6}[unit.group(1)] if unit else 1e-3 if n and min(n) >= 100 else None
    return [x * f for x in n] if f else []  # no unit: only values of 100 and up are read as MHz


def _rf_numbers(specs: dict, stage: str) -> dict:
    out: dict = {}

    def put(k, x):
        if x is not None and k not in out:
            out[k] = x

    fc, bw = None, None
    for key, val in specs.items():
        k, n = str(key), _nums(val)
        if _SKIP.search(k) or not n:
            continue
        kl = k.lower()
        if "freq" in kl or kl in ("bw", "frequency range"):
            g = _ghz(k, val)
            if not g:
                continue
            if "min" in kl:
                put("fmin", g[0])
            elif "max" in kl:
                put("fmax", g[-1])
            elif "cent" in kl or "test" in kl or len(g) == 1:
                fc = fc or g[0]
            else:
                put("fmin", g[0]), put("fmax", g[-1])
        elif kl.startswith("bandwidth") and "mhz" in kl:
            bw = n[0] / 1000
        elif kl.startswith("gain"):
            put("gain", n[0] if "max" not in kl else None)
        elif "noise figure" in kl or kl.startswith("nf") or kl == "min. nf":
            put("nf", n[0])
        elif "oip3" in kl:
            put("oip3", n[0])
        elif "iip3" in kl:
            put("iip3", n[0])
        elif re.match(r"(typ\.? )?ip3", kl):
            put("iip3" if stage in ("switch", "filter") else "oip3", n[0])
        elif re.search(r"\bi ?p ?1 ?db|typ\.? ip ?1", kl):
            put("ip1db", n[0])
        elif re.search(r"\bo?p ?1 ?db", kl):
            put("op1db", n[0])
        elif "insertion loss" in kl or re.search(r"\bil\b", kl):
            put("il", n[0] if "min" not in kl else None)
    if fc and "fmin" not in out:
        half = (bw or fc * 0.1) / 2
        out["fmin"], out["fmax"] = fc - half, fc + half
    if out.get("fmin", 0) > out.get("fmax", float("inf")):  # dual-band parts list one band's min and another's max
        out["fmin"], out["fmax"] = out["fmax"], out["fmin"]
    if "iip3" not in out and "oip3" in out and "gain" in out:
        out["iip3"] = round(out["oip3"] - out["gain"], 1)
    return out


@lru_cache
def rf_parts() -> list[dict]:
    """Active Skyworks / Qorvo RF catalogue parts with the numbers the receiver visuals use (GHz, dB, dBm)."""
    from app.services import lifecycle, vocab

    out = []
    for path, data in blocks._catalog_docs():
        for p in data.get("parts") or []:
            fns = vocab.fills(p.get("function"), p.get("also") or [])
            stage = next((_STAGE[f] for f in fns if f in _STAGE), None)
            mfr = p.get("manufacturer") or ("Qorvo" if "qorvo" in path.name else "Skyworks")
            status = str(p.get("status") or "")
            if not stage or mfr not in ("Skyworks", "Qorvo") or lifecycle.is_risk(status):
                continue
            nums = _rf_numbers(p.get("key_specs") or {}, stage)
            if "fmin" in nums and "fmax" in nums and (len(nums) > 2 or stage == "filter"):
                out.append({"mpn": p["mpn"], "mfr": mfr, "stage": stage, "preview": "preview" in status.lower(),
                            **{k: round(v, 4) for k, v in nums.items()}})  # fmt: skip
    return out
