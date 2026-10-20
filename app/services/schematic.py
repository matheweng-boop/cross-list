"""Convert an application block diagram (or one frame / one block of it) into schematic sheets.

Two steps, both from the diagram JSON the editor holds (nothing needs saving first):
  check(): resolves every block to a device (a part with its pin list, or a marked placeholder), runs the design
           rules and returns issues plus the questions that decide what is drawn (supply rails, isolated grounds,
           enable pins, which pins each frame connection uses, optional parts)
  draw():  the same, with the answers applied, plus one SVG sheet per frame and a bill of external parts.

External parts (decoupling, pull-ups, DC blocking …) come only from the typical-application data in
data/schematic/*.yaml, extracted from each part's datasheet with a verbatim quote; a part without such data is
drawn without external parts and the check says so. Nothing here is a verified design.
"""

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.models import Part
from app.services import blocks

ROOT = Path(__file__).resolve().parents[2]
VOLTS = [1.8, 2.5, 3.3, 5.0, 12.0, 15.0, 20.0]

# ---- data


@lru_cache
def typical() -> dict[str, dict]:
    """Typical-application entries keyed by datasheet file name."""
    out = {}
    for f in sorted((ROOT / "data" / "schematic").glob("*.yaml")):
        for e in (yamlio.load(f.read_text()) or {}).get("datasheets") or []:
            out[e["datasheet"]] = e
    return out


@lru_cache
def datasheet_of() -> dict[str, str]:
    """Normalised MPN -> datasheet file name, from the real-data files."""
    out = {}
    for f in sorted((ROOT / "data" / "real").glob("*.yaml")):
        for p in (yamlio.load(f.read_text()) or {}).get("parts") or []:
            if p.get("datasheet"):
                out[blocks._norm_mpn(p["mpn"])] = p["datasheet"]
    return out


# ---- pins

PIN_KINDS = [
    ("nc", r"^(NC|DNC|N/C)$"),
    ("ground", r"^(GND|VSS|AGND|DGND|PGND|EP$)"),
    ("power", r"^(VDD|VCC|VIO|VBAT|VIN|VISO|VREC|VUREC|SPI_VDD|VDDL|AVDD|DVDD)"),
    ("rf", r"^(RF|ANT|RFC)"),
    ("enable", r"^(EN\d?|DISABLE|SLEEP\d?|SHDN|STBY)$"),
    ("bus", r"^(SCLK|SDATA|SCL|SDA|SPI_|MIPI|TXD|RXD|BUS|IRQ)"),
    ("config", r"^(DT|MODE|COMP|FB)$"),
    ("control", r"^(V\d$|CTRL|SEL)"),
    ("output", r"^(OUT|VO[A-Z]?$|VO$)"),
    ("input", r"^(IN|VI[A-Z]?$|VI$|PWM)"),
    ("io", r"^IO"),
]


def pin_kind(name: str) -> str:
    n = name.upper()
    for kind, rx in PIN_KINDS:
        if re.search(rx, n):
            return kind
    return "signal"


def _suffix(name: str) -> str:
    """Domain suffix of a supply or ground pin: VDD1 -> 1, VDDA -> A, GNDI -> I, VSSB -> B, VDD -> ''."""
    m = re.match(r"^(VDD|VCC|GND|VSS)([0-9A-Z]?)$", name.upper())
    return m.group(2) if m else ""


GENERIC = {  # placeholder pins by function category: left side, right side (top to bottom)
    "power": (["VIN", "EN", "GND"], ["VOUT", "PG", "GND"]),
    "rf": (["RF_IN", "CTRL", "GND"], ["RF_OUT", "VDD", "GND"]),
    "radio": (["RF_IN", "VDD", "GND"], ["AUDIO_OUT", "BUS", "GND"]),
    "isolation": (["VDD1", "IN", "GND1"], ["VDD2", "OUT", "GND2"]),
    "timing": (["VDD", "EN", "GND"], ["CLK_OUT", "NC", "GND"]),
    "processing": (["VDD", "IO", "GND"], ["BUS", "IRQ", "GND"]),
    "networking": (["VDD", "BUS", "GND"], ["IO", "IRQ", "GND"]),
    "interface": (["VDD", "IN", "GND"], ["OUT", "BUS", "GND"]),
    "memory": (["VDD", "BUS", "GND"], ["IO", "NC", "GND"]),
}
GENERIC_DEFAULT = (["VDD", "IN", "GND"], ["OUT", "CTRL", "GND"])


@dataclass
class Device:
    ref: str
    block: dict
    group: dict
    fn_label: str
    category: str = ""
    mpn: str | None = None
    manufacturer: str = ""
    pins: list[str] = field(default_factory=list)
    placeholder: bool = False
    why: str = ""
    datasheet: str | None = None
    typ: dict | None = None
    values: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.block.get("label") or self.fn_label

    def grounds(self) -> list[str]:
        """Distinct ground pin names in pin order (one per isolated domain)."""
        out = []
        for n in self.pins:
            if pin_kind(n) == "ground" and n not in out:
                out.append(n)
        return out

    def ground_of(self, pin: str) -> str:
        """The ground return of a supply pin: from the datasheet data, else by matching suffix."""
        for s in (self.typ or {}).get("supplies") or []:
            if s.get("pin") == pin and s.get("ground"):
                return s["ground"]
        gs = self.grounds()
        suf = _suffix(pin)
        for g in gs:
            if _suffix(g) == suf:
                return g
        return gs[0] if gs else "GND"

    def supply_ranges(self, pin: str) -> list[list[float]]:
        """Stated operating windows of a supply pin (some datasheets give separate 3.3 V and 5 V windows)."""
        stated = [
            [float(x) for x in s["range_v"]]
            for s in (self.typ or {}).get("supplies") or []
            if s.get("pin") == pin and s.get("range_v")
        ]
        if stated:
            return stated
        r = self.supply_range(pin)
        return [r] if r else []

    def supply_range(self, pin: str) -> list[float] | None:
        primary = (self.grounds() or [""])[0]
        if self.ground_of(pin) != primary and self.values.get("output_supply_v"):
            return [float(x) for x in self.values["output_supply_v"]]
        r = self.values.get("vdd_range_v")
        return [float(x) for x in r] if isinstance(r, list) and len(r) == 2 else None


