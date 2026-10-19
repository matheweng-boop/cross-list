# TI application block diagrams and app notes for Skyworks/Qorvo product areas: research notes

Structured data:
- `data/blocks/research/ti_block_diagrams.yaml`: 16 application block diagrams. Same schema as `ti_power.yaml`.
- `data/catalog/ti_appnotes.yaml`: 309 TI application notes, white papers, application briefs, Analog Design Journal articles and e-books, each tagged with an area and BizDev function ids.

Everything comes from public ti.com pages and PDFs, read in October 2026. TI is a competitor, so TI part numbers are recorded only to show what TI draws in each block. They are not BizDev recommendations. This work does not repeat `ti_power.yaml` (traction inverter, gate driver subsystem, isolated bias power) or `motor_and_switches.yaml` (LEV and 48 V drives, RF switch placements from other vendors).

---

## 1. Method

**robots.txt.** `https://www.ti.com/robots.txt` sets `Crawl-delay: 1` and disallows `/sitesearch/...`, `/productmodel/`, `/materialcontent/.../search`, `/bin/ti/` and similar paths. I used none of the disallowed paths. Requests were made one at a time with 1.5 s between them, and longer after any error (none occurred). There was no login and no bot-protection workaround.

**Finding the application pages.** `https://www.ti.com/solution/sitemap-standard.xml` lists 469 `ti.com/solution/<app>` pages. I fetched 68 that are relevant to Skyworks/Qorvo areas.

**What a solution page contains.** Each page embeds `const VARIANT_LIST = [...]` in its HTML source. This is the JSON the site itself uses to draw the interactive diagram. For each variant (for example "AAS RF sampling" vs "AAS IF sampling") it holds:
- the block diagram as an inline Visio SVG;
- the clickable subsystem list. Each subsystem has a name, a description, TI product families with part lists, reference designs, and per-subsystem `techDocs`.

The page also has a "Top documentation" table of app notes, white papers and technical articles.

**How the diagrams were read.** I rendered the SVGs to PNG locally (cairosvg in a throwaway `uv run --no-project` environment) and read them by eye. Groups in the yaml are the red dashed subsystem boxes, labelled with TI's own words. Links are the arrows and buses drawn in the figure.

- The head unit and radio SVGs draw their connectors on a transparent background, so the arrows did not survive rendering. Their links are limited to what the subsystem descriptions state, and should be treated as approximate.
- The V2X diagram is the TCU diagram with a C-V2X LTE module and a DSRC 802.11p module added. I merged the two into `telematics_v2x`.

**App-note sources:**
- the "Top documentation" tables and per-subsystem `techDocs` of the 68 solution pages;
- the technical-documentation tables of 83 public `ti.com/product/<part>` pages.

I chose about 4 to 11 representative TI parts per area. Examples: ISO7741, UCC21750, AMC1311, UCC14240-Q1, LMK05318B, CDCE6214, LMK6C, TPS65219, TPS61094, TPS25985, DRV8316, MCF8316A, CC1190, CC2592, AFE7950, AFE7769D, TAS6584-Q1 and PCM6260-Q1. Together these gave a pool of 1,314 documents. I filtered the pool to app notes, white papers, app briefs, ADJ articles and e-books, then hand-picked 309 and wrote a 1–2 sentence summary for each.

**PDFs.** I downloaded only 24 PDFs (about 20 MB in total, kept in the scratchpad and not in the repo). I used them to check for system block diagrams and to cite figure and page numbers. In `ti_appnotes.yaml`, `block_diagram.present` takes three values:
- `true`: a system or application block diagram was found, and `where` gives the figure and page;
- `false`: the PDF was opened and has no such diagram;
- `null`: the PDF was not opened. This applies to most entries, and is deliberate.

**Raw downloads.** Saved in `/tmp/claude-0/-home-user-cross-list/20ed48d6-a5ec-5e79-a521-701f7b4cc7d6/scratchpad/ti_docs/`:
- `sol/` (solution HTML), `prod/` (product HTML), `svg/` and `png/` (diagrams), `pdf/`;
- `solutions.json`, the parsed subsystem data;
- `pool_all.json`, the full document pool.

