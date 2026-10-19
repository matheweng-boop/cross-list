# RF platform research: MediaTek, Qualcomm, NXP

Read 2026-10-19. Machine-readable extracts:

- `data/blocks/research/rf_platforms.yaml`: 22 applications (NXP 10, MediaTek 6, Qualcomm 6), 59 cited docs. Each group says whether it is a socket a Skyworks / Qorvo-type part fills (`socket: true` + `socket_fn`) and how it is known (`drawn` / `text` / `inferred`).
- `data/catalog/rf_platform_docs.yaml`: 88 documents (vendor, title, URL, date, area, functions, gated, summary). 10 are gated.

These are platform vendors. Their diagrams show the chipset (SoC, modem, Wi-Fi, UWB, V2X, radio). The front end around the chipset (PA/FEM, LNA, switch, tuner, filter, crystal, PMIC) is the socket.

## Method and access

| Host | robots.txt | Result |
|---|---|---|
| www.nxp.com | allows all except `/search`, `/files/benefits`, ... | Server-rendered HTML. Application pages embed an SVG block diagram with a text layer, plus a "Functional Blocks" product list per block. Product pages carry JSON-LD document lists. Used the sitemaps (`sitemap_en_webpages`, `sitemap_en_collateral`) instead of `/search`. |
| www.mediatek.com | allow all (HubSpot preview paths disallowed) | Server-rendered spec tables and blogs. No RF diagrams. |
| genio.mediatek.com | allows all except `/login`, `/register`, `/search`, ... | Block-diagram PNG is public. The hardware-design downloads go through info pages that link to account login and carry an NDA marker, so they were treated as gated. |
| www.qualcomm.com | no rule for generic agents | Product pages are a React shell with a Cloudflare JS script. Only `<title>` and the meta description are readable. Not bypassed: no GraphQL or API calls. `llms.txt` lists `.md` versions, but only a few exist (FWA Gen 6, QCS6490 were read; the rest return 404). |
| docs.qualcomm.com | allow all, sitemap | Public PDF product briefs and some hardware guides download fine. HTML topic pages are a JS shell (the same 52 kB page for every topic), so they could not be read. |

Fetching ran at about 1 request per 1.2 s with backoff. TLS used the proxy CA bundle. Raw files are in `/tmp/claude-0/-home-user-cross-list/20ed48d6-a5ec-5e79-a521-701f7b4cc7d6/scratchpad/rf_platforms/` (not in the repo). No host blocked automated access outright. The only limits were Qualcomm's JS rendering and login gates.

## NXP: best source, 10 applications

NXP publishes real application block diagrams as SVG with text, PDF, and per-block product lists.

| Application id | Source diagram(s) | Sockets for Skyworks / Qorvo |
|---|---|---|
| nxp_connected_radio | CONNECTED-RADIO, eCockpit, SAF9000, SAF9800, TLH501x | Active-antenna LNA (TLH501x is no longer manufactured, so the socket is open), radio tuner / digital radio (competes with Skyworks broadcast), Xtal, PMIC, Wi-Fi FEM + diplexer (88Q9098 external-FEM diagram) |
| nxp_v2x | V2X page, SAF5400 diagram + fact sheet | 5.9 GHz FEM / remote-antenna compensator (text; inferred), 40 MHz reference, PMIC; cellular / GNSS front end not drawn |
| nxp_car_access_uwb | Smart Car Access (4 diagrams), NCJ29D5, NCx3321 | UWB antenna switching for AoA (the RF switch is on chip for a single antenna), BLE FEM (inferred), SBC/PMIC |
| nxp_wlan_ap | WLAN AP, 88Q9098 external FEM, IW693 fact sheet | Wi-Fi FEM per chain (2.4 / 5 / 6 GHz; 2x2 or 4x4), diplexer, IoT-radio FEM, PMIC |
| nxp_wifi_bt_combo | IW612 data sheet figures, 88Q9098, IW693, AN14463 | External FEM, diplexer, SPDT for Wi-Fi/BT antenna sharing or SPDT/DPDT diversity (AN14463 says external switches are required), crystal, 3.3 / 1.8 V rails |
| nxp_5g_mmimo | 5G mMIMO diagram | Pre-driver, PA module, circulator, RX FEM (switch + LNA with bypass), filter |
| nxp_5g_radio_unit | 5G Radio Unit, Digital Airfast | 122.88 MHz & PPS timing (jitter attenuator / clock generator), -48 V DC/DC, PA x4, LNA/RX FEM x4 |
| nxp_femtocell | Femtocell BD1 (sub-6 4T4R) / BD2 (mmWave) | PA/LNA per chain, analog beamformer, GPS / network-listening LNA, PoE / power |
| nxp_radar | Radar Systems x3, TEF82xx, SAF85xx | The 77 GHz front end is integrated. Sockets are only the crystal and PMIC. |
| nxp_smartphone | Smartphone diagram | 2.4 GHz Wi-Fi FEM (NXP lists its own legacy WLAN7207H), NFC crystal, load switches / chargers |

