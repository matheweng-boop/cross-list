# Open questions for the owner

Ask these before the next update of the live site (the next merge into `main`), then record the answers here and
remove what is settled. Kept on the owner's request, 21 Oct 2026.

1. **NSI6601S.** Novosense NSI6601S has two outputs (OUT and OUTF) for two slew rates. Treat it as a split output
   in the gate-driver matching, instead of its own output option?
2. **Tuner market figures.** The three public TAM figures for automotive tuner ICs disagree by more than 2x
   ($0.89 B to $2.31 B for 2024). They are yes/no questions in the Data quality review queue, and the answers now
   change the Opportunity explorer's market size directly.
3. **Competitors.** Competitive analytics starts with SiTime. Which companies next, and in what order?

## Settled (owner, 22 Oct 2026)

- Old commercial inputs: delete them (done at start-up).
- Prelim case button: hidden on our own Skyworks / Qorvo parts.
- Crossed means a drop-in exists; parts without one get the prelim case button, parts with no cross at all first.
- Pinouts: transcribe them (docs/pinout_backlog.md, a few datasheets per daily run).
- fetch-tool: merged.
- Updates: through the daily run; off-schedule only after the owner confirms several times.
- Old explorer table: keep it while it still holds sort, filter and set-aside; remove it once those are on Cross-sell & gaps.
- Drone diagrams: added now (three generic ones); deep dives follow in the daily runs.