## 2. App notes by area (`data/catalog/ti_appnotes.yaml`)

| area | notes | notes with a verified system diagram |
|---|---|---|
| pmic_dcdc | 41 | 0 (power notes are mostly circuit level) |
| rf_front_ends | 31 | SBAA686, SLAA862A, SLAA860, SWRA808A |
| clocks_timing | 28 | SNAA386, SNAA314 |
| isolated_amplifiers_current_sensing | 26 | SBOA366C, SBOA624 |
| motor_drivers | 25 | – |
| audio | 25 | – (SBAA424A has a device diagram only) |
| industrial | 25 | SLLA370D, SDAA162, SBAA631, SLLA498A, SLLA497, SLVAEI6B |
| digital_isolators | 23 | – |
| isolated_gate_drivers | 22 | – |
| automotive | 22 | SLYY197A |
| isolated_dcdc_bias_power | 19 | SLUAAS6, STDA010, SLUAB19 |
| infrastructure | 19 | – |
| broadcast_radio | 3 | – |
| rf_switches_antenna_tuning | 0 | see gaps |
| lna | 0 | see gaps |

Most useful for Skyworks/Qorvo specifically:
- **SBAA686**, *Enabling Triple-Band Base Station Radio Design Using AFE7769D Featuring Skyworks Power Amplifiers* (Sep 2025). Fig 1-1 on p.2 is a triple-band radio block diagram: AFE7769D, Skyworks PAs SKY66391-12, SKY66394-11 and SKY66522-11, LNAs, duplexer/circulator, and balun/match.
- **SDAA098** and **SBAA710**: DPD test reports for AFE77xxD with SKY66522-11 and with SKY66391-12.
- These are the only documents I found in which TI names Skyworks parts. They give a direct, documented pairing of TI transceivers with Skyworks PAs.

## 3. Block diagrams captured (`ti_block_diagrams.yaml`)

| id | TI source (solution page variant) | supporting PDFs |
|---|---|---|
| onboard_charger | onboard-charger (35 subsystems) | SLUAAS6, STDA010 |
| hv_lv_dcdc | dc-dc-converter (HEV/EV HV to 12 V) | SLUAB19 |
| ev_hv_battery_system | high-voltage-battery-system (wired) | SLYY197A |
| ess_bms | ess-battery-management-system-bms (multimodule, daisy chain) | – |
| aas_5g_mmimo | active-antenna-system-mmimo-aas (RF sampling) | SBAA686 |
| small_cell | small-cell-base-station | SLAA862A |
| wifi_access_point | wlan-wifi-access-point | – |
| telematics_v2x | automotive-telematics-control-unit + vehicle-to-everything-v2x | – |
| head_unit_radio | automotive-head-unit + automotive-radio-tuners | – |
| adas_domain_controller | adas-domain-controller | SNAA386 (PCIe clocking) |
| plc_digital_input | digital-input-module (IEC 61131-2) | SLLA370D |
| plc_analog_input | analog-input-module (V and I inputs) | SDAA162 |
| solar_string_inverter | string-inverter (three-phase) | SLLA498A, SBOA624 |
| server_psu_54v | ac-dc-power-supply-unit-psu-48v-54v-output | – |
| industrial_ac_drive | ac-drive-power-stage-module (isolated) | – |
| phone_as_a_key | phone-as-a-key-paak | SWRA791 (listed, PDF not opened) |

### Where Skyworks/Qorvo functions sit in these diagrams
- **Digital isolators:**
  - OBC: PFC↔DC/DC communication and the PFC communication link;
  - HV-LV DC/DC: diagnostics;
  - BMS: SPI across the barrier to the BDU;
  - PLC DI and AI modules: signal isolation;
  - string inverter: optional data isolation;
  - server PSU: control-unit isolator;
  - AC drive: STO, fan and wired interface;
  - PoE PD in the small cell and Wi-Fi AP: "needed for dual port".
