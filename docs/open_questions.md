# Open questions for the owner

Ask these before the next update of the live site (the next merge into `main`), then record the answers here and
remove what is settled. Kept on the owner's request, 21 Oct 2026.

1. **NSI6601S.** Novosense NSI6601S has two outputs (OUT and OUTF) for two slew rates. Treat it as a split output
   in the gate-driver matching, instead of its own output option?
2. **Tuner market figures.** The three public TAM figures for automotive tuner ICs disagree by more than 2x
   ($0.89 B to $2.31 B for 2024). They are yes/no questions in the Data quality review queue, and the answers now
   change the Opportunity explorer's market size directly.
3. **Competitors.** Competitive analytics starts with SiTime. Which companies next, and in what order?
4. **HyperPhysics links.** HyperPhysics could not be opened from the research machine (it serves plain HTTP, and its
   HTTPS certificate does not match its name), so the HyperPhysics links on the new physics topics
   (`/rf-notes#cat-physics`) use the site's own page names but are unchecked. Could you click two or three of them
   from your browser? If they work, keep them; if not, say which and they are replaced in the next Saturday run.
5. **Timing: Microchip.** Microchip timing (ZL30733, PL610) was skipped because microchip hosts are blocked for this
   work. Leave Microchip out of timing crosses, or name a public source you are happy with?
6. **Timing: strictness.** A timing cross lists a part only when it has at most 2 shortfalls among function, outputs,
   output formats, frequency range and core supply. That hides near misses such as TI CDCE6214-Q1 for Si5332-AM1
   (4 outputs, no LVPECL, stops at 328 MHz) and every competitor oscillator for Si545 / Si549 (narrower frequency
   range, no 1.8 V). They show with "allow 3 deviations" on the part page. Keep it strict, or count the core supply
   as priority 2 (a board rail is often available)?
7. **Timing: SiTime datasheet links.** SiTime serves its datasheets from a folder named "gated", although they open
   without a form or login (robots.txt allows them). Fine to keep reading them that way?
8. **SI86S640HE-IS2 prop delay.** You wrote 10 ns. The datasheet (si86s6xx rev B, ordering guide and Table 10) says
   the "H" code is the default-high option **with a 36 ns deglitch filter**: 36 ns typ (42 max) and 10 Mbps. The
   ~10 ns you quote is the B / E codes without the filter (9 ns typ; Si86SLx 11.5 ns). We now show 36 ns and 10 Mbps
   for the F / H codes. Is that right, or do you have a source for 10 ns on the H code? (For CA-IS3740HB the no-filter
   SI86S640EE-IS2 may then be the better offer; it has 100 instead of 150 kV/µs CMTI.)
9. **1ED3140 UVLO letters.** The Infineon datasheet (1ED314xMU12F / 1ED314xMC12H, v2.20) sets the UVLO by the fourth
   digit: 1ED3140 9.3 V, 1ED3141 12.0 V, 1ED3142 13.6 V. The G / B / C / E letters are the Skyworks Si82x code, and
   the Si82Bx datasheet gives 4 / 8 / 12 / 15 V (B = 8 V, not 6 V). The cross now ranks the 8 V (B) code first for
   the 9.3 V 1ED3140. Agreed?
10. **MSW2060-206.** The MACOM datasheet (MSW206x-206 rev V2) gives MSW2060 = 20–1200 MHz, MSW2061 = 200–4500 MHz,
   MSW2062 = 1.5–6.5 GHz, operating –65 to +125 °C (+150 °C is the storage limit), body 8 x 5 x 2.5 mm. We used
   those. 0.5–6 GHz is the MASW-011060. Which source showed 0.5–6 GHz and 150 °C for the MSW2060?

## Settled (owner, 22 Oct 2026)

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
