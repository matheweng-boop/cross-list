# Isolation in the ASIL-D traction inverter (400 V / 800 V, SiC and IGBT)

Topic key: `traction_asil_d` · researched 2026-10-21 · machine-readable twin: `traction_asil_d.yaml`

## References (the six)

| id | Document | Type | Why | Licence |
|---|---|---|---|---|
| r1 | TI SLUA963B, *HEV/EV Traction Inverter Design Guide Using Isolated IGBT and SiC Gate Drivers* (rev. Oct 2022) | app note | Maps failure modes to gate-driver protections; covers the three bias-supply architectures | TI copyright, summary only |
| r2 | TI SDAA370, *Towards Functional Safety in Traction Inverter* (May 2026) | app note | ISO 26262 worked example: safety goals, FTA, FMEA, FSR/TSR, safe states, DFA, decomposition | TI copyright, summary only |
| r3 | TI SSZT066, *Understanding Functional Safety for Gate Drivers and Traction Inverter Systems* (Aug 2022) | white paper / tech article | ASIL-D metrics; supplier documentation levels | TI copyright, summary only |
| r4 | Skyworks Si829x (Si82900/10/11/13) Isolated Safety Gate Drivers Product Summary, 207561A (Sep 2026) | vendor (own) | Our ASIL-D traction driver | Skyworks public |
| r5 | Pogulaguntla & Karuppaswamy, *Analysis and Design of Desaturation Short-Circuit Protection for SiC MOSFET Under High Switching Voltage Transients*, arXiv 2609.23000 (Sep 2026) | open paper | Quantitative SiC DESAT design | arXiv; licence not checked, summary only |
| r6 | MIT OCW 6.622 Power Electronics (Perreault, 2023), Lecture 38 *Gate Drive, Level Shift, Layout* | course | Physics under the rules: gate-drive power, loop inductance, floating supplies | CC BY-NC-SA 4.0 |

Also read, not in the six:
- Infineon 1EDI3041AS datasheet excerpt (Dec 2025). It is the competitor reference: reinforced 8 kV peak per IEC 60747-17, 5.7 kVrms UL 1577, 20 A split output (TON30/TON70, TOFF30/TOFF70), SOFTOFF pin, secondary ASC pin (SASC), 11-bit isolated ADC, ISO 26262 SEooC, "developed according to ISO 26262 ASIL D".
- Skyworks AN583 (*Safety Considerations and Layout Recommendations for Digital Isolators*, rev 0.3, 2021). It covers creepage and clearance, pollution degree, and the basic vs reinforced rule of thumb.

Neither IEC 60747-17, IEC 60664-1 nor ISO 26262 is free to read, so the standard slot is filled by r3 (the metrics) and the vendor certification statements (r4, 1EDI3041AS).

## Block diagram explained (drawn by us)

LV domain (12 V) on the left, the galvanic barrier in the middle, HV domain (400/800 V) on the right.

1. **LV supply and supervision.** A safety PMIC supplies the LV side. It provides voltage monitors, a Q&A watchdog and an error-pin monitor for the MCU. A pre-regulator feeds the bias supplies (r2 §3.5.4).
2. **Control and safety logic.**
   - A lockstep MCU runs FOC and sends PWM x6. It configures and reads the drivers over SPI, protected by CRC.
   - Independent logic (r2 uses a TPLD1201-Q1 CPLD) drives the drivers' ASC inputs, so a safe state is reachable even if the MCU fails.
   - CAN connects to the VCU.
3. **Isolated bias supply.** Each driver gets VCC2/VEE2. The options are:
   - centralized (one supply for all six drivers): a single point of failure;
   - semi-distributed (one per high-side driver plus one shared low-side supply);
   - distributed (one per driver).
   An optional HV-battery-fed backup supply powers the low-side drivers, so ASC still works if the 12 V net is lost (r1 §4, r2 §3.5.3).
4. **Isolated gate drivers.** One per switch. They carry:
   - DESAT and/or current-mirror short-circuit protection with soft or two-level turn-off;
   - an active Miller clamp;
   - UVLO/OVLO on VCC1, VCC2 and VEE2;
   - a gate monitor that compares the gate with the PWM input;
   - shoot-through protection with programmable dead time;
   - ASC inputs on the primary and secondary side;
   - SPI with CRC, BIST, and an ADC for NTC and DC-link voltage (r1, r4).
5. **Isolated sensing.**
   - DC-link voltage through an isolated amplifier or sigma-delta modulator.
   - Phase current: three coreless Hall sensors, or shunts read by isolated amplifiers. The third phase is used for plausibility (r2 §3.5).
   - Digital isolators carry the fault and back-channel signals.
6. **Power stage.** HV battery, DC-link capacitor, three SiC or IGBT half-bridges, and an NTC/diode temperature sensor read by the driver ADC.
7. **Motor and discharge.** Motor, redundant position sensing (two inductive or resolver sensors, ASIL B(D) each), and the DC-link active-discharge switch driver.

