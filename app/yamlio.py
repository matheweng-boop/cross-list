"""Reading YAML data files with libyaml's C loader when it is installed (several times faster on the multi-MB
catalogues than the pure-Python loader; same safe subset of YAML)."""

from pathlib import Path

import yaml

Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def load(stream):
    return yaml.load(stream, Loader=Loader)


def folder_signature(folder: Path) -> tuple[tuple[str, float], ...]:
    """The folder's YAML files (not those starting with _) with their modification times: a cache key that changes
    when a file is added, removed or edited."""
    return tuple(sorted((str(p), p.stat().st_mtime) for p in folder.glob("*.yaml") if not p.name.startswith("_")))
