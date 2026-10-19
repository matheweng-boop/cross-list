# Skyworks category tree (skyworksinc.com, collected 2026-10-19)

Companion to `data/catalog/skyworks_parts.yaml` (4,443 parts). Counts below are parts in that file;
"Function id(s)" is the Cross List block-diagram function each category maps to (count per id when a
category splits). See the YAML header for how the data was collected.

## Summary by top category

| Top category | Parts | Main function id(s) | Part-number level |
|---|---:|---|---|
| Isolation | 2249 | `gate_driver`, `digital_isolator`, `isolated_amplifier`, `isolated_smart_switch`*, `isolated_digital_input`*, `rs485_transceiver`, `isolated_switch_driver`, `current_sensor` | orderable |
| Front-end Modules | 439 | `rf_frontend` (`rf_pa`* for PA-only modules) | product (base) |
| Timing | 394 | `clock_generator`, `jitter_attenuator`, `clock_buffer`, `pcie_buffer`, `crystal_oscillator`, `rf_synthesizer`* | orderable / base |
| Diodes | 375 | `schottky_diode`*, `varactor_diode`*, `pin_diode`*, `rf_limiter`* | product / series |
| Amplifiers | 373 | `rf_pa`*, `lna`, `rf_gain_block`*, `audio_amp`, `wireless_audio_soc`* | product (base) |
| Switches | 179 | `rf_switch`, `antenna_switch` | product (often orderable, e.g. -LF) |
| Optocouplers | 86 | `optocoupler`*, `isolated_switch_driver` | product |
| Audio and Radio | 82 | `digital_radio_demod`, `am_fm_tuner`, `single_chip_radio`, `gate_driver`, `wireless_audio_soc`* | base / orderable |
| Power Management | 56 | `led_driver`, `pol_buck`, `pmic`, `load_switch`, `buck_boost` | product |
| Attenuators | 50 | `rf_attenuator`* | product |
| Voice | 39 | `slic`*, `modem_daa`* | base |
| TV and Video | 31 | `tv_demodulator`*, `tv_tuner`* | base |
| RF Passives | 28 | `rf_passive`* | product |
| Mixers/Demodulators/Modulators | 26 | `rf_mixer`* | product |
| Power over Ethernet | 14 | `poe_pse`*, `poe_pd`* | orderable |
| Filters | 10 | `rf_filter`* | product |
| Modems and DAAs | 9 | `modem_daa`* | base |
| PLLs/Synthesizers/VCOs | 3 | `rf_synthesizer`* | product |

`*` = proposed new function id (below). Two parts have `function: null`: AAT3693 (Li-ion battery
charger) and SKY87604-12 (over-molded fuse); no existing id fits and one-off ids were not worth adding.

## Proposed NEW function ids

| id | label | category | used for |
|---|---|---|---|
| `rf_pa` | RF power amplifier / PA module | rf | cellular, Wi-Fi, small-cell, macro driver and GNSS/ZigBee PAs; PA-only modules filed under FEMs |
| `rf_gain_block` | RF gain block / driver / VGA | rf | general-purpose gain blocks, CATV/HFC line and set-top amplifiers, VGAs, small-cell gain blocks |
| `rf_attenuator` | RF attenuator | rf | digital, voltage-variable and fixed (pad) attenuators |
| `rf_mixer` | RF mixer / modulator / demodulator | rf | up/down-conversion, diversity and quadrature mixers/demodulators |
| `rf_synthesizer` | RF PLL / synthesizer / VCO | rf | PLLs/Synthesizers/VCOs and Timing > RF Synthesizers (Si411x/Si4133) |
| `rf_filter` | RF filter | rf | BAW filters |
| `rf_passive` | RF passive component | rf | MIS silicon chip capacitors, multiplexers, power splitters (coaxial resonators/inductors and dividers exist as site categories but list no parts) |
| `rf_transceiver` | RF transceiver | rf | GSM/GPRS transceivers (category exists in the filter tree; no part currently listed) |
| `pin_diode` | PIN diode | rf | switching and attenuator PIN diodes (chips, beam-lead, SMT, hi-rel) |
| `schottky_diode` | Schottky / detector / mixer diode | rf | Schottky, zero-bias detector, beam-lead mixer diodes and quads |
| `varactor_diode` | Varactor (tuning) diode | rf | abrupt and hyperabrupt varactors |
| `rf_limiter` | RF limiter diode / module | rf / protection | limiter diodes, chips and limiter modules |
| `optocoupler` | Optocoupler | isolation | phototransistor, photodarlington, logic-gate, high-speed, linear and Schmitt optocouplers (photovoltaic and MOSFET-driver optos use `isolated_switch_driver`) |
| `isolated_smart_switch` | Isolated smart (high-side) switch | isolation | Si830x / Si834x isolated smart switches with integrated switch |
| `isolated_digital_input` | Isolated digital input (24 V field input) | isolation | Si838x multi-channel isolated digital inputs |
| `wireless_audio_soc` | Wireless audio SoC | audio | wireless audio / gaming SoCs (SKY76280, SKY76303, SKY7636x) |
| `tv_tuner` | TV / STB tuner | radio | Si21x7, Si2151/41, Si2144 |
| `tv_demodulator` | Digital TV / satellite demodulator | radio | Si216x / Si218x DVB, ISDB-T demodulators |
| `slic` | SLIC / ProSLIC voice interface | networking | ProSLIC subscriber line interface circuits |
| `modem_daa` | Modem / DAA | networking | data/voice and fax modems, voice DAAs |
| `poe_pd` | PoE powered-device interface | power | Class 3 / 4 / 8 PoE PD controllers |
| `poe_pse` | PoE PSE controller | power | single- and multi-port PSE controllers |

