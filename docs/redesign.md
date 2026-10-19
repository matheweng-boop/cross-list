# Cross List redesign – implementation report

Branch: `redesign` (not deployed; `main` and the live Render service are unchanged). All 177 automated tests pass;
the browser workflow check (`tools/browser_workflows.py`) passes all seven workflows at desktop and phone width.

## 1. What changed

**Navigation shell.** A compact top bar (brand, part-number search, *Data management*), a stable sidebar with four
task-based sections, a visually separate *Data management* utility group, breadcrumbs, in-page tabs for views of the
same thing, and a drawer on narrow screens (button with `aria-expanded`, Escape closes, scrim, skip link, visible
focus). The long rows of 13 sibling tabs are gone. Navigation is defined in one place: `app/web/nav.py`.

**Products.** Home has three starting actions (find a replacement, explore an application, assess an opportunity)
around one prominent part-number search. *Browse products* is one index of every product (catalogue records and
parts with full parameters, de-duplicated to one identity) in one functional taxonomy (`data/taxonomy.yaml`), with a
category tree, facet counts that respect the other filters, active-filter chips, reset, result count, and capability
badges (*Parameters*, *Crosses*, *Pinout*, *Catalogue*, *Source*). Catalogue-only records link to the manufacturer and
never to a comparison. Part pages open with a compact reference summary; the cross table shows candidate,
compatibility class, package, pins, critical deviations, qualification and lifecycle; variants, alternate packages
and full parameters moved into each row's detail; a comparison tray (count, reference, clear, compare) follows the
page. Package overlays, pinouts, engineering links, CMTI explorer and Excel/CSV exports are unchanged.

**Systems & applications.** The application library has facets for end market and source, and flags possible
architecture variants (never merged). Technical coverage and Portfolio coverage are tabs of the library.

**Opportunities.** Gaps & ranking and Technology fit became one *Opportunity explorer* with six views (application
reach, cross-sell adjacency, technical feasibility, competition, commercial potential, evidence quality), gap-type and
path filters, a scope switch (library only / library + background) and the denominator on the page. Formulas are the
existing ones. The overview puts results first, one short limitations line, and the pipeline in a disclosure.
Markets and Customers, and Ideas and Business cases, are connected tabs; ideas and explorer rows start a case.

**Data management.** *Requests & reviews* is one queue over the existing records (cross requests, cross verdicts,
diagram feedback, part mappings, data reviews, technology feedback) with seven issue types, each line stating how it
is resolved and what it affects. *Commercial inputs* are searchable tables with known / unknown filters and optional
source, year, geography, currency, scenario and confidence per value (new table `business_assumptions`; values and
calculations unchanged). *Data quality* gained a *Human validation* tab: a full data scan with prioritised items.

**Reliability.** Catalogues are parsed once per process with the libyaml loader; per-function candidates are cached
until the parts change; caches warm in a background thread at start-up; a failed page shows an error page that keeps
its URL (search and filters) and API calls return JSON errors. Cold `/blocks` went from 9.4 s to 3.0 s (0.03 s warm),
cold `/parts` from 7.5 s to about 1 s, peak memory from 264 MB to 211 MB in a local run.

## 2. Navigation and category mapping

| Section | Item | URL (old URLs still work) |
|---|---|---|
| Products | Search & replacements | `/`, `/find`, `/parts/{id}`, overlays, downloads |
| | Browse products | `/parts` (old `family=`, `catalog=`, `lifecycle=` links still filter correctly) |
| | Compare | `/compare` |
| | Lifecycle | `/lifecycle` |
| | Radio & audio | `/broadcast` |
| Systems & applications | Application library (tabs: Library, Technical coverage, Portfolio coverage) | `/blocks`, `/blocks/coverage`, `/business/applications` |
| | Application workspace | `/blocks/new`, `/blocks/{id}` |
| | Radio configurations | `/broadcast/configurations` |
| Opportunities | Overview | `/business` |
| | Opportunity explorer | `/business/explorer`; `/business/gaps` and `/business/technology` redirect to the matching view; `/business/evidence/{fn}` |
| | Cross-sell | `/business/attach` |
| | Markets & customers (tabs) | `/business/markets`, `/business/customers` |
| | Business cases (tabs: Ideas, Business cases) | `/business/explore`, `/business/cases` |
| Engineering knowledge | Knowledge search | `/technical` (application notes and specification guides together) |
| | Specification guides | `/engineering` |
| | Technology platforms | `/business/capabilities` |
| Data management (utility) | Requests & reviews (tabs: Review queue, Part requests, Diagram feedback) | `/manage/reviews`, `/requests`, `/blocks/feedback` |
| | Commercial inputs | `/business/data` |
| | Data quality (tabs: Data quality, Human validation) | `/business/quality`, `/business/validation` |
| | Methodology (tabs: Opportunity methodology, Cross rules) | `/business/method`, `/rules` |

