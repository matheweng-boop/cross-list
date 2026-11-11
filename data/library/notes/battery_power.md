# Battery and power distribution (deep dive, key `battery_power`)

Researched 2026-11-11 (weekly deep dive: Automotive › Battery and power distribution had no deep dive yet). The
summaries are our own wording; quotes are short. The YAML for the app is in `battery_power.yaml`; the six block
diagrams of the sub-system stay in `data/blocks/templates.yaml` (TI, NXP and Renesas EV BMS, TI 12 V / 48 V battery,
TI HV-to-LV DC-DC, TI 12 V / 48 V power distribution box). The block diagram in the topic is drawn by us.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | TI BQ79631-Q1 product page (pack monitor: current, voltage, insulation resistance) | Read 2 Nov 2026 for the current-sensing case (its background 6.5); reused, no new request |
| r2 | Cao, Gao, Fu, Mi, "Wireless Battery Management Systems: Innovations, Challenges, and Future Perspectives", Energies 17(13) 3277, 2024 (CC BY) | New, 11 Nov 2026: authors' copy on chrismi.sdsu.edu (robots.txt allows all but /wp-admin/); mdpi.com is blocked for our reader |
| r3 | TI SDAA247 "Replacing Melting Fuses with TI Smart eFuse High-Side Switches" (Jan 2026) | Cached copy from the hot-swap report (28 Oct 2026), re-read: sections 1-2 |
| r4 | TI TPSI3050-Q1 product page (reinforced isolated switch driver; TIDA-050063 active pre-charge) | Read 23 Oct 2026 for the hot-swap report (its background 1.1); reused |
| r5 | Skyworks AN1052 "Selecting a FET For Use With the Si875x Driver" (Rev. 0.1, Jul 2021) | BizDev app-note cache (var/appnotes), re-read |
| r6 | Skyworks Si8921/22 data sheet (Rev. 206437E, Jun 2026) | BizDev datasheet cache (var/datasheets/skyworks), re-read: safety tables, CMTI, ordering guide |

Also used without a new request: the hot-swap report background (auto-hv-hot-swap: TPSI2140-Q1, TPS2HCS10-Q1,
TPS4811-Q1, Infineon eFuse page and 2ED4820-EM, Qorvo ACT4910 / ACT85610 and ACT4751M from the catalogue), the
current-sensing case background (iso-current-sense-charging: Si892x / Si894x and TI AMC figures, Infineon XENSIV),
the traction deep dive (traction_asil_d: ASIL method, creepage open question) and the Skyworks / Qorvo catalogue in
data/catalog.

## Key numbers taken

- r1: "Automotive high-voltage battery pack monitor with voltage, current and insulation resistance sensing"; AEC-Q100
  grade 1; systematic and hardware capability up to ASIL D; low-side shunt current; isolated differential daisy chain;
  says it "simplifies BJB / BDU system by eliminating safety MCU, CAN transceivers, and multi-wire interface";
  BQ79731-Q1 is the newer generation with coulomb counting.
- r2 section 1-2: connectors are about 8 % of the electrical component cost of an EV propulsion system (their ref 24)
  and cause wire breaks and poor contact under vibration; wired BMS: cell management units (CMUs) linked by wire to a
  central controller; wireless: CMUs talk over the air. Table 2: wired is mature with standards, wireless is emerging
  with "lack of universal standards", lower weight and complexity.
- r2 section 3, Table 3: ADI (ADRF8850 manager, ADRF8800 node, SmartMesh, mesh), TI (CC2662R with BQ79616, SimpleLink
  wBMS protocol, star), NXP (MC33771 + KW37 node, 2 x KW38 + MPC5744P manager, optimised BLE 5.0, star), Dukosi
  (DK8102 / DK8202, one CMU per cell, C-SynQ near-field bus antenna); all 2.4 GHz, 1-2 Mbps, AES-128 or better.
  Slave nodes sit inside the pack and the master can be remote, so security work never stops. GM's Ultium wBMS with
  ADI cut pack wiring "by as much as 90%".
- r3 sections 1-2: zonal power must be protected "directly off the battery, at the zone input level and at the
  output level"; fuse rule of thumb: derate 25 %, then rerate for temperature (91 % at 85 °C, so a 10 A fuse is good
  for 6.825 A); accurate I²t in eFuses lets wire gauge and connectors shrink.
- r4: TPSI3050-Q1 reinforced, 5000 Vrms, 1000 Vrms working, 12 kVpk surge, 10 V gate drive, self-powered secondary,
  $2.30 at 1k; TIDA-050063 HV solid-state active pre-charge without an MCU.
- r5: Si875x self-generates 8-12 V gate drive; at or below 7.5 kHz; Si8751 with 10 kΩ TT about 500 µs to 90 % into
  600 pF (Si8752 at 5 mA about 800 µs); FET choice by Vth, Qg, BVDSS with transient margin and a thermal check.
- r6: WB stretched SOIC-8: 5 kVrms, VIOWM 1500 Vrms, VIORM 2121 Vpk, VIOTM 7070 Vpk, VIOSM 10400 Vpk, creepage and
  clearance 8.5 mm; NB SOIC-8: 2.5 kVrms, 445 Vrms, 630 Vpk, 4.0 mm; CMTI 50 min / 75 typ kV/µs (failure = more than
  100 mV for 1 µs); automotive OPNs -AS / -AS4; battery management systems listed as an application.

## Our reasoning (est)

- Creepage at 400 / 800 V (d2): IEC 60664-1 basic values for pollution degree 2, material group I (about 2 mm at
  400 V, 4 mm at 800 V) doubled for reinforced; the same reading as the site's creepage guide and the traction deep
  dive. Standard not read.
- Market (all est): about 20 M EVs and PHEVs a year; $4-10 of isolation and sensing content per car in the BJB / BMS
  and $2-5 in the DC-DC, from our count of sockets in the block diagram and typical 1k prices seen in earlier reports.
- No FEM in a wBMS (t2, open question): the nodes sit inside a metal pack at short range; our reading, not checked
  against a teardown.
- Cell-to-pack (t6): fewer modules means fewer daisy-chain links; no source read in this run.

## Requests made on 11 Nov 2026

All GET, one at a time, robots.txt first, with the polite reader (tools/research/fetch.sh):
chrismi.sdsu.edu robots.txt and /publications/223.pdf (2 requests, no block). One web search to find an open-access
wireless BMS review. Nothing was requested from qorvo.com, analog.com, nxp.com, onsemi.com, microchip.com or
distributors. One new document in total.