Mapping notes (existing ids): Timing > Network Synchronizers (IEEE 1588 / SyncE, NetSync, coherent
optical clocks) are mapped to `jitter_attenuator` (they are DPLL jitter attenuators; a separate
`network_synchronizer` id could be added if the app needs it). PCIe clock buffers (by description) use
`pcie_buffer`; PCIe clock generators stay `clock_generator`. Si88xx isolators with integrated dc-dc are
`digital_isolator` (also relevant to `isolated_dcdc`). Si824x Class-D audio drivers are isolated gate
drivers -> `gate_driver`. Si894x / Si8935-37 delta-sigma modulators and Si892x / Si8931-32 isolated
amplifiers -> `isolated_amplifier`; Si8540 (non-isolated high-side current sensor) -> `current_sensor`.
Power Management: Over Voltage Protection -> `load_switch`; RF PMIC -> `pmic`; Step-Down -> `pol_buck`.
Antenna switch modules / tuning / swap / DPDT diversity switches -> `antenna_switch`; all other RF
switches -> `rf_switch`.

## Category tree with part counts

### Amplifiers — 373 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Amplifiers** (total) | 373 | `rf_pa` (254), `lna` (71), `rf_gain_block` (41), `rf_frontend` (3), `audio_amp` (2), `wireless_audio_soc` (2) |
| *(listed without a sub-category on the site; function from description keywords)* | 221 | `rf_pa` (143), `lna` (42), `rf_gain_block` (33), `rf_frontend` (3) |
| Amplifiers for Smart Energy-Connected Home and Automation 802.15.4, ISM and ZigBee® | 2 | `rf_pa` |
| BDS/GPS/GNSS Power Amplifiers | 1 | `rf_pa` |
| CATV Amplifiers | 1 | `rf_gain_block` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Amplifiers for Set-top Box | 1 | `rf_gain_block` |
| Cellular Power Amplifiers | 50 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 2G/GSM/GPRS/EDGE Power Amplifiers | 3 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 3G/CDMA/TDSCDMA/WCDMA Power Amplifiers | 21 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 4G/LTE Power Amplifiers | 13 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 5G/5G NR Power Amplifiers | 1 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Multimode Multiband (MMMB) Power Amplifiers | 12 | `rf_pa` |
| Gain Block (General Purpose) Amplifiers | 3 | `rf_gain_block` |
| Low Noise Amplifiers | 12 | `lna` |
| Multi-Level Class-D Audio Amplifier IC | 2 | `audio_amp` |
| Variable Gain Amplifiers (VGAs) | 3 | `rf_gain_block` |
| Wi-Fi Connectivity Amplifiers | 27 | `rf_pa` (19), `lna` (8) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 2.4 GHz Low Noise Amplifiers for Wi-Fi Connectivity | 4 | `lna` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 2.4 GHz Power Amplifiers for Wi-Fi Connectivity | 14 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 5 GHz Low Noise Amplifiers for Wi-Fi Connectivity | 4 | `lna` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 5 GHz Power Amplifiers for Wi-Fi Connectivity | 5 | `rf_pa` |
| Wireless Audio System-on-Chip (SoC) | 2 | `wireless_audio_soc` |
| Wireless Infrastructure / Small Cell Power Amplifiers | 49 | `rf_pa` (39), `lna` (9), `rf_gain_block` (1) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Driver Amp for Macro Base Station and Massive MIMO | 28 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Efficiency Linearizable Small Cell Power Amplifiers | 4 | `rf_pa` (3), `lna` (1) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Linearity Pre-Driver Power Amplifiers | 8 | `rf_pa` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ LNA and Pre Driver for Macro Base Station and Massive MIMO | 8 | `lna` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Small Cell Gain Blocks | 1 | `rf_gain_block` |

### Attenuators — 50 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Attenuators** (total) | 50 | `rf_attenuator` |
| *(listed without a sub-category on the site; function from description keywords)* | 17 | `rf_attenuator` (17) |
| Digital Attenuators | 2 | `rf_attenuator` |
| Fixed Attenuator Pads | 30 | `rf_attenuator` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ ATN3580 Fixed Attenuator Pads | 15 | `rf_attenuator` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ ATN3590 Fixed Attenuator Pads | 15 | `rf_attenuator` |
| Voltage Variable Attenuators | 1 | `rf_attenuator` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 0.7 - 5.0 GHz Plastic Packaged Voltage Variable Attenuators - PIN Diode-Based | 1 | `rf_attenuator` |

