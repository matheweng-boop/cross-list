# TI power / isolation block diagrams: traction inverter, isolated gate driver, isolated bias power

Research extract for the block-diagram generator. Machine-readable version: `ti_power.yaml` (same folder).
All content comes from the six TI documents below. Page numbers are the PDF page numbers, which match the
printed page numbers in these documents. TI parts are listed for reference only (competitor parts).

| Doc | Title | URL |
|---|---|---|
| SLUA963B | HEV/EV Traction Inverter Design Guide Using Isolated IGBT and SiC Gate Drivers (Oct 2022) | https://www.ti.com/lit/an/slua963b/slua963b.pdf |
| SLUAAS4 | Isolated Bias Power Supply Architecture for HEV and EV Traction Inverters (Jan 2024) | https://www.ti.com/lit/pdf/sluaas4 |
| TIDUF23A | TIDM-02014 800 V / 300 kW SiC Traction Inverter Reference Design (rev. May 2025) | https://www.ti.com/lit/ug/tiduf23a/tiduf23a.pdf |
| SLUAAH0 | UCC14240-Q1 Simplifies HEV, EV, Bias Supply Design for Isolated Gate Drivers (Feb 2022) | https://www.ti.com/lit/an/sluaah0/sluaah0.pdf |
| SPRAD58B | Design Priorities in EV Traction Inverters (rev. Feb 2026) | https://www.ti.com/lit/wp/sprad58b/sprad58b.pdf |
| SLYY169 | IGBT & SiC Gate Driver Fundamentals (e-book) | https://www.ti.com/lit/eb/slyy169/slyy169.pdf |

No extra documents were needed: these six already contain system, gate-driver and bias-supply block diagrams.

---

## 1. HEV/EV traction inverter

### 1.1 Block diagrams read

- **SLUA963B p.5, Fig 2-4 "High-Voltage Traction Inverter Block Diagram"**. LV side: CAN bus, PMIC, MCU,
  "shoot-through protection and RESET control". On the isolation barrier: two "Signal Isolation" blocks,
  "Isolated Bias Supply(s)", "Isolated HS Driver", "Isolated LS Driver". HV side: DC bus voltage sensing,
  VCE monitoring, short-circuit monitoring / protection, HV battery, DC-link capacitor, IGBT modules (with
  temperature sensor), motor M with position sensor. Below the lower signal isolation: temperature sensing,
  current sensing, voltage sensing, position sensing.
- **SLUA963B p.6, Fig 2-5**: three-phase two-level inverter, six switches S1..S6, each with its own driver;
  "voltage / current / position" fed back to the MCU. p.5-6: FOC uses two phase currents plus position;
  the PWM is space-vector modulation.
- **SLUA963B p.4, Fig 2-3** (EV system context): traction inverter, electric motor/generator, HV Li-ion battery,
  DC/DC converter, OBC, 12 V battery, controllers (MCU, PMIC).