# ---- resolve the diagram


def _in_scope(data: dict, scope: dict) -> list[tuple[dict, dict]]:
    kind = (scope or {}).get("kind", "all")
    out = []
    for g in data.get("groups") or []:
        if kind == "group" and g.get("id") != scope.get("group"):
            continue
        for b in g.get("blocks") or []:
            if kind == "block" and b.get("id") != scope.get("block"):
                continue
            out.append((g, b))
    return out


def resolve(session: Session, data: dict, scope: dict, skipped: list | None = None) -> list[Device]:
    """Devices for the blocks in scope. With scope["drawable"], blocks without a part that has a pin list are left out
    (named in `skipped`) instead of being drawn as placeholders."""
    fns = blocks.catalogue()["functions"]
    devs = []
    for i, (g, b) in enumerate(_in_scope(data, scope), 1):
        f = fns.get(b.get("fn"), {})
        d = Device(
            ref=f"U{i}", block=b, group=g, fn_label=f.get("label", b.get("fn", "?")), category=f.get("category", "")
        )
        mpn = b.get("part")
        part = None
        if mpn:
            part = session.scalar(select(Part).where(Part.mpn == mpn))
            d.mpn = mpn
            if part is not None:
                d.manufacturer = part.manufacturer.name
                d.values = {pv.key: pv.value for pv in part.params}
        if part is not None and part.pinout:
            d.pins = list(part.pinout)
            d.datasheet = datasheet_of().get(blocks._norm_mpn(mpn))
            d.typ = typical().get(d.datasheet) if d.datasheet else None
        else:
            left, right = GENERIC.get(f.get("category"), GENERIC_DEFAULT)
            d.pins = left + list(reversed(right))
            d.placeholder = True
            d.why = (
                "no part chosen"
                if not mpn
                else "part not in BizDev with parameters"
                if part is None
                else "pin list not in BizDev"
            )
        if d.placeholder and (scope or {}).get("drawable"):
            if skipped is not None:
                skipped.append(f"{d.label} ({d.why})")
            continue
        devs.append(d)
    for i, d in enumerate(devs, 1):  # number the drawn devices U1, U2 … without gaps
        d.ref = f"U{i}"
    return devs


# ---- questions and rules


def _q(qid, text, choices, default, device=None, why="", kind="choice", group="Devices"):
    return {
        "id": qid,
        "text": text,
        "choices": choices,
        "default": default,
        "device": device,
        "why": why,
        "kind": kind,
        "section": group,
    }


def _volts(v) -> str:
    return f"{v:g} V"


def _rail(v: float, iso: str) -> str:
    s = f"+{int(v)}V" if float(v).is_integer() else "+" + f"{v:g}".replace(".", "V")  # 3.3 -> +3V3, 5 -> +5V
    return f"{s}_{iso}" if iso else s


SIGNAL_KINDS = {"input", "output", "io", "bus", "rf", "control", "signal"}


def _facing(d: Device, role: str) -> list[str]:
    """Signal pins that face a connection: an isolating part (two or more grounds) receives on its first half of
    pins and sends from its second half; other parts use all their signal pins."""
    n = len(d.pins)
    idx = range(n)
    if len(d.grounds()) > 1:
        idx = range(math.ceil(n / 2)) if role == "dst" else range(math.ceil(n / 2), n)
    return list(dict.fromkeys(d.pins[i] for i in idx if pin_kind(d.pins[i]) in SIGNAL_KINDS))


def _pair_score(pa: str, pb: str, hint: str) -> int:
    ka, kb = pin_kind(pa), pin_kind(pb)
    na, nb = pa.upper(), pb.upper()
    s = 0
    if ka == "rf" and kb == "rf":
        s = 3 + (("RFC" in na) != ("RFC" in nb))
    elif ka == "bus" and kb == "bus":
        s = 4 if na == nb or {na, nb} == {"TXD", "RXD"} else 1
    elif ka == "output" and kb == "input":
        s = 3 + (na[-1:] == nb[-1:])  # OUTA -> VIA
    elif ka == "output" and kb == "control":
        s = 2
    elif ka == "io" and kb in ("io", "input", "bus"):
        s = 2
    elif ka == kb == "signal":
        s = 1
    h = hint.lower()
    if s and (
        ka == "rf"
        and ("rf" in h or "antenna" in h)
        or ka == "bus"
        and any(x in h for x in ("spi", "i2c", "mipi", "uart"))
    ):
        s += 2
    return s


def _virtual(real: Device, pin: str) -> str:
    """Pin added to a placeholder for one connection: named after the far end, so pins never merge."""
    return f"~{real.ref}_{pin}"