### Audio and Radio — 82 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Audio and Radio** (total) | 82 | `digital_radio_demod` (29), `am_fm_tuner` (24), `single_chip_radio` (22), `gate_driver` (4), `wireless_audio_soc` (3) |
| Automotive Digital Data Receivers | 3 | `digital_radio_demod` |
| Automotive Digital Radio Coprocessors | 26 | `digital_radio_demod` |
| Automotive Tuners | 24 | `am_fm_tuner` |
| Class D Audio Drivers | 4 | `gate_driver` |
| Consumer Digital Radios | 6 | `single_chip_radio` |
| FM Radios | 3 | `single_chip_radio` |
| Multiband Radios | 13 | `single_chip_radio` |
| Wireless Gaming | 3 | `wireless_audio_soc` |

### Diodes — 375 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Diodes** (total) | 375 | `schottky_diode` (209), `varactor_diode` (77), `pin_diode` (55), `rf_limiter` (34) |
| *(listed without a sub-category on the site; function from description keywords)* | 127 | `varactor_diode` (59), `schottky_diode` (35), `pin_diode` (31), `rf_limiter` (2) |
| High Reliability Diodes | 11 | `rf_limiter` (10), `pin_diode` (1) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Hermetic Ceramic Packaged Silicon Limiter Diodes | 10 | `rf_limiter` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Hermetic Ceramic Switching PIN Diodes | 1 | `pin_diode` |
| Limiter Diodes | 22 | `rf_limiter` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Limiter Diode Chips | 10 | `rf_limiter` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Limiter Modules | 2 | `rf_limiter` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Plastic Surface Mount (SMT) Limiter Diodes | 10 | `rf_limiter` |
| PIN Diodes | 23 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Attenuator PIN Diodes | 6 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Attenuator PIN Diode Chips | 1 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Attenuator PIN Diodes | 1 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Plastic Surface Mount (SMT) Attenuator PIN Diodes | 4 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Switching Silicon PIN Diodes | 17 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam Lead PIN Diodes | 2 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Switching PIN Diodes | 8 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ PIN Diode Chips | 6 | `pin_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ PIN Diode Wafer on Film Frame | 1 | `pin_diode` |
| Schottky Diodes | 174 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 0201 and Plastic Surface Mount (SMT) Schottky | 3 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ AEC-Q101 Qualified Schottky Diodes | 2 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Schottky Diode | 61 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Anti-Parallel, N-Type | 10 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Bridge Quad | 9 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Common Cathode | 12 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead P-Type Detector | 4 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Ring Quad | 11 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Series Pair, N-Type | 6 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Beam-Lead Single N-Type | 9 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Schottky Diodes | 82 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Epoxy Octo Quad Ring Schottky Diodes | 3 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Hermetic Ceramic Schottky Diodes | 72 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Silicon Schottky Barrier Diodes | 3 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Zero Bias Silicon Schottky Barrier Detector Diodes (CDC763X) | 2 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Zero Bias Silicon Schottky Barrier Detector Diodes (DDC235X) | 2 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Schottky Chips and Beamless Diodes | 24 | `schottky_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Schottky Diode Wafer on Film Frame | 2 | `schottky_diode` |
| Varactor Diodes | 18 | `varactor_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Abrupt Varactor Diodes | 5 | `varactor_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Hermetic Ceramic Abrupt Varactor Diodes | 5 | `varactor_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Hyperabrupt Varactor Diodes | 13 | `varactor_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ High Reliability Hermetic Ceramic Hyperabrupt Varactor Diodes | 5 | `varactor_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Hyperabrupt Varactor Diode Chips | 1 | `varactor_diode` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Plastic Surface Mount (SMT) Hyperabrupt Varactor Diodes | 7 | `varactor_diode` |

### Filters — 10 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Filters** (total) | 10 | `rf_filter` |
| BAW Filters | 10 | `rf_filter` |

### Front-end Modules — 439 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Front-end Modules** (total) | 439 | `rf_frontend` (432), `rf_pa` (7) |
| *(listed without a sub-category on the site; function from description keywords)* | 173 | `rf_frontend` (167), `rf_pa` (6) |
| BDS/GPS/GNSS Front-end Modules | 9 | `rf_frontend` |
| CATV Front-end Modules | 1 | `rf_frontend` |
| Cellular Front-end Modules | 82 | `rf_frontend` (81), `rf_pa` (1) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 2G/GSM/GPRS/EDGE Front-end Modules | 10 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 3G/CDMA/TDSCDMA/WCDMA Front-end Modules | 9 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 4G/LTE Front-end Modules | 27 | `rf_frontend` (26), `rf_pa` (1) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 5G/5G NR Front-end Modules | 24 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Front-end Modules for Cellular IoT and M2M | 6 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Multi-Band Front-end Modules for Cellular | 6 | `rf_frontend` |
| Diversity Receive Modules | 8 | `rf_frontend` |
| Front-end Modules for Automotive | 28 | `rf_frontend` |
| Front-end Modules for Connected Home, Industrial, M2M, Medical, Smart Energy and Wearables | 35 | `rf_frontend` |
| Infrastructure Front-end Modules | 1 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Front-end Modules for Massive-MIMO | 1 | `rf_frontend` |
| Wi-Fi Connectivity Front-end Modules | 102 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 2.4 GHz Front-end Modules for Wi-Fi Connectivity | 37 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 5 GHz Front-end Modules for Wi-Fi Connectivity | 43 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ 6 GHz Front-end Modules for Wi-Fi Connectivity | 15 | `rf_frontend` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Multi-Band Front-end Modules for Wi-Fi Connectivity | 7 | `rf_frontend` |

### Isolation — 2249 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Isolation** (total) | 2249 | `gate_driver` (1118), `digital_isolator` (1018), `isolated_amplifier` (60), `isolated_smart_switch` (24), `isolated_digital_input` (14), `rs485_transceiver` (10), `isolated_switch_driver` (4), `current_sensor` (1) |
| Digital Isolators | 1018 | `digital_isolator` |
| Industrial IO | 38 | `isolated_smart_switch` (24), `isolated_digital_input` (14) |
| Isolated Analog and ADCs | 60 | `isolated_amplifier` |
| Isolated Current Sensors | 1 | `current_sensor` |
| Isolated FET Drivers | 4 | `isolated_switch_driver` |
| Isolated Gate Drivers | 1118 | `gate_driver` |
| Isolated Transceivers | 10 | `rs485_transceiver` |

### Mixers/Demodulators/Modulators — 26 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Mixers/Demodulators/Modulators** (total) | 26 | `rf_mixer` |
| *(listed without a sub-category on the site; function from description keywords)* | 21 | `rf_mixer` (21) |
| Diversity Downconverter Mixers | 2 | `rf_mixer` |
| Single Channel Mixers | 2 | `rf_mixer` |
| Up/Downconversion Mixers | 1 | `rf_mixer` |

### Modems and DAAs — 9 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Modems and DAAs** (total) | 9 | `modem_daa` |
| Data and Voice Modems | 7 | `modem_daa` |
| Fax Modems | 2 | `modem_daa` |

### Optocouplers — 86 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Optocouplers** (total) | 86 | `optocoupler` (80), `isolated_switch_driver` (6) |
| High-speed MOS-FET Driver | 2 | `isolated_switch_driver` |
| High-speed Optocouplers | 14 | `optocoupler` |
| High-speed Switching, High CMR, Logic Gate Optocouplers | 6 | `optocoupler` |
| Linear Optocouplers | 2 | `optocoupler` |
| Low Input Current Photodarlington Optocouplers | 11 | `optocoupler` |
| Phototransistor Optocouplers | 44 | `optocoupler` |
| Photovoltaic Optocouplers | 4 | `isolated_switch_driver` |
| Schmitt Trigger Optocouplers | 3 | `optocoupler` |

### PLLs/Synthesizers/VCOs — 3 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **PLLs/Synthesizers/VCOs** (total) | 3 | `rf_synthesizer` |
| *(listed without a sub-category on the site; function from description keywords)* | 2 | `rf_synthesizer` (2) |
| High Performance Synthesizers | 1 | `rf_synthesizer` |

### Power Management — 56 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Power Management** (total) | 56 | `led_driver` (41), `pol_buck` (7), `pmic` (3), `load_switch` (2), `buck_boost` (1), null (2) |
| *(listed without a sub-category on the site; function from description keywords)* | 22 | `led_driver` (15), `pol_buck` (4), `buck_boost` (1), null (2) |
| Display and Lighting | 26 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ LED Camera Flash Drivers | 7 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Charge Pump™ Camera LED Flash Drivers | 5 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Serial Boost Camera LED Flash Drivers | 2 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Mid to Large Screen LCD LED Backlight with PMW Interface | 2 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ RGB LED Driver | 1 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ White LED Drivers | 16 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Charge Pump Based White LED Backlight Drivers | 15 | `led_driver` |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└ Serial Boost White LED Backlight Drivers | 1 | `led_driver` |
| Port Protection and Power Distribution | 2 | `load_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Over Voltage Protection | 2 | `load_switch` |
| Voltage Regulation | 6 | `pmic` (3), `pol_buck` (3) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ RF PMIC | 4 | `pmic` (3), `pol_buck` (1) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Step-Down Converters | 2 | `pol_buck` |