- **Isolated gate drivers:**
  - OBC: PFC, DC/DC primary and DC/DC secondary;
  - HV-LV DC/DC: primary bridge;
  - string inverter: DC/DC and DC/AC stages;
  - server PSU: PFC and LLC;
  - AC drive: 3-phase bridge plus the brake chopper.
- **Isolated amplifiers and current sensing:** OBC primary, secondary and PFC sense; BDU HV sensing; ESS HV monitor and insulation-resistance detection; string-inverter input, bus and output sense; AC drive DC-link and motor sense; server PSU sense.
- **Isolated DC/DC and bias power:** OBC primary, secondary and PFC bias; HV-LV DC/DC gate-driver bias plus sensing bias; BMS isolation power; PLC AI isolated supply; string inverter low-side and high-side isolated DC/DC; AC drive "hot side"; -48 V isolated brick in the AAS.
- **Clocks and timing:**
  - AAS and small cell: TCXO/OCXO, network synchronizer/jitter cleaner and clock buffer;
  - Wi-Fi AP: crystal, clock generator and buffer;
  - TCU: RTC, oscillator, spread-spectrum clock, synthesizer and watchdog;
  - head unit: clock generator and buffers;
  - ADAS: oscillator, clock generator and buffer;
  - AC drive: clock distribution.
- **RF front end, LNA, RF switch and antenna:**
  - AAS: "RF front end & power amplifier" (DVGA, filter, PA module, duplexer, LNA, switch, eFuse, analog monitor);
  - small cell: the same blocks plus a Wi-Fi FE (4x4 dual-band radio, Wi-Fi FEM, analog switches);
  - Wi-Fi AP: 4x4 radio front end with FEMs and diplexer;
  - TCU/V2X: LNA for GNSS, RF power detector, antenna LDO and antenna ESD, C-V2X and DSRC modules;
  - PaaK: BLE SoC with antenna and satellites.
- **Audio:** TCU hands-free (codec, class-D, ANC amp); head unit audio channel; radio tuner audio amplifier.
- **Broadcast radio:** the head unit and radio-tuner pages draw the tuner as a non-TI white box: "AM/FM/HD/DAB/DMB tuners", radio DSP and audio ADC/DAC. Around it TI places only an antenna LDO, a high-PSRR LDO and short-to-battery/ESD protection.
- **PMIC and DC-DC:** every diagram. Examples are the ADAS processor PMIC with multiphase core supply, the AAS POL with sequencer, and the TCU system power, which includes buck-boost and a 3.8–4.2 V modem rail.

### Features (design questions)
Each application has 4 to 10 features. They cover choices such as topology, voltage class, switch technology, bias architecture, sensing method, duplex mode, MIMO order, broadcast standards, tuner count, Wi-Fi generation and FEM type, ranging technology and ASIL. The choices are options, not answers. `filters` names existing BizDev parameters where one fits; otherwise the attribute is marked "(new)".

## 4. Function ids
All `fn_hint` and `skyworks_qorvo_functions` values use existing ids, and I checked them against the list I was given. Proposed new ids, in case finer tagging becomes useful:
- `rf_pa`: PA module or PA. The AAS, small cell and TCU diagrams draw PA modules, and `rf_frontend` is currently used for them.
- `rf_transceiver`: TI AFE77xx/AFE79xx/AFE80xx RF-sampling transceivers. These are not Skyworks/Qorvo, but the PA/LNA attach to them.
- `wifi_fem`: Wi-Fi front-end module, as distinct from the generic `rf_frontend`.
- `efuse_hotswap`: eFuse and hot-swap. Currently `power_loss_protection` is used for these.
- `high_side_switch`: smart high-side switches and contactor drivers. Currently `load_switch` is used.
- `isolated_digital_input`: ISO121x-style IEC 61131-2 inputs.
- `battery_monitor`: cell monitor/AFE. Currently `adc` is used.
- `solid_state_relay`: TPSI2240/TPSI3100. Currently `isolated_switch_driver` is used.
- `pyro_driver`: the safety breaker in the BDU.