def proposals(a_devs: list[Device], b_devs: list[Device], hint: str, taken: set | None = None) -> tuple[list, list]:
    """Candidate pin pairs (value, text) for a connection from a_devs to b_devs, and the suggested ones."""
    scored = []
    for a in a_devs:
        for b in b_devs:
            if a.placeholder and b.placeholder:
                scored.append(
                    (2, f"{a.ref}.~{b.ref}_IN|{b.ref}.~{a.ref}_OUT", f"{a.ref} (unassigned) → {b.ref} (unassigned)")
                )
            elif a.placeholder or b.placeholder:
                ph, real = (a, b) if a.placeholder else (b, a)
                rf_side = ph.category in ("rf", "radio") or "rf" in hint.lower() or "antenna" in hint.lower()
                for p in _facing(real, "dst" if real is b else "src"):
                    k = pin_kind(p)
                    if k == "rf":
                        sc = 3 if rf_side else 1
                    else:
                        sc = 1 if rf_side else 3 if k in ("input", "output", "io", "bus", "control") else 2
                    if k == "control" and "control" in hint.lower():
                        sc += 1
                    pair = (
                        f"{ph.ref}.{_virtual(real, p)}|{real.ref}.{p}"
                        if ph is a
                        else f"{real.ref}.{p}|{ph.ref}.{_virtual(real, p)}"
                    )
                    text = f"{a.ref} {'(unassigned)' if ph is a else p} → {b.ref} {p if ph is a else '(unassigned)'}"
                    scored.append((sc, pair, text))
            else:
                for pa in _facing(a, "src"):
                    for pb in _facing(b, "dst"):
                        sc = _pair_score(pa, pb, hint)
                        if sc:
                            scored.append((sc, f"{a.ref}.{pa}|{b.ref}.{pb}", f"{a.ref} {pa} → {b.ref} {pb}"))
    scored.sort(key=lambda c: -c[0])
    scored = scored[:24]
    used, default = set(taken or ()), []
    for sc, pair, _ in scored:  # greedy: best pairs first, each real pin used once
        ends = pair.split("|")
        if sc >= 3 and not used & set(ends):
            default.append(pair)
            used |= {e for e in ends if ".~" not in e}
    if not default and scored and not used & set(scored[0][1].split("|")):
        default = [scored[0][1]]
    return [(v, t) for _, v, t in scored], default


def connections(data: dict, devs: list[Device]) -> list[dict]:
    """Every connection to decide: frame links in the selection, and neighbouring blocks inside each frame."""
    by_group: dict[str, list[Device]] = {}
    for d in devs:
        by_group.setdefault(d.group["id"], []).append(d)
    labels = {g["id"]: g.get("label", g["id"]) for g in data.get("groups") or []}
    out = []
    taken: set[str] = set()  # pins already suggested for another connection, so no pin is driven twice
    for gid, ds in by_group.items():
        for i in range(len(ds) - 1):
            cands, default = proposals([ds[i]], [ds[i + 1]], "", taken)
            taken |= {e for pair in default for e in pair.split("|") if ".~" not in e}
            out.append(
                {
                    "id": f"in:{gid}:{i}",
                    "text": f"Inside {labels.get(gid, gid)}: {ds[i].ref} {ds[i].label} → "
                    f"{ds[i + 1].ref} {ds[i + 1].label}",
                    "partial": False,
                    "cands": cands,
                    "default": default,
                }
            )
    for i, link in enumerate(data.get("links") or []):
        ga, gb, hint = (list(link) + ["", "", ""])[:3]
        da, db = by_group.get(ga, []), by_group.get(gb, [])
        if not da and not db:
            continue
        cands, default = proposals(da, db, hint or "", taken) if da and db else ([], [])
        taken |= {e for pair in default for e in pair.split("|") if ".~" not in e}
        out.append(
            {
                "id": f"link:{i}",
                "text": f"Connection {labels.get(ga, ga)} → {labels.get(gb, gb)}" + (f" ({hint})" if hint else ""),
                "partial": not (da and db),
                "cands": cands,
                "default": default,
            }
        )
    return out


def _parts_choices(d: Device) -> tuple[list, list]:
    """External parts of a device as choices; suggested: decoupling and anything the datasheet requires."""
    choices, default = [], []
    for ci, c in enumerate((d.typ or {}).get("components") or []):
        try:
            rx = re.compile(c.get("pins") or "^$")
        except re.error:
            continue
        pins = [p for p in dict.fromkeys(d.pins) if rx.search(p) and pin_kind(p) != "nc"]
        if not pins:
            continue
        val = c.get("value") or "value per datasheet"
        need = "required" if c.get("required", True) else "recommended / optional"
        text = f"{c.get('kind')} {val} on {', '.join(pins)} → {c.get('to')} ({need})" + (
            f" – {c['note'][:90]}" if c.get("note") else ""
        )
        choices.append((str(ci), text))
        decoupling = (
            c.get("kind") == "capacitor"
            and all(pin_kind(p) == "power" for p in pins)
            and c.get("to") in ("GND",) + tuple(d.grounds())
        )
        topology = re.search(r"bootstrap|dead.?time|filter|gate resist|cmti", c.get("note") or "", re.I)
        if c.get("required", True) or decoupling and not topology:
            default.append(str(ci))
    return choices, default


