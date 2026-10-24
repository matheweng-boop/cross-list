"""A logo for the header band of a shareable page (owner, 24 Oct 2026: "in case I get permission to a company logo").

PNG, JPG or SVG up to 1 MB. The type is read from the file's content, never its name. An SVG is rebuilt from its
parsed elements without scripts, event handlers, external references, styles that load anything, or embedded HTML;
a document type or entity declaration is refused outright. The file is stored like every upload (Data management >
Uploads, files under <data dir>/uploads/) with the topic LOGO_TOPIC; only uploads with that topic are served at
/shareable/logo/<id>, as an image with a strict content-security policy.
"""

import re
import secrets
import xml.etree.ElementTree as ET

from sqlalchemy.orm import Session

from app.models import Upload
from app.services import uploads

LOGO_TOPIC = "shareable-logo"
MAX_BYTES = 1024 * 1024
SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "{http://www.w3.org/1999/xlink}href"
_DROP = {"script", "foreignObject", "iframe", "object", "embed", "audio", "video", "style", "handler", "listener",
         "animate", "set", "animateMotion", "animateTransform"}  # fmt: skip
_URL = re.compile(r"url\s*\(\s*['\"]?\s*(?!#)", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sanitize_svg(data: bytes) -> bytes:
    """A safe copy of an SVG, or ValueError when it is not one we can make safe."""
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise ValueError("This SVG declares a document type or entities; save it as a plain SVG or a PNG.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError("This is not a readable SVG file.") from e
    if _local(root.tag) != "svg":
        raise ValueError("This is not an SVG image.")
    parents = {c: p for p in root.iter() for c in p}
    for el in list(root.iter()):
        if el is not root and _local(el.tag) in _DROP:
            parents[el].remove(el)
            continue
        for name in list(el.attrib):
            value = el.attrib[name]
            local = _local(name).lower()
            ref = local == "href" or name == XLINK
            if (
                local.startswith("on")
                or (ref and not value.strip().startswith("#"))
                or "javascript:" in value.lower()
                or _URL.search(value)
                or local in ("src", "action", "formaction")
            ):
                del el.attrib[name]  # fmt: skip
    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="utf-8")


def kind_of(data: bytes) -> str:
    """'png', 'jpeg' or 'svg' from the content; '' when it is none of them."""
    sniffed = uploads.sniff(data[:16])
    if sniffed and sniffed[0] in ("image/png", "image/jpeg"):
        return sniffed[0].split("/")[1]
    text = data.lstrip(b"\xef\xbb\xbf \t\r\n")[:2048].lower()
    if (text.startswith(b"<?xml") or text.startswith(b"<svg") or text.startswith(b"<!--")) and b"<svg" in text:
        return "svg"
    return ""


def store(session: Session, data: bytes, original: str, author: str) -> Upload:
    """Check, clean and store a logo; ValueError with a plain message when refused."""
    if not data:
        raise ValueError("Choose a PNG, JPG or SVG file first.")
    if len(data) > MAX_BYTES:
        raise ValueError("The logo is larger than 1 MB; use a smaller file.")
    kind = kind_of(data)
    if not kind:
        raise ValueError("Only PNG, JPG or SVG files can be used as a logo.")
    if kind == "svg":
        data = sanitize_svg(data)
        name = f"{secrets.token_hex(16)}.svg"
        (uploads.upload_dir() / name).write_bytes(data)
        ctype = "image/svg+xml"
    else:
        name, ctype = uploads.store(data)
    up = Upload(title="Technology overview logo", kind="picture", topic=LOGO_TOPIC, file_name=name,
                original_name=(original or "logo")[:200], content_type=ctype, size=len(data), author=author[:100],
                status="used", note="Header logo of the Technology overview (only with permission)")  # fmt: skip
    session.add(up)
    session.flush()
    return up


def get(session: Session, upload_id: int) -> Upload | None:
    up = session.get(Upload, upload_id)
    return up if up is not None and up.topic == LOGO_TOPIC and up.file_name else None