### Power over Ethernet — 14 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Power over Ethernet** (total) | 14 | `poe_pse` (8), `poe_pd` (6) |
| PSE Controllers - Power Sourcing Equipment | 8 | `poe_pse` |
| Powered Devices | 6 | `poe_pd` |

### RF Passives — 28 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **RF Passives** (total) | 28 | `rf_passive` |
| *(listed without a sub-category on the site; function from description keywords)* | 3 | `rf_passive` (3) |
| MIS Silicon Chip Capacitors | 22 | `rf_passive` |
| Multiplexers | 3 | `rf_passive` |

### Switches — 179 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Switches** (total) | 179 | `rf_switch` (147), `antenna_switch` (32) |
| *(listed without a sub-category on the site; function from description keywords)* | 94 | `rf_switch` (83), `antenna_switch` (11) |
| Antenna Swap Switches | 3 | `antenna_switch` |
| Antenna Switch Modules | 8 | `antenna_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Carrier Aggregation Switches | 3 | `antenna_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Throw Count (>4T) Switches / Antenna Switch Modules (ASM) | 5 | `antenna_switch` |
| Antenna Tuning Switches | 5 | `antenna_switch` |
| Band Distribution, General Purpose Signal Routing | 57 | `rf_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ High Throw Count Switches (Band Distribution, Linear Tx/Rx, Rx Diversity, General Purpose Signal Routing) | 13 | `rf_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ SP3T RF Switches | 11 | `rf_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ SP4T RF Switches | 7 | `rf_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ SPDT (SP2T) RF Switches | 26 | `rf_switch` |
| DPDT Antenna Diversity Switches | 5 | `antenna_switch` |
| Differential Receive Filter Switches | 1 | `rf_switch` |
| High Power SPDT and SPST PIN Diode Switches | 3 | `rf_switch` |
| Switches for Infrastructure | 3 | `rf_switch` |
| &nbsp;&nbsp;&nbsp;&nbsp;└ Switches for Macro Base Station and Massive MIMO | 3 | `rf_switch` |