def questions(data: dict, devs: list[Device]) -> list[dict]:
    qs = []
    iso_grounds = []
    for d in devs:
        if d.placeholder:
            continue
        gs = d.grounds()
        for g in gs[1:]:
            iso = f"ISO_{d.ref}_{g}"
            iso_grounds.append(iso)
            qs.append(
                _q(
                    f"gnd:{d.ref}:{g}",
                    f"{d.ref} {d.mpn}: ground for the {g} side",
                    [iso, "GND"] + [x for x in iso_grounds if x != iso],
                    iso,
                    d.ref,
                    "Isolated side: keep its own ground unless another isolated circuit shares it.",
                    group="Grounds",
                )
            )
        for p in dict.fromkeys(n for n in d.pins if pin_kind(n) == "power"):
            rngs = d.supply_ranges(p)
            ok = [v for v in VOLTS if any(lo <= v <= hi for lo, hi in rngs)]
            default = 3.3 if 3.3 in ok else 5.0 if 5.0 in ok else 15.0 if 15.0 in ok else (ok[0] if ok else 3.3)
            qs.append(
                _q(
                    f"vdd:{d.ref}:{p}",
                    f"{d.ref} {d.mpn}: {p} supply",
                    [_volts(v) for v in VOLTS],
                    _volts(default),
                    d.ref,
                    "Operating range " + " or ".join(f"{lo:g}–{hi:g} V" for lo, hi in rngs)
                    if rngs
                    else "Operating range not in BizDev data",
                    group="Supplies",
                )
            )
        rules = {r["pins"]: r for r in (d.typ or {}).get("pin_rules") or [] if r.get("pins")}
        for p in dict.fromkeys(n for n in d.pins if pin_kind(n) == "enable"):
            rule = next((r for rx, r in rules.items() if re.search(rx, p)), None)
            active_low = p.upper().startswith(("DISABLE", "SLEEP", "SHDN", "STBY"))
            choices = ["tie to its supply", "tie to ground", "to the controller (net label)"]
            if rule and re.search(r"pull|float|open|unconnected", rule.get("rule", ""), re.I):
                choices.append("leave unconnected")
            default = "tie to ground" if active_low else "tie to its supply"
            qs.append(
                _q(
                    f"en:{d.ref}:{p}",
                    f"{d.ref} {d.mpn}: {p}",
                    choices,
                    default,
                    d.ref,
                    (rule.get("rule", "") + (f" (datasheet: “{rule['quote']}”)" if rule.get("quote") else ""))
                    if rule
                    else "",
                    group="Enable pins",
                )
            )
    for d in devs:
        choices, default = _parts_choices(d)
        if choices:
            qs.append(
                _q(
                    f"parts:{d.ref}",
                    f"{d.ref} {d.mpn}: external parts from {(d.typ or {}).get('doc') or d.datasheet}",
                    choices,
                    default,
                    d.ref,
                    "Suggested: decoupling and parts the datasheet requires. Tick topology parts "
                    "(bootstrap, dead time, "
                    "filters, gate resistors) only if your design uses them.",
                    kind="multi",
                    group="External parts",
                )
            )
            comps = (d.typ or {}).get("components") or []
            for ci, text in choices:
                if not comps[int(ci)].get("value"):
                    qs.append(
                        _q(
                            f"val:{d.ref}:{ci}",
                            f"{d.ref} {d.mpn}: value for {text.split(' (')[0].replace('value per datasheet ', '')}",
                            [],
                            "",
                            d.ref,
                            (comps[int(ci)].get("note") or "The datasheet gives no value.")[:300],
                            kind="text",
                            group="External parts",
                        )
                        | {"parent": f"parts:{d.ref}", "item": ci}
                    )
    for c in connections(data, devs):
        if not c["cands"]:
            continue
        qs.append(
            _q(
                c["id"],
                c["text"],
                c["cands"],
                c["default"],
                why="Suggested from pin names and sides; tick the connections to draw. "
                "Unticked pins stay as labelled open ends."
                + (" One end is outside the selection: drawn as a net label." if c["partial"] else ""),
                kind="multi",
                group="Connections",
            )
        )
    return qs


def _answer(qs_by_id: dict, answers: dict, qid: str):
    q = qs_by_id.get(qid)
    if q is None:
        return None
    a = (answers or {}).get(qid)
    if q["kind"] == "text":
        return str(a).strip()[:40] if a else q["default"]
    if q["kind"] == "multi":
        valid = {c[0] for c in q["choices"]}
        return [x for x in a if x in valid] if isinstance(a, list) else q["default"]
    return a if a in q["choices"] else q["default"]


