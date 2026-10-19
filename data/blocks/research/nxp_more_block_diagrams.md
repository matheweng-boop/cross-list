# NXP application block diagrams, second batch

`nxp_more_block_diagrams.yaml` has 29 NXP applications that are not in `templates.yaml`. It adds 300 groups, 290 links and 29 cited pages, and proposes 7 new function ids. It uses the same format as `ti_block_diagrams.yaml`, with three changes: it uses `vendor_parts` instead of `ti_parts`, each application has a `category`, and the new ids are listed under a top-level `new_functions`. Everything was read on 2026-10-19.

## Method

- **Sources.** All sources are public `www.nxp.com/applications/<APP>` pages, found through the cached NXP sitemap (`sitemap_en_webpages`) rather than `/search`. Fetching was read-only GET at about 1 request per 1.2 s. Nothing was logged into, posted or installed.
- **Reading the diagrams.** Each page has one or more block-diagram SVGs with a text layer. Each SVG was rendered locally with the project's Playwright Chromium (`set_content` with network off) and viewed. Groups and links come from what the figure draws. Grey ("Non NXP Technology") blocks are kept, with empty `vendor_parts`.
- **Products.** `vendor_parts` come from the page's "Functional Blocks" panel for that diagram, spelled exactly as NXP lists them. A script checked that every listed part string appears in the fetched page HTML. When a page has several diagrams, the panel list for the matching diagram was used.
- **Diagram PDFs.** The diagram PDFs (`/assets/block-diagram/en/<APP>_<SVG>.pdf`) hold the same figure plus a recommendation table. One was used to check the airbag diagram. The BMS PDF has no drawing.
- **Raw files.** Raw files and renders are in `/tmp/claude-0/-home-user-cross-list/20ed48d6-a5ec-5e79-a521-701f7b4cc7d6/scratchpad/nxp_more/` and `.../nxp_svgpng/`. They are not in the repo.

## Applications

| Category | Applications (page) |
|---|---|
| Automotive systems (10) | Zone controller (AUTOMOTIVE-ZONE-CONTROLLER, BD3); HV BMS with BMU, CMU and battery junction box (BATTERY-MANAGEMENT-SYSTEM); EPS; exterior LED lighting; TPMS; airbag (PSI5 / DSI3); instrument cluster (hybrid 2D); braking and stability (ABS / ESC); central gateway; automotive HVAC |
| Industrial (4) | Electricity meter; PLC control module; AC EV charging station; flow meter (water, gas, heat) |
| Motor drives (2) | PMSM sensorless FOC; BLDC with Hall sensors |
| Power & isolation (1) | USB Type-C PD wall charger |
| Appliances & building (5) | Physical access reader; home control panel / hub; smart lock; smart plug; refrigerator inverter compressor (JPG, no product list) |
| Consumer & personal electronics (4) | Smartwatch; mobile POS; open / closed-loop payment terminal; smart speaker (lists NXP BGS8324 Wi-Fi FEM x4) |
| Medical (2) | Disposable CGM patch; multiparameter patient monitor (mainstream, MPU-based) |
| Communications equipment (1) | 5G mmWave FWA CPE (SoC + programmable baseband + up to 4 analog beamformers) |

## New function ids (`new_functions`)

| id | Where it is used |
|---|---|
| `lin_transceiver` | Zone controller, gateway, HVAC, airbag, cluster, TPMS receiver |
| `switch_detection_interface` | MSDI (MC33978 / MC33972 / CD1020 / CD1030) in zone controller, EPS, HVAC, cluster, PLC |
| `motor_driver_brushed` | H-bridges (HB200x, MC33926, MC33932) for contactors, pumps, flaps, locks |
| `display_driver` | Segment / character LCD drivers (PCF8531U, PCF8553DTT, PCF2119X) |
| `acdc_controller` | Offline AC/DC flyback / SR controllers (TEA17xx / TEA2xxx) |
| `usb_pd_controller` | Type-C / PD PHY (PTN5110, PTN5150, PTN5100) |
| `smartcard_interface` | ISO 7816 contact reader interface (TDA8026ET, TDA8035HN) in POS and payment |

Some other blocks map to the closest existing id:

- Battery cell controller and pack monitor: `battery_monitor`.
- Battery gateway (TPL): `can_transceiver`.
- Low-side valve drivers: `load_switch`.
- Sensors and accelerometers: `vehicle_sensors` in cars, `external_block` elsewhere.
- Electrochemical AFE: `adc`.

Left without a function: PSI5 / DSI3 transceiver, squib driver, FlexRay interface, TPMS LF input and motor-control software.

## Gaps and uncertain points

- **Comms.** NXP has no public application page for RF power in macro cellular or for a 5G repeater. The MacroGaN fact sheet (MACROGANFS) has only a product table, and the Airfast wideband white paper has only package figures. The NXP mMIMO, O-RAN RU and small-cell entries already in `rf_platforms.yaml` cover cellular RF. The 5G FWA CPE was added instead.
- **Not found.** There is no standalone NXP page for a smart thermostat or for a Matter hub with a diagram. The home control panel stands in for both.
- **Industrial gateway and eCockpit.** NXP's "Gateway" page is the automotive central gateway. The eCockpit page diagram is the connected-radio layout, which is already in `rf_platforms.yaml`, so it was not repeated.
- **Categories.** The categories for POS and payment ("Consumer & personal electronics") and for the EV charger ("Industrial" rather than "Power & isolation") are judgment calls.
- **Link direction.** Most NXP figures use double-headed arrows, so links are written MCU-first and `""` means unlabelled. In the speaker figure, the Wi-Fi-to-FEM link is labelled "PCIe" and BLE is drawn on I2C. Both were kept as drawn.
- **Part lists.** Some product entries on the pages are family or category ids (TJA144x, KM3x, MCX-A13X-A14X-A15X, PN736X). These are kept as listed. Category-page codes (MC_xxxxx, *_SERIES, *-SOLUTIONS) were dropped. The access reader's load switch and some other blocks only have a category code, so their `vendor_parts` are empty.
- **Refrigerator page.** The refrigerator compressor diagram is a JPG with no Functional Blocks panel, so it has no `vendor_parts`.
- **Variants not turned into applications.** These diagrams were seen on the pages but not used:
  - BMS: low-voltage (12 V / 48 V), wireless, EIS and secure BMS.
  - EV charger: DC fast charger.
  - Patient monitor: the module diagrams (ECG, NIBP, SpO2, temperature).
  - Smart lock: UWB and e-lock.
  - Smartwatch: UWB watch.
  - Power adapters: shared power bank.
  - Also: remote I/O, logical access, and cluster entry / 3D.
- **Fetched but not used.** INSULIN-PEN, HEARABLES and SERVICE-ORIENTED-GATEWAY were fetched but not used. SMALL-MEDIUM-APPLIANCE has no diagram. DATA-BUSSES-BATTERY turned out to be a drone diagram.
- **Not fetched.** These sitemap pages were not fetched and could be a next batch: AUTOMOTIVE-DATA-LOGGER, ACTIVE-SUSPENSION, ELECTRIC-PUMPS, TRANSMISSION-GEARBOX, INDUSTRIAL-HMI, HEARING-AIDS, VENTILATORS-RESPIRATORS, CIRCUIT-BREAKER, PV-GENERATION, SMALL-BUSINESS-ROUTER and SERVERS.
