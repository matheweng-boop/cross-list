# Deep dive: automotive multi-band GNSS front ends (gnss_frontend)

Retrieved 2026-10-21 (SKY5A2110 datasheet reused from the 2026-10-20 download). These are our own summaries. Quotes are
under 25 words and cited. Files are in `research/dl/deep/gnss_frontend/`; the SKY5A2110 datasheet is in `research/dl/gn/`.

## References (6)

| id | Document | Type | Why we chose it | What we read |
|----|----------|------|-----------------|--------------|
| r1 | ETSI EN 303 413 V1.2.1 (2021-04), *GNSS receivers, 1164–1300 MHz and 1559–1610 MHz; Harmonised Standard (RED)* | standard | The EU radio-spectrum requirement every GNSS receiver in a car sold in Europe has to meet: receiver blocking and spurious emissions | Full text: clauses 4.2, 5.4, Annexes B and C |
| r2 | u-blox ZED-X20P Integration manual R05 (UBXDOC-963802114-12901), 2026 | app_note | Current all-band (L1/L2/L5/E6, L-band) receiver. Gives antenna-side gain, NF, rejection and group-delay requirements, a rejection-budget method, the B13/B14 harmonic notch, and AGC/spectrum monitoring | Ch. 1.2, 1.4, 2.2.3, 4.2–4.4, 4.7.4 |
| r3 | Skyworks SKY5A2110 datasheet 206174G (Nov 2025) | app_note (datasheet) | Our automotive L1 + L5 module. Measured out-of-band rejection per aggressor band, B13 harmonic, gain under +10/+15 dBm blockers | Tables 2–9, block diagram, evaluation board |
| r4 | Vana & Bisnath, "Low-cost, triple-frequency, multi-GNSS PPP and MEMS IMU integration…", *NAVIGATION* 70(2), 2023 (CC BY 4.0) | paper | Land-vehicle (ITS/L3) study that measures what dual and triple frequency buy with a low-cost patch antenna | Abstract, intro, Table 2, conclusions |
| r5 | Kazim, Darwich, Marais, "GNSS jamming detection with AGC and C/N0 observables from a COTS receiver", arXiv 2602.12688, 2026 | paper | Interference monitoring with front-end observables (AGC versus C/N0). Measured detection and false-alarm rates | Full text (7 pp.) |
| r6 | Steer, *Microwave and RF Design IV: Modules*, §4.3 "Noise Characterization" (LibreTexts) | textbook | Friis cascade, attenuator NF and the "low-noise first stage" rule, which together explain the pre-filter versus post-filter trade | Full section |

Competitor context reused from the case file and earlier downloads (not counted as references): TI TRF3302-Q1, a Grade 1
LNA covering 1165–1630 MHz (`dl/gn/ti_trf3302.txt`), and the u-blox ZED-X20K product summary (`dl/gn/zedx20k.txt`).

## Block diagram explained (our drawing, from r2, r3, r6)

```
 roof / shark fin                                                       | TCU or ADAS ECU
 [RHCP patch, L1+L2/L5/E6(+L-band)] -> [pre-filter / B13 notch] -> [LNA L1] -> [post-filter L1] -\
                                    \-> [band split] -> [LNA L2/L5/E6] -> [post-filter] -------> [diplexer] == coax (RF + DC) ==> [bias-T + current limit/short detect] -> [GNSS RF_IN: internal LNA/PGA/AGC, 3 RF blocks] -> [PVT/RTK/PPP engine] -> ADAS fusion
 aggressors in the same fin: LTE/5G (B13/B14, n77/n79), V2X 5.9 GHz, Wi-Fi 2.4/5/6 GHz, NTN/MSS uplink    corrections: cellular (NTRIP/SSR) or L-band satellite (separate receiver in u-blox's case)
```

- **Antenna element.** The u-blox manual (r2, Table 63) specifies L1/L2/L5/E6 gain of 3 dBic typ, L-band gain of 4 dBic typ, axial ratio of
  2 dB max at L1 and 2.9 dB max for 1166–1285 MHz, RHCP, and phase-centre variation under 10 mm, all on a 120 mm ground plane.
- **Pre-filter, then LNA, then post-filter.** In an automotive fin the first block has to survive watts of nearby transmit
  power, so a filter or notch sits before the LNA even though its loss adds straight to NF (Friis, r6). SKY5A2110
  puts the B13 notch in the L1 input match. On L5 it relies on a post-filter, which gives less than –70 dB rejection below 1 GHz (r3).