def rules(session: Session, data: dict, devs: list[Device], qs: list[dict], answers: dict) -> list[dict]:
    """Design-rule findings: level error | warn | info, with the device ref when there is one."""
    out = []
    add = lambda level, text, ref=None: out.append({"level": level, "text": text, "device": ref})  # noqa: E731
    by_id = {q["id"]: q for q in qs}
    reqs = blocks.catalogue()["functions"]
    if not devs:
        add("error", "Nothing to draw: no block in the selection has a chosen part with a pin list. Pick parts first.")
    for d in devs:
        b = d.block
        if d.placeholder:
            add("info", f"{d.ref} {d.label}: {d.why}; drawn as a marked placeholder with generic pins.", d.ref)
        elif not d.typ:
            add(
                "warn",
                f"{d.ref} {d.mpn}: no typical-application data for its datasheet yet; drawn without external parts.",
                d.ref,
            )
        elif not d.typ.get("components"):
            add(
                "info",
                f"{d.ref} {d.mpn}: the datasheet states no external parts ({d.typ.get('doc', d.datasheet)}).",
                d.ref,
            )
        chosen = set(_answer(by_id, answers, f"parts:{d.ref}") or [])
        comps = (d.typ or {}).get("components") or []
        for ci, text in _parts_choices(d)[0]:
            c = comps[int(ci)]
            if ci in chosen and not c.get("value") and not _answer(by_id, answers, f"val:{d.ref}:{ci}"):
                add(
                    "warn",
                    f"{d.ref} {d.mpn}: the datasheet gives no value for the "
                    f"{text.split(' (')[0].replace('value per datasheet ', '')}; "
                    "enter it next to that part under External parts.",
                    d.ref,
                )
        if (b.get("qty") or 1) > 1:
            add("info", f"{d.ref} {d.label}: quantity {b['qty']}, drawn once and marked ×{b['qty']}.", d.ref)
        if d.mpn and d.values:
            fr = {r["id"]: r for r in reqs.get(b.get("fn"), {}).get("requirements") or []}
            for rid, want in ((data.get("req") or {}).get(b.get("fn")) or {}).items():
                r = fr.get(rid)
                if r is None or want in (None, "", False):
                    continue
                want = r.get("value", want) if want is True else want
                if not blocks.meets(d.values, r, want):
                    add(
                        "warn", f"{d.ref} {d.mpn} does not meet the requirement “{r.get('label', rid)}: {want}”.", d.ref
                    )
        for q in qs:
            if q["device"] != d.ref:
                continue
            a = _answer(by_id, answers, q["id"])
            if q["id"].startswith("vdd:"):
                pin = q["id"].split(":", 2)[2]
                rngs = d.supply_ranges(pin)
                v = float(a.split()[0])
                if rngs and not any(lo <= v <= hi for lo, hi in rngs):
                    add(
                        "error",
                        f"{d.ref} {d.mpn}: {pin} at {a} is outside its operating range "
                        + " or ".join(f"{lo:g}–{hi:g} V" for lo, hi in rngs)
                        + ".",
                        d.ref,
                    )
                elif not rngs:
                    add(
                        "info", f"{d.ref} {d.mpn}: {pin} range not in the data; check {a} against the datasheet.", d.ref
                    )
            if q["id"].startswith("gnd:") and a == "GND":
                add(
                    "error",
                    f"{d.ref} {d.mpn}: {q['id'].split(':')[2]} tied to system ground bridges the isolation barrier.",
                    d.ref,
                )
            if (
                q["id"].startswith("en:")
                and a == "tie to ground"
                and not q["id"].split(":")[2].upper().startswith(("DIS", "SLEEP", "SHDN", "STBY"))
            ):
                add("warn", f"{d.ref} {d.mpn}: {q['id'].split(':')[2]} tied to ground keeps that side disabled.", d.ref)
    for c in connections(data, devs):
        if c["partial"]:
            add("info", f"{c['text']}: one end is outside the selection; its pins stay as net labels.")
        elif not c["cands"]:
            add("info", f"{c['text']}: no matching signal pins; not drawn.")
        elif not _answer(by_id, answers, c["id"]):
            add("warn", f"{c['text']}: no pins ticked; not drawn.")
    for pin_net in _shorts(devs, qs, answers):
        add("error", pin_net)
    return out


# ---- nets


def build(devs: list[Device], qs: list[dict], answers: dict) -> tuple[dict, dict]:
    """Net name per (ref, pin), and the supply net per (ref, pin) for decoupling."""
    by_id = {q["id"]: q for q in qs}
    devmap = {d.ref: d for d in devs}
    net: dict[tuple[str, str], str] = {}
    gnd_net: dict[tuple[str, str], str] = {}
    for d in devs:
        gs = d.grounds()
        for i, g in enumerate(gs):
            n = (
                "GND"
                if i == 0 or d.placeholder
                else (_answer(by_id, answers, f"gnd:{d.ref}:{g}") or f"ISO_{d.ref}_{g}")
            )
            gnd_net[(d.ref, g)] = n
            net[(d.ref, g)] = n
        for p in d.pins:
            k = pin_kind(p)
            if k == "power":
                g = d.ground_of(p)
                iso = gnd_net.get((d.ref, g), "GND")
                if d.placeholder:
                    net[(d.ref, p)] = f"{p}_{d.ref}"
                else:
                    v = _answer(by_id, answers, f"vdd:{d.ref}:{p}") or "3.3 V"
                    net[(d.ref, p)] = _rail(float(v.split()[0]), "" if iso == "GND" else iso)
    for d in devs:
        for p in dict.fromkeys(n for n in d.pins if pin_kind(n) == "enable"):
            a = _answer(by_id, answers, f"en:{d.ref}:{p}")
            if a == "tie to its supply":
                g = gnd_net.get((d.ref, _enable_ground(d, p)), "GND")
                sup = next(
                    (
                        net[(d.ref, s)]
                        for s in d.pins
                        if pin_kind(s) == "power" and gnd_net.get((d.ref, d.ground_of(s))) == g
                    ),
                    None,
                )
                net[(d.ref, p)] = sup or f"{p}_{d.ref}"
            elif a == "tie to ground":
                net[(d.ref, p)] = gnd_net.get((d.ref, _enable_ground(d, p)), "GND")
            elif a == "leave unconnected":
                net[(d.ref, p)] = ""
    for q in qs:
        if not q["id"].startswith(("link:", "in:")):
            continue
        for pair in _answer(by_id, answers, q["id"]) or []:
            ends = [x.split(".", 1) for x in pair.split("|")]
            if any(r not in devmap for r, _ in ends):
                continue
            for r, p in ends:  # a placeholder gets one pin per connection
                if p.startswith("~"):
                    devmap[r].pins.append(p)
            real = next(((r, p) for r, p in ends if not p.startswith("~")), None)
            name = next((net[tuple(e)] for e in ends if net.get(tuple(e))), None) or (
                f"{real[0]}_{real[1]}" if real else f"{ends[0][0]}_{ends[1][0]}"
            )
            for r, p in ends:
                net[(r, p)] = name
    for d in devs:  # a placeholder's generic signal pins give way to its connection pins
        if d.placeholder and any(p.startswith("~") for p in d.pins):
            d.pins = [p for p in d.pins if p.startswith("~") or pin_kind(p) in ("power", "ground")]
    return net, gnd_net


