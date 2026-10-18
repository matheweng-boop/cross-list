"""Skyworks application notes for the families Cross List covers (isolation and RF switches).

fetch()  lists every document from the site search, keeps the relevant application notes and
         downloads their PDFs to var/appnotes/ (resumable)
build()  extracts the text page by page into data/appnotes.jsonl, which the search page indexes

Run: uv run python -m app.sources.skyworks_appnotes
"""

import json
import re
from pathlib import Path

import pdfplumber

from app.config import PROJECT_ROOT
from app.sources.http import get

SITE = "https://www.skyworksinc.com"
SEARCH = SITE + "/api/feature/search/searchitems"
PDF_DIR = PROJECT_ROOT / "var" / "appnotes"
LIST_FILE = PDF_DIR / "list.json"
OUT_FILE = PROJECT_ROOT / "data" / "appnotes.jsonl"

RELEVANT = re.compile(
    r"isolat|Si8[0-9]|gate driv|CMTI|current sens|creepage|IEC 60747|VDE|reinforced|UL 1577|smart switch"
    r"|SPST|SPDT|SP[3-9]T|RF switch|\bswitches\b|PIN diode|SKY1[23]\d|SKYA21",
    re.I,
)
# Matched by the pattern above but about something else (VCOs, regulators, clocks, PAs).
UNRELATED = re.compile(r"VCO|synthesizer|ripple|regulator|AAT4285|AWB7|Si534x|SKY65367|PoE PD|Switch Power", re.I)


def select(items: list[dict]) -> list[dict]:
    notes = []
    for x in items:
        url = x.get("ItemUrl") or ""
        title = (x.get("TitleSummary") or x.get("Title") or "").strip()
        if x.get("ItemType") != "Document" or "application-note" not in (x.get("FileUrl") or "").lower():
            continue
        if not url.lower().endswith(".pdf") or not RELEVANT.search(title) or UNRELATED.search(title):
            continue
        m = re.match(r"(AN\d+|APN\d+)", title, re.I) or re.match(r"(AN\d+|APN\d+)", x.get("Title") or "", re.I)
        notes.append({"id": m.group(1).upper() if m else Path(url).stem, "title": title, "url": SITE + url})
    return sorted({n["url"]: n for n in notes}.values(), key=lambda n: n["id"])


def fetch() -> list[dict]:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    if not LIST_FILE.exists():
        body = get(SEARCH, json.dumps({"keyword": "application note", "page": 1}).encode(), "application/json")
        LIST_FILE.write_text(json.dumps(select(json.loads(body)["GlobalResultItems"]), indent=1))
    notes = json.loads(LIST_FILE.read_text())
    for n in notes:
        path = PDF_DIR / Path(n["url"]).name
        if not path.exists():
            data = get(n["url"])
            if data[:5] == b"%PDF-":
                path.write_bytes(data)
            else:
                print("not a PDF:", n["url"])
    return notes


def build() -> int:
    notes = json.loads(LIST_FILE.read_text())
    rows = 0
    with OUT_FILE.open("w") as out:
        for n in notes:
            path = PDF_DIR / Path(n["url"]).name
            if not path.exists():
                continue
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = re.sub(r"[ \t]+", " ", page.extract_text() or "").strip()
                    if len(text) < 40:
                        continue
                    out.write(json.dumps({**n, "page": i, "text": text}, ensure_ascii=False) + "\n")
                    rows += 1
    return rows


if __name__ == "__main__":
    print(len(fetch()), "application notes")
    print(build(), "pages indexed")
