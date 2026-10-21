# Multi-radio roof and smart-antenna module: coexistence, filtering and EMC (deep dive, topic `roof_coexistence`)

Date: 2026-10-21. Public sources only, about 20 GETs through `fetch.sh` (logged in `research/requests.log`) plus WebSearch for discovery.
Downloads are in `research/dl/deep/roof_coexistence/`. The Oakland dissertation was reused from `research/dl/ad/` (fetched 2026-10-20), and ETSI EN 302 571 from `research/dl/docs/`.
Confidence: **high** = primary document read; **med** = vendor claim or secondary description of a paid standard; **low** = snippet.
Context read: `notes/wifi_roof.md` (roof TCU evidence from LG, Harman and Continental) and `notes/auto_connectivity.md` (V2X/Wi-Fi filters, glass roof, AEC-Q104).

## 1. References (the six)

| id | Reference | Type | Year | Why | Licence |
|---|---|---|---|---|---|
| r1 | ETSI EN 302 571 V2.1.1, ITS 5 855-5 925 MHz harmonised standard (etsi.org) | standard | 2017 | V2X emission, blocking and selectivity numbers and CEN DSRC protection | free; no reproduction |
| r2 | Com-Power, *Automotive EMC Testing: Meeting ISO 11452 and CISPR 25 Requirements* v1.0 (com-power.com) | app note | 2025 | Free secondary description of the CISPR 25 / ISO 11452 setups and typical levels | (c) Com-Power |
| r3 | A. Ibrahim, *Compact multi-band (5G/GNSS/V2X) antenna and glass-roof analysis*, PhD dissertation, Oakland Univ. (our.oakland.edu) | paper | 2023 | Measured fin-antenna and glass-roof data, plus the active GNSS chain | (c) author, open in repository |
| r4 | A. Bawangaonwala (Qorvo), *Mitigating Spectrum Coexistence of V2X Systems with High-Performance Filters*, Microwaves & RF | app note (vendor article) | 2020 | Isolation versus filter trade (LTCC compared with BAW), Wi-Fi-path notch, ETC | (c) publisher/author |
| r5 | A. Leiba (GM), *Rethinking vehicle connectivity: the integrated Connectivity Hub Module (CHM)*, engineering.gm.com | white paper | 2026-05-27 | OEM primary source: TCU, radios and antennas in the roof with an Ethernet interface; desense, coexistence and thermal | (c) GM |
| r6 | M. Steer, *Microwave and RF Design IV: Modules*, ch. 4 (4.4-4.7), LibreTexts | textbook | 2019 | Desense mechanisms: compression, IM3 and IP3, SFDR/DR, phase noise, PIM | CC BY-NC (book), page footers say "not declared" |

Also read but not counted among the six:
- **TI SLLA569B**, *Understanding CISPR25 Current Probe and Voltage Method for Conducted Emissions* (2022, rev. 2025). It gives the LISN setup, unit conversions (dBuV = dBuA + 20log Z; dBm = dBuV - 10log Z - 90) and a table of CISPR 25 Class 5 peak conducted limits (e.g. 76-108 MHz FM: 38 dBuV; 0.53-1.8 MHz AM: 54 dBuV). Its first row reads "0.15 to 30 MHz 70 dBuV", which looks like a typo for 0.15-0.3 MHz, so treat it with caution. It states that CISPR 25 covers 150 kHz to 2.5 GHz, while r2 says Ed. 5 extends to 5.925 GHz (edition difference).
- **Steer vol. I ch. 3 and 5** index pages (no nonlinear content; not used).
- Qorvo's own white paper on the same topic sits on www.qorvo.com and was **not requested** (forbidden host). r4 is the author's trade-press version of it.

## 2. Block diagram (drawn by us)

