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

## Settled (owner, 22 Oct 2026)

- Old commercial inputs: delete them (done at start-up).
- Prelim case button: hidden on our own Skyworks / Qorvo parts.
- Crossed means a drop-in exists; parts without one get the prelim case button, parts with no cross at all first.
- Pinouts: transcribe them (docs/pinout_backlog.md, a few datasheets per daily run).
- fetch-tool: merged.
- Updates: through the daily run; off-schedule only after the owner confirms several times.
- Old explorer table: keep it while it still holds sort, filter and set-aside; remove it once those are on Cross-sell & gaps.
- Drone diagrams: added now (three generic ones); deep dives follow in the daily runs.