Gated or not public at NXP:
- SAF9000, SAF4000 and SAF5400 data sheets are not listed.
- The NCJ29D5 / NCJ29D6 "Customer Support Package" (UM12397, UM12283) is access-controlled.
- UM12200 is licence-gated and marked Confidential.
- UM11857 is restricted.
- Some `webapp/Download` items (whitepapers, training) were not attempted.

## MediaTek: no public RF diagrams, 6 applications built from specs

MediaTek publishes no board-level RF or reference-design diagrams on mediatek.com. Data sheets and reference designs go to customers under NDA (customer portal), so they are recorded as gated. The applications use spec tables and marked `drawn: text` / `inferred`:

- **mtk_smartphone_5g (Dimensity 9400).** States "a new RFFE":
  - DL 4CC 300 MHz, LB 4x4 MIMO; UL 2CC, FDD UL 2x2 MIMO / PC2.
  - AI UAC 3.0 (+3 dB antenna).
  - GNSS L1 + L5.
  - Wi-Fi 7 tri-band 2x2+2x2+1x1, BT 6.0.
  - Sockets (inferred): PA modules, diversity RX, antenna switch / tuner, filters, GNSS LNA, Wi-Fi FEM.
- **mtk_wifi7_ap (Filogic 880 / 860).** Chain counts are stated: 4x4 + 4x4 + 4x5 (4T5R), or 4x4 + 5x5. That gives 12–15 Wi-Fi FEM sockets. AFC / 6 GHz standard power is also stated.
- **mtk_wifi7_client (Filogic 380 / 360).** The Filogic 360 spec says "Single chip with RF, Baseband, MAC, iFEM". This is a useful feature: integrated FEM vs external FEM. The Filogic 380 has an extra BT antenna for MRC.
- **mtk_genio_iot (Genio 700).** The only real MediaTek diagram. It shows the MT8390 with companions:
  - MT6365 PMIC (DC-DC/LDO, DCXO, codec, RTC).
  - MT6319 / MT5721 DC-DC and MT6680 LDO.
  - RT9471 charger.
  - MT7663 / MT7921 Wi-Fi/BT (optional chip-on-board).
- **mtk_fwa_cpe (T930).** 3Tx, 8Rx, 6CC CA, integrated RF transceiver, GNSS receiver and power management.
- **mtk_auto_telematics (MT2739 + cockpit).** 5G-Advanced, NB-NTN / NR-NTN, AEC-Q100 Grade 2. No RF detail.

Gated at MediaTek: the Genio hardware design files (EVK schematics, PMIC and connectivity data sheets, preferred part list) are behind login / NDA. All Dimensity, Filogic and Auto design documents are not public.

## Qualcomm: product briefs only, 6 applications

The www.qualcomm.com pages are JS-only. The public PDF product briefs on docs.qualcomm.com give the RF architecture in words:

- **qc_smartphone_modem_rf (X80 / X85).**
  - Converged mmWave-Sub6 transceiver and QTM565 mmWave module.
  - "RFFE" features: RF Uplink Optimization, Downlink Boost, Power RF Efficiency Suite (ET), Smart Transmit.
  - Switched / supplemental UL, satellite, GNSS.
  - The sub-6 RFFE is a **competitive socket**: Qualcomm sells its own RFFE "modem-to-antenna".
- **qc_fastconnect_wifi7 (FastConnect 7900).** Wi-Fi 7 + BT 6.0 + UWB on one chip, with "new RF FEMs" and QXM1099/98 HBS modules. This is again a Qualcomm-supplied FEM socket.
- **qc_networking_ap (NPro A8 Elite).** "Radios and RF Front End" in one platform; up to 20 antennas; 2.4 / 4.9 / 5 / 6 GHz.
- **qc_fwa_cpe (FWA Gen 5 / 6, QTM567).**
  - 8Rx/6Rx/4Rx.
  - "RFFE modules and filters" for NTN.
  - Tri-band Wi-Fi 8 5x5.
  - The QTM567 integrates transceiver, PMIC, RFFE and a phased array, so it is not an open socket.
- **qc_iot_ble (QCC711 HW design guide + QCS6490).** The best Qualcomm source. It has a public reference schematic with:
  - PCB antenna.
  - Pi network or band-pass filter.
  - 32 MHz and 32.768 kHz crystals (spec + recommended parts).
  - QCS6490 pairs with WCN6750 / WCN6856.
- **qc_auto_connectivity.** Only titles and meta descriptions were readable (Auto 5G Modem-RF Gen 2, QCA6696, C-V2X 9150). All sockets are inferred.

Gated or unreadable at Qualcomm:
- Device specifications, hardware design guidelines and reference schematics are not in the public sitemap (authorised access).
- docs.qualcomm.com HTML topics (telematics `hardware_antenna`, RB3 Gen 2 RF antennas) are listed publicly but render only with JS. Not attempted.

## Gaps