- **Band split and per-band LNA.** SKY5A2110 has two inputs (RFIN_L1, RFIN_L5), two LNAs, a diplexer and one RFOUT (r3, Fig. 1).
  The receiver side has gone single-input: ZED-X20P has one RF_IN feeding "three independently configurable internal LNAs,
  one in each RF path" (r2, §4.3.1), and its antenna spec covers 1166–1285 MHz plus 1535–1602 MHz (L-band included).
- **Cable and DC feed.** The receiver supplies the active antenna over the coax through a bias-T. u-blox asks for an inductor above 500 Ω
  across 1–1.8 GHz, a current limit (a 60 mA example), and short and open detection on ANT_SHORT_N and ANT_DETECT (r2, §3.4, §4.4.1).
  Active antennas typically draw 5–20 mA (r2).
- **Receiver.** An internal LNA, a PGA and AGC feed an integrated spectrum analyser (UBX-MON-SPAN). The PGA value drops when out-of-band
  power arrives (r2, §4.2.3). r5 shows how AGC and C/N0 can serve as jamming flags.

## Design rules (numbers from the sources)

1. **Gain window.** External gain at the receiver input, including cable, filter and connector losses, must be 17–40 dB with
   the receiver LNA in normal mode, or 20–50 dB in low-gain mode (r2, Table 62). Above the maximum the PGA runs out of
   range, and below the minimum NF suffers. These ratings do not apply to L-band.
2. **Antenna-module NF and rejection.** NF must be under 3.5 dB, out-of-band rejection 40 dB typ, and group-delay variation in band under 10 ns
   (r2, Table 63). Group delay is the new constraint compared with L1-only designs.
3. **Put the noise in the first stage.** The cascade follows F = F1 + (F2−1)/G1 + … (r6), and a passive loss in front of the LNA adds its full loss
   to NF (r6, attenuator example). Our worked example (our arithmetic, illustrative values): an LNA with 1.3 dB NF and 18 dB gain,
   followed by 6 dB of cable and a receiver NF of 3 dB, gives about 1.6 dB in total. With 28 dB of LNA gain the total stays within 0.05 dB of 1.3 dB.
   This is why the fin needs at least about 17 dB of gain after losses, and why NF should be compared on cascaded
   figures (module with filter versus bare LNA plus SAW) rather than on bare-LNA NF.
4. **Rejection budget.** Required rejection equals (aggressor Tx power − antenna isolation) − receiver immunity limit. Typical
   isolation is 15–20 dB, or 6–10 dB in very small devices. It is typically met with one or two SAW filters, and LNA gain reduces the
   effective rejection (r2, §4.3.3). With an LTE or 5G UE at +23 dBm (our assumption) and 15–20 dB isolation, about +3 to +8 dBm reaches the GNSS antenna. That is
   the level SKY5A2110 is tested to: gain holds at 17–21 dB with a +10 dBm mid/high-band blocker or a +15 dBm low-band blocker (r3).
5. **B13/B14 second harmonic.** The second harmonics of 777–787 MHz and 788–798 MHz land at 1554–1574 and 1576–1596 MHz, on L1/E1/B1I.
   The fix is a notch at 777–798 MHz *before* the external LNA, so the harmonic is never generated (r2, §4.3.3). SKY5A2110
   gives B13 2fo of –108.5 dBm typ and –97 dBm max at NTC (r3).
6. **Per-aggressor rejection is a spec line.** SKY5A2110 L1 typ/max: 600–1000 MHz –61/–53 dB; 1710–1980 –66/–47; n77
   3.3–4.2 GHz –64/–59; n79 4.4–5.0 GHz –66/–51; Wi-Fi 6/7 and V2X range 5.15–7.125 GHz –64/–50; B13/B14 777–798 –58/–47 dB (r3).
   The weakest worst-case lines (mid-band –47 dB, 2.4/5 GHz Wi-Fi –42 dB max) are the ones to check against an in-fin V2X or Wi-Fi radio.