```
 [Roof antennas]          [Antenna-side filters]     [Active antenna]            [Roof TCU front ends]        [Transceivers]        [Digital link]     [Zonal/central]
  4G/5G MIMO 617-5925 ──►  BAW band-pass / notch ─►  GNSS pre-filter+LNA ─────►  cellular TX FEM / PAMiD ──►  5G modem (+NTN) ──►  Automotive     ──►  central computer
  GNSS L1/L5               GNSS/SDARS diplexer       SDARS LNA                    MIMO diversity RX             Wi-Fi/BT SoC          Ethernet PHY        / zone ECU
  V2X 5.9 GHz              cellular multiplexer      V2X compensator/FEM          Wi-Fi FEM + 5.9 GHz notch     V2X modem             (SerDes option)
  Wi-Fi/BT, UWB            band/antenna switch       AM/FM amplifier              UWB FE
  SDARS/AM-FM/DAB                    │                      │
                                     │                      └── legacy coax (up to ~5 m) ──► head-unit AM/FM/DAB tuner, SDARS demod, cabin TCU
                             [Power/protection: wide-Vin buck, low-noise LDO for LNAs (phantom feed), TVS/ESD]
```

How to read it:
- **Classic architecture (r5):** a fin with passive or active antennas, and coax runs of up to about 5 m to a TCU in the cabin. Gain has to sit at the antenna (GNSS active antenna with SAW + about 28 dB LNA, r3; V2X compensator), because coax loss before the first LNA adds directly to the noise figure.
- **Integrated architecture (r5):** the "Connectivity Hub Module" puts network processors, memory, RF transceivers, antenna arrays and an OnStar backup battery in one sealed roof unit. It presents "a clean, high-bandwidth digital interface" (Ethernet) to the vehicle. LG, Harman and Continental build the same class of product (see `wifi_roof.md`).
- **Coexistence filters** go in two places: on the **aggressor** (a 5.9 GHz notch on the Wi-Fi TX path removes PA wideband noise in the V2X band) and on the **victim** (a V2X B47 BAW band-pass rejects UNII-1..3; GNSS pre-filters reject cellular). See r4.

## 3. Desense mechanisms (what to budget)

| Mechanism | What happens | Budget lever | Source |
|---|---|---|---|
| Blocking / compression | A strong off-channel transmitter compresses the LNA or mixer and lowers its gain | Antenna isolation + victim pre-filter; LNA P1dB/IIP3 | r1 (blocking at least -30 dBm), r6 |
| Wideband noise (TX noise) | The aggressor PA noise floor lands in-band at the victim and cannot be filtered at the victim | **Notch/band-stop on the aggressor path** (e.g. 5.9 GHz notch on Wi-Fi, up to 18 dB desense without it) | r4 |
| Harmonics | nxf of a transmitter lands in another receive band (e.g. 2 x B13 UL 777-787 MHz gives 1554-1574 MHz, next to GNSS L1) | PA harmonic filter, linear switch, GNSS pre-filter/notch | r6 + our arithmetic; Skyworks' older "GNSS FEM with B13 notch" parts corroborate |
| Intermodulation | Two transmitters (e.g. cellular + Wi-Fi) mix in a nonlinear stage; IM3 rises 3:1 | IIP3 budget; SFDR = 2/3 (IIP3 - N) | r6 |
| Reciprocal mixing | A strong close-in blocker mixes with the receiver LO phase noise | LO phase noise L(Δf) at the blocker offset | r6 (phase-noise definition; the formula in d8 is our derivation) |
| Passive IM (PIM) | Contacts, ferromagnetic plating (nickel) and dissimilar metals generate IM in "linear" parts | Mechanical design of the fin and connectors; low current density | r6 |
| Self-generated digital noise | GbE switch, DDR, PCIe and SMPS noise raise the noise floor of GNSS and cellular | Multi-cavity shields, ground planes, buried stripline, spread-spectrum clocks, drive strength, local filters | r5 |

## 4. Design rules (summary; full list with refs in the YAML)

