# Open questions for the owner

Ask these before the next update of the live site (the next merge into `main`), then record the answers here and
remove what is settled. Kept on the owner's request, 21 Oct 2026.

1. **Old commercial inputs.** Values entered earlier on the retired Commercial inputs page (ASPs and volumes) are
   still stored in the live database (table `business_inputs`), unused. Delete them? Deleting cannot be undone.
2. **Prelim case on our own parts.** "Start a prelim case" still shows on Skyworks and Qorvo part pages (there is
   nothing to cross). Hide it there?
3. **When a part counts as crossed.** A drop-in or a functional equivalent counts as "we can cross it, no case
   needed"; a package-only equivalent does not, so those parts still get the prelim case button. Right line?
4. **NSI6601S.** Novosense NSI6601S has two outputs (OUT and OUTF) for two slew rates. Treat it as a split output
   in the gate-driver matching, instead of its own output option?
5. **Missing pinouts.** 108 Infineon and 55 Chipanalog gate drivers have no pinout recorded, so their output option
   (Miller clamp / split output) is unknown unless the feature list says so. Transcribe them from public datasheets?
6. **Tuner market figures.** The three public TAM figures for automotive tuner ICs disagree by more than 2x
   ($0.89 B to $2.31 B for 2024). They are yes/no questions in the Data quality review queue, and the answers now
   change the Opportunity explorer's market size directly.
7. **`fetch-tool` branch.** The polite research fetch helper (tools/research) is still unmerged. Merge it into
   `main`?
