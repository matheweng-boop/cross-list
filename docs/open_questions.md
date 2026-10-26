# Open questions for the owner

Ask these before the next update of the live site (the next merge into `main`), then record the answers here and
remove what is settled. Kept on the owner's request, 21 Oct 2026.

1. **Isolator data rate as priority 1 (26 Oct 2026).** A 10 Mbps deglitch code (Si86S F/H) no longer comes first
   for a 150 Mbps part; the B/E codes do (Si86S620HE / SI86S640FC are 36 ns, 10 Mbps per the datasheet ordering
   guide; 10 ns is the E/B code). Is that right?

## Settled (owner, 26 Oct 2026, automotive crosses): "No industrial fallback. Automotive needs automotive"

- An AEC-Q100 part is crossed to AEC-Q100 parts only; with none, the row stays red (ISOW7841AQDWERQ1, no automotive
  Si86P). The fallback to the closest industrial part was removed before it went live.

## Settled (owner, 25 Oct 2026, reference-design matching): "Should be based on feedback. So a bit stricter at first"

- Matching rules made a bit stricter (app/services/refmatch.py, old → new): title-word weight 60 % → 70 %; shared
  functions ≥ 2 → ≥ 3 (1 → 2 when the title words match fully); suggestions ≥ 30 % of ≥ 3 designs → ≥ 40 % of
  ≥ 4; automatic block additions ≥ 50 % and ≥ 5 → ≥ 60 % and ≥ 8 (still only with no close alternative). Result:
  127 → 111 of 190 diagrams with matches, median 19 → 13 designs, 150 → 107 suggestions, 2 → 0 blocks added (the two
  earlier additions, power_fets in the USB-C power bank and digital_isolator in the DC fast charging power module, no
  longer qualified and were removed).
- Feedback adjusts it: on a diagram's reference-design list the owner marks each design "Fits" / "Doesn't fit" and
  can dismiss a suggestion; a design that does not fit leaves that diagram at once. The daily run looks for patterns
  in those answers and tightens or loosens the rules (docs/daily_update.md).

## Settled (owner, 26 Oct 2026, questions 1-6)

- New systems (Industrial & energy, Aerospace & defense, Consumer & wearables, Home & building, Medical): OK.
- Interior radar diagram drawn after a 60 GHz radar design under "UWB in the car": OK for now.
- UWB anchor clock from Murata's public module designs: OK.
- Car radio reference systems (Si47961 / Si47962 tuners, Si46922 demodulator, LNA, antenna switch, audio amplifier):
  OK; the prices are still to be entered by the owner under Price estimate.
- Digital share of new-car radios: no share known; slow adoption, about 10 % digital where nothing is mandated; a
  mandate takes a region to 100 % within a few years (data/business/radio_market.yaml: 2030 base 0.34, China-mandate
  scenario 0.66, est).
- US AM for Every Vehicle Act: no new status known; it stays as shown (passed the House 16 Sep 2026, Senate not
  checked).

## Settled (owner, 26 Oct 2026, shareable documents)

- Shareable reports, PDFs, PowerPoints and presentations are built only from content already on the site; no
  research or new content is generated on request for them. New research comes in through the usual channels (daily
  run, requests, reviews) and then appears on the site, from where the shareables pick it up.

## Settled (owner, 26 Oct 2026, data protection)

- No customer names are stored unless they come from public sources the site has pulled itself (with the link); no
  private customer-name list. The confidential-data check uses only patterns (e-mail, phone, "confidential",
  "internal", quote-like prices) and public names already in the data.
- Only the owner can approve data (no other approvers, guests never).
- Every input, the owner's own included, is screened for patterns and potential insider information; flagged items wait
  for the owner's approval (docs/plan_data_protection.md, section 2b).
- Retention: 12 months (owner, 26 Oct 2026) for feedback, comments, lookup requests and the daily inbox files; then
  deleted automatically.

## Settled (owner, 25 Oct 2026, radio market)

- MarketIntelo ($1.8 B, digital radio tuners only): not linked to the radio-tuner-next case's market size; shown as an
  open discrepancy (different definition), since the market that counts is the total radio market incl. adjacent
  technologies.