7. **ETSI blocking (RED).** The rule is ΔC/N0 ≤ 1 dB for *each* declared constellation and signal, with a 1 MHz AWGN blocker (r1, eq. 4-1,
   Table 4-4). Test points for L1-band receivers: 1524 MHz at –65 dBm, 1548 at –95, 1554 at –105, 1615 at –105 and 1627 at –85 dBm.
   For the 1164–1300 band: 1154 MHz at –75 dBm and 1310 MHz at –85 dBm (r1, Tables 4-2 and 4-3). Every extra band (L2, E6) adds signals
   that must each pass.
8. **Where –105 dBm comes from.** The near-band level is set to I/N = –6 dB: –174 dBm/Hz + 73 dB-Hz (20 MHz) + 2 dB NF – 6 dB = –105 dBm
   (r1, Annex C.3). I/N = –6 dB costs about 1 dB of C/N0 (our arithmetic: 10·log(1+0.25)). A wider RF bandwidth or a higher NF raises the noise floor
   and therefore the allowed blocker. Declared NF and bandwidth are inputs to the test.
9. **Receiver spurious emissions.** Limits are –57 dBm/100 kHz from 30 MHz to 1 GHz and –47 dBm/1 MHz from 1 to 8.3 GHz, conducted at the antenna port (r1, Table 4-5).
   LNA stability matters here, and SKY5A2110 specifies k ≥ 1.5 from 10 to 15000 MHz (r3).
10. **Bias-T.** The feed inductor must exceed 500 Ω over 1–1.8 GHz and carry at least 300 mA. Use a current limit (60 mA example) and short and open detection
    so that antenna diagnostics are available (r2, §4.4.1–4.4.2).
11. **Protect the LNA from compression.** An active antenna or external LNA "must be protected from excessive RF power" to avoid
    compressing the receiver's internal LNA (r2). SKY5A2110 absolute maximum RF input is +10 dBm, in-band IIP3 –8.6 dBm typ and
    in-band P1dB –18.6 dBm typ (r3).
12. **Temperature.** SKY5A2110 is AEC-Q104 Grade 2, specified from –40 to +105 °C with TJ max 105 °C. Over that range L1 NF goes from 1.2 dB typ to 2.4 dB max
    and L5 NF from 1.4–1.5 dB typ to 3.0 dB max (r3). Margin against the 3.5 dB antenna NF spec (r2) shrinks at hot roof temperatures.
13. **Antenna placement (consideration).** Under-dash and rear-view-mirror positions are named as unsuitable (r2). Roof or fin placement
    over a ground plane is assumed.
14. **Third frequency (consideration).** Triple-frequency PPP+IMU gave 7 cm horizontal rms against 9 cm for dual frequency and 124 cm for single frequency,
    with 10–13 min convergence. During outages with 0–2 satellites, triple frequency was 10–40 % better than dual frequency (r4). The case for L2/E6 or L5 in the antenna front end
    rests on continuity in urban driving, not on open-sky accuracy.

## Considerations and pitfalls

- **L-band corrections versus ETSI blocking.** Receiving L-band corrections means passing about 1525–1559 MHz (u-blox antenna band
  1535–1602 MHz). Yet ETSI puts a –65 dBm blocker at 1524 MHz and –95/–105 dBm points at 1548/1554 MHz (r1). A widened L1
  filter must still fall steeply below 1525 MHz. *Unverified:* how ETSI treats a combined GNSS + L-band-correction receiver.
- **NTN uplink next to L1 (n255).** The 3GPP NTN L-band uplink (about 1626.5–1660.5 MHz) sits inside the ETSI "MSS Earth-to-space"
  region tested at only –85 dBm at 1627 MHz (r1). An in-car NTN UE transmitting at UE power would be about 100 dB stronger. This band
  edge is not covered by SKY5A2110's rejection table (r3 starts at 1710 MHz). *n255 limits not read from 3GPP in this run (conf low).*
- **Intermodulation.** Large out-of-band signals can generate in-band IM products in the front end (r2). Two fin transmitters (cellular plus V2X,
  or cellular plus Wi-Fi) need a two-tone check, not just single-blocker rejection.
- **Interference made inside the car.** In-band emissions from digital electronics cannot be filtered on the RF path (r2), so layout,
  shielding and the receiver's spectrum monitor are the tools.
- **Dual-input versus single-input.** Receivers have one RF_IN (r2). A two-input LNA module needs a dual-feed patch or an input diplexer,
  and every passive split before the LNA costs NF (r6).