def _shorts(devs: list[Device], qs: list[dict], answers: dict) -> list[str]:
    """Ticked connections that join two driven outputs, or the same pin to two different pins."""
    by_id = {q["id"]: q for q in qs}
    seen: dict[str, str] = {}
    out = []
    for q in qs:
        if not q["id"].startswith(("link:", "in:")):
            continue
        for pair in _answer(by_id, answers, q["id"]) or []:
            a, b = pair.split("|")
            for x, y in ((a, b), (b, a)):
                if ".~" in x:
                    continue
                if (
                    x in seen
                    and seen[x] != y
                    and ".~" not in seen[x]
                    and pin_kind(x.split(".", 1)[1]) == "output"
                    and pin_kind(y.split(".", 1)[1]) == "output"
                ):
                    out.append(f"{x.replace('.', ' ')} would drive the same net as another output: untick one.")
                seen.setdefault(x, y)
            if pin_kind(a.split(".", 1)[1]) == "output" and pin_kind(b.split(".", 1)[1]) == "output":
                out.append(
                    f"{a.replace('.', ' ')} and {b.replace('.', ' ')} are both outputs: "
                    "connecting them shorts two drivers."
                )
    return out


def _enable_ground(d: Device, pin: str) -> str:
    suf = re.sub(r"^(EN|DISABLE|SLEEP)", "", pin.upper())
    for g in d.grounds():
        if _suffix(g) == suf:
            return g
    return (d.grounds() or ["GND"])[0]


def components(devs: list[Device], net: dict, gnd_net: dict, answers: dict, qs: list[dict]) -> list[dict]:
    """External parts per device pin, numbered C1…, R1…, from the typical-application data."""
    by_id = {q["id"]: q for q in qs}
    prefix = {
        "capacitor": "C",
        "resistor": "R",
        "ferrite": "FB",
        "inductor": "L",
        "diode": "D",
        "tvs": "D",
        "zener": "D",
        "crystal": "Y",
    }
    seq: dict[str, int] = {}
    out = []
    for d in devs:
        if d.placeholder or not d.typ:
            continue
        chosen = set(_answer(by_id, answers, f"parts:{d.ref}") or [])
        for ci, c in enumerate(d.typ.get("components") or []):
            if str(ci) not in chosen:
                continue
            try:
                rx = re.compile(c.get("pins") or "^$")
            except re.error:
                continue
            for p in dict.fromkeys(d.pins):
                if not rx.search(p) or pin_kind(p) == "nc":
                    continue
                to = c.get("to", "GND")
                if to == "GND":
                    other = gnd_net.get((d.ref, d.ground_of(p)), "GND")
                elif to == "VDD":
                    other = net.get((d.ref, p), "VDD")
                elif to in d.pins:
                    other = net.get((d.ref, to)) or to
                else:
                    other = to
                pre = prefix.get(c.get("kind"), "X")
                seq[pre] = seq.get(pre, 0) + 1
                out.append(
                    {
                        "ref": f"{pre}{seq[pre]}",
                        "kind": c.get("kind"),
                        "value": c.get("value") or _answer(by_id, answers, f"val:{d.ref}:{ci}") or "",
                        "device": d.ref,
                        "pin": p,
                        "series": bool(c.get("series")),
                        "to": other,
                        "required": c.get("required", True),
                        "note": c.get("note") or "",
                        "doc": d.typ.get("doc") or d.datasheet,
                        "page": c.get("page"),
                        "quote": c.get("quote") or "",
                    }
                )
    return out


# ---- drawing

INK, MUTED, NET, GNDC, WARN = "#1d2228", "#6b7280", "#1f5fa8", "#3f6f3a", "#c0262d"
PIT, BOXW, STUB = 58, 176, 26


def _t(x, y, s, size=11, color=INK, anchor="start", weight="normal", italic=False):
    st = ' font-style="italic"' if italic else ""
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
        f'font-weight="{weight}"{st}>{escape(str(s))}</text>'
    )


def _ln(d, color=INK, w=1.6, dash=""):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<path d="{d}" stroke="{color}" stroke-width="{w}" fill="none"{da}/>'


def _gnd(x, y, name):
    s = _ln(f"M{x} {y}v8M{x - 9} {y + 8}h18M{x - 6} {y + 12}h12M{x - 3} {y + 16}h6", GNDC, 1.6)
    if name != "GND":
        s += _t(x, y + 28, name, 9, GNDC, "middle")
    return s


