# Open questions for the owner

Ask these before the next update of the live site (the next merge into `main`), then record the answers here and
remove what is settled. Kept on the owner's request, 21 Oct 2026.

1. **New systems (26 Oct 2026).** The 95 diagrams under "Other" now sit in five new systems, none left in Other:
   Industrial & energy (factory automation, motor drives and robots, solar and wind, energy storage and grid, power
   supplies and isolation, e-mobility / rail / industrial vehicles), Aerospace & defense (radar, electronic warfare,
   SATCOM and space, tactical radio, test and measurement), Consumer & wearables (wearables and XR, audio, PCs /
   payments / portable power, connectivity chips and modules), Home & building (smart home, home Wi-Fi and broadband,
   smart meters) and Medical (imaging, monitoring, therapy). Are the names and the split right?
2. **Interior radar diagram.** The new child-presence diagram is drawn after Infineon's 60 GHz radar in-cabin
   monitoring diagram; no public UWB-radar child-presence block diagram was found (Microwave Journal's robots.txt blocks
   our reader). The UWB-radar option is a question on the diagram. Is a 60 GHz radar diagram right under "UWB in the
   car"?
3. **UWB anchor clock source.** The clock block cites Murata's public UWB module designs (Qorvo QM33120W and NXP SR150,
   both with a 38.4 MHz crystal); NXP's automotive anchor pages give no clock frequency. Is a module design acceptable
   as the "public reference design" for the anchor?

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
