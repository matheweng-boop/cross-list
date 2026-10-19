# Motor drives (48 V to 72 V+) and where RF switches sit: research notes

Structured data: `motor_and_switches.yaml` (same folder). Everything below comes from a page or document I read. Each item cites its URL and page or figure. Vendor part numbers are listed only as references to what the source draws. They are not BizDev recommendations.

---

## Part 1: 48 V to 72 V (up to ~100 V) motor drives

### Voltage summary

| Entry (yaml id) | Voltage stated by source | Application | Diagram |
|---|---|---|---|
| `lev_motor_drive_48v` | 48 V (SLVA642B p.9 "Rated voltage: 48 VDC"; p.11 "24V, 36V, or 48V nominal"). Fig 4-2 input is "DC input (<100V)". | e-bike / LEV traction | TI LEV page SVG; SLVA642B Fig 4-2 (p.9), Fig 5-1 (p.10); SSZTDA3 Fig 1 (p.2) |
| `lev_traction_inverter_48v_5kw` | 48 V DC bus recommended, 60 V max VDS, 90 V transient (TIDUF56 Table 1-1 p.2, p.3) | 2- and 3-wheeler traction, 5 kW | TIDUF56 Fig 2-1 (p.3) |
| `forklift_inverter_48v_5kw` | 48 VDC lead-acid (TIDUCB6 p.1). Forklift batteries are typically 24, 36 or 48 V, with inverters up to 8 kW (p.2). | forklift / golf cart / tow truck AC traction | TIDUCB6 Fig 2 (p.4) |
| `automotive_48v_bldc_1kw` | 48 V automotive, 1 kW, 30 A (TIDUAY9 p.1) | pumps, fans, eTurbo (not LEV) | TIDUAY9 Fig 1 (p.6), Fig 2 (p.7) |
| `lev_motor_drive_72v` | 18 to 85 V VBUS, up to 20S Li-ion (AN5324 p.1). Tested with a "72V/10000W 3 phase BLDC Motor" (p.10). | e-scooters, e-motorcycles, e-boats | Microchip AN5324 Figure 1 (p.2) |

**72 V gap:** I found no TI or Infineon block diagram that states 72 V.
- TI's newest 2/3-wheeler design (TIDM-02017) is 48 V. Its DRV3255-Q1 gate driver is described as "for 48-V automotive motor drive applications" with 90 V transient support (TIDUF56 p.4).
- Infineon's LEV page has a block diagram, but the diagram gives no voltage. The only 72 V mention is product text: "OptiMOS 6 135 V targets high-power motor-drive applications such as LEV's, e-forklifts, power and gardening tools ... which predominantly use 72 V and 84 V batteries" (https://www.infineon.com/applications/automotive/light-electric-vehicles).
- Infineon's e-bike sub-page diagram labels its blocks 36 V ("Traction Inverter (250W 36V PMSM Motor)").
- The only 72 V-class diagram I found is **Microchip AN5324**.

**Not 48 V:** `tidubp9.pdf` (from the task list) is **TIDA-00901, an automotive 12 V 200 W BLDC drive**, not 48 V. The 48 V design on the TIDA-00281 tool page is documented in **TIDUAY9**, which is what I used. I read TIDUBP9 but kept it out of the yaml.

### 1. Light-EV traction drive, 48 V (TI)

Sources:
- TI LEV block diagram, https://www.ti.com/solution/e_bike. The diagram is an SVG embedded in the page source (`33672-2Wheeler-3WheelerTractionDrive-18246.svg`); its subsystem list sits in the page JSON `VARIANT_LIST`.
- SLVA642B https://www.ti.com/lit/pdf/slva642: Fig 4-2 "Typical Controller Block Diagram" (p.9) and Fig 5-1 "Typical E-Bike Block Diagram" (p.10).
- SSZTDA3 https://www.ti.com/lit/pdf/ssztda3: Fig 1 "E-bike system block diagram showing the DRV8363-Q1 with brake control" (p.2).