## Settled (owner, 25 Oct 2026: "Yes to all")

- Systems grouping: the diagrams under "Other" become more systems (e.g. Industrial & energy, Consumer & wearables,
  Aerospace & defense); Kick sensor and Interior radar each get their own diagram. To build in the next run.
- Cross-sell: keep the Application library preview without pairs; keep weak supply-only pairs (shown last); add a
  clock / crystal block to the UWB anchor diagram from a public reference design; keep the bundle table at 30 of 172.
- Priority score: weights T 45 / L 30 / D 25; "All" in three groups; non-isolated gate drivers 0.7; current sensing
  0.9 only for isolated or integrated-shunt parts; PoE and isolated RS-485 at 0.9; one-diagram RF band gaps
  acceptable; background diagrams count fully in D; competition stays out of likeliness.

## Settled (owner, 25 Oct 2026, Shareable reports and reviews)

- Automotive report: the "from Skyworks" tile is removed.
- Report length: keep each management report at 3 pages.
- "Combined since October 2026" is correct.
- ACT88321 review concept item 0: the owner is not sure what else was wrong; the correction against datasheet Rev. C
  stands.
- QPF1003Q stays counted as AEC-Q qualified (Q ending, catalogue entry), marked; recheck at release.

## Settled (owner, 24 Oct 2026, site check): "Yes to all"

- Browse products: the Package column is hidden on desktops below 1400 px, so the table no longer scrolls sideways at
  1280 px; the package stays on each part's page, in the summary line and on phones.
- Data management › Overview: the tile now reads "Skyworks and Qorvo parts with full data".
- Touch screens (iPad, phones) only: small buttons and button-like links, Agree / Disagree included, are at least
  40 px tall; the desktop stays dense.
- The menu item "Business cases" is now "Shortlist & cases" (title and heading too); the URLs are unchanged.
- Guests no longer see TAM numbers: the TAM column of the detailed table, TAM on the gap cards, the market size in the
  walk-through, the TAM basis in score tables, and the ASP-priced content on the application pages are hidden for
  them (decided by the owner-only list in app/auth/access.py).
- Numbers are right-aligned in tabular figures in the creepage tables, methodology weights and points, cross-rule
  priorities, RF coverage, the application coverage table and the detailed table.
- RF band chart: label colours below 4.5:1 are darkened in the same hue (at least 4.6:1); the bar colours are
  unchanged.

## Settled (owner, 23 Oct 2026, systems grouping)

- DC fast chargers under Automotive › Charging, smartwatches under Cellular › Phones and wearables: OK.
- Car radio split into tuner, digital-radio demodulator, antenna amplifier and audio amplifier: correct. To expand
  later: remote tuner modules (decentralised full tuner modules) and software-defined radio (tuner plus a
  microprocessor only) as further car-radio applications.

## Settled (checked 23 Oct 2026, from the owner's verification of MSW2030-203 → SKY12212-478LF)

- MSW2030-203: our values stand and now say where they come from. The MACOM product page for MSW2030-203 gives
  50–1000 MHz, 0.30 dB insertion loss, 52 dB isolation, 65 dBm IIP3, 100 W CW. The datasheet it links (MSW203x-203
  Rev. V3) no longer lists the MSW2030: "400 MHz to 6 GHz in 2 bands, 0.25 dB, 65 dBm" is the front-page headline for
  MSW2031-203 (0.4–4 GHz, 0.5 dB typ, 35 dB typ) and MSW2032-203 (2–6 GHz, 0.6 dB typ, 35 dB typ). The 35 dB
  isolation belongs to those two parts.
- SKY12212-478LF insertion loss is specified both ways (datasheet Table 4, typical): TX–ANT 0.47 / 0.29 / 0.33 /
  0.46 / 0.55 dB and ANT–RX 0.44 / 0.26 / 0.24 / 0.32 / 0.34 dB at 0.05 / 0.6 / 1.2 / 2.0 / 2.7 GHz. We store the
  worse path (TX–ANT).