def _shunt(x, y, c, d):
    """Component from the wire at (x, y) down to its other net; label on the outward side."""
    k = c["kind"]
    s = f'<circle cx="{x}" cy="{y}" r="2.6" fill="{INK}"/>'
    top, bot = y + 7, y + 25
    if k == "capacitor":
        s += _ln(f"M{x} {y}V{y + 13}M{x - 8} {y + 13}h16M{x - 8} {y + 18}h16M{x} {y + 18}V{bot + 4}")
    elif k in ("diode", "tvs", "zener"):
        s += _ln(f"M{x} {y}V{top}M{x - 7} {top}h14M{x} {top}l-7 12h14z M{x} {top + 12}V{bot + 4}")
    else:
        fill = INK if k == "ferrite" else "#fff"
        s += (
            _ln(f"M{x} {y}V{top}M{x} {bot}V{bot + 4}")
            + f'<rect x="{x - 5}" y="{top}" width="10" height="{bot - top}" '
            + f'fill="{fill}" stroke="{INK}" stroke-width="1.4"/>'
        )
    end = bot + 4
    if c["to"].startswith(("GND", "ISO_")):
        s += _gnd(x, end, "GND")
        if c["to"] != "GND":
            s += _t(x + 11, end + 17, c["to"].replace("ISO_", "").replace("_", " "), 8, GNDC)
    else:
        s += _t(x, end + 12, c["to"], 9, NET, "middle")
    lx = x + 9 * d if d > 0 else x - 9
    anchor = "start" if d > 0 else "end"
    opt = "" if c["required"] else " rec."
    s += _t(lx, y + 15, c["ref"] + opt, 10, INK if c["required"] else MUTED, anchor, "bold")
    s += _t(lx, y + 26, c["value"] or "value: see datasheet", 9, INK if c["value"] else WARN, anchor)
    return s


def _series(x, y, c, d):
    """Component inline on the wire from x outward (d = ±1), 56 px long."""
    a, b = x + 14 * d, x + 42 * d
    lo, hi = min(a, b), max(a, b)
    k = c["kind"]
    if k == "capacitor":
        m = (a + b) / 2
        s = _ln(f"M{x} {y}H{m - 3}M{m - 3} {y - 8}v16M{m + 3} {y - 8}v16M{m + 3} {y}H{x + 56 * d}")
    else:
        fill = INK if k == "ferrite" else "#fff"
        s = (
            _ln(f"M{x} {y}H{a}M{b} {y}H{x + 56 * d}")
            + f'<rect x="{lo}" y="{y - 5}" width="{hi - lo}" height="10" '
            + f'fill="{fill}" stroke="{INK}" stroke-width="1.4"/>'
        )
    s += _t(
        (a + b) / 2, y - 11, f"{c['ref']} {c['value'] or '?'}" + ("" if c["required"] else " rec."), 9, INK, "middle"
    )
    return s


def _flag(x, y, name, d, color=NET):
    w = max(34, 6.3 * len(name) + 14)
    if d > 0:
        p = f"M{x} {y}l7 -8h{w}v16h-{w}z"
        tx = x + 7 + w / 2
    else:
        p = f"M{x} {y}l-7 -8h-{w}v16h{w}z"
        tx = x - 7 - w / 2
    return f'<path d="{p}" fill="#eef3fa" stroke="{color}" stroke-width="1.2"/>' + _t(
        tx, y + 4, name, 10, color, "middle"
    )


def _side_extent(d: Device, comps_by_pin: dict, pins_idx: list[int]) -> int:
    w = 0
    for i in pins_idx:
        cs = comps_by_pin.get((d.ref, d.pins[i]), [])
        w = max(w, STUB + 56 * sum(c["series"] for c in cs) + 48 * sum(not c["series"] for c in cs) + 40 + 130)
    return w


def draw_device(d: Device, net: dict, comps: list[dict], x0: float, y0: float) -> tuple[str, float, float]:
    """One device with its pins, external parts and net labels; returns (svg, width, height)."""
    n = len(d.pins)
    nl = math.ceil(n / 2)
    left = list(range(nl))
    right = [n - 1 - j for j in range(n - nl)]
    cb: dict[tuple[str, str], list[dict]] = {}
    for c in comps:
        if c["device"] == d.ref:
            cb.setdefault((d.ref, c["pin"]), []).append(c)
    wl, wr = _side_extent(d, cb, left), _side_extent(d, cb, right)
    bx0 = x0 + wl
    bx1 = bx0 + BOXW
    rows = max(len(left), len(right))
    top = y0 + 40
    h = rows * PIT + 16
    s = []
    dash = "6 4" if d.placeholder else ""
    s.append(
        f'<rect x="{bx0}" y="{top}" width="{BOXW}" height="{h}" rx="4" fill="#fff" '
        f'stroke="{MUTED if d.placeholder else INK}" stroke-width="2"'
        + (f' stroke-dasharray="{dash}"' if dash else "")
        + "/>"
    )
    title = (
        f"{d.ref} · {d.mpn}"
        if d.mpn and not d.placeholder
        else f"{d.ref} · {'unassigned' if not d.mpn else d.mpn + ' (generic pins)'}"
    )
    qty = (d.block.get("qty") or 1) > 1
    s.append(
        _t(
            bx0 + BOXW / 2,
            y0 + 16,
            title + (f"  ×{d.block['qty']}" if qty else ""),
            13,
            WARN if d.placeholder else INK,
            "middle",
            "bold",
        )
    )
    s.append(
        _t(bx0 + BOXW / 2, y0 + 31, d.label + (f" · {d.manufacturer}" if d.manufacturer else ""), 10, MUTED, "middle")
    )
    drawn: set[str] = set()
    for side, idxs in ((-1, left), (1, right)):
        for row, i in enumerate(idxs):
            p = d.pins[i]
            y = top + 22 + row * PIT
            xb = bx0 if side < 0 else bx1
            k = pin_kind(p)
            col = MUTED if d.placeholder else INK
            shown = p[1:].replace("_", " ", 1) if p.startswith("~") else p  # placeholder pin: named after the far end
            s.append(_t(xb - 8 * side, y + 4, shown, 10, col, "end" if side > 0 else "start", italic=d.placeholder))
            if not d.placeholder:
                s.append(_t(xb + 12 * side, y - 5, str(i + 1), 8, MUTED, "middle"))
            x = xb + STUB * side
            s.append(_ln(f"M{xb} {y}H{x}"))
            name = net.get((d.ref, p))
            if k == "nc":
                s.append(_ln(f"M{x - 4} {y - 4}l8 8M{x + 4} {y - 4}l-8 8", MUTED, 1.4))
                continue
            if k == "ground":
                s.append(_ln(f"M{x} {y}H{x + 10 * side}"))
                s.append(_gnd(x + 10 * side, y, name or "GND"))
                continue
            cs = [] if p in drawn else cb.get((d.ref, p), [])  # a pin name used twice gets its parts once
            drawn.add(p)
            chain = [c for c in cs if c["series"]]
            if k == "power":  # decoupling first, at the pin; a series chain (e.g. bootstrap) then leads to its own net
                for c in [c for c in cs if not c["series"]]:
                    s.append(_ln(f"M{x} {y}H{x + 24 * side}"))
                    x += 24 * side
                    s.append(_shunt(x, y, c, side))
                    s.append(_ln(f"M{x} {y}H{x + 24 * side}"))
                    x += 24 * side
                if chain:
                    s.append(_ln(f"M{x} {y}H{x + 16 * side}"))
                    x += 16 * side
                    s.append(f'<circle cx="{x}" cy="{y}" r="2.6" fill="{INK}"/>')
                    s.append(_t(x, y - 8, name or "", 9, NET, "middle"))
                    for c in chain:
                        s.append(_series(x, y, c, side))
                        x += 56 * side
                    name = chain[-1]["to"]
            else:
                for c in chain:
                    s.append(_series(x, y, c, side))
                    x += 56 * side
                for c in [c for c in cs if not c["series"]]:
                    s.append(_ln(f"M{x} {y}H{x + 24 * side}"))
                    x += 24 * side
                    s.append(_shunt(x, y, c, side))
                    s.append(_ln(f"M{x} {y}H{x + 24 * side}"))
                    x += 24 * side
            s.append(_ln(f"M{x} {y}H{x + 14 * side}"))
            x += 14 * side
            if name == "":
                s.append(_t(x + 4 * side, y + 4, "unconnected", 9, MUTED, "start" if side > 0 else "end", italic=True))
            elif name and name.startswith(("GND", "ISO_")):
                s.append(_gnd(x, y, name))
            elif name:
                s.append(_flag(x, y, name, side))
            else:
                s.append(_flag(x, y, f"{d.ref}_{p}", side, MUTED))
    return "".join(s), wl + BOXW + wr, 40 + h + 34