Blocks, as labelled on the TI LEV SVG (matches SLVA642B Fig 5-1):
- **Input power protection:** E-Fuse / reverse polarity protection. Fig 4-2 adds eFuse/hot-swap controllers and an ideal diode.
- **Non-isolated DC/DC power supply:** DC/DC, LDO, sequencer. The rails are battery (FETs), 15 V (gate driver) and 5 V (MCU) (SLVA642B p.11, TPS54360 buck rated 8.5 to 60 V in). SSZTDA3 Fig 1 shows 48 V battery to DC/DC to 12 V to LDO to 5 V.
- **Self-diagnostics/monitoring:** temperature sense, supervisor, watchdog, humidity.
- **Wired interface:** RS-485, CAN, isolation, circuit protection. Fig 4-2 adds USB.
- **Sensor input interface:** protection, amp, ADC. Inputs: throttle, brake assist, wheel speed, cadence, torque, grip and seat detection, electronic gear shift.
- **Output user interface:** LED driver, audio amp (lights, horn).
- **Digital processing:** MCU, **redundant MCU**, logic, level shifter.
- **Current and voltage sense:** amp, ADC, REF. Fig 5-1 adds comparator and shunt.
- **Power stage:** 3-phase gate driver plus **GaN/FETs**.
- **Angle sensor:** Hall, or inductive, or AMR ("Inductive or AMR can be sampled directly by MCU ADC").
- **Sensor front end / angle feedback interface:** protection, buffer/level shifter, Schmitt trigger, load switch. Fig 4-2 says the Hall interface is "optional, not required for sensorless control".

Links follow SLVA642B Fig 5-1:
- Battery DC link to input protection to DC/DC, and DC link to the power stage.
- MCU to power stage (PWM, per SSZTDA3 Fig 1).
- Power stage to motor.
- Shunts to current sense to MCU.
- Rider inputs to MCU, and MCU to output UI.
- MCU to and from the wired interface.
- Hall to angle interface to MCU.

Decisions an engineer makes (yaml `features`):
- **Position sensing:** Hall vs sensorless back-EMF. Comparison table in SLVA642B p.10: Hall works at all speeds with no startup shake. Sensorless suits medium to high speed, is very low cost and has high reliability. The TI LEV SVG adds inductive and AMR angle sensors.
- **Current sensing:**
  - Low-side shunts with the amplifier inside the gate driver (Fig 4-2 "Gate drivers w/ optional low-side sense amp"; SSZTDA3 Fig 1 CSA).
  - Discrete op amp (SLVA642B p.13, LM358).
  - The TI LEV page "Current & voltage sense" subsystem lists current-sense amplifiers (INA180-Q1, INA240-Q1, ...) and isolated amplifiers (AMC0300D-Q1, AMC1351, ...).
- **Active short circuit (ASC):** SSZTDA3 pp.1-4.
  - Brake mode turns on all high-side or all low-side FETs to recirculate back-EMF current.
  - DRV8363-Q1 triggers it from the ASCIN pin, over SPI, or automatically on supply over-voltage, even with no MCU.
  - It checks HS/LS VDS to avoid shoot-through and can toggle HS/LS to spread heating.
  - A discrete ASC "involves multiple comparators and sensing circuitry".
- **Gate driver architecture:**
  - 3-phase smart gate driver (DRV8320S, SLVA642B Fig 8-1 p.18).
  - A driver with an integrated buck that generates a low-voltage rail (DRV8323R/DRV8353R, SLVA642B p.11).
  - The LEV page lists BLDC drivers, half-bridge drivers and isolated gate drivers for the power stage.
- **Wired bus:** CAN / RS-485 / USB, optionally isolated.
- **Redundant MCU:** drawn on both TI diagrams. No functional-safety standard (ISO 26262 or similar) is named in these LEV sources, so I did not record one.
- **Input protection type:** e-fuse / hot-swap / ideal diode / load switch / reverse-polarity diode (SLVA642B p.12, diode D5).
- **Switch technology:** Si MOSFET vs GaN (SVG "GaN/FETs").
- Other protection details: overcurrent by external comparator for sudden rises and by feedback current for more than ~50 A (SLVA642B p.14). The brake input accepts high or low level (p.14-15).

