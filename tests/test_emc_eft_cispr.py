"""EFT burst and CISPR emissions note and its what-if visual (23 Oct 2026)."""

import re

from app.config import PROJECT_ROOT
from app.services import engineering, knowledge, library
from app.sources.skyworks_isolators_more import DATASHEETS

JS = (PROJECT_ROOT / "app" / "web" / "static" / "visuals.js").read_text()
NOTE = "/engineering/emc_eft_cispr"


def test_note_renders_with_sections_and_sources(client):
    page = client.get(NOTE)
    assert page.status_code == 200
    html = page.text
    assert "EFT burst and CISPR emissions on isolated designs: what the setup and the design change" in html
    for heading in ("The one idea", "EFT burst (IEC 61000-4-4): setup choices", "CISPR 25 / CISPR 32 emissions",
                    "Design levers and their trade-offs", "Why it matters to the customer",
                    "Testing to pass versus testing right", "Sources"):
        assert heading in html, heading
    for src in ("data-sheets/si88x2x.pdf", "an1131-layout-guide.pdf", "AN892.pdf", "IEC 61000-4-4"):
        assert src in html, src
    assert 'href="/visuals#emc"' in html and 'class="kn-est"' in html


def test_note_numbers_match_the_datasheet(client):
    html = client.get(NOTE).text
    assert "CMTI 40 kV/µs minimum, 100 kV/µs typical" in html and "<b>1.4 pF</b>" in html
    ev = DATASHEETS["si88x2x.pdf"]["facts"]["cmti_kv_us"]
    assert ev["value"] == 40 and "40 100" in ev["evidence"]
    sheet = PROJECT_ROOT / "var" / "datasheets" / "skyworks" / "si88x2x.txt"
    if sheet.exists():  # local datasheet cache (not in git)
        text = sheet.read_text()
        assert re.search(r"Capacitance \(Input-Output\)1 C f = 1 MHz 1\.4 pF", text)
        assert re.search(r"CMTI See Figure 38, “Common-Mode 40 100", text)


def test_visual_exists_with_its_toggles(client):
    assert library.VISUALS["emc"][1] == "/visuals#emc"
    block = JS[JS.index('id: "emc"'):]
    block = block[:block.index("related:")]
    for k in ("mode", "inj", "tie", "cdn", "kv", "y", "dcdc", "sec", "std", "cinj", "cra", "crb", "cww"):
        assert f'k: "{k}"' in block, k
    for opt in ('["33", "33 nF (standard)"]', '["3.3", "3 × 10 nF in series = 3.3 nF (not standard)"]',
                '["1", "1 nF"]', '["3.3", "3.3 nF (3 × 10 nF)"]', '["bond", "Bonded to the plane"]', '["n", "N only"]'):
        assert opt in block, opt
    assert re.search(r"SI88 = \{cmtiMin: 40, cmtiTyp: 100, cio: 1\.4\}", JS)
    assert "/engineering/emc_eft_cispr" in JS[JS.index('id: "emc"'):]


def test_linked_from_guides_knowledge_and_rules(client):
    assert "emc_eft_cispr" in engineering.NOTES and knowledge.problems() == []
    for guide in ("cmti_kv_us", "isolation_rating_kvrms", "isolation_class"):
        assert f'href="{NOTE}"' in client.get(f"/engineering/{guide}").text, guide
    kn = client.get("/knowledge").text
    assert 'id="p-isolators_dcdc"' in kn and f'href="{NOTE}"' in kn and 'href="/visuals#emc"' in kn
    assert f'href="{NOTE}"' in client.get("/rules").text
