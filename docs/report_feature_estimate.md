# Technology platforms: "Compare" and "Produce report" (estimate, not built)

Owner request (22 Oct 2026): compare technology platforms and produce a report from them. This page estimates three
ways to do it. Figures are estimates (est) for the current setup: one Render "starter" web service (512 MB RAM) with a
1 GB disk shared with the database. Existing HTML reports average about 14 KB per file (23 files, 320 KB).

| | (a) Summary page, print to PDF in the browser | (b) PDF made on the server | (c) Background agent writes the report |
|---|---|---|---|
| What it is | A clean one-page summary of the chosen platforms; the browser's "Save as PDF" makes the file | The site renders a PDF (WeasyPrint or headless Chromium) and offers it for download | The request is queued like a technology review request; the daily run (or a triggered session) researches and writes an HTML report |
| Effort | 1–1.5 days (8–12 h): selection, summary page, print styles, tests | 3–5 days: library in the Docker image, layout, fonts, memory limits, tests | 2–3 days: request form and queue, report format, run instructions, tests; then agent time per report |
| Storage per report | 0 on the server (file stays with the user); 20–60 KB if a summary is saved | 150–500 KB per PDF with charts | 15–40 KB HTML (like today's reports) |
| Storage total | none | 1,000 reports ≈ 0.15–0.5 GB of the 1 GB disk; or make on the fly and store nothing | 1,000 reports ≈ 15–40 MB |
| Running cost | $0 extra | WeasyPrint fits the starter plan (+60–80 MB image); Chromium (~300 MB RAM per render) likely needs the next plan (about +$18/month, est) | Model usage, about $1–5 per report (est), plus review time |
| Speed | Instant | Seconds | Hours, or next day after the owner's go-ahead (off-schedule merges are blocked) |
| Risks | Page breaks differ a little between browsers; no archive unless the user saves the PDF | Out-of-memory on the small plan; fonts and charts render differently from the page; one more dependency to maintain | Latency; quality varies and needs review; cost grows with the number of requests |

**Recommendation: (a) now**, for "Compare" and a quick one-page "Produce report". It is the cheapest, instant, and adds
no server cost or storage. Use **(c)** only for in-depth narrative reports, through the existing request queue and
daily run (no new infrastructure). Skip **(b)** unless PDFs must be made without a browser (e.g. sent automatically by
e-mail).

## Design sketch: the two floating buttons

- Each platform card on Technology platforms gets a small checkbox "Select". The selection is kept in the page address
  (`?sel=gan,baw,soi`), so a selection can be shared as a link.
- A floating bar appears at the bottom right once one platform is selected (on phones: a full-width bar at the bottom,
  buttons at least 44 px high, above the feedback button so they do not overlap):
  - **Compare (3)**: active from 2 selected platforms, up to 4. Opens a side-by-side table: owner (Skyworks / Qorvo /
    both), process, advantage, best for, markets, sources. No horizontal scroll: on phones the table stacks per row.
  - **Produce report**: opens the one-page summary of the selection (or of all platforms when none is selected) with a
    "Print / Save as PDF" button; the print styles hide navigation and buttons and keep each platform on one page.
- "Clear" link in the bar; the count is announced to screen readers; the bar never covers the last card (page padding).
- With option (c) later, the report page gets one more button, "Ask for an in-depth report", which files a request.
