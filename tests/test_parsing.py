"""Datasheet parsing on synthetic PDFs generated during the test."""

from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.parsing.datasheet import analyze, detect_revision, find_date, revision_history


def make_pdf(path, pages):
    c = canvas.Canvas(str(path), pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(50, y, line)
            y -= 16
        c.showPage()
    c.save()
    return path


def test_ti_style_header(tmp_path):
    pdf = make_pdf(
        tmp_path / "a.pdf",
        [
            [
                "SYN1234 Quad-Channel Digital Isolator",
                "SLLSZZ9D - SEPTEMBER 2018 - REVISED MAY 2023",
                "5000 VRMS isolation, 100 kV/us CMTI, 150 Mbps",
            ]
        ],
    )
    info = analyze(pdf)
    assert info.revision == "D"
    assert info.revision_date == date(2023, 5, 1)
    assert info.first_issue_date == date(2018, 9, 1)
    got = {s.key: s.value for s in info.suggestions}
    assert got == {"isolation_rating_kvrms": 5.0, "cmti_kv_us": 100.0, "data_rate_mbps": 150.0}


def test_rev_number_with_date_in_footer(tmp_path):
    pdf = make_pdf(
        tmp_path / "b.pdf",
        [
            ["SYN8641 Digital Isolator", "Up to 5.0 kVrms isolation"],
            ["Document history", "Rev. 1.8  10 November 2023"],
        ],
    )
    info = analyze(pdf)
    assert info.revision == "1.8" and info.revision_date == date(2023, 11, 10)
    assert info.suggestions[0].page == 1


def test_no_revision_found():
    assert detect_revision(["Some text without any markers"]) == (None, None, None)


def test_date_formats():
    assert find_date("issued 2024-03-05") == date(2024, 3, 5)
    assert find_date("March 7, 2022") == date(2022, 3, 7)
    assert find_date("Rev 2, 06/2021") == date(2021, 6, 1)


def test_skyworks_footer_and_revision_history():
    pages = [
        "Si8641 Data Sheet\n206329A • Skyworks Proprietary Information • Subject to Change\n1 March 23, 2026",
        "16. Revision History\nRevision A\nJuly 2022\n• Added footer.\nRevision 2.16\nJune, 2021\n• Changes.\n"
        "Revision 1.0\nNovember 18, 2015\n• Initial release.",
    ]
    rev, rev_date, first = detect_revision(pages)
    assert rev == "206329A" and rev_date == date(2026, 3, 23) and first == date(2015, 11, 18)


def test_tabular_revision_history():
    pages = [
        "12. Revision History\nRevision Date Description\nB September, 2023 Removed parts.\n"
        "A July, 2022 Added footer.\n1.72 April, 2018 Added OPN.\nSome text May 2001 not a row"
    ]
    assert revision_history(pages) == [("B", date(2023, 9, 1)), ("A", date(2022, 7, 1)), ("1.72", date(2018, 4, 1))]