Functional categories (manufacturer labels kept as source metadata on every record): Isolation; RF amplifiers; RF
front-end modules; RF switches; Filters and RF passives; RF control; Frequency conversion and transceivers; Timing;
RF diodes; Power management; Motor control; Radio, audio and video; Optical. Examples of the mapping: *Filters* and
*Filters and Duplexers* → Filters, duplexers and multiplexers; *Timing › Oscillators*, Qorvo *Oscillators* →
Oscillators, while *PLLs/Synthesizers/VCOs* and *Timing › RF Synthesizers* → RF synthesizers, PLLs and VCOs;
*Switches* (both) → RF switches; *Front-end Modules* and *Integrated Modules › Front-End Modules* → front-end
subfamilies by band; Qorvo *Control Products* is split into PMICs, DC-DC, protection, battery management,
attenuators, phase shifters, limiters, equalizers, motor controllers and wireless SoCs; amplifiers stay split into
LNAs, RF power amplifiers, CATV, RF power transistors, multipliers and tunable capacitors, separate from audio
amplifiers. 6,731 of 6,738 products are classified; 7 Qorvo "Other" records stay visible as Unclassified.

## 3. Suspected defects

| # | Finding | Status |
|---|---|---|
| 1 | Home described FFF as matching every priority 1 parameter; rules say equal or better | Confirmed; one shared definition on home and rules |
| 2 | ISO7741DBQR showed the same count for automotive and non-automotive | Counts were correct (34 / 34: each Skyworks device exists as -A… and -I…), but they ignored the company filter and counted unknown grade as non-automotive; now facet counts with the active filters, a third "Grade not stated" state, and an explanation |
| 3 | Parts showed 3 fully parameterised families, Compare offered 5 | Confirmed: Compare listed rule files, Parts listed families with parts; both now use one list, families without parts are shown as "rules defined, no parts imported yet" |
| 4 | "RF passive (capacitor" | Confirmed, root cause in data: unquoted commas in YAML flow mappings split five labels and notes in `functions.yaml`; quoted at the source and guarded in the taxonomy file |
| 5 | Coverage implied validated suitability | Confirmed; renamed *Candidate coverage* with "requirements not validated" everywhere |
| 6 | Markets inferred qualification opportunities from missing metadata, while radio parts were AEC-Q100 | Confirmed: catalogue "no" and "not stated" were merged, and 56 AEC-Q100 radio parts lost their grade on the way into the analysis (the AM/FM tuner was wrongly listed as an opportunity); three states now, the radio grade is carried, "qualify for automotive" needs a stated non-automotive part |
| 7 | Gap kinds not distinguished | Gap type now separates candidate, probably sold already (mapping missing), true gap, competitor only, not assessed, not our product type; a confirmed electrical mismatch is not inferred (no per-socket requirements in the data) |
| 8 | Modeled co-occurrence vs sales attach | Cross-sell states "modeled, not observed" |
| 9 | Source confidence shown like review status | Separate chips: human review (not reviewed / reviewed ✓ / disputed), source check, source confidence |
| – | Found during the scan: 316 parts where the catalogue's series-level AEC-Q100 flag contradicts the per-part datasheet ordering code | Datasheet value wins in Browse products; listed for a spot check on Human validation |
| – | 502 errors (not reproducible locally without Render logs) | Likely cause: one worker on a 512 MB starter instance blocked for 7–9 s on cold catalogue parsing and per-request candidate recomputation; addressed by the parsing, caching and warm-up changes above |

## 4. Workflows tested (browser, desktop 1300 px and phone 390 px)

1. Competitor replacement: search ISO7741DBQR → reference → select two candidates → tray → Compare → Excel export – ok
2. System exploration: library filtered to Automotive → architecture → block → candidates – ok
3. Cross-sell: product → co-occurring functions → markets → customers of a function – ok
4. Product opportunity: explorer (feasibility) → evidence page → ASP in context on Commercial inputs → new case – ok
5. Data correction: mark an evidence item wrong in context → review queue shows type and resolution → to-do – ok
6. Phone: drawer opens, Escape closes it, no horizontal page scroll – ok
7. Keyboard: skip link, disclosure controls – ok

No JavaScript errors on any page visited.

## 5. Remaining limitations and data decisions

- Architecture variants are flagged (24 groups), not grouped: unique-application counts need a person to decide.
- Electrical requirements per socket are not in the data, so "candidate" cannot become "validated" and a confirmed
  electrical mismatch cannot be shown yet.
- Reviews flag data; correcting a fact still needs a data-file update in the repository (stated on every queue item).
- Knowledge search covers application notes and specification guides; technology platforms are linked, not indexed.
- Human validation lists 51 items (14 high): missing priority 1 parameters (e.g. creepage on 91 isolators), seven
  "probably sold already" mappings, unconfirmed evidence for top-ranked functions, grade not stated for 20 functions
  in automotive architectures, no ASPs entered.

## 6. Migration and deployment (not executed)

- No destructive migration. Two new tables (`business_assumptions`, already-existing review tables) are created by
  `create_all` at start-up; existing records and review history are untouched.
- Merge `redesign` into `main` when reviewed; Render redeploys from `main` automatically.
- Optional infrastructure, needs Render access: if 502s continue after this release, look at the Render logs for
  restarts (memory) or health-check timeouts and consider a larger instance or a second worker.