1. **Budget = antenna isolation + filter rejection.** With LTCC only on the V2X path, more than 80 dB of isolation is needed for a 1 km V2X link next to 5 GHz Wi-Fi. With a B47 BAW in the TCU, about 15 dB is enough. With more than 20 dB, one coexistence filter in the active antenna may be enough (r4, med: vendor 2020).
2. **Notch the aggressor:** a 5.9 GHz notch on the 5 GHz Wi-Fi TX path; up to 18 dB of V2X desense without it (r4).
3. **EU V2X limits (r1):** 33 dBm e.i.r.p.; 23 dBm/MHz; OOB 5835-5855 and 5925-5945 MHz at or below -30 dBm/MHz; spurious 1-18 GHz at or below -30 dBm/MHz (below 1 GHz: -36 dBm e.r.p./100 kHz). In-band mask -26/-32/-40/-50 dBc at ±5/5.5/10/15 MHz. Receiver spurious -47 dBm e.i.r.p. per MHz (1-18 GHz); in the tolling band 5795-5815 MHz, -60 dBm (antenna ≤2 m high) or -65 dBm. Receiver blocking at least -30 dBm at ±50/100/200 MHz. ACR/AACR 16/32 dB (BPSK 1/2) down to -1/15 dB (64-QAM 3/4). Frequency stability ±20 ppm. TPC range from 3 dBm up to the maximum.
4. **ETC (CEN DSRC) protection:** a notch at the V2X FEM input to reach -65 dBm/MHz at 5795-5815 MHz (r4, r1).
5. **Linearity math (r6):** IIP3 = OIP3 - G; SFDR = 2/3 (IIP3 - N_i); DR_i = 2/3 (IIP3 - N_i - SNR_min). P1dB does not set dynamic range, but modulated signals are backed off from P1dB by the PMEPR.
6. **Harmonic plan:** check n x f of each transmitter against each receiver (B13 to L1 is the classic case).
7. **PIM:** no nickel or steel in the RF current path, no dissimilar-metal pressure contacts, keep current density low (r6).
8. **Integrated module EMC:** shields, planes, stripline, SSC clocks, slew/drive tuning, filtering at the source (r5).
9. **Three-layer coexistence:** isolation (spatial diversity, orthogonal polarization), acoustic filters, TDM scheduling in software (r5).
10. **Cable loss:** up to about 5 m of coax in the classic architecture, with "several dB" lost at GHz (r5, no exact number). Use an active antenna (GNSS about 28 dB LNA after a SAW, r3) or integrate the radio at the antenna.
11. **Thermal:** sealed module, no fan; cast-aluminium housing as the heat sink, TIMs, software throttling of TX power and compute; a battery in the roof makes it harder (r5).
12. **Glass roof:** about 8 dB average gain loss at 5.9 GHz on a full glass roof compared with a metal ground plane, with deep side nulls. The cause is the low-E/metallic coating; moving the coating to the top surface helps (simulated) (r3).
13. **Fin envelope:** under 70 mm high and under 120 mm long. More antennas mean more coupling and shadowing, so prefer multi-band elements: a 617-5925 MHz + GNSS L1 folded monopole at 58 x 37 x 17 mm with 50-90 % efficiency and -2.2 to 3 dBi linear-average gain (r3).
14. **EMC test plan (r2, secondary):** CISPR 25 in an ALSE (shielding over 80 dB, absorber reflectivity under -10 dB), DUT 50 mm above a ground plane of at least 2 x 2 m, antenna at 1 m, both polarizations, bands from 150 kHz up to 5.925 GHz (Ed. 5); conducted 150 kHz-108 MHz (voltage), current probe up to 245 MHz per TI. ISO 11452-2 ALSE 200 MHz-18 GHz, typically 30-200 V/m set by the OEM, 1 kHz 80 % AM, at least 2 s dwell. ISO 11452-4 BCI 1-400 MHz, typically 60-200 mA. ISO 7637-2 transients (load dump pulse 5 up to +123 V) on the supply.