### TV and Video — 31 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **TV and Video** (total) | 31 | `tv_demodulator` (27), `tv_tuner` (4) |
| Digital TV and Satellite Demodulators | 27 | `tv_demodulator` |
| TV Tuners | 4 | `tv_tuner` |

### Timing — 394 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Timing** (total) | 394 | `clock_generator` (133), `jitter_attenuator` (130), `clock_buffer` (54), `crystal_oscillator` (43), `pcie_buffer` (24), `rf_synthesizer` (10) |
| Clock Buffers | 78 | `clock_buffer` (54), `pcie_buffer` (24) |
| Clock Generators | 133 | `clock_generator` |
| Jitter Attenuators | 66 | `jitter_attenuator` |
| Network Synchronizers (IEEE 1588 / SyncE) | 64 | `jitter_attenuator` |
| Oscillators | 43 | `crystal_oscillator` |
| RF Synthesizers | 10 | `rf_synthesizer` |

### Voice — 39 parts

| Category | Parts | Function id(s) |
|---|---:|---|
| **Voice** (total) | 39 | `slic` (38), `modem_daa` (1) |
| ProSLIC Voice Solutions | 38 | `slic` |
| Voice DAAs | 1 | `modem_daa` |

## Product families (Silabs-heritage tables, orderable part numbers)

