"""Excel (colour-highlighted) and CSV exports."""

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.matching.engine import CrossResult
from app.services.compare import Comparison

FILLS = {
    "better": PatternFill("solid", fgColor="C6EFCE"),
    "worse": PatternFill("solid", fgColor="FFC7CE"),
    "different": PatternFill("solid", fgColor="FFEB9C"),
    "unknown": PatternFill("solid", fgColor="E7E6E6"),
    "baseline": PatternFill("solid", fgColor="DDEBF7"),
}
BOLD = Font(bold=True)
SYNTHETIC_NOTE = "SYNTHETIC DEMO DATA – not real parts"


def _cross_rows(r: CrossResult) -> list[list[str]]:
    rows = []
    for d in r.all_diffs:
        rows.append([f"P{d.priority}", d.label, d.ref_display, d.cand_display, d.status])
    return rows


def _autosize(ws):
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, width + 2), 60)


def cross_xlsx(r: CrossResult) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Cross"
    ws.append([f"Cross: {r.reference.label} → {r.candidate.label}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Categories", ", ".join(r.categories) or "none"])
    ws.append(["Top 5 differences", r.comment()])
    ws.append(["Candidate lifecycle", r.candidate.lifecycle_status.value])
    if r.reference.is_synthetic or r.candidate.is_synthetic:
        ws.append([SYNTHETIC_NOTE])
    ws.append([])
    header = ["Priority", "Parameter", r.reference.label + " (reference)", r.candidate.label, "Status"]
    ws.append(header)
    for c in ws[ws.max_row]:
        c.font = BOLD
    for row in _cross_rows(r):
        ws.append(row)
        status = row[-1]
        if status in FILLS:
            for c in ws[ws.max_row][2:]:
                c.fill = FILLS[status]
    ws["B3"].alignment = Alignment(wrap_text=True)
    _autosize(ws)
    ws.column_dimensions["B"].width = 30
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def cross_csv(r: CrossResult) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Priority", "Parameter", r.reference.label + " (reference)", r.candidate.label, "Status"])
    w.writerows(_cross_rows(r))
    return buf.getvalue()


def _comparison_header(c: Comparison) -> list[str]:
    return ["Priority", "Parameter"] + [p.label + (" (baseline)" if p.id == c.baseline.id else "") for p in c.parts]


def comparison_xlsx(c: Comparison) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Comparison"
    ws.append(["Comparison – priority 1 & 2 parameters"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Colours vs baseline: green better, red worse, yellow different, grey unknown. Bold = best in row."])
    if any(p.is_synthetic for p in c.parts):
        ws.append([SYNTHETIC_NOTE])
    ws.append([])
    ws.append(_comparison_header(c))
    for cell in ws[ws.max_row]:
        cell.font = BOLD
    for row in c.rows:
        ws.append([f"P{row.param.priority}", row.param.label] + [cell.display for cell in row.cells])
        for xl, cell in zip(ws[ws.max_row][2:], row.cells, strict=True):
            if cell.status in FILLS:
                xl.fill = FILLS[cell.status]
            if cell.best:
                xl.font = BOLD
    _autosize(ws)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def comparison_csv(c: Comparison) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_comparison_header(c) + ["(best in row)"])
    for row in c.rows:
        best = [p.label for p, cell in zip(c.parts, row.cells, strict=True) if cell.best]
        values = [cell.display for cell in row.cells]
        w.writerow([f"P{row.param.priority}", row.param.label, *values, "; ".join(best)])
    return buf.getvalue()
