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
6. **Timing: SiTime datasheet links.** SiTime serves its datasheets from a folder named "gated", although they open
   without a form or login (robots.txt allows them). Fine to keep reading them that way?
7. **MSW2060-206.** The MACOM datasheet (MSW206x-206 rev V2) gives MSW2060 = 20–1200 MHz, MSW2061 = 200–4500 MHz,
   MSW2062 = 1.5–6.5 GHz, operating –65 to +125 °C (+150 °C is the storage limit), body 8 x 5 x 2.5 mm. We used
   those. 0.5–6 GHz is the MASW-011060. Which source showed 0.5–6 GHz and 150 °C for the MSW2060?
8. **CMTI, like with like.** Skyworks states only a minimum CMTI for Si86S (B/E codes 100, F/H codes 150 kV/µs);
   Chipanalog CA-IS374x states 100 min / 150 typ. With "typ first", CA-IS3740HB (150 typ) looks better than
   SI86S640EE-IS2 (100 min), although both guarantee 100 kV/µs. Compare CMTI minimum against minimum whenever one
   side gives no typical value (the fair test), or keep typ first?

## Settled (owner, 22 Oct 2026)

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
