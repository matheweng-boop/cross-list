"""Repository hygiene: nothing local to one machine may be committed."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ONLY = (".venv", "venv", "var", "node_modules", ".pytest_cache", ".ruff_cache")


def _tracked() -> list[tuple[str, str]]:
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files", "-s"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [(line.split()[0], line.split("\t", 1)[1]) for line in out.splitlines()]


def test_no_symlinks_committed():
    # a committed link (e.g. .venv -> another checkout) replaces the real folder on merge and breaks deploys
    links = [path for mode, path in _tracked() if mode == "120000"]
    assert not links, f"symbolic links are committed: {links}"


def test_no_local_environment_committed():
    bad = [path for _, path in _tracked() if path.split("/")[0] in LOCAL_ONLY]
    assert not bad, f"local environment files are committed: {bad[:10]}"
