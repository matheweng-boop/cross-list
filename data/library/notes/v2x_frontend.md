# V2X 5.9 GHz front ends and coexistence with car Wi-Fi (topic key: v2x_frontend)

Deep-dive notes, 2026-10-21. These are our own summaries. Quotes are under 25 words and cited. The app data is in
`v2x_frontend.yaml` in the same folder. Downloads are in `research/dl/deep/v2x_frontend/`. The SKY5A2105 and SKY5A1005/1006
product summaries and the 5GAA FAQ came from earlier runs and are in `dl/cv/` and `dl/ad/`.

## References (the six)

| id | Document | Type | Why | Licence |
|---|---|---|---|---|
| r1 | ETSI EN 302 571 V2.1.1 (2017-02), ITS radio equipment 5855–5925 MHz | Standard | Legal EU RF limits (power, PSD, mask, OOB, blocking, selectivity, tolling) | Free; no reproduction (paraphrased) |
| r2 | 3GPP TR 38.886 V16.3.0 (2021), NR-V2X UE RF | Standard (TR) | n47 power class, MPR/A-MPR, G_post_connector, ACLR, EVM, REFSENS, ACS, LTE/NR TDM on one PA | © 3GPP; paraphrased |
| r3 | Skyworks SKY5A2105 product summary 206756A (Nov 2023) | Vendor | Our reference V2X FEM | Public PS |
| r4 | C2C-CC WP 2084 MCO Part 2: technical capabilities and limits (2020) | White paper | What limits several V2X channels in one area; 802.11bd features | No reproduction (summarised) |
| r5 | C2C-CC WP 2091 Co-channel coexistence mitigation methods (2021) | White paper | ITS-G5 + LTE-V2X in the same channel (ETSI TR 103 766 methods A–F) | No reproduction (summarised) |
| r6 | Choi et al., "Survey of Spectrum Regulation for ITS", IEEE Access 2020 (arXiv 2008.00084) | Paper (OA) | DSRC / C-V2X / UNII-4 Wi-Fi sharing by region; Wi-Fi adjacent-channel results | CC BY 4.0 |

Supplementary, read but not in the six:
- C2C-CC WP 2098 "IEEE 802.11bd: the V2X evolution" (2023): 256-QAM, LDPC (2–3 dB), DCM (3 dB), 20 MHz from two 10 MHz channels, 60 GHz mode, ranging.
- 5GAA 5.9 GHz Second R&O FAQ (2025): US C-V2X uses 5905–5925 MHz (20 MHz) first, then 5895–5905 MHz, which "would require a second C-V2X radio". DSRC ends 14 Dec 2026. Geofenced higher OBU power has no FCC certification process yet.
- SKY5A1005 / SKY5A1006 product summaries (Dec 2025).
- arXiv 2501.17878 (SL-U and Wi-Fi coexistence, 2025): this is about the MAC/LBT and IIoT, not automotive RF, so we did not select it.

## Block diagram explained

The drawing is ours, built from r1–r5. One V2X path is a T/R switch (SP4T in SKY5A2105, which also has a BAW-bypass state), a
BAW band-pass for 5855–5925 MHz, a PA, an LNA, a digital step attenuator (DSA), a log power detector and a temperature sensor.
It can sit:
- **At the antenna (compensator mode).** The LNA comes before the coax, so cable loss does not add to the noise figure. The DSA
  (0–31.75 dB in 0.25 dB steps over SPI) trims the gain to the measured cable loss, and the detector closes the TX power loop.
- **In the TCU/ECU (ECU mode).** GPIO sets the DSA in 5 dB steps. The PA must then also drive the cable loss to reach the EIRP
  limit.

A dual-carrier car (US 20 + 10 MHz, EU ITS-G5 + C-V2X) needs two paths today. The car Wi-Fi FEM (5/6 GHz) on the same roof
needs its own filter (V2X notch or 5 GHz BAW) to keep its emissions out of 5855–5925 MHz. The V2X receiver cannot filter out
emissions that fall inside its own channel (r4).

## Design rules (short form; full list with numbers in the yaml)

1. **EIRP-based power:** 33 dBm e.i.r.p. and 23 dBm/MHz in the EU (r1). In 3GPP the limit is 33 − G_post_connector dBm, or
   10 − G in a tolling zone (r2).
2. **Per waveform:** SKY5A2105 gives LTE +29, NR +26.5 (2.5 dB MPR) and 11p +26 dBm (r3). NR-V2X PC3 in n47 is 23 dBm (r2).
3. **MPR (PC3 NR-V2X):** 2.5 dB inner / 4.5 dB outer for QPSK–64QAM, 7.0 dB for 256QAM. RAN4 assumed one PA shared between LTE
   and NR, calibrated to −30 dBc ACLR (r2).
4. **A-MPR grows with gain after the connector:** step 0.5 dB per dB on most channels, 0.7–1.2 dB at 5860 MHz (r2). A
   compensator gain is not free.
5. **Mask:** −26/−32/−40/−50 dBc at ±5/±5.5/±10/±15 MHz, absolute at 33 dBm (r1). ACLR 30 dB (r2). The TX mask, not RX
   selectivity, limits multi-channel operation (r4).
6. **EVM:** 8 % for 64QAM and 3.5 % for 256QAM (r2). 802.11bd brings 256-QAM to ITS-G5 too (r4).
7. **OOB:** −30 dBm/MHz e.i.r.p. in 5835–5855 and 5925–5945 MHz, and spurious from 1 to 18 GHz. Tolling at 5795–5815 MHz is
   protected. TPC must reach down to 3 dBm (r1).
