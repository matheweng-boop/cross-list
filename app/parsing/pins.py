"""Normalised pinouts shared by all manufacturers.

Supplies become VDD1/VDD2; isolator channels are relabelled A, B, C… in order of
their side-1 pin, so that two parts with the same physical arrangement get the
same pin list whatever each manufacturer calls its channels.
"""

import re

SUPPLY = {"VCC1": "VDD1", "VDD1": "VDD1", "VCCI": "VDD1", "VCC2": "VDD2", "VDD2": "VDD2", "VCCO": "VDD2"}


def canonicalize(pin_map: dict[int, str], pin_count: int | None = None) -> list[str] | None:
    """``pin_map`` maps pin number -> name as printed (INA, OUTB, VCC1, NC…)."""
    pin_count = pin_count or max(pin_map, default=0)
    if sorted(pin_map) != list(range(1, pin_count + 1)):
        return None
    half = pin_count // 2
    pins: dict[int, str] = {}
    channels: dict[str, dict[str, int]] = {}
    for pin, raw in pin_map.items():
        name = re.sub(r"\s+", "", raw).upper()
        if name in SUPPLY:
            pins[pin] = SUPPLY[name]
        elif m := re.fullmatch(r"(IN|OUT)([A-H]?)", name):
            ends = channels.setdefault(m.group(2) or "A", {})
            if m.group(1) in ends:
                return None
            ends[m.group(1)] = pin
        else:
            pins[pin] = name
    order = []
    for ends in channels.values():
        if set(ends) != {"IN", "OUT"}:
            return None
        order.append((ends["IN"] if ends["IN"] <= half else ends["OUT"], ends))
    for idx, (_, ends) in enumerate(sorted(order, key=lambda o: o[0])):
        letter = "ABCDEFGH"[idx]
        pins[ends["IN"]], pins[ends["OUT"]] = f"IN{letter}", f"OUT{letter}"
    return [pins[p] for p in range(1, pin_count + 1)]


def fwd_rev(pins: list[str]) -> tuple[int, int]:
    half = len(pins) // 2
    side1 = pins[:half]
    fwd = sum(1 for p in side1 if re.fullmatch(r"IN[A-H]", p))
    rev = sum(1 for p in side1 if re.fullmatch(r"OUT[A-H]", p))
    return fwd, rev


DIAGRAM_RE = re.compile(
    r"([A-Z][A-Z0-9_/+-]*)\s+(\d{1,2})\s+(?:(NSI?[0-9A-Z]+(?:-Q1)?)\s+)?(\d{1,2})\s+([A-Z][A-Z0-9_/+-]*)"
)


def parse_pin_diagrams(text: str) -> dict[str, dict[int, str]]:
    """Pin-out drawings extracted as text rows, several devices side by side:
    "INC 5 12 OUTC INC 5 12 OUTC OUTC 5 12 INC" and a row carrying the device
    names: "GND1 8 NSI8240 9 GND2 GND1 8 NSI8241 9 GND2". Returns {device: {pin: name}}."""
    columns: list[dict[int, str]] = []
    names: list[str | None] = []
    for line in text.splitlines():
        found = list(DIAGRAM_RE.finditer(line))
        if not found:
            continue
        while len(columns) < len(found):
            columns.append({})
            names.append(None)
        for k, m in enumerate(found):
            left_name, left_pin, device, right_pin, right_name = m.groups()
            columns[k][int(left_pin)] = left_name
            columns[k][int(right_pin)] = right_name
            if device:
                names[k] = device.upper()
    return {name: col for name, col in zip(names, columns, strict=True) if name}