### 2. 2/3-wheeler traction inverter 5 kW, 48 V (TI TIDM-02017)

Source: TIDUF56 https://www.ti.com/lit/pdf/tiduf56, Fig 2-1 "TIDM-02017 Two-Wheeler Traction Inverter Block Diagram" (p.3).

Blocks:
- **Bias supply** from the 12 V LV battery: isolated flyback (LM25184-Q1) to rectifier to +12 V isolated, then buck LMR33620-Q1 to 5 V and LDO TPS7A21-Q1 to 3.3 V. LMR38010-Q1 also feeds from the 48 V battery.
- **MCU:** TMS320F28P65x-Q1 (SPI, ePWM, eQEP, eCAP, MCAN, ADC).
- **Gate driver:** DRV3255-Q1 3-phase (SPI/fault), with integrated, configurable ASC (p.4).
- **Inverter:** six switches, 4 MOSFETs in parallel per switch (IAUT300N10S5N015, p.2-3).
- **Position sensing:** ABI/PWM through the TXB0106-Q1 level translator.
- **Signal conditioning:** Ia,b,c, Vbus, Vthrottle. Phase current uses ACS772 Hall-effect in-phase sensors (p.2).
- **CAN:** through the ISO6731-Q1 isolator, with the TCAN1044A-Q1 transceiver (p.5).

Software and safety notes: FreeRTOS runs on the C28x core and FOC runs on the CLA. The ADC hardware redundancy checker is described "for safety-critical ADC conversions" (p.4).

### 3. Forklift AC traction inverter 5 kW, 48 V (TI TIDA-00364)

Source: TIDUCB6 https://www.ti.com/lit/ug/tiducb6/tiducb6.pdf, Fig 2 "Block Diagram" (p.4).

Signal and power path:
- C2000 LaunchPad behind an isolation line (isolated USB to the PC).
- PWM_HS x3 and PWM_LS x3 to UCC27211 half-bridge drivers (120 V, 4 A, bootstrap, external 12 V).
- Drivers to the CSD19536KTT three-phase inverter, 5 FETs in parallel per switch, on an IMS PCB.
- The DC bus link-capacitor board sits between the 48 V battery and the inverter.
- The inverter drives a 33 V ACIM.

This is a power stage only: no current or position sensing and no CAN on the board.
- Choices it raises: ACIM vs DC traction motor (p.2) and the number of FETs in parallel.
- Applications listed (p.1): forklift, golf cart, tow trucks.

### 4. Automotive 48 V 1 kW BLDC (TI TIDA-00281)

Sources: TIDUAY9 https://www.ti.com/lit/pdf/tiduay9, Fig 1 (p.6) and Fig 2 (p.7); tool page https://www.ti.com/tool/TIDA-00281.

The motor runs from 48 V. Everything else runs from the 12 V battery and is isolated from the 48 V side (p.6).

12 V side:
- 12 V protection (LM74610-Q1 + FET).
- TPS40210-Q1 flyback across the barrier to a TPS62152-Q1 buck.
- CAN: HVDA553-Q1 through the ISO7331C digital isolator.

48 V side:
- LM5060-Q1 protection and switching.
- UCC27201A-Q1 120 V half-bridge drivers x3 driving CSD19535KTT FETs.
- OPA365-Q1 / OPA2365-Q1 current sense and LMT86-Q1 temperature sensors per phase.
- Sensorless control, with Hall inputs available.

This is a 48 V mild-hybrid style aux drive, not LEV traction.

### 5. 72 V class: Microchip AN5324 (only 72 V diagram found)

Source: https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ApplicationNotes/ApplicationNotes/High-Power-BLDC-Motor-Driver-Reference-Design-DS00005324.pdf, Figure 1 "Block Diagram" (p.2).