8. **Blocking:** at least −30 dBm at ±50/100/200 MHz (r1), so the BAW goes before the LNA.
9. **Sensitivity:** ETSI −85 dBm (assumes NF 10 dB) (r1); EN 302 663 −88 dBm (r4); NR n47 −92.5 dBm at 10 MHz with 13 dB NF
   assumed (r2). Coax loss ahead of the LNA adds dB for dB to the NF (basic RF; our addition).
10. **Wi-Fi coexistence:** leakage inside the V2X channel has to be removed at the Wi-Fi transmitter and by antenna isolation
    (r4, r6).
11. **Own two radios:** an adjacent-channel transmitter at 23 dBm can push the victim's CSMA energy-detect level up to about
    15 m away (about 5 m with a better mask). At <2 m, overloading and intermodulation depend on the architecture (r4).
12. **NR + LTE in n47:** TDM only, one PA as the baseline, 150 µs switching. Dual PAs could switch faster (r2).
13. **Co-channel method C:** a 40 µs 11p header in front of the LTE subframe leaves about 30 µs for TX/RX switching (r5).
14. **Closed loop:** the detector covers >25 dB, while the TPC span is about 30 dB. Check the bottom end (r1, r3).
15. **Duty cycle:** bursts ≤ 4 ms and ≤ 3 % (r1). AEC-Q104 Grade 2 is 105 °C (r3).
16. **RX-mode emissions:** ≤ −60 dBm e.i.r.p. in 5795–5815 MHz (r1).

## Considerations and pitfalls

- **Compensator trade-off.** The compensator removes cable loss from both the NF and the PA requirement. But under 3GPP, any
  declared gain after the connector raises A-MPR, so a hot compensator costs back-off on NR (r2). EU EIRP limits apply after the
  antenna in any case (r1).
- **Absolute mask.** The ETSI mask is absolute. A low-power device gets no relief, so PA leakage at back-off still matters
  (r1, r4).
- **US UNII-4.** Our 5855–5925 MHz BAW (QPQ2200Q, inside SKY5A2105) passes all of UNII-4 above 5855 MHz. In the US, the only
  protection is the Wi-Fi-side filter and antenna isolation. A 5895 MHz guard BAW would need a far steeper edge than
  SKY5A1005's 40 MHz transition (feasibility not known; see the case file).
- **Mode switching.** Co-channel method C and LTE/NR TDM both need fast waveform and power changes (≈30 µs and 150 µs) through the
  same PA, switch and DSA (r2, r5).
- **Glass roofs.** About 8 dB loss at 5.9 GHz, from earlier notes (wifi_roof.md, row 14; low confidence, not from the six
  references).

## Research trends

- Multi-channel operation in the EU, with a TX mask per power class proposed (r4).
- ITS-G5 / LTE-V2X co-channel coexistence: only dynamic method C is viable, and NR cannot share a channel with LTE-V2X (r5).
- NR-V2X and LTE-V2X time-shared on one PA in n47, with dual PAs as the faster option; channels up to 40 MHz (r2).
- 802.11bd: 256-QAM, LDPC, DCM, 20 MHz and 60 GHz (r4; WP 2098).
- US: UNII-4 Wi-Fi directly next to C-V2X (r6); C-V2X only from 14 Dec 2026 (5GAA FAQ, supplementary).
- Beyond the six references: Rel-18 sidelink in unlicensed 5/6 GHz (SL-U, n46/n96/n102). We saw it only in an arXiv MAC paper and
  in search snippets; low confidence.

## Where Skyworks/Qorvo parts sit

- **v2x_fem:** SKY5A2105 (Preview; LTE/NR/11p; compensator and ECU modes), SKYA21043 (11p only), QPF1003Q and QPF1002Q (Qorvo).
  All have one path.
- **filter_saw_baw:** QPQ2200Q (5855–5925 MHz band-pass), SKY5A1005 / QPQ2230Q (V2X notch, ≥30 dB, 40 MHz transition), SKY5A1006
  (5 GHz Wi-Fi up to 5835 MHz), SKY5A1008 (6 GHz).
- **wifi_fem:** QPF4554Q (Wi-Fi/C-V2X, 5.18–5.925 GHz, Preview).
- **gnss_lna:** SKY5A2110.
- **Gaps:** a dual-path V2X FEM, a US guard BAW, and a PA linear enough for 256-QAM, 40 MHz and two carriers.

## Open questions

These are listed in the yaml: whether a newer EN 302 571 exists; the A-MPR budget for a compensator; the US FCC OBU limits from
the primary source; concurrent two-carrier IM targets; roof antenna isolation; PC2 use in n47; and whether the SKY5A2105
detector covers the full TPC span.

## Sources tried but blocked or not used

- api.openalex.org: stopped earlier in this session after a 429. We did not retry and used web search for discovery instead.
- docs.fcc.gov, federalregister.gov and rosap.ntl.bts.gov: stopped earlier (403). So the FCC Second R&O text and the USDOT
  UNII-4 interference report were not read.
- 3GPP TR 38.886 zip: the download was cut off at 1.998 of 2.12 MB. The main document text was recovered from the partial
  archive and is complete through clause 10.x; the tail (annexes) may be missing. We did not refetch it.
- arXiv 2501.17878 (SL-U and Wi-Fi): read, not selected (MAC-level, not automotive).