- Frequencies were not consistent: the cross compared SKY12212's worst values in its own band (0.55 dB and 28 dB, both
  at 2.7 GHz) with MSW2030's values for 50–1000 MHz. Fixed: an RF switch with a wider band is now read over the
  reference's band from its datasheet points. Over 0.05–1 GHz the SKY12212 has 0.47 dB insertion loss and about
  36 dB isolation (worst common port, between the 0.6 and 1.2 GHz points), against 0.30 dB and 52 dB: still worse
  on both, so it stays a cross with deviations.

## Settled (owner, 25 Oct 2026, radio market)

- Market size: total radio market incl. adjacent technologies (owner, 25 Oct 2026). Tuner content (tuner ICs only) is
  a labelled sub-layer inside it, not a separate market size. Content per vehicle comes from the site's price
  estimates; the owner's $5 (AM/FM only, 2–4 tuners) and $10 (DAB system by 2030) per vehicle are a cross-check.
  Vehicles: 90–92 M radio systems a year, flat; growth comes from content per vehicle.

## Settled (owner, 22 Oct 2026)

- Tuner market: no tuner-only figure. The market that counts is the total radio market (tuners plus digital radio
  demodulators). Each TAM report is labelled by what it covers (TAM estimates page): MRFR and DataHorizzon cover the
  total radio market, MarketIntelo digital radio tuners only, Emergen not checked (dead link). Total radio market,
  2024: $0.89 B (DataHorizzon) to $2.31 B (Market Research Future); the sources disagree, both are shown. Only the
  total-radio figures set the explorer's market size (median $1.6 B).
- Microchip timing parts: left out.
- SiTime datasheets from the "gated" folder: keep reading them (no login or form; robots.txt allows).
- MSW2060-206: the MACOM datasheet values stand (20–1200 MHz, –65 to +125 °C operating, 8 x 5 x 2.5 mm).
- Every parameter with min / typ / max (confirmed by the owner): compare at the best level BOTH datasheets state,
  in the order typical, then maximum, then minimum (the common denominator). Example: CA-IS3740HB (100 min / 150 typ) vs SI86S640EE-IS2 (100 min only) compares
  100 vs 100. To build: keep min / typ / max per part, CMTI and propagation delay first (daily run, standing work).
- NSI6601S: compared on its standard OUT as a single output (OUTF, the second slew-rate pin, is ignored).
- Competitors after SiTime: Murata next.
- HyperPhysics: the owner found no good links; use a different source. Replace the HyperPhysics links on the physics
  topics with other public sources (LibreTexts, Microwaves101, Falstad, PhET, the Wolfram Demonstrations pages
  already listed), in the next run.
- Timing: judged on function, jitter and outputs; package and pin-to-pin do not count; core supply is priority 2.
- SI86S640HE-IS2: 36 ns typ is right for the H code (deglitch filter); 9–10 ns typ applies to the B / E codes without
  the filter. For CA-IS3740HB the SI86S640EE-IS2 is the offer: 9 ns typ vs 12 ns typ, same 150 Mbps, UVLO 2.18 V vs
  2.24 V rising (typ). CA-IS374x prop delay now 12 ns typ (was 16 max).
- 1ED3140 UVLO: compare the actual UVLO voltages (owner: it matters); our 8 V (B) code first for the 9.3 V 1ED3140.

- Values: typical first, then max (min for CMTI); limits stay limits. Rolled out for prop delay and CMTI on the
  files listed in data/sources/GATE_DRIVER_DATA.md; the rest a few datasheets per daily run.
- UVLO: when no variant matches, the lower threshold is the better stand-in (still a deviation).
- Dead time vs overlap protection: one capability in the crosses (answer on /engineering/deadtime).

- Old commercial inputs: delete them (done at start-up).
- Prelim case button: hidden on our own Skyworks / Qorvo parts.
- Crossed means a drop-in exists; parts without one get the prelim case button, parts with no cross at all first.
- Pinouts: transcribe them (docs/pinout_backlog.md, a few datasheets per daily run).
- fetch-tool: merged.
- Updates: through the daily run; off-schedule only after the owner confirms several times.
- Old explorer table: keep it while it still holds sort, filter and set-aside; remove it once those are on Cross-sell & gaps.
- Drone diagrams: added now (three generic ones); deep dives follow in the daily runs.