Blocks:
- **Supply:** VBUS up to +85 V (20S) to pre-regulator (85 V to 43 V) to MCP16331 buck at +12 V, then MCP1754S LDOs to +5 V and +3.3 V.
- **Controller:** dsPIC33CK with inputs BRAKE, THROTTLE, AUXILIARY, PAS, UART/I2C, TEMPERATURE, HALL. It has three internal op amps for current sense and CAN through the ATA6561.
- **Drive:** three MIC4104 100 V half-bridge drivers driving 18 x AOTL66912 100 V MOSFETs, 3 in parallel per switch (p.3).
- **Current sense:** low-side 250 µΩ shunts (p.1).
- **Temperature:** MCP9700A on the heat sink.
- **Motor:** BLDC with 5 V Hall sensors.

Ratings: 10 kW peak, 150 A continuous, 300 A peak (p.1).

Decisions it shows:
- Current sensing with the MCU's internal op amps vs external amplifiers.
- A pre-regulator vs a wide-input buck when the bus reaches 85 V.
- 100 V-class FETs and drivers.
- Hall sensing.
- CAN.
- Rider inputs: PAS, throttle, e-brake.

### Infineon (checked)

- https://www.infineon.com/applications/automotive/light-electric-vehicles has a block diagram (static SVG `infineon-10561-blockdiagram-en.svg`, block data from `.../light-electric-vehicles.initialBlockDiagram.en.365.json`).
- Its motor-control part shows: microcontroller, rotor position sensor, current sensor, 3-phase inverter (MOSFETs), gate driver, power supply DC/DC, communication (CAN transceiver). It labels "PMSM / BLDC / Induction Motor", in industrial-grade and automotive-grade variants.
- The same diagram also covers BMS, charger, VCU, HMI, ABS speed sensor, tire pressure, radar (BSD), connectivity (Bluetooth / Wi-Fi), access (NFC) and lighting.
- No voltage is given on the diagram, so I did not turn it into a voltage-specific yaml entry.
- The e-bike sub-page diagram is 36 V.
- The two-three-wheelers sub-page has no block diagram.
- Page product groups: "Motor gate drivers (< 100 V)" and "45 V-80 V N-channel power MOSFETs".

---

## Part 2: where RF switches sit

### Skyworks application pages: how I found them

- The site search API (`POST /api/feature/search/searchitems`, keyword "application") returns 10,440 items but only 14 "Site Page" items with Application-Pages URLs. Most of those are software and tool pages, and `Infrastructure-CRAN-ORAN` is not among them.
- So I collected the full list by crawling the 11 `/en/Markets/*` pages: 77 application-page links.
- `Infrastructure-CRAN-ORAN` now redirects to `/application-pages/infrastructure-oran`, which has text and featured timing parts but **no block diagram**.
- The same API with keyword "block diagram" returns 41 legacy "Block Diagrams" PDFs. Their real file URL is in `ItemUrl` (`/-/media/SkyWorks/Documents/BlockDiagrams/*.pdf`). Two of them (Embedded Connectivity in Handsets, DB-FEM Computing) have no file URL in the index.

Application pages with a block-diagram image: ADAS, Battery Management, EV DC-DC, Infotainment/Digital Cockpit, Lidar/Radar/Camera, Network Gateways, On-Board Chargers, PTC Heaters, Traction Inverters, Radio/Infotainment, Data-center pages, Factory Automation, Motor Control, Macro Radio Unit, Massive MIMO, Small Cell, Connected Home (house picture plus product tables).
- **Only Macro Radio Unit, Massive MIMO and Small Cell draw an RF switch.**
- I opened the Infotainment/Digital Cockpit and Network Gateways images: both are clock-tree diagrams (clock generator / buffer to SoC, tuner, WLAN, PHYs) with no RF parts. I did not open the other automotive, industrial and data-center images one by one; their file names point to timing and isolation content. Radio/Infotainment is covered separately below.

