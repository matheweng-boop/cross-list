# TCU RF front end: 5G / RedCap / satellite NTN / NG-eCall (deep dive, key `tcu_rf`)

Researched 2026-10-21. The summaries are our own wording. Short quotes are marked and cited. The YAML for the app is in `tcu_rf.yaml`.

## References (6)

| id | Document | Type | Why | Read |
|---|---|---|---|---|
| r1 | 3GPP TS 38.101-5 V19.6.0 (ETSI TS 138 101-5, Sep 2026): NR UE radio, satellite access | standard | The normative NTN UE RF spec | §5.2, 6.2.1–6.2.3, 6.5.3, 7.3.2 |
| r2 | 5GAA, *Maximising the benefit of future satellite communications for automotive*, TR v1.0, Sep 2024 | white paper | Automotive NTN link budget and vehicle UE parameters | §5.3–5.4, conclusions (reused download from the feasibility run) |
| r3 | Skyworks SKY5A2110 GNSS L1+L5 FEM data sheet 206174G (Nov 2025) | vendor data sheet | GNSS rejection of the other transmitters in the car | Full |
| r4 | Skyworks 2025 automotive brochure, plus the SKY5A2206 (206993A) and SKY5A2205 (206995B) product summaries | vendor | Sky5A TCU partitioning, power class 2 (PC2), qualification | Telematics and V2X pages, both summaries |
| r5 | arXiv:2203.05634, *Overview of 3GPP Rel-17 RedCap* (Ericsson authors, 2022) | paper | RedCap reductions and what they cost in coverage | Full |
| r6 | arXiv:2412.16611, *A Tutorial on Non-Terrestrial Networks: towards 6G* (2024) | paper | NTN roadmap from Rel-17 to Rel-19 and the step to 6G | §I-A (3GPP releases), skimmed the rest |

URLs are in the YAML. Caveat on r6: its band text has errors. It gives the n255 downlink as "1525 - 1659 MHz" and swaps the Ka uplink and downlink ranges. We took band numbers only from r1.

## Block diagram (our drawing, based on r1–r6)

```
 [Roof module / shark fin]                         [TCU board]
  Cellular main + MIMO (2-4) ──► main/backup ──► TX/RX switch + coupler ◄── LMH PA (PC3; PC2 n40/41) ◄─┐
  eCall backup antenna ────────► switch       └► duplexers ─► DRx/MIMO modules, LNA bank ─────────────►│
  NTN L/S patch (0-3 dBi) ──────────────────────► n255/n256 duplexers ◄─ NTN PA 23/26/31 dBm ◄────────►│ MODEM
                                                                    └─► NTN LNA ─────────────────────►│ (+transceiver)
  GNSS L1/L5 patch ─────────────────────────────► GNSS LNA, pre/post filters (L1 notch B13) ──────────►│ GNSS also gives
  V2X 5.9 GHz (with compensator at the antenna) ─► V2X FEM (PA+LNA+switch) ───────────────────────────►│ NTN timing and Doppler
  Wi-Fi/BT ──────────────────────────────────────► Wi-Fi FEM ─────────────────────────────────────────►│
                                                    PMIC with backup battery, MCU (eCall) ────────────►┘
```

- **Premium TCU:** 4×4 MIMO on the cellular side. Skyworks splits it into a discrete transmit path and integrated receive modules, about 7 parts (r4). NTN runs as its own path. V2X and Wi-Fi are separate front-end modules.
- **Value NG-eCall TCU (RedCap / Cat-1bis):** one transmit chain and 1–2 receivers (r5). It keeps GNSS and the main/backup antenna switch.

## Design rules and numbers, by area

**NTN transmit (r1, Rel-19 text)**
- Power classes for n255/n256:
  - PC3: 23 dBm ±2 dB
  - **PC2: 26 dBm +2/−3 dB**
  - **PC1: 31 dBm +2/−3 dB**
  - The other FR1 NTN bands (n250–n254) have PC3 only.
- The spec notes that PC1 is "not targeted for smartphone form factor", which points at vehicles and fixed terminals.
- With 2Tx or 4Tx, the power class counts the sum over all antenna connectors. The PC1 4Tx MPR table assumes ≥ 15 dB isolation between antennas.
- PC3 power boosting (`powerBoosting-NTN-r19`, plus the Rel-18 pi/2-BPSK/QPSK boosts) raises the reference power. A "23 dBm" NTN PA therefore needs headroom above 23 dBm.
- Regulatory EIRP limits are turned into conducted limits using a 0 dBi reference antenna. Example: n254 at 27 dBm/4 kHz mean. A 3 dBi vehicle antenna therefore eats into the margin; this is our inference.

