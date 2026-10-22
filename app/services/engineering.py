"""Engineering notes: one short page per specification, explaining what a deviation means in
the application, with a quick calculator where a defensible one exists.

Note bodies live in app/web/templates/engineering/notes/<key>.html (plain HTML, easy to edit);
a parameter without a body gets a generic page built from its rules definition.
"""

from dataclasses import dataclass
from pathlib import Path

from app.matching.engine import compare_param, format_at
from app.matching.rules import ParamDef, load_all_rules
from app.models import Part

NOTES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates" / "engineering" / "notes"

# Key -> (title, one-line summary). Keys are the rules' parameter keys; a few notes cover
# several keys (e.g. both peak currents).
NOTES = {
    "cmti_kv_us": ("CMTI", "How fast the switch node may move before the isolator risks a logic upset."),
    "isolation_rating_kvrms": ("Isolation rating", "The one-minute withstand voltage and what it does not say."),
    "isolation_class": ("Basic vs reinforced isolation", "When one barrier must protect a person on its own."),
    "creepage_mm": ("Creepage", "Surface distance across the package and why the standard decides the minimum."),
    "viorm_vpk": ("Working voltage", "The voltage the barrier may see continuously for its lifetime."),
    "default_output": ("Default output state", "What the outputs do while the input side is unpowered."),
    "qualification": ("Automotive grade", "Why an industrial part cannot replace an AEC-Q100 one."),
    "channel_config": ("Channel configuration", "Number and direction of channels: never a deviation."),
    "integrated_power": ("Integrated isolated power", "Parts that also carry power across the barrier."),
    "prop_delay_ns": ("Propagation delay", "Latency through the barrier and the SPI clock it allows."),
    "data_rate_mbps": ("Data rate", "Headroom between the signal and the part's maximum rate."),
    "vdd_range_v": ("Supply range", "Whether your logic rails sit inside the part's supply range."),
    "temp_range_c": ("Operating temperature", "Ambient range and what a narrower one means."),
    "pwd_ns": ("Pulse-width distortion and skew", "Timing errors that eat into dead time and duty cycle."),
    "peak_source_a": ("Peak drive current", "How long the driver takes to move the gate charge."),
    "uvlo_v": ("UVLO threshold", "Why UVLO variants are not interchangeable."),
    "certifications": ("Safety certifications", "UL 1577, VDE / IEC 60747-17, CSA, CQC, TÜV."),
    "deadtime": ("Dead time and overlap protection", "Two names for one shoot-through guard in half-bridge drivers."),
}
ALIASES = {"skew_ns": "pwd_ns", "peak_sink_a": "peak_source_a"}


@dataclass
class Context:
    """The reference and candidate a user came from, compared on this note's parameter."""

    reference: Part
    candidate: Part
    param: ParamDef
    ref_display: str
    cand_display: str
    status: str


def note_key(key: str) -> str:
    return ALIASES.get(key, key)


def param_def(key: str, family: str | None = None) -> ParamDef | None:
    rules = load_all_rules()
    if family and family in rules and rules[family].get(key):
        return rules[family].get(key)
    return next((r.get(key) for r in rules.values() if r.get(key)), None)


def families_using(key: str) -> list[tuple[str, int]]:
    return [(r.title, r.get(key).priority) for r in load_all_rules().values() if r.get(key)]


def has_body(key: str) -> bool:
    return (NOTES_DIR / f"{key}.html").exists()


def context(key: str, reference: Part | None, candidate: Part | None) -> Context | None:
    if reference is None or candidate is None:
        return None
    rules = load_all_rules().get(reference.family)
    p = rules.get(key) if rules else None
    if p is None:
        return None
    rv, cv = rules.at_same_conditions(rules.values(reference), rules.values(candidate))
    status, _ = compare_param(p, rv.get(key), cv.get(key))
    return Context(reference, candidate, p, format_at(rules, p, rv), format_at(rules, p, cv), status)


def device(part: Part) -> dict:
    """What the calculators need from a part: its numeric parameter values."""
    values = {pv.key: pv.value for pv in part.params}
    sources = {pv.key: pv.source for pv in part.params if pv.source}
    return {"id": part.id, "mpn": part.mpn, "maker": part.manufacturer.name, "values": values, "sources": sources}


def index() -> list[dict]:
    rows = []
    for key, (title, summary) in NOTES.items():
        rows.append({"key": key, "title": title, "summary": summary, "families": families_using(key)})
    return rows