- **SLUAAS4 p.2, Fig 1-1 = SPRAD58B p.8, Fig 3-1** (the same diagram). LV side: LV battery, reverse polarity
  protection, DC/DC power supply, a second DC/DC giving 3P3V, PMIC & SBC (Diagnostic, ISO-CAN, CAN), ESD CAN,
  MCU (Debug, ADC, GPIO, ASC, PWM, SPI), position sensor interface, safety logic. On the barrier: DC/DC
  (redundant power supply, HV to LV, diode-ORed into the LV rail), DC/DC (bias supply) producing the gate supply,
  isolated current-sense and HV-voltage-sense amplifiers going to the MCU ADC, the gate driver (6x PWM and
  4x SPI in, 6x gate out, 3P3V and gate supply), a digital isolator (SPRAD58B labels it "Digital isolator /
  Opto-emulator"). HV side: HV battery, active discharge, DC link capacitor, power stage, motor, current sense,
  position sensing, ADC for temperature sense.
- **TIDUF23A p.4, Fig 2-1 (TIDM-02014)**. 12 V battery Vin goes to the PMIC (SPI to the VCU, WD to the MCU,
  battery voltage monitoring) and to two "Supply Diagnostics / Monitoring" blocks feeding "Bias Supply High Side"
  and "Bias Supply Low Side" across the barrier. Isolated gate driver (DESAT, adjustable gate drive, BIST,
  2x A-to-D, ASC, SPI) drives the SiC power modules (OUT1/OUT2); the PMIC has an ASC path to the driver; NTC
  temperature, temperature sensing and phase-node sensing return to the driver's A-to-D. Isolated amplifier
  (phase current sensing, Hall) goes to the MCU ADC; isolated comparator (DC bus sensing) goes to the CMPSS.
  DC link cap with discharge, 800 V bus, motor phases, resolver / Hall, resolver AFE (excitation, signal
  conditioning). Safety MCU blocks: CAN, HSM, PWM, CLB, SPI, CMPSS, ADC, wired interface.
- **SLUAAH0 p.5, Fig 2-1**. Galvanic isolation drawn as a line. LV: reverse polarity / input power protection,
  non-isolated DC/DC (loads), PMIC (system monitors, diagnostics, SPI, DC/DC, LDOs, WDT), safety & glue logic,
  MCU core (CAN, PWM, GPIOs, ADC), wired interface (CAN), rotor position sensing. Barrier: redundant power supply
  (backup, HV to LV), UCC14240-Q1 isolated bias supply (24 V in, 18-25 V out), digital isolator + ISO + logic
  into the HS / LS drivers, current and voltage sense (AMP, ISO, AMP), signal isolation. HV: DC link capacitor,
  half bridge, motor, position, self-diagnostics / monitoring (ADC, sensors V/T/I, VREF, AFE).
- **SLYY169 p.9, "Table 5" (actually a figure)**. LV: power supply, wired interface, digital processing,
  system-on-chip (GND1). Barrier: isolated bias supply, isolated driver, signal isolation. HV: power stage,
  current and voltage sense, diagnostics and monitoring, motor (GND2).

### 1.2 Consolidated blocks and connections

| Group | Side | Blocks | Source |
|---|---|---|---|
| LV battery input & protection | LV | 12 V battery, reverse polarity protection, ideal diode with OV / short-circuit protection | SLUAAS4 p.2; SLUAAH0 p.5; TIDUF23A p.7, p.12 |
| LV power / PMIC | LV | DC/DC, PMIC / SBC, watchdog and voltage monitors, LDOs, 3.3 V | SLUA963B p.5; SLUAAS4 p.2; SPRAD58B p.10-11; TIDUF23A p.4, p.11 |
| Control | LV | MCU (PWM, ADC, SPI, ASC, CAN, HSM), safety / glue logic, shoot-through protection and reset control | SLUA963B p.5; SLUAAS4 p.2; SLUAAH0 p.5; TIDUF23A p.4 |
| Vehicle network | LV | CAN, isolated CAN, ESD on CAN | SLUAAS4 p.2; TIDUF23A p.6-7 |
| Isolated bias supply | barrier | pre-regulator, isolated DC/DC HS, isolated DC/DC LS, supply diagnostics | SLUA963B p.5; SLUAAS4 p.2; TIDUF23A p.4 |
| Redundant HV-to-LV supply | barrier | isolated HV to LV DC/DC, diode-OR into the LV rail | SLUAAS4 p.2; SLUAAH0 p.5; SPRAD58B p.8, p.16 |
| Isolated gate drivers | barrier | 6x isolated gate driver (3 HS + 3 LS) | SLUA963B p.5-6; SLUAAS4 p.2; TIDUF23A p.4 |
| Signal isolation | barrier | digital isolator; isolated ADC path for temperature | SLUA963B p.5; SLUAAS4 p.2; SPRAD58B p.8 |
| Isolated sensing | barrier | DC-link voltage sense, phase current sense, isolated amplifier / modulator / comparator, VCE monitoring | SLUA963B p.5; SLUAAS4 p.2; TIDUF23A p.4; SPRAD58B p.19-21 |
| Power stage | HV | HV battery, DC-link capacitor, IGBT / SiC modules, module NTC / diode | SLUA963B p.5-6; TIDUF23A p.4 |
| Active discharge | HV | discharge switch / resistor, isolated switch driver, discharge controller | SLUAAS4 p.2; TIDUF23A p.4, p.22; SPRAD58B p.16-17 |
| Motor & position | HV | motor, resolver / inductive / Hall sensor, excitation amplifier, sensor interface | SLUA963B p.5; SLUAAS4 p.2; TIDUF23A p.4; SPRAD58B p.18-19 |

Connections (from the figures above): LV battery to PMIC and, through a pre-regulator, to the bias supplies;
PMIC to MCU (supply, watchdog / reset); MCU to CAN; MCU to gate drivers (6x PWM, SPI, ASC); bias supplies to
gate drivers (VCC2 / VEE2); HV battery to the redundant HV-to-LV DC/DC, ORed into the LV rail; gate drivers to
power modules (6x gate); module NTC and DESAT / OC back to the drivers; driver faults / SPI / sensing diagnostics
to the MCU; DC-link voltage and phase current through isolated sensing to the MCU ADC / comparators;
temperature through ADC + digital isolator to the MCU; DC link to active discharge; position sensor to MCU,
MCU to resolver excitation; power stage to motor (3 phases).

Functions from SPRAD58B p.8-9 ("Key functions in the high-voltage domain"): power switches (SiC or IGBT
modules, controlled by isolated gate drivers with temperature sensing and ASC), isolated gate driver, isolated
bias supply, isolated voltage and current sensing, position sensing, active discharge (UN ECE R94: DC bus
under 60 V in less than 5 s). SPRAD58B p.3 also lists the cost items: housing / cooling / busbars, power modules,
EMI filter, DC link capacitor, MCU and control electronics, gate drivers, power conversion, active discharge,
motor position sensor, current and voltage sensors, communication interfaces.

### 1.3 Features an engineer decides (system level)

| Feature (question) | Choices | Block | Filters on | Source |
|---|---|---|---|---|
| Power switch technology | SiC MOSFET / IGBT | power modules, gate driver | gate driver short-circuit method; uvlo_v; bias output voltages | SLUA963B p.5; SLUAAH0 p.8 Table 3-1; SLYY169 p.6, p.32 |
| Inverter topology | two-level / three-level T-type | power stage | number of switches / drivers | SPRAD58B p.4 Fig 2-1 |
| DC bus voltage class | 400 V / 800 V | power stage | driver isolation_class / working voltage; sensor input range; HV-bias Vin | SLUAAS4 p.3; SPRAD58B p.3, p.6, p.16; TIDUF23A p.3 |
| Functional safety target | QM / ASIL C / ASIL D | MCU, PMIC, gate driver | functional safety category | SPRAD58B p.3, p.6, p.13; SLUA963B p.2, p.19; TIDUF23A p.1, p.5 |
| Active short circuit (ASC) safe state | none / primary / secondary / both | gate driver | protection contains ASC | SLUA963B p.26-27 Fig 3-24; SPRAD58B p.8, p.11, p.13; TIDUF23A p.4 |
| Redundant supply from HV battery | yes / no | redundant HV-to-LV DC/DC | Vin up to 1 kV, start-up near 30 V | SLUAAS4 p.2, p.8-10; SPRAD58B p.8, p.16 |
| DC-link active discharge | switched resistor (on/off) / PWM resistor / motor windings / power stages / passive bleed | active discharge | isolated switch driver with integrated secondary bias | SPRAD58B p.16-17; TIDUF23A p.22 |
| DC-link voltage sensing | isolated amplifier (analog) / isolated delta-sigma modulator / gate-driver isolated ADC or APWM | isolated voltage sensing | output type; integrated HV divider; ±600 / ±1000 V input | SLUA963B p.18, p.28; TIDUF23A p.6, p.17; SPRAD58B p.20-21 |
| Phase current sensing | Hall C-core / U-shield / differential coreless / multi-sensor coreless / shunt + isolated amplifier / isolated amplifier on a transducer | phase current sensing | sensor technology; overcurrent detection | SPRAD58B p.6, p.19-20 Table 10-1; SLYY169 p.21; TIDUF23A p.3-4 |
| Phases sensed | 3 / 2 (third calculated) | phase current sensing | channel count | SPRAD58B p.20; SLUA963B p.5-6 |
| Rotor position sensor | resolver / inductive / Hall | position sensing | sensor type | SPRAD58B p.6, p.18-19; TIDUF23A p.4 |
| Isolated module temperature sensing | NTC / thermal diode / none | module temp sense (via driver or ADC + isolator) | driver temperature input | SLUA963B p.5, p.18, p.28; TIDUF23A p.19-20; SLYY169 p.19 |
| Isolated CAN | yes / no | CAN transceiver | isolation | SLUAAS4 p.2; TIDUF23A p.7 |
| PMIC with MCU watchdog / error monitoring | yes / no | PMIC | watchdog type (Q&A / trigger) | SLUA963B p.8 Table 2-2; SPRAD58B p.10 |

Other trends SPRAD58B p.6 lists (not decisions on a part, so not in the YAML): Ethernet, EESM motors (extra
excitation H-bridge, p.9), integrating active discharge or a DC/DC controller into the gate driver, and
integrating the transformer into the bias supply.

### 1.4 TI parts named, per block

- MCU: F29H859TU-Q1 (TIDUF23A p.1, p.5), F29H85x / C29 C2000 (SPRAD58B p.9), TMS320F28069M (SPRAD58B p.23, TIDA-01527), Sitara (SPRAD58B p.13, p.17)
- PMIC: TPS653860-Q1, TPS653861-Q1 (SPRAD58B p.10; TIDUF23A p.1); Fig 4-2 is titled TPS65386x-Q1
- Gate drivers: UCC21732-Q1, UCC21750-Q1, UCC21710-Q1, UCC5870-Q1 (SLUA963B); UCC5880-Q1, UCC5881-Q1 (TIDUF23A p.1, p.5; SPRAD58B p.11-13); UCC2182xx-Q1 (SPRAD58B p.11)
- Isolated bias: UCC14240-Q1, UCC14241-Q1, UCC33421-Q1 (TIDUF23A); see section 3.4 for the full list
- Pre-regulator / power tree: LM5158-Q1, LM5157-Q1, LM74202-Q1, TPS7B6933-Q1, TLV733P-Q1, LM63635-Q1 (TIDUF23A p.7, p.11-13)
- Redundant HV supply: UCC28C5x-Q1, UCC28700-Q1, UCC28730-Q1, UCC28740-Q1, UCC28781-Q1 (SLUAAS4 p.3; SPRAD58B p.16); reference designs UCC28C56EVM-066, TIDA-01505, PMP22288, PMP10200 (SPRAD58B p.16)
- Voltage sensing: AMC0386-Q1, AMC0381D-Q1 (TIDUF23A p.6); AMC0380D-Q1 / AMC038x-Q1, AMC3330-Q1 / AMC33xx-Q1, AMC1311, RES60A-Q1 (SPRAD58B p.20-21)
- Current sensing: TMCS2100-Q1, TMCS1123-Q1, TMCS1126-Q1 (SPRAD58B p.19-20). TIDM-02014 itself uses LEM LF 510-S transducers (non-TI, TIDUF23A p.3)
- Position sensing: ALM2403-Q1 (excitation amplifier), INA1650-Q1 (differential amplifier), LDC5072-Q1 (inductive sensor front end) (SPRAD58B p.18-19; TIDUF23A p.7)
- CAN: TCAN1043-Q1, ISO1042-Q1 (TIDUF23A p.6-7)
- Active discharge: TPSI3100-Q1 (isolated switch driver), AFE539F1-Q1 (smart AFE) (SPRAD58B p.17)
- Power module (non-TI, Wolfspeed XM3): CAB450M12XM3 / EAB450M12XM3 / C4B450M12XM3 (TIDUF23A p.3, p.18, p.21)

---

## 2. Isolated gate driver subsystem (one switch position)

### 2.1 Block diagrams read

- **SLUA963B p.9, Fig 3-1 "Block Diagram of a Traction Inverter System with UCC217xx-Q1"** (legend:
  self-test / diagnostics / protection / driver function).
  Primary side of UCC21732-Q1: PWM input (IN+, IN-), shoot-through protection, VCC UVLO, primary logic, fault
  decode, MOD / DEMOD across the barrier, PWM driver for the APWM output; pins RDY, nFLT, nRST/EN, APWM.
  Secondary side: output stage, VDD UVLO, short-circuit clamping, secondary logic, 2-level + soft turn-off,
  Miller clamp control (CLMPE pin to an external Miller clamp), fault encode, OCP logic (OC pin), analog-to-PWM
  (AIN pin). Outside the driver: isolated bias supply with external OVLO + TEST, digital isolators for
  OVLO_MON / UVLO_TEST / OVLO_TEST and VGE_MON / VGE_TEST / OC_TEST / AIN_TEST, gate-source / emitter monitoring,
  12 V battery, PMIC, MCU, CAN bus, HV battery, DC-link capacitor, 3x power stage, motor + position,
  VDC sensing, current sensing, phase voltage sensing.
- **SLUA963B p.11, Fig 3-2**: same system, with failure points F1 (PMIC), F2 (MCU), F3 (driver), F4
  (motor / mechanical) and the prevention circuit for each.
- **SLUA963B p.20, Fig 3-15 (UCC5870-Q1)**: primary: VCC / VREG1 monitor, I/O, shoot-through protection,
  digital core, die-to-die comms, diagnostics + TEST, VREG1; pins nFLT1, nFLT2/DOUT, PWM+, PWM-, SPI (CLK,
  nCS, SDI, SDO), ASC, ASC_EN. Secondary: VCC2 / VREG2 / VEE2 monitor, VCE clamp, DESAT, 2-level / soft
  turn-off, output stage, gate monitor, Miller clamp control, ADC core, OC/SC, ASC logic, digital core,
  VREG2; AI1..AI6 inputs to temperature sensors, shunts, DC-link sense and an HV safety controller.
- **SLUA963B p.21, Fig 3-16**: UCC5870-Q1 failure-prevention view (UVLO/OVLO monitor, shoot-through protection,
  gate voltage monitor, DESAT, OC/SC, ASC override, HV controller, ADC core, die-to-die comms).
- **SLUA963B p.27, Fig 3-24**: ASC interfaces. Primary: PMIC watchdog / MCU drive ASC_EN and ASC_IN.
  Secondary: AI5 = ASC_EN, AI6 = ASC_IN from an HV controller.
- **SLUAAH0 p.27, Fig 13-1 (PMP22817A)**: single-channel gate-drive solution =
  LM5156-Q1 12 V to 24 V SEPIC pre-regulator, UCC14240-Q1 24 V to +15 / -5 V isolated bias, UCC5870-Q1
  30 A isolated gate driver with digital interface, IGBT / SiC (TO-220, 4-pin Kelvin or module).
- **TIDUF23A p.4, Fig 2-1**: isolated gate driver with DESAT, adjustable gate drive, BIST, A-to-D (NTC temp,
  phase node), ASC, SPI; supply diagnostics / monitoring for the HS and LS bias supplies.

### 2.2 Consolidated blocks and connections

| Group | Side | Blocks | Source |
|---|---|---|---|
| Primary-side control | LV | MCU (PWM+/-, SPI, nFLT, RDY, nRST/EN, APWM / DOUT), PMIC | SLUA963B p.9, p.11, p.20, p.21 |
| Driver primary side | LV | PWM input with deglitch, interlock / shoot-through, VCC UVLO, primary logic, SPI, primary ASC | SLUA963B p.9, p.20, p.26-27 |
| Driver barrier | barrier | SiO2 capacitive isolation, die-to-die comms, MOD / DEMOD for PWM and APWM | SLUA963B p.9, p.19, p.21; SLYY169 p.8-9 |
| Driver secondary side | HV | split output stage, VDD / VCC2 / VEE2 UVLO and OVLO, DESAT / OC, 2-level / soft turn-off, Miller clamp, SC clamping, active pulldown, gate monitor, threshold monitor, VCE clamp, isolated ADC / APWM, secondary ASC, TSD, BIST / CRC / clock monitor | SLUA963B p.9, p.11-30; SPRAD58B p.11-13; TIDUF23A p.4 |
| External self-test (UCC217xx case) | barrier | digital isolators, external OVLO and VGE comparators, DESAT / OC test switch | SLUA963B p.9, p.12, p.14, p.16 |
| Isolated bias for this driver | barrier | SEPIC pre-regulator, isolated DC/DC module, enable / power good | SLUAAH0 p.27-28; TIDUF23A p.9 |
| Power switch | HV | IGBT / SiC, sense-FET mirror + shunt, NTC / diode, DESAT diode network, external clamp FET, TVS | SLUA963B p.12-13, p.17-18, p.24, p.28; TIDUF23A p.19 |

Connections: MCU to driver (PWM+/PWM-, SPI, nRST/EN, ASC); driver to MCU (nFLT, RDY, APWM / DOUT); bias supply
to driver secondary (VDD or VCC2 / VEE2); MCU to bias ENA, bias /PG to MCU; driver to switch (OUTH / OUTL,
CLAMP); switch to driver (DESAT or OC, AIN / AIx temperature, VCE clamp sense); external monitors back to the MCU
through digital isolators.

### 2.3 Features an engineer decides

| Feature (question) | Choices | Filters on | Source |
|---|---|---|---|
| Short-circuit detection | DESAT / shunt or sense-FET overcurrent / both | protection contains desaturation / overcurrent | SLUA963B p.12-13, p.22; SLYY169 p.27 Table 4, p.29-33 (DESAT suits IGBT, shunt OC suits SiC); SPRAD58B p.11, p.13 |
| Fault turn-off | normal / soft turn-off / two-level turn-off / selectable | protection contains soft shutdown, 2-level turn-off | SLUA963B p.14-15 Fig 3-7, 3-8, p.23; SPRAD58B p.11 |
| Active Miller clamp | none / internal / external FET driver / configurable | protection contains Miller clamp; clamp type | SLUA963B p.17, p.27; SLYY169 p.23-25; SPRAD58B p.13 |
| Split outputs (OUTH / OUTL) | yes / no | output type | SLYY169 p.11; SPRAD58B p.13 |
| Peak drive current | ±10 A / 15 A / 20 A / 30 A (no external booster) | peak_sink_a, peak_source_a | SLUA963B p.9, p.19; TIDUF23A p.5; SPRAD58B p.11; SLUAAH0 p.27; SLYY169 p.10, p.12 |
| Real-time adjustable drive strength | yes / no | adjustable strength (SPI / GPIO) | SPRAD58B p.6, p.11-13 (more than 2% inverter efficiency, CLTC); TIDUF23A p.5, p.23-26 |
| Secondary UVLO | 12 V / 15 V / 17 V | uvlo_v | SPRAD58B p.11; SLUA963B p.11; SLYY169 p.16 |
| OVLO | integrated / external / none | protection contains OVLO | SLUA963B p.11, p.21; SPRAD58B p.13 |
| Bipolar gate supply (negative VEE) | yes / no | VEE / dual-supply support | SLUAAH0 p.10-11; SLYY169 p.16; SLUA963B p.21 |
| Interlock / dead time | none / fixed interlock / programmable dead time | deadtime; protection contains interlock | SLUA963B p.16-17, p.26; SLYY169 p.13, p.18; SPRAD58B p.13 |
| Input deglitch / min pulse rejection | yes / no | protection contains input glitch filter | SLYY169 p.17; SPRAD58B p.13; SLUA963B p.26 |
| Gate voltage monitoring vs PWM | integrated / external comparator / none | gate monitor | SLUA963B p.15-16, p.24 |
| Gate threshold / health monitoring | yes / no | threshold monitor | SLUA963B p.25; SPRAD58B p.13 |
| Active high-voltage (VCE) clamp | yes / no | protection contains VCE clamp | SLUA963B p.19, p.23-24 |
| Isolated analog channel in driver | none / analog-to-PWM / multi-channel ADC over SPI | isolated ADC / APWM | SLUA963B p.18, p.19, p.28 |
| Module temperature input | NTC or PTC / thermal diode / none | temperature-sensor bias current | SLUA963B p.18, p.28; SPRAD58B p.13; TIDUF23A p.19 |
| ASC inputs on driver | none / primary / primary and secondary | protection contains ASC | SLUA963B p.26-27; SPRAD58B p.11, p.13 |
| Configuration interface | pins only (nFLT / RDY) / SPI (incl. daisy-chain / address) | SPI | SLUA963B p.9, p.19, p.30; SPRAD58B p.11, p.13 |
| Self-test / CRC / clock monitor | integrated / external circuits / none | BIST | SLUA963B p.13-14, p.22, p.29-30; SPRAD58B p.11; TIDUF23A p.4 |
| Driver thermal warning / shutdown | yes / no | protection contains thermal shutdown | SLUA963B p.29 |
| Isolation class | basic / reinforced (up to 5.7 kVrms) | isolation_class, isolation_rating_kvrms | SLUA963B p.9 (1.5 kVrms working, reinforced), p.19 (1 kVrms working, basic); SPRAD58B p.11; SLYY169 p.9 |
| CMTI | at least 100 V/ns / 150 V/ns | cmti_kv_us | SLUA963B p.9, p.19; SLYY169 p.20 |
| Low propagation delay, tight part-to-part skew | yes / no | propagation delay / skew | SLYY169 p.13-15; SLUA963B p.9 |
| Channels per driver | single / dual with interlock | channel_config | SLYY169 p.15, p.18 |
| Driver functional safety category | Functional Safety-Compliant / Quality-Managed | FuSa category | SLUA963B p.2, p.19; TIDUF23A p.1; SPRAD58B p.13 (ASIL D) |
| Automotive, -40 to +125 °C | yes / no | qualification | SPRAD58B p.13 |

Also listed in the documents but not made into decisions: short-circuit clamping and active pulldown (in all
TI traction drivers shown, SLUA963B p.18, p.29); integrated sensing alternatives in SLYY169 p.27 (di/dt,
gate-charge, current transformer / Rogowski).

### 2.4 TI parts named

- UCC21732-Q1 (OC via sense-FET shunt, 2-level turn-off, external Miller clamp CLMPE, APWM; SLUA963B p.9, p.12, p.15, p.17)
- UCC21750-Q1 (DESAT, soft turn-off; SLUA963B p.10, p.13, p.15)
- UCC21710-Q1 (OC, soft turn-off; SLUA963B p.12, p.15)
- UCC5870-Q1 (SPI, 10-bit ADC with AI1..AI6, DESAT + OC, ASC, CRC; SLUA963B p.19-30; SLUAAH0 p.27)
- UCC5880-Q1, UCC5881-Q1 (variable drive strength, 20 A; TIDUF23A p.5; SPRAD58B p.11-13)
- UCC2182xx-Q1 ("protection gate driver", UVLO 12 / 15 / 17 V, 15 A, ASC, BIST; SPRAD58B p.11)
- Evaluation: UCC5880INVERTEREVM (SPRAD58B p.13, p.22), PMP22817A (SLUAAH0 p.27)

---

## 3. Isolated bias power for the gate drivers

### 3.1 Block diagrams read

- **SLUA963B p.31-32, Fig 4-1 / 4-2 / 4-3**: centralized (one isolated supply, six drivers), semi-distributed
  (three HS supplies + one LS supply), distributed (six supplies).
- **SLUAAS4 p.4 Fig 2-1**: LV battery, one pre-regulator for HS and LS, six isolated bias supplies, six drivers.
  **p.5 Fig 2-2**: separate HS and LS pre-regulators. **p.5 Fig 2-3**: HV flyback from the HV battery used as
  the pre-regulator. **p.6 Fig 3-1**: fully distributed. **p.7 Fig 4-1**: semi-distributed, LS shared
  (1:3 transformer). **p.7 Fig 4-2**: semi-distributed, HS shared 1:3 + LS shared 1:3. **p.8 Fig 5-1**:
  centralized 1:6. **p.8 Fig 6-1**: no redundancy, HS from LV battery, LS from HV flyback (1:3) through LDOs.
  **p.9 Fig 6-2**: HV flyback redundancy to all drivers. **p.9 Fig 6-3**: redundancy to LS only.
  **p.10 Fig 6-4**: redundancy to HS only.
- **SLUAAH0 p.7, Fig 3-1**: centralized (1 transformer), distributed (6), semi-distributed (4).
- **SPRAD58B p.14, Fig 6-1**: fully distributed / centralized (1:6, or 1:4 with HS individual and LS shared) /
  semi-distributed (LS from a 1:3 or 1:1 transformer). **Fig 6-2** (p.15): four topologies (PSR flyback,
  open-loop push-pull, open-loop LLC, integrated module).
- **TIDUF23A p.11, Fig 2-5 (power tree)**: 12 V in (J100) to LM74202-Q1 ideal diodes; +12V_H to LM5158-Q1
  SEPIC (24 V) to 3x UCC14240 (VCC2 / VEE2 for U, V, W high side), TPS7B6933-Q1 3.3 V HS logic; the same
  for the low side; LM63635-Q1 5 V to MCU card, CAN, and two UCC33421-Q1 isolated 5 V modules (isolated CAN,
  isolated AMC sensing); LM5157-Q1 dual SEPIC ±15 V for LEM sensors and resolver excitation.
- **SLUAAH0 p.27, Fig 13-1 to 13-3**: LM5156-Q1 SEPIC 12 V to 24 V, UCC14240-Q1 to +15 V / -5 V, UCC5870-Q1.

### 3.2 Consolidated blocks and connections

| Group | Side | Blocks | Source |
|---|---|---|---|
| LV source | LV | 12 V (or 48 V) battery, ideal diode / protection | SLUAAS4 p.3-4; SLUAAH0 p.9; TIDUF23A p.11-12 |
| Pre-regulator | LV | SEPIC / buck-boost / boost / flyback / push-pull; single or separate HS and LS | SLUAAS4 p.4-5; SLUAAH0 p.9, p.27; TIDUF23A p.12-13 |
| Isolated bias, HS | barrier | 3 individual isolated DC/DC (or one 1:3 multi-winding) | SLUAAS4 p.6-7; SLUA963B p.31-32; SPRAD58B p.14 |
| Isolated bias, LS | barrier | 3 individual isolated DC/DC, or one shared 1:3 / 1:1 supply | SLUAAS4 p.6-7; SLUAAH0 p.7-8; SPRAD58B p.14 |
| HV battery flyback | HV | HV battery 400 / 800 V, HV flyback (redundant or pre-regulator) | SLUAAS4 p.3, p.5, p.8-10; SPRAD58B p.16 |
| Post-regulation (optional) | HV | LDO per driver | SLUAAS4 p.8 Fig 6-1; SLUAAH0 p.10 |
| Gate drivers | HV | HS_1..3, LS_1..3 | SLUAAS4 p.4-10 |
| Host / monitoring | LV | ENA / power-good handshake, supply diagnostics, driver primary LDO | SLUAAH0 p.24; TIDUF23A p.4, p.9, p.12 |
| Other isolated rails | barrier | isolated 5 V / 3.3 V module for isolated CAN and sensing | TIDUF23A p.6, p.11-13 |

Connections: LV battery to pre-regulator (8-16 V in; 24 V out for UCC14240-Q1); pre-regulator to HS and LS
isolated supplies; HV flyback to HS and / or LS supplies as a redundant input, or as the pre-regulator;
isolated supplies to drivers (VCC2 / VEE2, e.g. +15 / -4 V); MCU enable to the module, power good back (driver
switching starts only after /PG); separate isolated 5 V modules for isolated CAN and isolated voltage sensing.

### 3.3 Features an engineer decides

| Feature (question) | Choices | Filters on | Source |
|---|---|---|---|
| Bias architecture | centralized / semi-distributed (LS shared) / semi-distributed (HS + LS shared) / fully distributed | isolated outputs; output power per device | SLUA963B p.31-32; SLUAAS4 p.6-8; SLUAAH0 p.7-8; SPRAD58B p.14 |
| Topology | integrated transformer module / PSR flyback / open-loop push-pull / open-loop LLC | integrated transformer; topology | SLUAAS4 p.2-3 Table 1-1, p.6; SPRAD58B p.14-16 |
| Input source | 12 V / 48 V LV battery / HV battery / LV + HV | Vin min / max | SLUAAS4 p.2-3; SPRAD58B p.14, p.16; SLUAAH0 p.3 |
| Pre-regulator | none (wide-Vin) / single / separate HS and LS | pre-reg Vin 3.5-60 V, output current | SLUAAS4 p.4-5 Table 2-1; SLUAAH0 p.9; TIDUF23A p.12-13 |
| Redundancy from HV battery | none / all / LS only / HS only | HV flyback Vin (240-450 V, 550-950 V, up to 1 kV) | SLUAAS4 p.3, p.8-10; SPRAD58B p.16 |
| HV flyback switching | hard-switched / valley / ZVS (primary or secondary regulation) | switching type, feedback, power level | SLUAAS4 p.3 Table 1-2; SPRAD58B p.16 Table 7-1 |
| Output rails | single positive / dual positive-negative / dual positive | dual output; VOUT 15-25 V | SLUAAH0 p.3, p.10-12; SLUAAS4 p.6 Table 3-1 |
| Gate-drive voltages | +15 / -4 V (SiC, TIDM-02014) / +15 / -5 V / +15 / -8 V (IGBT) / +20 V single | VCC2 / VEE2 set points | TIDUF23A p.9, p.12; SLUAAH0 p.8 Table 3-1, p.11-12, p.28; SLYY169 p.6 |
| Output regulation | unregulated / about 5% / 1.5% or better | output accuracy | SLUAAH0 p.10 (SiC conduction loss 1.32x at 13 V vs 15 V); SLUAAS4 p.3; SPRAD58B p.15-16; TIDUF23A p.9 |
| Bias power per driver | 1.0 / 1.5 / 2.0 / 2.5 W | output power (P = QG·ΔV·fsw + ΔV·IQ) | SLUAAH0 p.8-9; SLUAAS4 p.6 Table 3-1; TIDUF23A p.12 |
| Isolation | basic 3 kVrms / reinforced 5 kVrms | isolation_class, isolation_rating_kvrms | SLUAAS4 p.3, p.6; TIDUF23A p.6 |
| Enable and power good | yes / no | ENA / PG pins | SLUAAH0 p.4, p.24-25; TIDUF23A p.9 |
| Bias protections (UVLO, OVP, OCP, TSD) | yes / no | protection | SLUAAH0 p.4; SPRAD58B p.15 |
| Low EMI (spread spectrum, low Cio) | yes / no | spread spectrum | SPRAD58B p.15-16; TIDUF23A p.7, p.12; SLUAAH0 p.1 |
| Low-profile module (< 4 mm) | yes / no | package height | SLUAAH0 p.8; TIDUF23A p.2; SLUAAS4 p.6 |
| Separate isolated 5 V / 3.3 V for isolated CAN / sensing | yes / no / sensor with integrated isolated DC/DC | regulated 5 V / 3.3 V output | TIDUF23A p.6, p.13; SPRAD58B p.20 |

### 3.4 TI parts named

- Integrated transformer modules: UCC14240-Q1, UCC14241-Q1, UCC14140-Q1, UCC14141-Q1, UCC14340-Q1, UCC14341-Q1,
  UCC14130-Q1, UCC14131-Q1, UCC15240-Q1, UCC15241-Q1 (SLUAAS4 p.6 Table 3-1); families UCC1413x / 1414x / 1424x /
  1434x / 1524x-Q1 (SLUAAS4 p.3 Table 1-1); UCC34xxx-Q1, UCC35xxx-Q1, UCC34141-Q1 (SPRAD58B p.15, p.23);
  UCC33421-Q1 (5 V / 3.3 V, 5 kVrms; TIDUF23A p.6)
- LLC: UCC25800-Q1 (SLUAAS4 p.3, p.7; SLUAAH0 p.8; SPRAD58B p.15)
- Push-pull: SN6501-Q1, SN6505-Q1, SN6507-Q1 (SLUAAS4 p.3, p.7; SPRAD58B p.16)
- PSR flyback: LM518x-Q1, LM2518x-Q1, LM515x-Q1, LM34xxx-Q1 (SLUAAS4 p.3, p.7; SPRAD58B p.16)
- HV flyback controllers: UCC28C5x-Q1, UCC28700-Q1, UCC28730-Q1, UCC28740-Q1, UCC28781-Q1 (SLUAAS4 p.3 Table 1-2;
  SPRAD58B p.16 Table 7-1)
- Pre-regulators: LM5155x-Q1, LM5156x-Q1, LM5157x-Q1, LM5158x-Q1 (SLUAAS4 p.4 Table 2-1); LM5156-Q1 (SLUAAH0 p.27);
  LM5158-Q1, LM5157-Q1 (TIDUF23A p.7, p.12-13); UCC280x-Q1 PWM controllers (SLUAAH0 p.9)
- Around it: LM74202-Q1 ideal diode, TPS7B6933-Q1 LDO (TIDUF23A p.7, p.12)

---

## 4. Uncertain points and discrepancies in the sources

- **UCC14240-Q1 power**: 1.5 W in SLUAAH0 p.1, p.3 and TIDUF23A p.5; 2.0 W "typical power" in SLUAAS4 p.6 Table 3-1.
  The SLUAAS4 table (pdfplumber text) is also garbled for the UCC14130/131 rows; the values in the YAML are not
  taken from those rows.
- **UCC14240-Q1 package**: SLUAAH0 p.3 says "wide-body 16-pin SOIC" while p.4 shows a "DWN 36-pin SSOP".
- **UCC5870-Q1 drive current**: 15 A in SLUA963B p.19, 30 A in SLUAAH0 p.27 (likely 15 A source / sink each vs
  a combined figure, but the documents do not say).
- **Gate-driver drive-strength example**: SPRAD58B p.13 says UCC5881-Q1 split output "±15 A and ±5 A"; Fig 5-3
  quotes strong 20 A / weak 5 A; TIDUF23A p.23 quotes 15 A / 5 A.
- **UCC5880INVERTEREVM bias parts**: SPRAD58B p.13 says two UCC14241-Q1; p.22 says two UCC14240-Q1.
- **TIDUF23A typos**: "UCC142140-Q1" (p.5), "LMR63635-Q1 / LM63625-Q1" next to LM63635-Q1 (p.11-13), "1.5 kW" for
  the 1.5 W UCC33421-Q1 (p.13). SPRAD58B writes "LCD5072-Q1" and "LDC5072-Q1" for the same sensor, and
  "AMC038D-Q1". The YAML uses LDC5072-Q1 and LM63635-Q1.
- **Position sensing side of the barrier** differs by figure: SLUA963B Fig 2-4 puts position sensing after a
  signal-isolation block; SLUAAS4 / SPRAD58B Fig 1-1 / 3-1 put the position sensor interface directly on the LV
  side; TIDUF23A has the resolver AFE without an isolator. The YAML puts motor + position on the HV side, as
  the figures do for the motor, and keeps the interface in that group.
- **Redundant supply naming**: "redundant power supply (HV to LV)" in the system figures (SLUAAS4 p.2, SLUAAH0
  p.5) is the same concept as the HV flyback redundancy in SLUAAS4 Section 6. In the system figures it feeds the
  LV rail; in the bias figures it feeds the isolated bias supplies directly.
- The "filters" column names an existing BizDev parameter where one fits (protection, uvlo_v, peak_sink_a,
  peak_source_a, isolation_class, isolation_rating_kvrms, cmti_kv_us, channel_config, deadtime, qualification).
  Everything marked "(new)" in the YAML is a parameter BizDev parts do not carry yet. The parameter mapping
  is my suggestion; the TI documents give the feature, not a BizDev parameter name.