Safe states (r2 §2.4):
- **Zero torque** (iq = 0): for communication faults.
- **Freewheel** (all switches off): at low speed.
- **ASC** (all high-side or all low-side switches on): at high speed, when the back-EMF exceeds the battery voltage and opening the switches would push uncontrolled regenerative current into the battery.
- **Derating**: for over-temperature.

## Design rules (summary; full list with numbers in YAML d1–d14)

**Short-circuit protection for SiC (r5)**
- The withstand time is typically under 3 µs. In r5's 650 V device at 400 V it was estimated at 1.2 µs, and the target detection time was ≤ 600 ns.
- A textbook DESAT with 100 pF blanking gave 1.04 µs, which is too slow.
- Turn-off dv/dt (40 V/ns in the analysis) charges the blanking capacitor through the diode's Cj and causes false trips.
- Recommended values:
  - type-1 with external resistor: Cj ≤ 5 pF, Cblk = 350 pF, Re ≤ 500 Ω;
  - type-2: Cblk = 500 pF, R1 = 600 Ω.
- Prefer driver ICs with short internal delays.

**Fault turn-off (r1)**
- Soft turn-off: 400 mA pull-down in the UCC2175x example.
- Two-level turn-off: about 9 V plateau, then ramp down.
- UCC5870 adds active VCE clamping: on overvoltage it switches OUTL from more than 15 A to the soft turn-off current.

**Miller clamp and CMTI**
- Active Miller clamp below 2 V on OUTL (r1). Si829x has an integrated 15 A clamp plus an MCOUT pin for an external clamp FET (r4).
- CMTI: Si829x 125 kV/µs; TI UCC217xx > 150 V/ns, UCC5870 > 100 V/ns. Our Si82Bx/Ex/Fx reach 200 kV/µs (repo data).

**Supply supervision**
- UVLO and OVLO on all three driver rails, with thresholds per switch type. r1 example: VDD UVLO 12 V with 0.8 V hysteresis, VCC 2.7 V.
- On Si829x the positive gate voltage is regulated on-chip from an 18–30 V VDDO, and the negative voltage follows from it (r4).

**Functional safety (r2, r3)**
- Example SG1 "avoid unintended acceleration torque" is ASIL C/D, with a user-specified FTTI (750 ms in the example).
- ASIL D targets SPFM ≥ 99 %, LFM ≥ 90 %, PMHF ≤ 10 FIT (r3).
- The gate driver is allocated TSRs at ASIL D (r2 1.6.10–1.6.12):
  - block PWM on an ASC command;
  - output the correct safe-state level;
  - check the isolation lane.
- Latent-fault coverage comes from BIST of the protection paths and CRC on the configuration and NVM.

**Bias supply sizing (r6, r1)**
- Per driver: P = V_drive · Q_g · f_sw, dissipated mostly in the driver and gate resistors, whatever their value.
- Keep the gate loop short with a stacked return (L ∝ length × spacing / width).
- Distributed or semi-distributed bias is required for redundancy.

**Isolation rating**
- The driver barrier is the human-safety barrier. Use reinforced isolation per IEC 60747-17 / VDE 0884-17 plus UL 1577:
  - Si829x: 6 kVrms (1 min), 1500 Vrms working, 10 kV surge, barrier life > 20 years (r4);
  - 1EDI3041AS: 8 kV peak (IEC 60747-17) and 5.7 kVrms (UL 1577).
- Creepage rule of thumb from AN583: basic 3.2 mm / 2.5 kVrms; reinforced 6.4 mm / 5 kVrms. Distances double for reinforced; Skyworks packages are rated material group I, pollution degree 2.
- An 800 V bus (about 1000 V peak) falls in AN583's 354–1414 Vpk test band (an IEC 60950-1 table, now superseded).
- In practice, choose wide-body packages with about 8 mm creepage (SSO-8, SOIC-16W/14W). IEC 60664-1 values were not verified.

## Considerations and pitfalls

- **DESAT fits IGBTs better than SiC.** The IGBT knee gives a clear threshold (r1: 9 V). SiC has no flat saturation region, and its short-channel effect stretches the ohmic region (r5). Sense-FET or current-mirror SCP and shunt OCP are the alternatives: UCC5870 AIx inputs, Si829x IV1/IV2.
- **Blanking capacitor trade-off.** Lowering Cblk for speed raises dv/dt false trips (r5). Deglitch filters help, but they add delay.
- **Gate monitor blanking must follow the fault profile.** It must start after the two-level turn-off plateau, or it flags false gate faults (r1 §3.10.5).
- **Centralized bias supply.** It is also bulky and suffers common-mode currents, and its long traces complicate layout (r1, r2).
- **Two current sensors are enough for FOC but not for safety.** Range checks alone give only about 60 % coverage (r2).
- **Dependent failures.** Look for shared supplies, cross-talk, local heating, EMI and ESD that could take out both redundant channels together. DFA is required (r2 §3.3).
- **Sensing CMTI.** The repo lists 50 kV/µs CMTI min for Si892x/893x/894x isolated amplifiers. That is lower than the drivers' rating, so check their behaviour next to fast SiC edges.
- **ASIL certification status.** Si829x states "Suitable for use in systems up to ASIL D (Pending)" (r4, p.1). Customers will ask for the certificate, FMEDA and safety manual.