1. **MediaTek and Qualcomm sockets are mostly inferred.** Neither vendor publicly draws its handset or AP front end. Counts (chains, Rx, Tx) are stated; the parts in those sockets are not. Treat `drawn: inferred` groups as suggestions, not as vendor statements.
2. **Qualcomm is a competitor in the RF front end.** It offers RFFE: QXM Wi-Fi FEMs, QXF filters, HBS diplexers, QTM modules. Its own platform material names these modules, so the socket is "competitive" rather than open.
3. **Automotive V2X front end.** NXP's SAF5400 draws a LNA/PA inside the chip and mentions a remote-antenna compensator, but no external FEM part. Qualcomm C-V2X 9150 was unreadable. The Skyworks car-to-car diagram (motor_and_switches.yaml, SKY_BD_V2X) remains the better reference for the 5.9 GHz FEM.
4. **NXP AN coverage.** Hardware design guides exist publicly for NFC (AN12988, AN13219) and Wi-Fi diversity (AN14463). The UWB and V2X hardware guides are in gated support packages.
5. **Not done (time / scope):**
   - AN13219 (NFC antenna matching) was downloaded but not mined.
   - Qualcomm X105, FC8800, MBB and NPro N-series briefs were listed only.
   - NXP 5G FWA (mmWave CPE with analog beamformer) and Automotive Access Point pages were fetched but not turned into applications.
6. **Dates.** Many NXP and MediaTek pages show no date; the `date` field is left empty in the catalogue.

## Proposed new function ids

| id | label | category | note |
|---|---|---|---|
| power_amplifier | RF power amplifier (discrete / infrastructure PA) | rf | Airfast-class PA modules, small-cell PA |
| pa_module | PA module / PAMiD (PA + switch + filter, handset) | rf | cellular TX front end (MediaTek / Qualcomm phones, FWA, telematics) |
| rf_predriver | RF pre-driver amplifier | rf | massive-MIMO line-up before the PA |
| diversity_rx_module | Diversity / RX front-end module (LNA + switch + filter) | rf | handset DRx, base-station RX FEM (BTS7202U-type) |
| wifi_fem | Wi-Fi front-end module (PA + LNA + switch) | rf | per chain, 2.4 / 5 / 6 GHz |
| bt_fem | Bluetooth / 802.15.4 front end (2.4 GHz PA/LNA) | rf | BLE / Thread range extension |
| uwb_fem | UWB front end (switch / LNA / filter for AoA) | rf | multi-antenna UWB |
| v2x_fem | V2X 5.9 GHz front end / antenna compensator | rf | DSRC / C-V2X |
| gnss_lna | GNSS LNA / front-end (L1 / L5) | rf | dual-frequency GNSS |
| active_antenna_amp | Active antenna amplifier (AM/FM ALNA) | radio | TLH501x-type; could also map to `lna` |
| antenna_tuner | Antenna aperture / impedance tuner | rf | handset antenna tuning |
| filter_saw_baw | RF filter (SAW / BAW / LTCC, band-pass) | rf | band filters, multiplexers |
| diplexer | Diplexer / multiplexer (band combiner) | rf | 2.4 / 5 GHz onto one antenna, HBS diplexer |
| circulator_isolator | Circulator / isolator | rf | base-station TX/RX |
| beamformer_ic | Analog beamformer IC (mmWave) | rf | small cell / CPE mmWave |
| mmwave_antenna_module | mmWave antenna module (transceiver + RFFE + array) | rf | QTM-type; usually not an open socket |
| rf_transceiver | RF transceiver (RFIC) | rf | handset / base-station transceiver; customer / platform part |
| modem | Cellular modem (4G / 5G / NTN) | processing | platform part (external) |
| wifi_soc | Wi-Fi / Bluetooth combo SoC | networking | platform part (external) |
| ble_soc | Bluetooth LE / 802.15.4 SoC | networking | platform part (external) |
| uwb_soc | UWB transceiver IC | networking | platform part (external) |
| v2x_transceiver | V2X modem / transceiver (802.11p, C-V2X) | networking | platform part (external) |
| nfc_frontend | NFC controller / front end | interface | platform part (external) |
| radar_transceiver | Radar transceiver / radar SoC (77 GHz) | sensors | platform part (external) |
| secure_element | Secure element (not RF) | processing | external, listed only because diagrams show it |
| battery_charger | Battery charger (not RF) | power | Genio diagram (RT9471) |

Mapping to existing ids where one fits:
- `rf_frontend` is the generic parent of `wifi_fem`, `bt_fem`, `uwb_fem`, `v2x_fem` and `pa_module`.
- `lna` covers single LNAs.
- `antenna_switch` / `rf_switch` cover the SPDT / DPDT sockets (filters `configuration`, `control_interface`, `qualification`).
- `crystal_oscillator`, `jitter_attenuator`, `clock_generator` cover the timing sockets.
- `am_fm_tuner` and `digital_radio_demod` cover the radio chipset socket.
