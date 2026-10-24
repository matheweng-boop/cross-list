# Drone radio links: control, video, GNSS, Remote ID, ADS-B In (deep dive, key `drone_radio_links`)

Researched 2026-10-24. The summaries are our own wording. The YAML for the app is in `drone_radio_links.yaml`.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | 47 CFR 15.247 (Cornell LII) | (a)-(d) in full |
| r2 | ETSI EN 300 328 V2.2.2 (2019-07) | Clauses 4.3.1-4.3.2 (RF output power, PSD, adaptivity, MU) |
| r3 | 14 CFR 89.310 (Cornell LII) | Full section |
| r4 | FAA Remote ID page (last updated 19 Mar 2025) | Full page |
| r5 | Skyworks SKY55951-11 data sheet 205521I (2 Mar 2026) | Features, Tables 2, 4, 5 |
| r6 | Our catalogue (Skyworks and Qorvo public product pages, 19 Oct 2026) | Band edges, power, gain per part |

## Key numbers taken

- r1: 1 W peak conducted (FHSS >= 75 ch at 2.4 GHz, all 5.8 GHz FHSS, >= 50 ch at 915 MHz, digital modulation);
  0.125 W for 2.4 GHz FHSS < 75 ch; 0.25 W for 915 MHz FHSS with 25-49 ch; 6 dBi antenna cap, 1:1 reduction above;
  hop counts 50 / 25 (915 MHz), 15 (2.4 GHz), 75 (5.8 GHz); digital modulation 6 dB BW >= 500 kHz; out-of-band
  20 dB below in-band in any 100 kHz.
- r2: FHSS and wideband 20 dBm EIRP; non-FHSS PSD 10 dBm/MHz; adaptive above 10 dBm EIRP; LBT threshold
  -70 dBm/MHz + 10 log(100 mW / Pout).
- r5 L1: gain 17 dB, NF 1.4 dB, IP1dB -29 dBm, IIP3 -21 dBm, 1 mA; rejection 93 dB (777-798 MHz), 87 dB (806-928),
  70 dB (1710-1980), 77 dB (2400-2500), 69 dB (5160-5560); B13 2nd harmonic -53 dBm. L5: gain 17.5 dB, NF 1.1 dB,
  IP1dB -13.8 dBm, 1.9 mA; rejection 56 dB (1710-1980), 48 dB (2400-2500), 52 dB (5160-5560). Absolute max RF input
  +10 dBm. Nothing specified at 5725-5850 MHz.

## Our reasoning (est)

- 16 dB EIRP gap US vs EU at 2.4 GHz = about 6.3x free-space range.
- Antenna diversity against pattern nulls; 2nd / 3rd harmonics of 915 MHz at 1830 / 2745 MHz.
- Trends t3-t5 (chirp control links, digital video, jamming) from general knowledge, marked low confidence.

## Not read / blocked

- ASTM F3411 (paywalled); EU 2019/945 and ERC Rec 70-03 (EUR-Lex unreachable earlier); 14 CFR 107.53 (ADS-B Out ban)
  not fetched in this run; Skyworks drone / UAV pages not checked.
