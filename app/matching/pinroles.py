"""Pin roles (data/pin_roles.yaml): control pins compared by what they do, not by their name (owner, 2 Nov 2026).

A part's pins take the roles of the datasheet its pinout was read from. Two pins at one position compare by the
``pairs`` table: our pin (the candidate) against the competitor's (the part being crossed). Pins without a role on
either side keep the name comparison (engine.pins_compatible).
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "pin_roles.yaml"
MATCH, CONDITIONAL, MISMATCH = "match", "conditional", "mismatch"
ANY = "any"
_PDF = re.compile(r"[^\s/;,()]+\.pdf\b", re.I)


@lru_cache
def data() -> dict:
    d = yamlio.load(FILE.read_text()) if FILE.exists() else {}
    d.setdefault("roles", {})
    d.setdefault("pairs", [])
    d["pins"] = {sheet.lower(): {str(k).upper(): v for k, v in (pins or {}).items()}
                 for sheet, pins in (d.get("pins") or {}).items()}  # fmt: skip
    d["names"] = frozenset(n for pins in d["pins"].values() for n in pins)
    d["input_side"] = {sheet.lower(): v for sheet, v in (d.get("input_side") or {}).items()}
    return d


def sheet_of(part) -> str | None:
    """The datasheet file a part's pinout was read from (its pinout source), else the file of its datasheet link or
    of its first stored datasheet; lower case."""
    for text in (getattr(part, "pinout_source", None), getattr(part, "datasheet_url", None)):
        m = _PDF.search(text or "")
        if m:
            return m.group(0).lower()
    sheets = getattr(part, "datasheets", None) or []
    return sheets[0].filename.lower() if sheets and getattr(sheets[0], "filename", None) else None


def role(part, pin: str) -> dict | None:
    """The role entry of one pin of a part ({"role": ..., "source": ...}), or None."""
    name = str(pin).strip().upper()
    if name not in data()["names"]:
        return None
    sheet = sheet_of(part)
    return data()["pins"].get(sheet, {}).get(name) if sheet else None


@dataclass(frozen=True)
class Judgement:
    result: str  # match | conditional | mismatch
    ref_role: str | None
    cand_role: str | None
    note: str | None = None  # conditional: the deciding note, "{pins}" to fill in
    default_variants: bool = False  # their default output follows the board, ours the ordering code


def judge(ref, cand, ref_pin: str, cand_pin: str) -> Judgement | None:
    """How our pin ``cand_pin`` takes the board wiring of their pin ``ref_pin``; None when neither has a role (or only
    one has and no pair covers it): the names decide then."""
    r, c = role(ref, ref_pin), role(cand, cand_pin)
    if r is None and c is None:
        return None
    rr, cr = (r or {}).get("role"), (c or {}).get("role")
    for p in data()["pairs"]:
        if p["ours"] == cr and (p["theirs"] == rr or (p["theirs"] == ANY and rr is not None)):
            return Judgement(p["result"], rr, cr, p.get("note"), bool(p.get("default_variants")))
    if rr is None or cr is None:
        return None
    return Judgement(MATCH if rr == cr else MISMATCH, rr, cr)


_SIDE_PIN = re.compile(r"^(VDD|GND|VCC|VSS|VEE)([12])$", re.I)


def input_side(part) -> int | None:
    """The side number a datasheet gives the input (sensing) side of an isolated amplifier, when it is not side 1
    (data/pin_roles.yaml ``input_side``: Analog Devices numbers it 2, Skyworks A and TI 1)."""
    sheet = sheet_of(part)
    entry = (data().get("input_side") or {}).get(sheet) if sheet else None
    return int(entry["side"]) if entry else None


def by_side(part, pins: list[str]) -> list[str]:
    """Pin names with the input side numbered 1: a part whose datasheet calls it side 2 has its side-1 and side-2
    supply and ground pins swapped (VDD2 -> VDD1, GND1 -> GND2), so pins compare by function (owner, 2 Nov 2026)."""
    if input_side(part) != 2:
        return pins
    return [_SIDE_PIN.sub(lambda m: m.group(1) + ("1" if m.group(2) == "2" else "2"), p) for p in pins]


def label(role_name: str | None) -> str:
    """A role in a few words ("output enable")."""
    return (role_name or "").replace("_", " ")


def pins_phrase(positions: list[int]) -> str:
    """"pin 7 is" / "pins 7 and 10 are" / "pins 6, 7 and 10 are"."""
    ps = [str(p) for p in sorted(positions)]
    if len(ps) == 1:
        return f"pin {ps[0]} is"
    return f"pins {', '.join(ps[:-1])} and {ps[-1]} are"