- **Detection is not mitigation.** In r5, AGC detected 7 of 7 chirp intervals and C/N0 detected 5 of 7, with 23 % false alarms. AGC drifts with temperature (r5).
  A front end with flat, known gain over temperature makes AGC-based detection more reliable (our inference).

## Research trends

1. **Triple-frequency PPP or PPP-RTK fused with a MEMS IMU** on low-cost patch antennas for L3 lane-level positioning (r4). Receivers already support
   SPARTN corrections over IP or L-band, and CLAS (r2). Horizon: now to 2–3 years.
2. **All-band single-input receivers** (L1/L2/L5/E6 plus L-band) with per-band internal LNAs (r2). The antenna front end has to follow:
   wideband or triplexed, with a group-delay specification.
3. **Interference monitoring from front-end observables** (AGC, C/N0, spectrum analyser), moving towards classification and
   localisation (r5, r2). The data feeds cybersecurity and functional-safety cases.
4. **More transmitters in the fin** (5G FR1 n77/n79, V2X, Wi-Fi 6E/7 up to 7.125 GHz, NTN). Out-of-band rejection tables are growing up to 7.1 GHz (r3).
5. **Harmonised-standard pressure.** Each declared signal must pass ΔC/N0 ≤ 1 dB (r1). Adding bands multiplies the conformance work.

## Where Skyworks/Qorvo parts sit (from the repo catalogue, read-only)

- **gnss_lna.** SKY5A2110 (automotive L1 + L5, AEC-Q104 Grade 2) is the only automotive GNSS part. Non-automotive active parts are SKY55951-11 (L1 + L5),
  SKY55950-11, SKY65943-11, SKY65723-11/-81, SKY65724-11 and SKY65725-11 (L1), and SKY65728-11 (L5 with pre-filter). The SKY656xx/657xx/659xx L1 parts are mostly LTB or obsolete.
- **L5/E5a.** SKY65730-13 (1166–1217 MHz, NF 1.8 dB, catalogue function rf_frontend).
- **filter_saw_baw.** Qorvo 880272/880273 BAW GPS (1575 MHz, IL 2.35 dB typ) and 880060/880094 (wideband GPS). The SAW 857139–857144 parts are discontinued.
- **diplexer.** Qorvo QPQ1028 (L1/L2 SAW diplexer), TQM2M9016 (automotive SDARS/GPS diplexer), and 890084/890085/890086 (L1/L2 and L1/L5 SAW diplexers, discontinued).
- **Neighbours in the fin.** SKY5A2105 and SKYA21043 (V2X FEM), Qorvo QPF1003Q, QPF1004Q, QPF1005Q and QPF4554Q (V2X/Wi-Fi FEM), and QPQ2200Q/QPQ2230Q
  (V2X BAW and V2X notch). Cellular: SKY5A2203 LNA bank. Switches: SKY5A5109/SKY5A5110.
- **Gaps.** We have no E6 (1278 MHz) or L-band (1525–1559 MHz) filter, no single-input L1 + L5 + L2/E6 automotive module, and no Grade 1 part. We have no
  public rejection data around 1610–1660 MHz (NTN uplink).

## Open questions

- Does EN 303 413 have a newer version (V1.3.x) with different blocking points or limits for NTN or L-band? We read only V1.2.1 (2021).
- What are the n255 and n256 UE emission and co-location requirements when the NTN UE shares the fin with GNSS? (3GPP not read in this run.)
- What is the ZED-X20P immunity level in dBm? It appears only as plots (Figs. 16–17), which we did not extract as numbers.
- What is the cascaded NF and C/N0 of SKY5A2110 against TRF3302-Q1 plus SAW? There is no public measurement.
- Can Qorvo BAW meet 1535–1602 MHz with a steep edge at 1525 MHz and still clear the ETSI 1524 MHz test point?

## Sources tried but blocked or not used

- link.springer.com (satellite-navigation.springeropen.com redirects there) returned a "Client Challenge" page on robots.txt. We logged the host as
  STOP in requests.log and did not use it. This blocked the PPP-RTK review (Satell. Navig. 2022) and the PPP-for-ITS vulnerability
  paper (2021).
- IEEE Access "GNSS User Technology: State-of-the-Art and Future Trends" (2022, OA) is on ieeexplore, which is blocked. We did not try it.
- MDPI surveys (jamming and spoofing, 2024) are on a blocked host. We did not try them.
