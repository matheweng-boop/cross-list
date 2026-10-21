# Automotive UWB: digital-key anchors, 802.15.4ab, cabin sensing and coexistence (auto_uwb)

Deep-dive notes, 2026-10-21. These summaries are our own. Quotes are short and cited. conf: high means we read the primary
document; med means an advocacy body, trade press or our inference from a primary document; low means a snippet or our judgement.
Machine-readable version: `auto_uwb.yaml` (same folder). Context in the repo (read-only):
`data/business/cases/auto-uwb-15-4ab.yaml` and `auto-uwb-cpd.yaml`.

## 1. References (the six)

| id | Document | Type | Why this one | Read |
|----|----------|------|--------------|------|
| r1 | ETSI EN 302 065-3-1 V3.2.1 (2025-02), UWB vehicular access systems, 3.8-4.2 GHz or 6-8.5 GHz. [pdf](https://www.etsi.org/deliver/etsi_en/302000_302099/3020650301/03.02.01_60/en_3020650301v030201p.pdf) | standard | The EU harmonised standard written specifically for car access | clauses 1, 4.2-4.4, annex D (full text) |
| r2 | IEEE P802.15-23-0452-07-04ab, *Coexistence Document for IEEE 802.15.4ab* (May 2024). [pdf](https://mentor.ieee.org/802.15/dcn/23/15-23-0452-07-04ab-coexistence-assessment-document.pdf) | standard (WG doc) | Public summary of what 4ab adds, plus the Wi-Fi 6E/7 coexistence evidence | all 15 pages |
| r3 | CCC, *UWB Spectrum Regulatory Position* v2025 R2. [pdf](https://carconnectivity.org/wp-content/uploads/2022/12/CCC-UWB-Spectrum-Regulatory-Position_v2025-R2.pdf) | white paper | The Digital Key body's own view on channels and spectrum | all |
| r4 | Luo et al. (Apple), *Secure Ranging with IEEE 802.15.4z HRP UWB*, arXiv 2312.03964v2 (2024). [abs](https://arxiv.org/abs/2312.03964) | paper | The most rigorous public treatment of STS receiver security | sections 1, 3-7 |
| r5 | Möderl et al. (TU Graz), *"UWBCarGraz" Dataset for Car Occupancy Detection using UWB Radar*, arXiv 2311.10478 (2023). [abs](https://arxiv.org/abs/2311.10478) | paper | Measured in-cabin UWB radar in two real cars, with an open dataset | all |
| r6 | Skyworks SKY5A2108 data sheet 206432E (Mar 2025). [pdf](https://www.skyworksinc.com/-/media/SkyWorks/Documents/Products/Data-Sheet/SKY5A2108_206432E.pdf) | vendor data sheet | Our own AEC-Q100 switch for UWB and Wi-Fi 6E; real loss and isolation figures | pages 1-3 |

Also read, as background and not counted in the six:
- IEEE 15-24-0444-00-04ab (Billy Verso, Qorvo, Aug 2024). It gives the message sequence chart for NBA UWB MMS ranging: an NBA control phase on the O-QPSK PHY, a ranging phase on the HRP UWB PHY, then an O-QPSK reporting phase.
- The P802.15.4ab PAR extension, 15-25-0378, from the earlier run in `dl/uwb/par_ext.txt`. It puts the start of SA ballot in Jan 2026 and RevCom in Dec 2026. At the time it called the draft "75 %" stable.
- The FiRa press release on 4ab (2025). It says FiRa will add 4ab features "building upon FiRa's existing IEEE 802.15.4z features" with backward compatibility.
- Earlier-run pages in `dl/uwb/` (cnx-software on ST64UWB, an MTT-S in-cabin radar review page, Wireless Design Online on Qorvo CPD). We use these only as med/low context.

## 2. Block diagram (explained)

Phone-as-key car access. We drew this from the references; it is not copied from any of them.

```
 [Phone / fob]  --UWB ch9 STS ranging-->  [Exterior anchors xN: antenna(s) - AoA switch - (bypass LNA) - UWB SoC - XO/LDO/ESD]
      |  \                                         |  CAN-FD / LIN
      |   \--BLE (today) / NBA O-QPSK (4ab)-->  [BLE anchor or NBA radio + 5.7-6.4 GHz filter]  -->  [Access ECU / zone: MCU + SE + CAN/LIN]
      |                                                                                            ^
      \--UWB ranging (inside)-->  [Interior anchor: UWB SoC also in radar mode: CPD, intrusion] ---/
 Interferers in the same car: Wi-Fi 6E/7 (5.925-7.125/7.25 GHz) with its FEM and BAW filter; 5.9 GHz V2X with its FEM.
```

- **Why a second radio exists:** ETSI's trigger-before-transmit rule says the vehicle anchor transmits only after a trigger (r1 4.3.7). The trigger is a BLE/NFC handshake, user detection or the door handle. CCC uses BLE as the control channel today, and 802.15.4ab moves that job onto its own narrowband O-QPSK radio (NBA).
- **Exterior anchors** do secure ranging, and two antenna ports allow angle of arrival. The weak cases are positions with body blockage, such as a phone in a back pocket. ETSI's baseline sensitivity note says these should be solved by link budget rather than by adding nodes (r1 4.4.4).
- **Interior anchor:** it ranges to decide whether the phone is inside the car (start the engine). The same chip runs as a monostatic or bistatic radar on the channel impulse response (CIR) to detect breathing. This covers child presence detection (CPD) and intrusion (r5; QPF5100Q in the case file).
- **Backbone:** in zonal cars the anchors become CAN-FD satellites of a zone or central computer (from the case file, med).

## 3. Design rules (summary; full list with refs in the yaml)

1. **Emission cap:** mean e.i.r.p. at most -41.3 dBm/MHz and peak at most 0 dBm in 50 MHz, in both 3.8-4.2 and 6.0-8.5 GHz (r1 Tables 4-5). CCC quotes the same "-41dBm/MHz" for Digital Key (r3). This is the nominal FCC level too, but we did not read the FCC text in this run.
2. **Trigger-before-transmit:** required for anchors. Category 1A is a responder triggered by a received UWB packet; category 1B is an initiator triggered by a control command (r1).
3. **Low duty cycle in 3.8-4.2 GHz:** Ton at most 5 ms, mean Toff at least 38 ms, and less than 18 s of Ton per hour. Fobs in 6-8.5 GHz are exempt (r1 Table 8, Table 1a).
4. **Receiver baseline sensitivity:** at most -111.3 dBm/MHz at the EUT, including antenna gain. That is 70 dB below the emission cap (r1 4.4.4).
5. **Receiver baseline resilience:** an anchor must hold criterion 1 against a -85 dBm CW interferer and criterion 2 against -50 dBm, in band and at ±1×/±2× the operating range from fc (r1 Tables 12-13).
6. **Channel 9 first:** channel 5 is compromised by Wi-Fi and IMT, and WRC-27 AI 1.7 threatens channel 9 (r3).
7. **Wi-Fi 6E/7 coexistence:** use frequency offset, diversity, SSBD (listen before talk) and Wi-Fi out-of-band filtering. Separation alone is not enough (r2 3.1.1).
8. **Asymmetry:** Wi-Fi cannot see UWB, so UWB has to sense and defer (r2).
9. **NBA band:** 5.725-5.850 and 5.925-6.425 GHz in 2.5 MHz channels, up to 250 of them. The V2X band, 5.855-5.925 GHz, sits in the gap between the two. The consequence for filtering is our inference (r2).
10. **Airtime:** ranging duty cycle is typically 1.5-5 %. MMS uses fixed slots with no retries (r2 3.1.3).
11. **Secure first-path detection:** use STS-validated first-path tests, not CIR thresholding, and do not correct the clock from the received waveform. At false acceptance 2^-48 the reference receiver detects the first path more than 99 % of the time when its SNR is -20 dB or better (r4 sections 4-6).
12. **CPD signal processing:** remove the static CIR and detect slow-time variation in windows of about 10 s. Measured AUC is 0.91 at -20 dB SNR for a breathing adult; infants give less signal (r5).
13. **Switch loss counts:** SKY5A2108 has 0.9/1.4 dB IL (typ/max) and 17 dB minimum isolation at 7.125-8.3 GHz. A bypass LNA ahead of the switch is worth it at weak positions (r6, plus our inference).
14. **Grade 2 parts** (-40 to +105 °C), tiny packages, and +32 dBm absolute-maximum input next to other transmitters (r6).

## 4. Considerations and pitfalls

- **The amount of Wi-Fi interference is large.** r2 cites in-band 802.11 effects on UWB out to 946 m. In other scenarios about 10 m is enough when combined with other mechanisms. A car carries its own 6 GHz Wi-Fi hotspot a metre or two from the roof and pillar anchors. Most of that risk falls on channel 5 and on out-of-band emissions near channel 9 once 802.11be reaches 7.25 GHz.
- **UWB rarely harms Wi-Fi.** r2 reports that it took 12 UWB devices transmitting continuously within 0.33 m of an 802.11ax AP to show any throughput loss (0-60 %). This argument helps in regulatory debates.
- **NBA brings UWB anchors next to V2X.** The 4ab narrowband channels flank the 5.9 GHz ITS band. A V2X transmitter (high power, often on the roof) near an NBA anchor is a blocking case. Our catalogue V2X notch filters (SKY5A1005, QPQ2230Q) show that the problem is already known on the Wi-Fi side (inference, med).
- **Security pitfalls:** Ghost-peak and Cicada-style attacks work on thresholding receivers. r4 describes an adaptive attack that places a fake peak at a time the attacker chooses. Relay attacks on BLE/LF keys are the reason UWB was adopted in the first place. Those relays are not analysed in r4, which deals with physical-layer distance reduction.
- **CPD data:** in r5 all participants were adults (34 people, 2 cars), and the lab sounder had more dynamic range than a production anchor. That is why they added noise down to -30/-40 dB SNR. Results for infants are not in this dataset. The TU Graz baby-dummy paper was blocked (see section 8).
- **The 3.8-4.2 GHz option** exists in ETSI for vehicles, but with low duty cycle. It is a fallback if channel 9 is lost, and it would need a different front end.
- **Catalogue caveat:** SKYA21003 is described as 0.1-8.5 GHz, but its key_specs say a maximum of 6.0 GHz. Check the data sheet before proposing it for UWB.

## 5. Research trends

- **802.15.4ab** (now): ballot from Jan 2026, RevCom planned Dec 2026. Its features include NBA-MMS, sensing, LE-UWB with SSBD, data rates of at least 50 Mb/s and better discovery (r2, PAR). ST (ST64UWB, 18 nm FD-SOI, NBA in UNII-3/UNII-5) and Calterah are already sampling (trade press, med).
- **MMS link budget:** a trade-press figure says MMS adds "up to 18 dB" and gives up to 8× range (cnx-software quoting ST; med/low). We have not verified it in an IEEE text.
- **Spectrum:** after channel 5 was lost, WRC-27 AI 1.7 (7.125-8.4 GHz) is the next fight (r3).
- **Cabin sensing on anchors:** data-driven detectors (ResNet on CIR) beat model-based variational message passing at low SNR and fit within car ECU compute limits (r5). 4ab standardises a sensing mode (r2).
- **Provable STS security** and certification levels (FiRa 1e-6 and 2^-48) (r4).
- **Cooperative coexistence:** SSBD, eDAA, channel-map exclusion and broadcast schedules (r2).

## 6. Where Skyworks/Qorvo parts sit

| Socket | Parts (from the repo catalogue) | Note |
|---|---|---|
| UWB SoC (`uwb_soc`) | QPF5100Q, DW3300Q, QM35825 | Automotive 4z, with ranging plus radar on QPF5100Q. No public 4ab/NBA part. |
| UWB front end (`uwb_fem`) | QM14068 (bypass switch + LNA, 6.2-8.3 GHz), QM14070 (PA with bypass, 6-9 GHz) | Automotive grade not stated. The PA is capped by -41.3 dBm/MHz. |
| Antenna/AoA switch (`rf_switch`) | SKY5A2108 (Grade 2, 2.4-8.3 GHz), QPC8019Q (to 8.0 GHz) | QPC8019Q does not cover the top of channel 9. SKY13298-360LF is last-time-buy. |
| Filters on the coexisting radios (`filter_saw_baw`) | SKY5A1008 (6 GHz Wi-Fi BAW), SKY5A1005 / QPQ2230Q (V2X notch) | No NBA-band filter yet, which is an opportunity. |
| V2X front end (`v2x_fem`) | QPF1004Q, QPF1005Q | The neighbour of the NBA band. |

Our reading of where we stand: we are the only UWB SoC vendor that also sells the switch, LNA and BAW parts around it. The 4ab NBA band (5.7-6.4 GHz) and the channel-9 blocking problem are both front-end problems that we can address.

## 7. Open questions

These are the same as in the yaml: the final 4ab NBA masks around V2X; the FCC Part 15 vehicle clauses (not read); CCC DK3/4 RF requirements (members only); the Euro NCAP CPD protocol and the ETSI EN 302 065-3-3 cabin radar limits (not read); SKY5A1008 rejection at 7.7-8.3 GHz; AEC-Q status of QM14068/QM14070; and the real anchor count per car (our estimate is 4-8).

## 8. Sources tried but blocked or not used

- **api.openalex.org:** 429 on the first query of this run, so the host was stopped and we found papers through web search instead.
- **tugraz.elsevierpure.com:** 403/checkpoint on the TU Graz paper *Measurement of a Baby Dummy with a Channel Sounder ... for Child Presence Detection*. The host was stopped and we did not look for another copy.
- **Rohde & Schwarz** white paper *Exploring the future of UWB* (4ab): behind a download form, not fetched.
- **FiRa** white paper *Collaboration advancing UWB interoperability*: behind a form, not fetched.
- **CCC Digital Key 3.0** white paper: form or members only, not fetched.
- **www.qorvo.com:** not allowed (DW3000/QPF5100Q application notes live there).
- **nxp.com, st.com, ieeexplore:** blocked earlier.
- **docs.fcc.gov:** stopped earlier, so the FCC Part 15 UWB text was not read.