## 5. Considerations and pitfalls
- **Victim-side filtering cannot remove aggressor wideband noise.** Both sides need filters (r4). This is the most common mistake when Wi-Fi is added to a module that already has V2X.
- **LTCC is not enough** at 5.9 GHz: it gives broadband rejection but none in UNII-1..3 (r4).
- **The integrated roof module trades one problem for another:** no cable loss, but the noise floor rises from on-board digital noise, and the module is thermally sealed (r5).
- **Even without built-in Wi-Fi**, passengers' phone hotspots on 5.6-5.9 GHz are aggressors to V2X (r4).
- **Glass-roof data exist only at 5.9 GHz** (r3). There are none for Wi-Fi 6 GHz or cellular n77/n79.
- **CISPR 25 limits are in the paid standard.** The figures here are secondary (r2, TI), and OEM specifications (Class 3-5 and the OEM's own lines) override them.

## 6. Research trends
- t1 **TCU into the roof** with an Ethernet interface (GM CHM 2026; LG in mass production in Aug 2026; Harman SCA; Continental IAM). Status: now; high.
- t2 **Board-level desense and coexistence** becomes the hard limit instead of cable loss (r5). Status: now.
- t3 **Wi-Fi 5/6 GHz around the 5.9 GHz ITS band** needs BAW band-pass + notch pairs (r4, r1). Status: now.
- t4 **Glass roofs** move antennas under the roof or into the glass and need compensation (r3). Horizon: 2-3 years.
- t5 **CISPR 25 Ed. 5 up to 5.925 GHz** (r2). Status: now (secondary source).
- t6 **Multi-band radiators** in the fin push selectivity onto multiplexers and filters (r3). Horizon: 2-3 years.
- t7 **Sealed-roof thermal limits** call for high-temperature FEMs and TX throttling (r5). Horizon: 2-3 years.
- Not verified here, and kept out of the YAML: **digital RF-over-fibre or SerDes from the roof**, **transparent and on-glass antennas** for 5G/V2X (OpenAlex results showed transparent antennas for glasses, not cars), and **NTN in the roof module**. A follow-up should look for an open paper on each.

## 7. Where Skyworks/Qorvo parts sit (catalogue data, read-only)
- **Coexistence BAW filters:** SKY5A1005 (C-V2X notch, 5855-5925 MHz, for the Wi-Fi path), SKY5A1006 (5 GHz Wi-Fi 5170-5835 MHz), SKY5A1008 (6 GHz Wi-Fi 5945-7125 MHz). All three are Preview and automotive. From Qorvo: QPQ2200Q (5.855-5.925 GHz BAW band-pass, 1.3 dB IL), QPQ2230Q (V2X notch), QPQ2254Q (2.4 GHz WLAN BAW). This matches the r4 recipe of a band-pass on V2X and a notch on Wi-Fi. **There are two overlapping product lines, so plan the portfolio.**
- **V2X FEM / compensator:** SKY5A2105 (Preview), SKYA21043 (DSRC), QPF1004Q, QPF1005Q, QPF4554Q (Wi-Fi + C-V2X).
- **GNSS:** SKY5A2110 (automotive L1+L5 with pre- and post-filters). **SDARS:** QPL6202Q/QPL6220Q LNAs, TQM2M9016 SDARS/GPS diplexer.
- **Cellular in the roof TCU:** Sky5 automotive FEMs (SKY5A3036, SKY5A3047), PA module SKYA21055, diversity RX SKY5A5003/SKY5A5009, switches SKY5A5110, SKYA21003, QPC8013Q.
- **Wi-Fi:** SKYA21040/41 (AEC-Q100 switch/LNA front ends).
- **Broadcast** (stays at the head unit): Si479xx tuners, Si469xx coprocessors.
- **Gaps:** no catalogue part is flagged for automotive NTN or UWB front ends at the roof. Check Grade 1 availability internally.

## 8. Open questions
See the YAML `open_questions`. The most important: which radios GM, LG and Harman roof modules actually integrate (V2X, SDARS?); the OEM thermal grade for the roof; the isolation actually achieved in integrated modules; and the current CISPR 25 edition and limit lines.

## 9. Sources tried, blocked or limited
- **api.openalex.org:** two searches returned 200 (oa1, oa2). The host was then **stopped after a 429**, triggered by a parallel run's query seconds later. The stop was respected, and further discovery used WebSearch.
- **www.mwrf.com:** the article was fetched with 200. The helper then flagged a "checkpoint" because the page contains reCAPTCHA script names, which is a false positive. The host is now stopped and no further requests were made. The text used is from that single 200 response.
- **ti.com/lit/pdf/slla569** returned a 302 to /lit/ab/slla569b/slla569b.pdf, which was then fetched directly (robots allows /lit).
- **engineering.gm.com/robots.txt** returned a 302 to a 404 page (no robots file), which was treated as no restrictions. One article page was fetched.
- Not requested: www.qorvo.com (Qorvo V2X coexistence white paper; forbidden host), IEEE Xplore and MDPI papers that OpenAlex listed (blocked hosts), the paid CISPR 25 and ISO 11452 standards, and Google Patents (stopped earlier).
- Not used to avoid duplication with sibling topic runs: ETSI EN 303 413 (GNSS, `gnss_frontend`) and the C2C-CC coexistence paper (`v2x_frontend`).
