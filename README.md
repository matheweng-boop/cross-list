# Cross List

Browser-based cross-reference tool for isolation semiconductors. Skyworks power
isolation parts are the reference; candidates come from Novosense, TI, ADI, Diodes
and others.

> **Demo mode:** the database starts with **synthetic** parts from fictional
> manufacturers ("SynRef" stands in for Skyworks). Values are invented. Real data
> is imported from public datasheets only.

## Cross types

Priority 1 parameters decide function; priority 2 and 3 are shown for information and
never block a cross. Each candidate gets one type, in order of preference:

| Type | Rule |
|---|---|
| **Drop-in (FFF)** | Same package, pin-to-pin, every priority 1 parameter equal or better (better ones marked). An engineer can reject it; it then becomes a package equivalent |
| **Functional equivalent** | Different package or pinout; priority 1 equal or better apart from at most 2 deviations (worse, different or unknown; adjustable 0–3 on the part page). A *package-locked* reference only accepts its own package |
| **Package equivalent** | Same package and basic function, different technical spec; marked pin-to-pin or not |

Anything else is not listed. "Same package" means the same body length, body width,
lead span and pitch; the pin count may differ, because a missing pin position is
equivalent to a no-connect pin. Pinouts are compared by physical position.

Automotive and non-automotive parts are kept apart: every part carries an AEC-Q100 or
Industrial badge, and AEC-Q100 is a hard requirement when the reference has it (industrial
parts are then not listed at all). For an industrial reference, automotive parts are listed
as an upgrade and the results can be filtered by grade.

"Hard" parameters (channel configuration, input type, output type…) define what the
part does: a mismatch is not listed at all. Obsolete /
NRND / last-time-buy candidates are always listed last. Priority groups live in
`rules/*.yaml` and are shown on the **Rules** page.

Every cross shows its **top 5 differences** (ranked by priority, then size). Tap it to
expand the full table, downloadable as colour-highlighted Excel or CSV. **Compare**
builds a priority 1 & 2 table for any list of parts.

## Run on macOS

Requirements: [uv](https://docs.astral.sh/uv/) (`brew install uv`) and Git.

```bash
git clone <repo-url> cross-list && cd cross-list
make install
make run          # then open http://localhost:8000
make test         # run the automated tests
```

The database is a SQLite file in `var/`. Delete `var/crosslist.db` to start fresh.
Settings come from environment variables (`CROSSLIST_DATABASE_URL`,
`CROSSLIST_SEED_SYNTHETIC`, `CROSSLIST_NEW_PART_DAYS`), or a `.env` file.

## Lifecycle refresh

`make refresh` reads lifecycle lists from `var/lifecycle/*.csv`:

```csv
manufacturer,mpn,status,release_date,revision,revision_date,source
TI,ISO7741,active,2015-03-01,E,2024-06-01,ti.com product page
```

Status is one of `preview, active, nrnd, last_time_buy, obsolete, unknown`.
Changes are recorded and shown on the **Lifecycle** page. To run it weekly on macOS:
`crontab -e` → `0 7 * * 1 cd ~/cross-list && make refresh`.

## Datasheet analysis

`uv run python -m app.cli analyze datasheet.pdf` prints the detected revision, revision
date, first-issue date and a few parameter suggestions (offline; nothing is uploaded).

## Project layout

```
app/
  matching/   rules loader + cross engine (fit, categories, top-5 ranking)
  services/   data loading, queries, comparison, Excel/CSV export, lifecycle
  parsing/    datasheet text, revision/date detection
  jobs/       lifecycle refresh job
  auth/       current-user stub (passkeys later)
  api/, web/  JSON API and HTML pages
rules/        priority groups per product family
data/         synthetic demo dataset
tests/        automated tests
```
