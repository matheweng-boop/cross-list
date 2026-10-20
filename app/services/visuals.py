"""Data for Engineering knowledge > Interactive visuals: values from the cross lists that the visuals draw as
reference lines (package creepage, isolator CMTI)."""

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Package, ParamValue, Part
from app.services import blocks

_CACHE: dict = {}


def package_creepage(session: Session, limit: int = 8) -> list[dict]:
    """Creepage per package as the data sheets state it: the most common value of each package used by at least
    20 isolation parts, widest spread of values first chosen by use."""
    v = blocks._data_version(session)
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
