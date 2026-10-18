"""Texas Instruments source: ti.com selection-tool data and datasheets.

fetch()  saves the digital-isolator table, per-device orderable part numbers
         and datasheets under var/raw/ti and var/datasheets/ti. Each file is
         saved as soon as it is fetched, and existing files are skipped, so an
         interrupted fetch resumes where it stopped.
"""

import json

from app.config import PROJECT_ROOT
from app.sources.http import get

BASE_URL = "https://www.ti.com"
RAW_DIR = PROJECT_ROOT / "var" / "raw" / "ti"
DATASHEET_DIR = PROJECT_ROOT / "var" / "datasheets" / "ti"
FAMILIES = {"digital_isolator": 3121}


def gpn_table_url(family_id: int) -> str:
    return (
        f"{BASE_URL}/selectionmodel/api/gpn/result-list?destinationId={family_id}&destinationType=GPT&mode=parametric"
    )


def opn_url(gpn: str) -> str:
    return f"{BASE_URL}/selectionmodel/api/opn/result-list?gpn={gpn}"


def datasheet_url(gpn: str) -> str:
    return f"{BASE_URL}/lit/ds/symlink/{gpn.lower()}.pdf"


def fetch(family: str = "digital_isolator", log=print, datasheets: bool = True) -> None:
    (RAW_DIR / "opn").mkdir(parents=True, exist_ok=True)
    DATASHEET_DIR.mkdir(parents=True, exist_ok=True)
    table_path = RAW_DIR / f"gpn_{FAMILIES[family]}.json"
    if not table_path.exists():
        table_path.write_bytes(get(gpn_table_url(FAMILIES[family])))
    gpns = [r["genericPartNumber"] for r in json.loads(table_path.read_text())["results"]]
    log(f"{len(gpns)} devices")
    for i, gpn in enumerate(gpns, 1):
        path = RAW_DIR / "opn" / f"{gpn}.json"
        if not path.exists():
            path.write_bytes(get(opn_url(gpn)))
        if datasheets:
            pdf = DATASHEET_DIR / f"{gpn.lower()}.pdf"
            if not pdf.exists():
                try:
                    body = get(datasheet_url(gpn), pause=1.5)
                except RuntimeError:
                    log(f"no datasheet for {gpn}")
                    continue
                if body[:4] == b"%PDF":
                    pdf.write_bytes(body)
                else:
                    log(f"{gpn}: datasheet link did not return a PDF")
        if i % 20 == 0:
            log(f"{i}/{len(gpns)}")


if __name__ == "__main__":
    fetch()
