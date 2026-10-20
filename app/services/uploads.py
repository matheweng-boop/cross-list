"""Uploaded pictures, block diagrams, documents and explanations (Data management > Uploads).

Files go to <data dir>/uploads/ (the persistent disk on the server) under a random name; the type is checked from
the file's first bytes, not from its name. Only raster images and PDF are accepted: SVG and HTML can carry scripts.
"""

import secrets
from pathlib import Path

from app.config import get_settings

KINDS = {"picture": "Picture", "block_diagram": "Block diagram", "document": "Document", "explanation": "Explanation"}
STATUSES = {"new": "New", "used": "Used", "archived": "Archived"}
MAX_BYTES = 10 * 1024 * 1024
_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"%PDF-", "application/pdf", ".pdf"),
]


def upload_dir() -> Path:
    path = get_settings().data_dir / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sniff(head: bytes) -> tuple[str, str] | None:
    """(content type, extension) from the first bytes, or None when the file is not an accepted type."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return next(((ct, ext) for magic, ct, ext in _MAGIC if head.startswith(magic)), None)


def store(data: bytes) -> tuple[str, str]:
    """Save the bytes under a random name; returns (stored name, content type). Raises ValueError when refused."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    kind = sniff(data[:16])
    if kind is None:
        raise ValueError("Only PNG, JPEG, GIF, WebP pictures and PDF documents can be uploaded")
    ct, ext = kind
    name = secrets.token_hex(12) + ext
    (upload_dir() / name).write_bytes(data)
    return name, ct


def path_of(name: str) -> Path | None:
    """The stored file, only for names this module created (no path tricks)."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    p = upload_dir() / name
    return p if p.is_file() else None


def remove(name: str | None) -> None:
    p = path_of(name or "")
    if p:
        p.unlink()
