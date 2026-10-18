"""Offline datasheet text extraction: revision, revision date, a few key parameters.

Datasheet layouts vary widely, so everything here produces *suggestions* that a
person reviews before they are stored.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

MONTHS = {
    m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)
}


def _month(name: str) -> int:
    return MONTHS[name.lower()[:3]]


_MONTH_RE = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

# TI style:  "SLLSEO9D – SEPTEMBER 2018 – REVISED MAY 2023"
TI_RE = re.compile(
    r"\b([A-Z]{4}[A-Z0-9]{2,4}?)([A-Z])?\s*[–—-]\s*" + _MONTH_RE + r"\s+(\d{4})"
    r"(?:\s*[–—-]\s*REVISED\s+" + _MONTH_RE + r"\s+(\d{4}))?",
    re.IGNORECASE,
)
REV_RE = re.compile(r"\bRev(?:ision)?\.?\s*:?\s*([0-9]+(?:\.[0-9]+)?|[A-Z]{1,2})\b(?![a-z])")
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (
        re.compile(r"\b(\d{1,2})[ -]" + _MONTH_RE + r"[ -,]*(\d{4})\b", re.I),
        lambda m: date(int(m[3]), _month(m[2]), int(m[1])),
    ),
    (re.compile(_MONTH_RE + r"\.?\s+(\d{1,2}),\s*(\d{4})\b", re.I), lambda m: date(int(m[3]), _month(m[1]), int(m[2]))),
    (re.compile(_MONTH_RE + r"\.?\s+(\d{4})\b", re.I), lambda m: date(int(m[2]), _month(m[1]), 1)),
    (re.compile(r"\b(\d{1,2})/(\d{4})\b"), lambda m: date(int(m[2]), int(m[1]), 1)),
]


@dataclass
class Suggestion:
    key: str
    value: object
    page: int
    snippet: str


@dataclass
class DatasheetInfo:
    pages: list[str]
    revision: str | None = None
    revision_date: date | None = None
    first_issue_date: date | None = None
    suggestions: list[Suggestion] = field(default_factory=list)


def extract_pages(path: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def find_date(text: str) -> date | None:
    best = None
    for rx, conv in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                d = conv(m)
            except (ValueError, KeyError):
                continue
            pos = m.start()
            if best is None or pos < best[0]:
                best = (pos, d)
            break
    return best[1] if best else None


def detect_revision(pages: list[str]) -> tuple[str | None, date | None, date | None]:
    """Return (revision, revision_date, first_issue_date)."""
    # Revision info is usually on the first page or in a page footer / last page.
    candidates = [pages[0]] + pages[-1:] if pages else []
    for text in candidates:
        m = TI_RE.search(text)
        if m and (m.group(2) or m.group(5)):
            first = date(int(m.group(4)), _month(m.group(3)), 1)
            revised = date(int(m.group(6)), _month(m.group(5)), 1) if m.group(5) else first
            return (m.group(2) or "original"), revised, first
    for text in candidates:
        m = REV_RE.search(text)
        if m:
            window = text[m.end() : m.end() + 60]
            return m.group(1), find_date(window) or find_date(text), None
    return None, None, None


PARAM_PATTERNS = [
    ("isolation_rating_kvrms", re.compile(r"(\d(?:\.\d+)?)\s*kV\s*RMS", re.I), lambda s: float(s)),
    ("isolation_rating_kvrms", re.compile(r"\b(\d{4})\s*V\s*RMS\b", re.I), lambda s: float(s) / 1000),
    ("cmti_kv_us", re.compile(r"(\d{2,3})\s*kV/[µu]s", re.I), lambda s: float(s)),
    ("data_rate_mbps", re.compile(r"(\d{1,4})\s*Mbps", re.I), lambda s: float(s)),
]


def suggest_params(pages: list[str]) -> list[Suggestion]:
    out, seen = [], set()
    for page_no, text in enumerate(pages, 1):
        for key, rx, conv in PARAM_PATTERNS:
            if key in seen:
                continue
            m = rx.search(text)
            if m:
                seen.add(key)
                snippet = text[max(0, m.start() - 40) : m.end() + 40].replace("\n", " ")
                out.append(Suggestion(key, conv(m.group(1)), page_no, snippet))
    return out


def analyze(path: Path) -> DatasheetInfo:
    pages = extract_pages(path)
    rev, rev_date, first = detect_revision(pages)
    return DatasheetInfo(pages, rev, rev_date, first, suggest_params(pages))