**n255 is harder than n256 (r1)**
- Duplex gap: n255 downlink tops out at 1559 MHz and the uplink starts at 1626.5 MHz, a gap of **67.5 MHz**. n256 has a 160 MHz gap.
- REFSENS degradation the spec allows at higher power classes:

  | Configuration | n255 | n256 |
  |---|---|---|
  | PC2, 1Tx | 0.8–0.9 dB | 0 dB |
  | PC2, 2Tx | 1.6–1.7 dB | 0 dB |
  | PC1, 1Tx | 2 dB | 1.5 dB |
  | PC1, 4Tx | 3.3 dB | 2.1 dB |

- So the n255 duplexer and transmit noise filtering are where the design is won.

**GNSS coexistence**
- From the spec (r1): when the network signals NS_02N on n255, emissions in 1559–1605 MHz must be ≤ −50 dBm/700 Hz and ≤ −40 dBm/1 MHz, with a ramp up to 1610 MHz. NS_03N on n254 has the same limits with a steeper ramp. n254's uplink at 1610–1626.5 MHz sits right on the RNSS edge.
- In the car (r3): SKY5A2110 L1 out-of-band rejection is specified for these ranges only:
  - 600–1000 MHz
  - 1710–1980 MHz: typ −66 dB, max −47 dB
  - 2.3–2.7 GHz
  - 3.3–5 GHz
  - Wi-Fi bands up to 7.125 GHz: max −42 to −52 dB

  **Nothing is specified at 1610–1660 MHz.** A same-car n255 transmitter at 23–31 dBm is therefore an unspecified blocker today. This is the core of the case for a combined NTN-plus-GNSS design.
- NR-NTN UEs are assumed to have GNSS for timing advance and Doppler (r6). If the car's own NTN transmitter blinds GNSS, it degrades the NTN link too.

**NTN receive and antenna (r2)**
- About 7 dB NF (phone level) is enough for S-band downlink. Antenna gain and transmit power matter more.
- Antenna size:
  - 0 dBi dual-band fits in < 5×5 cm.
  - 3 dBi fits in < 5×5 cm only for one band direction (80–100 MHz).
  - 3 dBi dual-band needs two radiators and more than 5×5 cm.
- Uplink rate runs from < 1 Mbps at 23 dBm / 0 dBi up to about 11 Mbps at 29 dBm / 6 dBi. 5GAA recommends > 23 dBm and > 3 dBi.
- At Ka band, the r2 tables use 1.2 dB NF and 33 dBm (2 W) for broadband terminals. Flat arrays of 25–33 dBi were assessed.

**Cellular / RedCap (r4, r5)**
- RedCap Rel-17 baseline:
  - FR1 bandwidth up to 20 MHz
  - 1 receive branch and 1 MIMO layer at minimum
  - no CA or DC
  - HD-FDD allowed
  - about 85/90 Mbps peak in FD-FDD
  - about 65% lower modem BOM
- With 1 Rx, FR1 downlink needs coverage recovery for random-access Message 2 in urban micro cells. With 2 Rx it does not. Use 2 Rx for emergency-call units.
- SKY5A2206: LMH PA, PC2 on n40/n41 at 4.5 V, APT-optimized, MIPI RFFE v3.0, 4.2×4.3 mm.
- SKY5A2205: 15 TRX ports, separate LB and M/HB antenna ports for downlink CA, harmonics < −50 dBm, IEC antenna ESD, coupler.
- Qualification: AEC-Q104 Grade 2 (−40/+105 °C), PPAP, IMDS. Data sheets give separate limits at NTC, ETC (−30/+85 °C) and A-ETC (−40/+105 °C) (r3), so ask for A-ETC data.

**V2X / Wi-Fi (r3, r4)**
- SKY5A2105 output: +29 dBm for LTE-V2X, +26.5 dBm for NR-V2X (2.5 dB MPR), +26 dBm for 802.11p. It also has a compensator mode for the antenna end of the cable.
- These are the strongest transmitters in the box after an NTN PC1 path. GNSS and Wi-Fi receivers need the rejection figures above.

## Considerations and pitfalls