## Research trends (detail in YAML t1–t7)

1. 800 V SiC drives sub-µs short-circuit detection and CMTI of 100–200 kV/µs (now).
2. Active and programmable gate drive: ProVCD current-mode drive (Si829x), split or slew-controlled outputs (1EDI3041AS), on-the-fly SPI tuning (2–3 years).
3. Drivers absorb sensing and health monitoring: ADC, Vth and RDS(on) monitoring, gate-timing capture (now).
4. FuSa becomes mandatory and certified: GB/T 43254-2023, EU 2019/2144, SAE J2980 cited by r2 (now).
5. Distributed and redundant (HV-fed) bias supplies (2–3 years).
6. dv/dt-driven EMI, multilevel and filterless WBG inverters (2–3 years; the PoliTo dummy-leg paper and the MDPI post-800 V topology paper were seen in OpenAlex metadata only).
7. GaN traction remains research-stage (5+ years).

## Where Skyworks / Qorvo parts sit (repo data, read-only)

| Function (fn) | Skyworks parts | Fit |
|---|---|---|
| gate_driver | SI82900AA/AB/BA/BB-AU (Si829x) | Main ASIL-D traction socket: 15 A, DESAT plus current-mirror SCP, BIST, FOS safe state, 6 kVrms reinforced, 125 kV/µs. The repo has only the single-package Si82900, not the Si82910 + Si82911/13 pairs listed in the Sep 2026 summary. |
| gate_driver | SI8285BD-AS, SI8286BC-AS | DESAT, soft shutdown and Miller clamp, but **basic** isolation. Suits IGBT or 400 V designs, or lower ASIL with external diagnostics. |
| gate_driver | SI82B40ABC-AS, SI82E39ABC-AS1, SI82F39ABC-AS1 | Reinforced, 6 kVrms, 200 kV/µs, no DESAT. Better for OBC/DC-DC SiC than the main inverter. |
| isolated_dcdc | SI88240BC-AS, SI88340EC-AS, SI88440EC-AS, SI88640EC-AS | Isolator plus DC-DC controller with external transformer, for per-driver bias. Basic isolation, 1414 Vpk working. |
| isolated_amplifier | SI8921AB-AS, SI8941AB-AS (shunt current); SI8931B-AS, SI8935B-AS (DC-link voltage) | Reinforced; SSO-8 rated 5 kVrms with 8–8.5 mm creepage. |
| digital_isolator | SI86S600AC-AS (Si86Sxx family) | Reinforced up to 6 kVrms, 100–150 kV/µs; for SPI, fault and safety signals. |
| isolated_switch_driver | (Si8751A/52A in the catalogue, not in data/real) | DC-link active discharge. |
| current_sensor | none | Coreless Hall phase sensor is an opportunity; only Si8540 (non-isolated, last-time-buy) exists. |

Qorvo: the repo's Qorvo data has no isolated gate driver or isolator. The Qorvo PAC5xxx motor-controller SoCs are for 12–600 V BLDC, not 800 V traction.

## Open questions

See the YAML list. In short:
- the Si829x full datasheet numbers and ASIL-D certificate status;
- the 800 V creepage and working-voltage requirement per IEC 60664-1 / ISO 6469-3 (not readable for free);
- a reinforced bias controller for 800 V high-side drivers;
- the CMTI margin of the isolated amplifiers;
- the Hall vs shunt trend;
- typical SiC gate rails for 800 V modules.

## Sources tried but blocked or not used

- **api.openalex.org** was stopped (429) by an earlier run, so no new OpenAlex query was possible. The OA paper was found by web search and read on arxiv.org/pdf (one request).
- **iso.org, IEC (paid), mdpi.com and ieeexplore** are blocked or paywalled. The OA candidates "Active Gate Drivers for SiC MOSFETs: Circuitry, Control, and Future Outlook" (IEEE TED 2026, CC BY) and the MDPI "post-800 V traction inverter topologies" paper were seen only in OpenAlex metadata from an earlier run.
- **Wolfspeed TIDM-02014 page** was already fetched in an earlier run but not used, because the MIT lecture filled the course slot.
- **Requests made in this run:**
  - MIT OCW typed-notes list, Lecture 38 page and Lecture 38 PDF;
  - Skyworks Si829x product summary and AN583;
  - TI SSZT066;
  - arXiv 2609.23000 PDF.
- Reused from earlier runs: SLUA963B, SDAA370, 1EDI3041AS.
