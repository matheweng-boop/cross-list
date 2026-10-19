# More TI application block diagrams: research notes

Structured data: `data/blocks/research/ti_more_block_diagrams.yaml`, 48 applications in the schema of `ti_block_diagrams.yaml`, plus a `category:` per application and a `new_functions:` map. None of the 48 is already in `data/blocks/templates.yaml`.

Everything comes from public `ti.com/solution/<app>` pages, read in October 2026. There was no login and nothing was posted. TI is a competitor, so the TI part numbers only show what TI draws in each block. They are not Cross List recommendations.

## Method

- **Fetching.** I used the slugs listed in `ti.com/solution/sitemap-standard.xml`. I fetched one page at a time, 1.5 s apart, and saved them with the earlier pages under `scratchpad/ti_docs/sol/`. Of the 49 pages read, 13 were already there from the first TI pass and 36 were new.
- **What each page holds.** Each page embeds `const VARIANT_LIST` with the Visio SVG and the subsystem JSON for every variant. Each subsystem lists its name, TI product families, parts and reference designs.
- **Groups and blocks.** I parsed the subsystem boxes and their teal blocks straight from the SVG structure: the `Subsystem` shape and its sibling `Rectangular Component` shapes. I then checked each diagram by eye after rendering the SVG with the headless Chromium already installed for the project's Playwright. Blocks drawn outside any subsystem, such as RF chains, the PC SoC and white "external" boxes, became their own group, and the group's `source` says so.
- **Links** are the arrows I read from the rendered images.
- **TI parts.** For each product family TI attaches to a subsystem, I took the first part.
- **Features.** Each application has 2 to 5 questions. Most come from the page's variant list or its drawn options ("OR" boxes, power options). Ones the page implies but does not draw are marked "(not drawn)".

## Applications by category

| category | applications |
|---|---|
| Automotive systems (8) | body control module, zone control module, LED headlamp (HB/LB), electric pump / fan, USB-C charging hub, ultrasonic park assist, EPS, in-cabin 60 GHz radar |
| Power & isolation (5) | AC wallbox (L2), DC fast charger, USB-C PD adapter (PFC, GaN), online UPS, solar micro inverter |
| Motor drives (4) | servo drive, HVAC motor control (AC input), cordless power tool, humanoid robot joint |
| Industrial (5) | PLC CPU, pressure transmitter, single-phase smart e-meter, ultrasonic gas meter, occupancy / people-counting sensor |
| RF & connectivity (3) | land mobile radio, satellite comms payload, smart asset tracker |
| Consumer & personal electronics (7) | power bank, smartwatch, TWS earbuds + case, tablet, notebook PC, robot vacuum, smart speaker |
| Medical (4) | ultrasound scanner, multiparameter patient monitor, pulse oximeter, CGM sensor |
| Appliances & building (7) | washer / dryer, refrigerator, cooktop, smart thermostat, smoke / heat / CO detector, video doorbell, IP camera |
| Enterprise & data center (3) | server motherboard, 48 V power distribution board, data center switch |
| Communications equipment (2) | optical transceiver module (SFP / QSFP), PON ONT with 4x4 Wi-Fi |

## Proposed new function ids

The 18 ids below are all in `new_functions`, and every one is used by at least one block:

`acdc_controller`, `efuse_hotswap`, `relay_driver`, `motor_driver_brushed`, `usb_pd_controller`, `battery_protector`, `wireless_power`, `dac`, `touch_controller`, `display_driver`, `haptics_driver`, `env_sensor`, `hall_switch`, `ultrasonic_afe`, `ecg_afe`, `ppg_afe`, `ultrasound_afe`, `hv_pulser`.

- **Most used.** `efuse_hotswap`, `acdc_controller`, `touch_controller`, `env_sensor` and `hall_switch` appear in 20 to 34 groups each. These are the gaps that matter most outside automotive.
- **Used once or twice.** `ultrasound_afe`, `hv_pulser`, `ecg_afe`, `ppg_afe`, `ultrasonic_afe` and `wireless_power` are each used in one to three groups and could be dropped or merged if the list must stay short.
- **Dropped ideas.** I did not propose `dram` or `nor_flash`, because the existing `ddr_flash` and `flash` already cover memory. I also did not propose an LIN-specific id: LIN transceivers use `can_transceiver`, as in `ti_block_diagrams.yaml`.