- **Satellite antenna vs EIRP:** a higher-gain roof patch helps the link but can push EIRP over regulatory limits that the spec writes at 0 dBi.
- **Multi-PA PC1 (4×25 dBm):** this route needs ≥ 15 dB antenna isolation, which is hard in a shark fin that also holds 4 cellular antennas, GNSS and V2X.
- **Cable loss:** with a roof antenna and the TCU in the dash, coax loss eats the PC2 gain. Antenna-side PA/LNA (compensator) is the known fix in V2X (r4) and applies to NTN. This is our inference; no NTN compensator is specified.
- **Value TCUs:** most of the RF front-end cost sits in duplexers. HD-FDD RedCap (r5) can replace them with a switch, but loses FD throughput.
- **Catalogue data:** `data/catalog/skyworks_parts.yaml` gives SKY5A2206 the description of SKY5A2205 and the function `rf_frontend`. The product summary says it is a PA module. Flag this for a fix (we did not edit the repo).

## NG-eCall (crash survivability, backup antenna)

Not verified from primary sources:
- UN R144 is on unece.org, which returned a Cloudflare 403. The host is stopped.
- CEN/TS 17184/17240 is paywalled.
- EUR-Lex was blocked in the earlier run.

What we know from snippets (low confidence):
- R144 covers accident emergency call components and systems, with mechanical impact and vehicle crash tests (R94/R95). Its scope excludes the communication module and antenna functions "unless otherwise prescribed".
- EU 2017/79 has a crash-resistance annex aimed at the audio equipment.

Practice we saw: Tier-1s offer an optional backup battery and backup cellular antenna (AUMOVIO page, snippet), and Qorvo sells an antenna routing switch, QPC1251Q (catalogue).

Design consequence (judgement): the backup path is a switch plus a small antenna on or near the TCU. It has to work after a crash with the roof antenna gone, so the main/backup switch must be in the TCU, not in the roof module.

## Research trends

1. **Now (r1):** Rel-19 brings PC2 and PC1 for n255/n256, 2Tx/4Tx options and power boosting. 5GAA's vehicle ask (r2) is met in power, though vehicle antenna gain is still at 0 dBi in the spec.
2. **Now (r1, r6):** the band list grows to n250–n256 at L/S band, plus Ku (n247/n248, n508/n509) and Ka (n510–n512).
3. **Next 2–3 years (r6):** RedCap over NTN, IoT-NTN uplink capacity (OCC), regenerative payloads, and a study of GNSS-independent operation.
4. **RedCap evolution (r5):** Rel-18 continues device reduction (eRedCap). We did not read a primary eRedCap spec here.
5. **5+ years (r2):** vehicle terminals become their own NTN UE type. Ka flat arrays after 2030.
6. **5+ years (r6):** NTN is built into 6G from the start, with integrated TN/NTN and direct-to-device.

## Where Skyworks/Qorvo parts sit

| Function | Parts (repo catalogue) | Gap |
|---|---|---|
| pa_module | SKY5A2206 (PC2 n40/41); SKY68040-11 (n255/n256, not automotive) | No automotive NTN PA; no 26/31 dBm NTN |
| rf_frontend | SKY5A2205, SKY5A3048 | — |
| lna / diversity_rx_module | SKY5A2203; SKY5A5010/5005/5009 | No NTN downlink LNA; oversized for RedCap |
| gnss_lna | SKY5A2110 | Rejection at the NTN uplink not specified |
| v2x_fem | SKY5A2105, QPF1004Q | — |
| antenna_switch (catalogue: rf_switch) | QPC8013Q, QPC8020Q (AEC-Q100), QPC1251Q (antenna routing) | — |
| filter_saw_baw | QPQ1040Q/1041Q (B40/B41), QPQ2200Q/2230Q (V2X) | No n255/n256 duplexer |
| diplexer | — | Opportunity: GNSS-protecting n255/n256 duplexers |

## Open questions

- See `open_questions` in the YAML.
- Biggest unknowns: the in-car GNSS blocking level at the n255 uplink; NG-eCall antenna and crash requirements (primary text blocked); SKY68040-11 output power and automotive capability.

## Sources tried but blocked or skipped

- **unece.org** (UN R144): robots.txt returned 403 behind a Cloudflare challenge. The host is stopped, and we did not work around it.
- **api.openalex.org:** already stopped by an earlier run, so we found the papers by web search and fetched them from arXiv (one /pdf each).
- **u-blox SARA-S528NM10 integration manual** (NTN + GNSS in one module): no public URL found; Mouser-hosted copies are not allowed.
- **globalautoregs.com:** robots.txt allows /documents, but the R144 texts link to unece.org, so we fetched nothing more.
- **arXiv 2312.15174** (Rel-19 overview): an earlier run already fetched its /abs page, so the one-request-per-paper rule kept us from fetching the PDF.
