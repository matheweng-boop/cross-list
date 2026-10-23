# Open questions for the owner

Ask these before the next update of the live site (the next merge into `main`), then record the answers here and
remove what is settled. Kept on the owner's request, 21 Oct 2026.

1. **Grouping of the diagrams into systems (Systems & applications, 23 Oct 2026).** Four systems are built:
   Automotive (8 sub-systems), Data center (4), Drones (3), Cellular (5); 77 of the 172 library diagrams sit in
   them, the other 95 under "Other" by their old category (industrial, solar and storage, motor drives, medical,
   consumer, home and building, test and defense RF). Please say: (a) should Other become more systems, for
   example Industrial & energy, Consumer & wearables, Aerospace & defense; (b) is it right that DC fast chargers sit
   under Automotive › Charging, smartwatches under Cellular › Phones and wearables, and only the enterprise Wi-Fi
   access point under Data center (home routers stay in Other); (c) Kick sensor and Interior radar are listed as
   parts of "UWB in the car" but only the in-cabin radar has its own diagram: should each get one; (d) Car radio
   is split into tuner, digital-radio demodulator, antenna amplifier and audio amplifier: is that the split you
   want. The mapping is one file (data/blocks/systems.yaml), so changes are quick.

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