## RF sockets worth noting (Skyworks / Qorvo relevance)

| application | RF content drawn |
|---|---|
| tablet | Complete cellular RF front end: PA, LNA, switches, filters, antenna tuner and match. TI lists no parts for it, so it is an open socket. |
| land mobile radio | T/R switch, LNA, mixer and PA, drawn outside TI's subsystems. |
| satellite comms payload | LNA, PA, T/R switch, beamformers and power detector, plus filters and mixers. |
| ONT | Two 4x4 dual-band Wi-Fi front-end modules. |
| other wireless apps | Antennas and radios in the doorbell, smart speaker, asset tracker, smartwatch, e-meter and gas meter (the gas meter draws a PA/LNA). |

## Gaps and uncertain points

- **Diagrams with little structure.**
  - Ultrasonic park assist is a single SoC box (PGA450-Q1).
  - The CGM sensor has only 3 subsystems.
  - Both are kept but are thin.
- **Links that were not traced block by block.**
  - Refrigerator: the diagram uses the same appliance layout as the washer and cooktop, which I traced by eye. I did not trace the fridge image itself, so its links follow the shared pattern.
  - IP camera: I did not view the image. Its groups come from the SVG structure, and its links follow the doorbell's hub-around-MPU pattern. The source string says so.
- **Dense pages that were condensed.**
  - The notebook PC has 46 subsystems, many with only a Visio id as name. I grouped them into 15 groups by the dotted super-boxes drawn: USB A and C, battery management, system power management, audio and sensors.
  - The DC fast charger's 36 subsystems were merged into 18 groups, for example the three sense boxes and the power-board power boxes.
- **Pages read but not turned into separate applications.**
  - The water meter is the same structure as the gas meter and appears only as a second source there.
  - The patient-monitor ECG module (variant 26674) was read; the overview "subsystems module" variant is used.
- **TI part lists are partial.**
  - Some subsystems list no TI parts. Examples: the tablet RF front end, smart speaker memory and the LMR low-noise supply.
  - Some subsystems list only logic gates. Examples: UPS control card, payload logic and appliance system controllers. For these I kept the logic parts or left `ti_parts` empty.
- **Not found in the TI sitemap.** There is no TI solution page for hearing aid, drone, induction-only cooktop or network-switch line card. The cooktop page covers induction, and the data center switch covers switches.
- **Doc titles.** The `title` in `docs:` is a descriptive name (the application name), not TI's exact page title.

## Sources read (all `https://www.ti.com/solution/...`)

The 49 pages read are listed below. The pages contributing one variant name that variant in the yaml.

| area | pages |
|---|---|
| Automotive and EV | body-control-module-bcm, zone-control-module, automotive-headlight, automotive-pump, automotive-usb-charging, ultrasonic-park-assist-sensor, electric-power-steering-eps, in-cabin-radar-module, ac-charging-pile-station, dc-fast-charging-station |
| Power | usb-acdc-adapter, power-bank, uninterruptible-power-supply, micro-inverter |
| Motor drives and industrial | robot-servo-drive, hvac-motor-control, cordless-power-tool, humanoid-robot-joint-motor-control, cpu-plc-controller, pressure-transmitter, electricity-meter, gas-meter, water-meter, occupancy-detection-people-tracking-people-counting |
| RF and consumer | land-mobile-radio, communications-payload, smart-asset-tracker, smartwatch, headsets-headphones-earbuds, tablet-multimedia, standard-notebook-pc, vacuum-robot, smart-speaker |
| Medical | ultrasound-scanner, multiparameter-patient-monitor, pulse-oximeter, continuous-glucose-monitor-sensor |
| Appliances and building | washer-dryer, refrigerators-and-freezers, cooking-top, thermostat, smoke-heat-detector, video-doorbell, ip-network-camera |
| Data center and comms | intel-server, power-distribution-board-with-48-v-input, fixed-data-center-switch, optical-module-small-form-factor-pluggable, optical-network-terminal-unit-ont |

Raw files are in `/tmp/claude-0/-home-user-cross-list/20ed48d6-a5ec-5e79-a521-701f7b4cc7d6/scratchpad/more/`: `svg/`, `png/`, `txt/*.sum` (the subsystem and part dumps) and `blocks.txt`.
