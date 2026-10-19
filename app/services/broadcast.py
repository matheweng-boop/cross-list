"""Skyworks broadcast radio ICs (Si46xx / Si47xx) for the block-diagram configurator.

Each file in data/broadcast/devices/ is transcribed from one data short or product summary
(format: data/broadcast/SCHEMA.md). A file can describe several orderable parts that share a
package and pinout but differ in standards or licensing; ``catalog()`` flattens them to one
entry per part number.
"""

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import PROJECT_ROOT

DEVICES_DIR = PROJECT_ROOT / "data" / "broadcast" / "devices"
ROLES = {
    "tuner": "Tuner (I/Q to a coprocessor)",
    "receiver": "Single-chip receiver",
    "coprocessor": "Digital radio coprocessor (demod)",
}
STANDARDS = ("AM", "FM", "LW", "SW", "WB", "RDS", "HD", "DAB", "DMB", "DRM", "CDR")


def _load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text()) or {}
    doc["doc"] = path.stem
    return doc


@lru_cache
def documents() -> list[dict]:
    return [_load(p) for p in sorted(DEVICES_DIR.glob("*.yaml"))]


def catalog() -> list[dict]:
    """One entry per orderable part, carrying its document's package, supplies and pins."""
    out = []
    for doc in documents():
        for part in doc.get("parts") or []:
            out.append({
                "mpn": part["mpn"],
                "family": doc.get("family"),
                "role": part.get("role") or doc.get("role"),
                "description": doc.get("description"),
                "doc": doc["doc"],
                "source": doc.get("source") or {},
                "package": doc.get("package") or {},
                "aec_q100": doc.get("aec_q100"),
                "supplies": doc.get("supplies") or [],
                "features": doc.get("features") or [],
                "tuners": part.get("tuners"),
                "channels": part.get("channels"),
                "analog": part.get("analog") or [],
                "digital_decode": part.get("digital_decode") or [],
                "digital_iq": part.get("digital_iq") or [],
                "options": part.get("options") or [],
                "note": part.get("note"),
                "pins": pins_of(doc),
                "numbered": bool(doc.get("pins")),
            })  # fmt: skip
    return sorted(out, key=lambda d: (list(ROLES).index(d["role"]) if d["role"] in ROLES else 9, d["mpn"]))


def pins_of(doc: dict) -> list[dict]:
    """The package pins; for a document without a pinout, its block-diagram signals.

    Signals have no pin number: they get keys from 1001 up (the editor identifies pins by
    ``n``) and an empty ``num`` so no number is displayed."""
    if doc.get("pins"):
        return [{**p, "num": p["n"]} for p in doc["pins"]]
    return [{**sig, "n": 1001 + i, "num": ""} for i, sig in enumerate(doc.get("signals") or [])]


@lru_cache
def configurations() -> dict:
    """Configurator presets (data/broadcast/configurations.yaml): regions, hardware configurations
    (what is populated and how it is wired) and software listening modes (what each tuner and
    demodulator channel does)."""
    path = DEVICES_DIR.parent / "configurations.yaml"
    return yaml.safe_load(path.read_text()) if path.exists() else {"regions": [], "hardware": [], "software": []}


@lru_cache
def guidance() -> dict:
    """Application guidance from the user (data/broadcast/guidance.yaml), kept apart from the
    data-brief facts: clock tree, ZIF / CLKO loading, licences, extra parts on named pins."""
    path = DEVICES_DIR.parent / "guidance.yaml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


@lru_cache
def explanations() -> dict:
    """Short explanations with an example or trade-off, shown in the editor (data/broadcast/explanations.yaml)."""
    path = DEVICES_DIR.parent / "explanations.yaml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def standards_of(device: dict) -> list[str]:
    have = set(device["analog"]) | set(device["digital_decode"]) | set(device["digital_iq"])
    return [s for s in STANDARDS if s in have]
