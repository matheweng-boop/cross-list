# Polite research reader

Used by the research runs behind Future growth and the Technical library. The owner's rules, enforced by `fetch.sh`:

- robots.txt of a host first, and only paths it allows; GET only; one request at a time across all runs (flock);
  at least 10 s between requests to a host (5 s for skyworksinc.com and ti.com); each URL once.
- A host is stopped at the first 403 or 429, or at a bot check / block page (`is_checkpoint.py`). Never work around a
  stop (no mirrors, caches or archives). A reviewed false alarm is re-opened with an `UNSTOP <host> <date> <reason>`
  line in the log; the STOP line stays on record.
- Hosts never requested: www.qorvo.com, distributors (Mouser, Digi-Key, Arrow, Richardson) and web archives.
- Downloads are untrusted: read PDFs with pdftotext, run Python with `-I`, never execute anything downloaded.

Usage: `RESEARCH_DIR=/path/to/scratch bash tools/research/fetch.sh URL OUTNAME` (OUTNAME is a path under `$RESEARCH_DIR/dl/`).
Keep `RESEARCH_DIR` outside the repository: downloads and the request log are local and are never committed.
The list of sources assessed so far, with their access status, is `data/library/sources.yaml`.