### Systems where an RF switch appears

| System (yaml id) | Where the switch sits | Switch type named | Source |
|---|---|---|---|
| Massive MIMO radio (`rf_massive_mimo_radio`) | **Observational receive switch**: selects coupler feedback into the transceiver ORx port. Also switches inside the **Dual RX module** (switch, LNA, attenuator, LNA, switch) after the circulator. | SP4T RF switches; 0.5-3.0 GHz SPST 50 Ω terminated; "Dual Wideband LNA with Fail-Safe Switch" | https://www.skyworksinc.com/en/Application-Pages/Massive-MIMO (image `M-MIMO-block-diagram-rev32.png`) |
| Macro base station radio unit, TDD (`rf_macro_radio_unit`) | **High-power switch** between the circulator and the Rx chain (LNA with bypass, LNA, limiters), with a termination | High-power SPDT / SPST PIN-diode switches, 100 W / 120 W / 160 W. Page text: "high power fail-safe switches, a critical component for TDD macro base stations ... up to 160W" | https://www.skyworksinc.com/en/Application-Pages/Infrastructure-Macro-Radio-Unit (image `MacroCell20241001R31.png`) |
| Small cell (`rf_small_cell`) | **Switch** between the circulator and the LNA (with termination). The older PDF shows a Tx switch "(TDD)" after the isolator and an antenna switch on Rx. | 0.1-8.5 GHz SPDT, 0.1-6.0 GHz SPDT; "Low Noise Amplifier + Switch" | https://www.skyworksinc.com/en/Application-Pages/Small-Cell (image `Small-Cell-20241016.png`); https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Small_Cell_Basestation.pdf |
| Automotive telematics and infotainment (`rf_automotive_telematics`) | **Cellular front end** (switch, LNA, PA) between the cellular main transceiver and the antenna. GPS, SDARS and WLAN paths have no switch. | Switches SKY13421-486LF, SKY13437-11 | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Telematics_and_Infotainment.pdf |
| V2X 802.11p (`rf_v2x_80211p`) | No discrete switch; the FEM sits between the Wi-Fi chipset and the antenna | n/a | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Car_to_Car_Communication.pdf |
| Wi-Fi networking front end (`rf_wifi_frontend`) | **T/R switch per band** (2.4 / 5 GHz) between PA/LNA and the diplexer to the antenna | 2.5 GHz and 5 GHz switch part lists | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/SB_FEM_Solutions_Networking.pdf |
| Connected home devices (same entry) | Product tables (no wiring diagram) | Home theater / smart speakers: SPDT SKY13585, DPDT SKY13438 (high-power, WLAN), Wi-Fi switch + LNA SKY85207 / SKY85608. Smart lighting: SP2T SKY13587, SP3T SKY13588 ("operation to 105°C"). Set-top box: SKY13585-679LF, SKY13586-678LF. Router FEMs list "PA, LNA w/bypass, T/R Switch". | https://www.skyworksinc.com/en/Application-Pages/IoT-Connected-Home |
| Set-top box / media gateway (note in `rf_wifi_frontend`) | One front end per antenna (Wi-Fi 2.4, Wi-Fi 5, LTE, GPS, RF4CE) | "LTE SPDT Switches" SKY13411-374LF | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Set_Top_Box_Media_Gateway.pdf |
| Smartphone (`rf_smartphone_switches`) | **Primary antenna switch** SP8T-SP16T; **mode/band 2T switches** after the WCDMA PA; **Rx differential DPx 2T/3T**; optional **SP4T diversity antenna switch** | part lists for each switch class | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Smartphone_Using_Discrete_Switches_or_ASMs.pdf |
| Base-station diversity receiver (`rf_basestation_diversity_rx`) | **Switch IC** for channel selection after the high-dynamic-range LNA; **100 dB SPDT** selecting the LO synthesizer; DPDT antenna diversity switches in the part list | DPDT antenna diversity switches; SPDT (SP2T) | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Bast_Station_Receiver_System_Using_Antenna_Diversity.pdf |
| Short-range radio / ISM (`rf_short_range_radio`) | **T/R and PA-bypass switches inside the Tx/Rx FEM** between the antenna filter and the SoC | switch part list (AS179-92LF, SKY13270-92LF, ...) | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Short_Range_Radio.pdf |
| RFID reader, active antennas (`rf_rfid_reader`) | **SP4T 2-6 GHz switch module** selecting 1 of 4 antennas (with bias tees for powering the remote active antennas) | SP4T | https://www.skyworksinc.com/-/media/SkyWorks/Documents/BlockDiagrams/Reader_Active_Antennas.pdf |

