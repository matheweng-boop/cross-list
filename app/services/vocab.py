"""One vocabulary for function ids (data/blocks/functions.yaml): the label every page shows, its plural, the other
ids source files use for the same function (rf_pa, rf_filter ...), and the functions a part is also offered for.
Every page that names a function goes through here, so one function never shows under two names."""

import re
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "blocks" / "functions.yaml"


@lru_cache
def functions() -> dict[str, dict]:
    return (yamlio.load(FILE.read_text()) or {}).get("functions") or {}


@lru_cache
def _aliases() -> dict[str, str]:
    return {a: fid for fid, f in functions().items() for a in f.get("aliases") or []}


def canonical(fn: str | None) -> str | None:
    return _aliases().get(fn, fn) if fn else fn


def fills(fn: str | None, also=()) -> list[str]:
    """Canonical functions a catalogue part fills: the one its source names first, then its `also` list, each with
    the functions it also fills (a CATV amplifier is offered for gain-block sockets too); each once."""
    out: list[str] = []
    for f in (fn, *also):
        f = canonical(f)
        if f:
            out += [f, *((functions().get(f) or {}).get("fills") or [])]
    return list(dict.fromkeys(out))


def _plural_word(w: str) -> str:
    if re.search(r"(s|x|ch|sh)$", w):
        return w + "es"
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    return w + "s"


def _plural(label: str) -> str:
    """'RF filter (SAW / BAW)' -> 'RF filters (SAW / BAW)', 'Diplexer / multiplexer' -> 'Diplexers / multiplexers'."""
    head, sep, tail = label.partition(" (")
    parts = [re.sub(r"(\S+)$", lambda m: _plural_word(m.group(1)), p.strip()) for p in head.split(" / ")]
    return " / ".join(parts) + sep + tail


def fn_label(fn: str | None, plural: bool = False) -> str:
    """The label of a function id (or of an alias); an unknown id is shown as words, never as snake_case."""
    f = functions().get(canonical(fn) or "")
    label = f["label"] if f else str(fn or "").replace("_", " ")
    if not plural:
        return label
    return (f or {}).get("plural") or _plural(label)


def family_title(family: str) -> str:
    """Title of a matching-rules family ('gate_driver' -> 'Isolated gate drivers')."""
    from app.matching.rules import load_all_rules

    r = load_all_rules().get(family)
    return r.title if r else family.replace("_", " ")
