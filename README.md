# Cross List

Browser-based cross-reference tool for isolation semiconductors. Skyworks power
isolation parts are the reference; candidates come from Novosense, TI, ADI, Diodes
and others.

> **Demo mode:** the database starts with **synthetic** parts from fictional
> manufacturers ("SynRef" stands in for Skyworks). Values are invented. Real data
> is imported from public datasheets only.

## Cross categories

| Category | Rule |
|---|---|
| **FFF** | Same package and pinout; every priority 1 parameter equal or better. Priority 2 differences need an engineer's review: accepted crosses become FFF, rejected ones drop out |
| **Pin-to-pin** | Same package and pinout; function ignored |
| **Upgrade** | No priority 1 parameter worse, at least one better; same or smaller package (same only if the reference is *package-locked*) |
| **Downgrade** | At least one priority 1 parameter worse; same package; closest first |

"Same package" means the same body length, body width, lead span and pitch; the
pin count may differ, because a missing pin position is equivalent to a no-connect
pin. Pinouts are compared by physical position.

"Hard" parameters (channel configuration, input type, output type…) must match for
FFF, Upgrade and Downgrade. Obsolete / NRND / last-time-buy candidates are always
listed last. Priority groups live in `rules/*.yaml` and are shown on the **Rules** page.

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