| Category | Family (base) | Parts |
|---|---|---:|
| Audio and Radio > Automotive Digital Data Receivers | Si462x Automotive Digital Data Receivers | 3 |
| Audio and Radio > Automotive Digital Radio Coprocessors | Si461x Automotive Digital Radio Coprocessors | 2 |
| Audio and Radio > Automotive Digital Radio Coprocessors | Si469xx/xxC Automotive Digital Radio Coprocessors | 24 |
| Audio and Radio > Automotive Tuners | Si4790x Automotive Tuners | 3 |
| Audio and Radio > Automotive Tuners | Si4791x High-Performance Automotive AM/FM Radio Receiver and HD Radio™/DAB/DAB+/DMB/DRM Tuner with Audio System | 2 |
| Audio and Radio > Automotive Tuners | Si4792x High-Performance Automotive AM/FM Radio Receiver and HD Radio™ Tuner with Audio System | 4 |
| Audio and Radio > Automotive Tuners | Si4794x Automotive RF-to-IQ Tuners | 1 |
| Audio and Radio > Automotive Tuners | Si4795x Automotive Receivers | 3 |
| Audio and Radio > Automotive Tuners | Si4796x Automotive Dual Receivers | 3 |
| Audio and Radio > Automotive Tuners | Si4797x Automotive Dual Receivers with Audio DSP Subsystem | 4 |
| Audio and Radio > Automotive Tuners | Si4798x Automotive Receivers with Audio DSP Subsystem | 4 |
| Audio and Radio > Class D Audio Drivers | Si824x Class D Audio Drivers | 4 |
| Audio and Radio > Consumer Digital Radios | Si468x Digital Radios | 6 |
| Audio and Radio > FM Radios | Si4704/05 FM Radio Receivers | 2 |
| Audio and Radio > FM Radios | Si4706 Enhanced FM RDS/TMC Radio Receiver | 1 |
| Audio and Radio > Multiband Radios | Si4730/31 AM/FM Radio Receivers | 2 |
| Audio and Radio > Multiband Radios | Si4734/35 AM/FM/SW/LW Radio Receivers | 2 |
| Audio and Radio > Multiband Radios | Si4825/31/35/36 Mechanically-Tuned AM/FM Radio Receivers | 6 |
| Audio and Radio > Multiband Radios | Si4827/40/44 Analog-Tuned AM/FM/SW Radio Receivers | 3 |
| Audio and Radio > Wireless Gaming | Wireless Gaming | 3 |
| Isolation > Digital Isolators | Si80xx 1 kV 3–6 Channel Digital Isolators | 7 |
| Isolation > Digital Isolators | Si84xx Digital Isolators | 90 |
| Isolation > Digital Isolators | Si86Px Digital Isolators | 30 |
| Isolation > Digital Isolators | Si86Sx Automotive Digital Isolators | 140 |
| Isolation > Digital Isolators | Si86Sx Digital Isolators | 140 |
| Isolation > Digital Isolators | Si86xx Automotive Digital Isolators | 163 |
| Isolation > Digital Isolators | Si86xx Digital Isolators | 163 |
| Isolation > Digital Isolators | Si86xxT Automotive Digital Isolators | 20 |
| Isolation > Digital Isolators | Si86xxT Digital Isolators | 21 |
| Isolation > Digital Isolators | Si87xx Automotive Optocoupler Replacement Isolators | 5 |
| Isolation > Digital Isolators | Si87xx Digital Isolators | 26 |
| Isolation > Digital Isolators | Si88xx Automotive Digital Isolators with Integrated dc-dc Converter | 92 |
| Isolation > Digital Isolators | Si88xx Digital Isolators | 121 |
| Isolation > Industrial IO | Si830x Smart Switch | 2 |
| Isolation > Industrial IO | Si834x Isolated Smart Switch | 22 |
| Isolation > Industrial IO | Si838x Digital Isolators | 14 |
| Isolation > Isolated Analog and ADCs | Si892x Automotive Isolated Amplifier | 8 |
| Isolation > Isolated Analog and ADCs | Si892x Isolated Amplifier | 8 |
| Isolation > Isolated Analog and ADCs | Si8931/32 Automotive Isolated Amplifier for Voltage Measurement | 4 |
| Isolation > Isolated Analog and ADCs | Si8931/32 Isolated Amplifier for Voltage Measurement | 4 |
| Isolation > Isolated Analog and ADCs | Si8935/36/37 Automotive Isolated Delta-Sigma Modulator for Voltage Measurement | 6 |
| Isolation > Isolated Analog and ADCs | Si8935/36/37 Isolated Delta-Sigma Modulator for Voltage Measurement | 6 |
| Isolation > Isolated Analog and ADCs | Si894x Automotive Isolated Delta-Sigma Modulator for Current Measurement | 12 |
| Isolation > Isolated Analog and ADCs | Si894x Isolated Delta-Sigma Modulator for Current Measurement | 12 |
| Isolation > Isolated FET Drivers | Si875x Automotive Isolated FET Drivers | 2 |
| Isolation > Isolated FET Drivers | Si875x Isolated FET Drivers | 2 |
| Isolation > Isolated Gate Drivers | Si822x/3x Automotive Isolated Gate Drivers | 73 |
| Isolation > Isolated Gate Drivers | Si822x/3x Isolated Gate Drivers | 84 |
| Isolation > Isolated Gate Drivers | Si8239x Automotive Isolated Gate Drivers | 75 |
| Isolation > Isolated Gate Drivers | Si8239x Isolated Gate Drivers | 75 |
| Isolation > Isolated Gate Drivers | Si823Hx Automotive Isolated Gate Drivers | 54 |
| Isolation > Isolated Gate Drivers | Si823Hx Isolated Gate Drivers | 54 |
| Isolation > Isolated Gate Drivers | Si825xx Automotive Isolated Gate Drivers | 12 |
| Isolation > Isolated Gate Drivers | Si825xx Isolated Gate Drivers | 6 |
| Isolation > Isolated Gate Drivers | Si826x Automotive Isolated Gate Drivers | 3 |
| Isolation > Isolated Gate Drivers | Si826x Isolated Gate Drivers | 12 |
| Isolation > Isolated Gate Drivers | Si827x Automotive Isolated Gate Drivers | 34 |
| Isolation > Isolated Gate Drivers | Si827x Isolated Gate Drivers | 34 |
| Isolation > Isolated Gate Drivers | Si828x Automotive Isolated Gate Drivers | 48 |
| Isolation > Isolated Gate Drivers | Si828x Isolated Gate Drivers | 48 |
| Isolation > Isolated Gate Drivers | Si829x Automotive Isolated Gate Driver for EV Traction Inverters | 10 |
| Isolation > Isolated Gate Drivers | Si82Ax Automotive Isolated Gate Drivers | 32 |
| Isolation > Isolated Gate Drivers | Si82Ax Isolated Gate Drivers | 32 |
| Isolation > Isolated Gate Drivers | Si82Bx Automotive Isolated Gate Drivers | 41 |
| Isolation > Isolated Gate Drivers | Si82Bx Isolated Gate Drivers | 40 |
| Isolation > Isolated Gate Drivers | Si82Cx Automotive Isolated Gate Drivers | 32 |
| Isolation > Isolated Gate Drivers | Si82Cx Isolated Gate Drivers | 32 |
| Isolation > Isolated Gate Drivers | Si82Dx Automotive Isolated Gate Drivers | 42 |
| Isolation > Isolated Gate Drivers | Si82Dx Isolated Gate Drivers | 41 |
| Isolation > Isolated Gate Drivers | Si82Ex Automotive Isolated Gate Drivers | 42 |
| Isolation > Isolated Gate Drivers | Si82Ex Isolated Gate Drivers | 62 |
| Isolation > Isolated Gate Drivers | Si82Fx Automotive Isolated Gate Drivers | 50 |
| Isolation > Isolated Gate Drivers | Si82Fx Isolated Gate Drivers | 50 |
| Isolation > Isolated Transceivers | Si858x Isolated RS-485 Transceivers | 10 |
| Modems and DAAs > Data and Voice Modems | Data and Voice Modems | 7 |
| Modems and DAAs > Fax Modems | Fax Modems | 2 |
| Power over Ethernet > PSE Controllers - Power Sourcing Equipment | Multi-port PSE Controllers | 6 |
| Power over Ethernet > PSE Controllers - Power Sourcing Equipment | Single-port PSE Controllers | 2 |
| Power over Ethernet > Powered Devices | Class 3 15W Powered Devices | 4 |
| Power over Ethernet > Powered Devices | Class 4 30W Powered Devices | 1 |
| Power over Ethernet > Powered Devices | Class 8 90W Powered Devices | 1 |
| TV and Video > Digital TV and Satellite Demodulators | Si2164/62/60 Digital DVB-C2 TV Demodulators | 3 |
| TV and Video > Digital TV and Satellite Demodulators | Si21642/622/602 Dual DVB-T2/C2/S2X/S2/T/C/S Digital Demodulators | 3 |
| TV and Video > Digital TV and Satellite Demodulators | Si2165 Demodulator | 3 |
| TV and Video > Digital TV and Satellite Demodulators | Si2166 Satellite TV Demodulator | 2 |
| TV and Video > Digital TV and Satellite Demodulators | Si2167-D DVB-S2X/S2/T/C/S Digital Demodulator | 2 |
| TV and Video > Digital TV and Satellite Demodulators | Si21672/662 Dual Digital TV Demodulators | 2 |
| TV and Video > Digital TV and Satellite Demodulators | Si2168 Digital TV Demodulators | 1 |
| TV and Video > Digital TV and Satellite Demodulators | Si2169 Dual Digital TV Demodulators | 1 |
| TV and Video > Digital TV and Satellite Demodulators | Si21692/682 Dual Digital TV Demodulators | 2 |
| TV and Video > Digital TV and Satellite Demodulators | Si2183/82/81/80 Digital ISDB-T TV Demodulators | 4 |
| TV and Video > Digital TV and Satellite Demodulators | Si21832/822/812/802 Dual ISDB-T Digital Demodulators | 4 |
| TV and Video > TV Tuners | Si2144 6th Generation Silicon STB Tuner ICs | 1 |
| TV and Video > TV Tuners | Si2151/41 6th Generation Silicon TV Tuner ICs | 2 |
| TV and Video > TV Tuners | Si21x7 5th Generation Silicon TV Tuner ICs | 1 |
| Timing > Clock Buffers | Any Format Clock Buffers | 19 |
| Timing > Clock Buffers | Automotive Clock Buffers | 4 |
| Timing > Clock Buffers | Automotive PCI Express Clock Buffers | 4 |
| Timing > Clock Buffers | CMOS Clock Buffers | 9 |
| Timing > Clock Buffers | HCSL Clock Buffers | 5 |
| Timing > Clock Buffers | HSTL Clock Buffers | 1 |
| Timing > Clock Buffers | LVDS Clock Buffers | 8 |
| Timing > Clock Buffers | LVPECL Clock Buffers | 10 |
| Timing > Clock Buffers | PCIe Clock Buffers | 13 |
| Timing > Clock Buffers | PCIe Zero-Delay Clock Buffers | 4 |
| Timing > Clock Buffers | SSTL Clock Buffers | 1 |
| Timing > Clock Generators | Automotive Clock Generators | 13 |
| Timing > Clock Generators | Automotive PCIe Clock Generators | 2 |
| Timing > Clock Generators | CMOS Clock Generators | 22 |
| Timing > Clock Generators | General Purpose Clock Generators | 29 |
| Timing > Clock Generators | Low-Jitter Clock Generators | 24 |
| Timing > Clock Generators | PCIe Clock Generators | 25 |
| Timing > Clock Generators | Ultra-Low Jitter Clock Generators | 18 |
| Timing > Jitter Attenuators | General Purpose Jitter Attenuators | 36 |
| Timing > Jitter Attenuators | High-Performance Jitter Attenuators | 19 |
| Timing > Jitter Attenuators | Wireless Jitter Attenuators | 11 |
| Timing > Network Synchronizers (IEEE 1588 / SyncE) | Coherent Optical Clocks | 2 |
| Timing > Network Synchronizers (IEEE 1588 / SyncE) | Legacy Network Synchronizer Clocks | 14 |
| Timing > Network Synchronizers (IEEE 1588 / SyncE) | NetSync™ Network Synchronizer Clocks | 48 |
| Timing > Oscillators | General Purpose Oscillators - XO | 8 |
| Timing > Oscillators | General Purpose Voltage Controlled Crystal Oscillators - VCXO | 6 |
| Timing > Oscillators | Low Jitter Crystal Oscillators - XO | 8 |
| Timing > Oscillators | Low Jitter Voltage Controlled Crystal Oscillators - VCXO | 4 |
| Timing > Oscillators | Ultra Series™ Crystal Oscillators - XO | 13 |
| Timing > Oscillators | Ultra Series™ Voltage Controlled Crystal Oscillators -VCXO | 4 |
| Timing > RF Synthesizers | RF Synthesizers | 10 |
| Voice > ProSLIC Voice Solutions | Si3217x + Si32911/19 Single-Chip ProSLIC | 12 |
| Voice > ProSLIC Voice Solutions | Si3218x Single-Channel ProSLIC | 2 |
| Voice > ProSLIC Voice Solutions | Si3219x Next Generation Single-Channel ProSLIC | 4 |
| Voice > ProSLIC Voice Solutions | Si3226x Single-Chip Dual ProSLIC | 4 |
| Voice > ProSLIC Voice Solutions | Si3228x Dual Channel ProSLIC | 8 |
| Voice > ProSLIC Voice Solutions | Si3229x Next Generation Dual Channel ProSLIC | 6 |
| Voice > ProSLIC Voice Solutions | Si3239x Analog Interface ProSLIC | 2 |
| Voice > Voice DAAs | Voice DAAs | 1 |