## 5. Gaps and what was blocked
- **Nothing was blocked.** All requests returned HTTP 200. No login wall or bot challenge was met, and no disallowed paths were used.
- **No TI search or listing JSON endpoint was used.** The site search (`/sitesearch/...`) and `/productmodel/` are disallowed in robots.txt. The JSON I used is the VARIANT_LIST embedded in each public solution page, which the page itself uses to draw the diagram.
- **RF switches, antenna tuning and LNAs.** TI makes no discrete RF switches, antenna tuners or cellular/Wi-Fi LNAs, so it publishes no app notes on them. I filed the closest material under `rf_front_ends`, using `lna`, `rf_switch`, `antenna_switch` and `antenna` function tags:
  - CC1190 and CC2592 PA/LNA range-extender notes;
  - WL18xx 5-GHz antenna diversity;
  - AFE77xx small-cell/repeater configurations with TDD switching;
  - antenna selection and matching guides.

  The `rf_switches_antenna_tuning` and `lna` areas therefore have 0 entries. Better sources for these areas are Skyworks' own notes (`data/appnotes.jsonl`) and the Qorvo research.
- **Broadcast radio.** TI makes no AM/FM/DAB/HD tuners or demodulators, so only 3 loosely relevant notes exist: an infotainment buck selection guide, an infotainment white paper and a supervisor note. The radio-tuner solution page's documents are mostly power and EMI notes. Its diagram is still useful because it shows where the tuner sits and what surrounds it.
- **UWB.** TI has no UWB transceiver. The PaaK page covers BLE (including channel sounding, SWRA791), not UWB.
- **Block-diagram flags.** Most `block_diagram` flags are `null` (not checked) because I deliberately avoided downloading hundreds of PDFs. A later pass could open the `null` entries in areas that matter most; the `found_on` field says where each document is listed.
- **Head unit and radio links.** These diagrams' connectors did not render (transparent background), so their links are approximate.
- **Other variants not captured.** Some solution pages have variants I did not capture: wireless BMS, single-phase string inverter, IF-sampling AAS, 12 V-output PSU, non-isolated AC drive, and the NAMUR and high-speed digital input modules. Their SVGs and subsystem lists are in `solutions.json` if they are needed.
- **ti_parts.** These are truncated to the first few parts of each family. The full lists are in `solutions.json`.

## 6. Sources (solution pages)
- https://www.ti.com/solution/onboard-charger
- https://www.ti.com/solution/dc-dc-converter
- https://www.ti.com/solution/high-voltage-battery-system
- https://www.ti.com/solution/ess-battery-management-system-bms
- https://www.ti.com/solution/active-antenna-system-mmimo-aas
- https://www.ti.com/solution/small-cell-base-station
- https://www.ti.com/solution/wlan-wifi-access-point
- https://www.ti.com/solution/automotive-telematics-control-unit
- https://www.ti.com/solution/vehicle-to-everything-v2x
- https://www.ti.com/solution/automotive-head-unit
- https://www.ti.com/solution/automotive-radio-tuners
- https://www.ti.com/solution/adas-domain-controller
- https://www.ti.com/solution/digital-input-module
- https://www.ti.com/solution/analog-input-module
- https://www.ti.com/solution/string-inverter
- https://www.ti.com/solution/ac-dc-power-supply-unit-psu-48v-54v-output
- https://www.ti.com/solution/ac-drive-power-stage-module
- https://www.ti.com/solution/phone-as-a-key-paak

PDFs cited (all `https://www.ti.com/lit/pdf/<doc>`): SLUAAS6, STDA010, SLUAB19, SLYY197A, SBAA686, SLAA862A, SLAA860, SLLA370D, SDAA162, SBAA631, SLLA498A, SBOA624, SLLA497, SLVAEI6B, SNAA386, SNAA314, SBOA366C, SWRA808A.