RF switches that appear only in an application page's **product list**, with no diagram drawing them (https://www.skyworksinc.com/en/Application-Pages/...):
- **Automotive-Cellular-Telematics** and **Automotive-Cellular-Compensator**: SPDT (0.9-6.0 GHz), SP3T (2.4-2.5 GHz), DPDT (0.4-5.9 GHz "Sky5 switch"), plus "2.4 GHz 802.11ac AEC-Q100 Switch/Low-Noise Amplifier Front End" and the 5 GHz equivalent.
- **Automotive-Remote-Keyless-Entry**: SP3T (0.1-3.0 GHz), SPDT (0.1-8.5 GHz, "AEC-Q100 Grade 2 Qualified").
- **IoT-M2M-Cellular-IOT**: SP3T (0.1-6.0 GHz).
- **IoT-Lighting**: RFX2411N "2.4 GHz TX/RX Booster with Diversity Switch".
- **IoT-Smart-City-and-Energy**: 2.4 GHz switch/LNA front end.
- **Consumer-Set-Top-Boxes**: 2.4-2.5 GHz SPDT switch with LNA; "5 to 1800 MHz Ultra-High Linearity SPDT 75 Ω Switch".
- **Consumer-Routers-and-Gateways** and **Consumer-Wireless-Audio-Video**: 2.4 GHz and 4.9-5.9 GHz SPDT switch with LNA.

These pages show where Skyworks markets switches (automotive telematics, RKE, cellular IoT, lighting, set-top box, consumer Wi-Fi), but they do not show where the switch sits in the system.

Other legacy PDFs mention RF switches in their part lists, but I did not turn them into yaml entries: CATV modem, LNB, satellite systems, base-station transmitter, superheterodyne / direct-conversion transceivers, SkyOne.

### Broadcast radio: no RF switch drawn

Source: https://www.skyworksinc.com/en/Application-Pages/Automotive-Radio-Infotainment. I read diagrams EU4 and US3; the page also has EU5, EU6, US2, India2 and World.

- Two antennas go through a passive **"Band Select (LC)"** network into the tuner inputs (AM In, FM A In, FM B In, B3A/B3B or LTB).
- FM phase diversity is done by feeding two antennas into separate tuner inputs. No switch is drawn.
- The existing template "Car radio tuner system" in `templates.yaml` places `antenna_switch` in the antenna group. **These Skyworks sources do not support that.** I did not edit the template; this note is only for review.

### Qorvo

`https://www.qorvo.com/applications` and `/applications/automotive/telematics` returned **HTTP 429** to automated requests, so they block automated access. I did not try to get around that, and no Qorvo data is included.

---

## Files read (local copies in the session scratchpad)

- Motor: slva642.pdf, ssztda3.pdf, tiducb6.pdf, tidubp9.pdf, tiduay9.pdf, tiduf56.pdf, an5324.pdf, e_bike.html (plus decoded SVG), tida00281.html, Infineon LEV / e-bike / two-three-wheeler pages, block-diagram JSON and SVG.
- RF: 77 Skyworks application pages, 11 market pages, 12 system-solution pages, 38 legacy block-diagram PDFs, block-diagram PNGs (Massive MIMO, Macro, Small Cell, radio EU4 / US3).
