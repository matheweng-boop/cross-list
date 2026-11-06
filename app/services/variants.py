"""One function, many bands (owner, 3 Nov 2026): rows that are the same device and differ only by frequency band or
power class (RF band gaps: "Frequency multiplier · L 1–2 GHz", "· S 2–4 GHz" …) fold into one parent row, so a list
of gaps counts and ranks functions, not every band of one function.

A parent sits where its first row sits in the order given (the best row by priority on Gaps & new technology, the
best by the chosen column in the detailed table), takes that row's scores, and keeps every row under `subs`, in the
same order. A function with one row stays that plain row.

Keep / set aside on a group: a decision on the function itself (its key is the function id) applies to all its band
rows; a decision on one band applies to that band only and wins over the function's (decision_of)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable


def _letter(band: dict, end: int) -> str:
    """A band's letter at one end of a span: "K / Ka 18–40 GHz" is K at the low end, Ka at the high end; a band with
    no letter (< 1 GHz) is "sub-1 GHz"."""
    letters = [t for t in re.split(r"[\s/]+", band["label"]) if t.isalpha() and t != "GHz"]
    return letters[end] if letters else "sub-1 GHz"


def _bands() -> list[dict]:
    from app.services import rf_coverage as rf  # lazy, like opportunity.rf_band_rows

    return rf.config()["bands"]


def decision_of(e: dict, decisions: dict):
    """The decision for a row: its own, else (for a band row) its function's. Returns (decision, inherited)."""
    own = decisions.get(e["key"])
    if own is not None or e["key"] == e["fn"]:
        return own, False
    up = decisions.get(e["fn"])
    return up, up is not None


def span(subs: Iterable[dict]) -> str:
    """The band span of the rows, lowest to highest: "L–Ka (1–40 GHz)", one band: "X 8–12 GHz", none: ""."""
    ids = {e.get("band_id") for e in subs}
    bs = [b for b in _bands() if b["id"] in ids]
    if not bs:
        return ""
    if len(bs) == 1:
        return bs[0]["label"]
    lo, hi = bs[0], bs[-1]
    return f"{_letter(lo, 0)}–{_letter(hi, -1)} ({lo['lo']:g}–{hi['hi']:g} GHz)"


def kind(subs: list[dict]) -> str:
    """What the rows differ by, in words for the count: bands, power classes or (mixed) variants."""
    bands = {e.get("band_id") for e in subs}
    powers = {e.get("power_label") for e in subs}
    if None not in bands and len(bands) == len(subs):
        return "bands"
    if len(bands) == 1 and None not in bands and len(powers) == len(subs):
        return "power classes"
    return "variants"


def _range(vals: list) -> tuple | None:
    vals = [v for v in vals if v is not None]
    return (min(vals), max(vals)) if vals else None


def parent(subs: list[dict]) -> dict:
    """The parent row of one function's rows: the first row's fields (its scores lead), the function's name, how many
    variants, the band span, the ranges of demand and TAM, and the rows themselves under `subs`."""
    head = subs[0]
    p = {**head}
    p.update(
        label=head.get("base_label") or head["label"],
        key=head["fn"],  # a decision on the group is a decision on the function (decision_of)
        subs=subs,
        n_variants=len(subs),
        variant_kind=kind(subs),
        span=span(subs),
        reach_range=_range([e.get("reach") for e in subs]),
        tam_range=_range([e.get("tam") for e in subs if e.get("tam_apps")]),
        n_kept=sum(status(e) == "keep" for e in subs),
        decision=_group_decision(subs),
        band_note=None,  # the per-band note belongs to the sub-rows
    )
    return p


def status(e: dict) -> str | None:
    """A row's decision status, whether the page holds the decision as a dict (detailed table) or a word."""
    d = e.get("decision")
    return d.get("status") if isinstance(d, dict) else d


def _group_decision(subs: list[dict]):
    """The decision on the function itself, as the detailed table holds it: the one its bands inherit; on Gaps & new
    technology (a word per row) the decision all its rows share, else none."""
    ds = [e.get("decision") for e in subs]
    if any(isinstance(d, dict) for d in ds):
        return next((d for d in ds if isinstance(d, dict) and d.get("inherited")), None)
    return ds[0] if len(set(ds)) == 1 else None


def group(rows: Iterable[dict], by: Callable[[dict], str] = lambda e: e["fn"]) -> list[dict]:
    """The rows in the order given, those of one function folded into one parent at the place of its first row."""
    order: dict[str, list[dict]] = {}
    for e in rows:
        order.setdefault(by(e), []).append(e)
    return [subs[0] if len(subs) == 1 else parent(subs) for subs in order.values()]


def count(rows: Iterable[dict]) -> int:
    """How many items a list shows once grouped: distinct functions."""
    return len({e["fn"] for e in rows})


def summary(p: dict) -> str:
    """The parent's line, e.g. "Frequency multiplier · 6 bands · L–Ka (1–40 GHz)"."""
    return " · ".join(x for x in (p["label"], f"{p['n_variants']} {p['variant_kind']}", p.get("span")) if x)