## Gaps and notes

- **No sub-category for 680 RF parts.** The site search lists them only under the top category
  (Amplifiers 221, Front-end Modules 173, Diodes 127, Switches 94, Power Management 22, Mixers 21,
  Attenuators 17, RF Passives 3, PLLs 2); they are not in the parametric "Product Specification"
  tables. Their function id was assigned from description keywords (e.g. "Low Noise" -> `lna`).
  Most are older parts (many are Obsolete / Last Time Buy in the lifecycle lookup).
- **Part-number level differs by line.** Silabs-heritage tables (Isolation, PoE, most Timing buffers)
  list orderable OPNs; RF lines list product/base numbers or "... Series" pages (diodes).
- **Lifecycle** comes from the separate Product Lifecycle Status Lookup (no status on product pages);
  292 listed parts are not in the lookup (status null). Base parts take the best status among
  matching orderable codes.
- **Excluded:** 313 evaluation-kit pages, 2 reference designs (SKYR23001-11, SKYR60002), 134 family
  overview pages (their parts are listed individually), 5 duplicate pages (SKY53512/53542/53582 listed
  under both HCSL and PCIe clock buffers; two gate-driver OPNs whose page title disagrees with the URL).
- **Blocked / broken:** `/api/sitecore/Product/DownloadExcel` (the public "Export Product Excel" button)
  returns HTTP 500; `sitemap.xml` is truncated at 5,000 URLs; `/en/Products/Voice/Si3000-Voice-Codecs`
  returns 404; the Si8540 family table is empty. No captcha/login/rate-limit was encountered.
- Filter-tree categories whose parametric table returned 0 rows (parts there, if any, were placed
  only via the search category or keywords): Transceivers > GSM/GPRS Transceivers; Switches > SPST RF
  Switches, High Reliability Switches, Smart Coupler; FEM > Bluetooth Front-end Modules; PIN / varactor
  AEC-Q101 sub-categories, wafer-on-film-frame and abrupt varactor chips/SMT; FET-based VVAs; quadrature
  demodulators and mixer modules with VCO; Fractional-N synthesizers; Slew Rate Controlled load switches;
  Coaxial Inductors / Resonators and Power Dividers; several CATV/HFC, Bluetooth PA, dual-band Wi-Fi PA,
  WiMAX PA and 5G NR PA amplifier sub-categories. The Silabs-heritage families (Timing, Isolation, Audio
  and Radio, TV and Video, Voice, PoE, Modems) are not in this filter tree at all; they were read from
  their own family tables.
- `wireless_audio_soc` covers SKY76280/76303 (Amplifiers > Wireless Audio SoC) and SKY76360/76361
  (Audio and Radio > Wireless Gaming).