def draw_sheets(data: dict, devs: list[Device], net: dict, comps: list[dict], title: str) -> list[dict]:
    order = []
    for d in devs:
        if d.group["id"] not in order:
            order.append(d.group["id"])
    sheets = []
    MAXW = 1500
    for si, gid in enumerate(order, 1):
        gdevs = [d for d in devs if d.group["id"] == gid]
        parts, x, y, rowh, W = [], 30.0, 70.0, 0.0, 1180.0
        for d in gdevs:
            svg, w, h = draw_device(d, net, comps, 0, 0)
            if x > 30 and x + w > MAXW:
                x, y, rowh = 30.0, y + rowh + 20, 0.0
            parts.append(f'<g transform="translate({x:.0f},{y:.0f})">{svg}</g>')
            x += w + 30
            rowh = max(rowh, h)
            W = max(W, x)
        H = y + rowh + 60
        glabel = gdevs[0].group.get("label", gid)
        head = _t(30, 32, f"{glabel}", 17, INK, weight="bold") + _t(
            30, 52, f"{title} · sheet {si} of {len(order)} · same net names connect across sheets", 11, MUTED
        )
        foot = _t(
            30,
            H - 18,
            "External parts from the parts' datasheets (see the parts list for source and quote). "
            "Placeholders are dashed; 'rec.' = recommended or optional in the datasheet. "
            "For discussion – not a verified design.",
            10,
            MUTED,
        )
        frame = f'<rect x="8" y="8" width="{W - 16:.0f}" height="{H - 16:.0f}" fill="none" stroke="#c9ced6"/>'
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" '
            f'font-family="Helvetica, Arial, sans-serif"><rect width="100%" height="100%" fill="#fff"/>'
            f"{frame}{head}{''.join(parts)}{foot}</svg>"
        )
        sheets.append({"title": glabel, "svg": svg})
    return sheets


# ---- entry points


def check(session: Session, data: dict, scope: dict, answers: dict | None = None) -> dict:
    skipped: list[str] = []
    devs = resolve(session, data, scope, skipped)
    qs = questions(data, devs)
    issues = rules(session, data, devs, qs, answers or {})
    return {
        "skipped": skipped,
        "devices": [
            {
                "ref": d.ref,
                "label": d.label,
                "mpn": d.mpn,
                "placeholder": d.placeholder,
                "pins": len(d.pins),
                "datasheet": d.datasheet,
                "typical": bool(d.typ),
            }
            for d in devs
        ],
        "questions": qs,
        "issues": issues,
        "errors": sum(i["level"] == "error" for i in issues),
    }


def draw(session: Session, data: dict, scope: dict, answers: dict | None = None, title: str = "") -> dict:
    answers = answers or {}
    out = check(session, data, scope, answers)
    devs = resolve(session, data, scope)
    qs = out["questions"]
    net, gnd_net = build(devs, qs, answers)
    comps = components(devs, net, gnd_net, answers, qs)
    out["sheets"] = draw_sheets(data, devs, net, comps, title or "Block diagram")
    out["bom"] = comps
    return out
