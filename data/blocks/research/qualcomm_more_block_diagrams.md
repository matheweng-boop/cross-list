# More Qualcomm application block diagrams

`qualcomm_more_block_diagrams.yaml` has 20 new applications, with 186 groups and 36 cited documents. It uses the same format as `ti_block_diagrams.yaml`, plus `category` on each application and `vendor_parts` on each group in place of `ti_parts`. Nothing repeats the six Qualcomm entries in `rf_platforms.yaml` / `templates.yaml`.

Everything was read on 2026-10-19 from public pages, with no login. Nothing was posted or uploaded. Raw files are in the session scratchpad and are not in the repo.

## Applications

| id | category | basis |
| --- | --- | --- |
| qc_xr_headset | Consumer | XR2 Gen 2 reference design (QXR2230P) parts list + XR2 Gen 2 and Reality Elite spec tables |
| qc_ar_smart_viewer | Consumer | AR2 Gen 1 smart viewer kit (QAR2130P) parts list |
| qc_ai_smart_glasses | Consumer | AR1 Gen 1 spec table |
| qc_smartwatch_4g | Consumer | **W5+ Gen 1 block diagram (drawn)**: WTR3925 + QPA5590 + QFM5518 RFFE, PMW5100 PMIC (fuel gauge, haptics, fast charge, speaker PA) |
| qc_smartwatch_redcap_ntn | Consumer | Wear Elite spec table (5G RedCap, NB-NTN, UWB, L1/L5, Wi-Fi 6, BT 6.0) |
| qc_tws_earbuds | Consumer | **QCC3020 earbud block diagram (drawn)** + QCC5141 / QCC5171 reference designs + S5 Gen 1 block diagram |
| qc_soundbar | Consumer | **MAPX soundbar block diagram (drawn)** |
| qc_windows_laptop | Consumer | X Elite / X2 Elite spec tables (5G and Wi-Fi as M.2 cards over PCIe Gen 3) |
| qc_ntn_asset_tracker | RF & connectivity | **9205S block diagram (drawn)** + contributing chipsets (SDR105, PME9205, SMB231, WCD9306) + QTS110 tracker |
| qc_thin_tracker_cat1bis | RF & connectivity | **QCX216 block diagram (drawn, external RFFE, QPA8675)** + QTS112 |
| qc_micropower_wifi_node | RF & connectivity | **QCC730M iPA / xPA block diagrams + QCC730 xPA reference schematic and BOM** |
| qc_triradio_smart_home | Appliances & building | QCC74x block diagram + reference schematic (40 MHz crystal, U.FL, match) |
| qc_smart_camera | Appliances & building | QCS410/610 block diagram + spec table (PM6150/PM6150L, WCN3980, WCD93xx, WSA88xx) |
| qc_robot_vacuum | Appliances & building | **RB2 board-level block diagram (drawn)** |
| qc_robotics_vision_kit | Industrial | **RB3 Gen 2 board-level block diagram (drawn)** |
| qc_drone | Industrial | QRB5165 block diagram + Flight RB5 spec table (the reference design is shown only as a photo) |
| qc_humanoid_amr | Industrial | IQ10 robotics reference design spec table + IQ10 block diagram (companion PMICs) |
| qc_edge_ai_box | Industrial | **QCS9100 data sheet Fig 1-1 (board level: 4x PMM8650AU + SIL-3 PMIC, XOs, SerDes, Ethernet switch, WLAN/BT, codec)** + IQ-9075 module diagram |
| qc_fiber_gateway | Communications equipment | FiberPro A8 Elite spec table |
| qc_wifi7_router | Communications equipment | NPro A7 Elite spec table |

Bold rows have a drawn diagram that shows sockets outside the chip. The other rows are built from spec tables or parts lists, and their source strings say so.

## Proposed function ids (`new_functions`)

- `mems_sensor` (sensors): IMU, pressure, humidity, ALS, proximity, PPG and bone-conduction sensors.
- `haptic_driver` (audio): the W5 PMIC lists a haptics driver.
- `acoustic_transducer` (audio): microphones and speakers.
- `usb_typec_hub` (interface): USB hub and Type-C ports on the robotics boards.

All other blocks use existing ids. In particular, cameras use `camera_radar`, LPDDR / UFS / NOR use `ddr_flash` / `flash`, and the SoC uses `soc`.

## Sources read

docs.qualcomm.com PDFs were found through its public `sitemap.xml`. The 32 docs.qualcomm.com documents used are in `docs:` (4 more are qualcomm.com pages and PDFs). These were also read but not used:

- Snapdragon 8 Elite brief: a phone AP; the phone modem-RF is already covered.
- FastConnect 7700 and 8800 briefs: close to FastConnect 7900, already covered.
- IQ-2390, IQ-X, IQ6 / IQ8 and FWA Gen 4 / Gen 6 briefs.
- QCC30xx dongle brief.
- Wi-Fi selector guide.
- QCC730 iPA reference schematic.
- QCC730 data sheet.

From qualcomm.com, these `.md` pages listed in `/en-us/*/llms.txt` were read: Flight RB5, RB6, X Elite, X2 Elite, QTS110, tracker and XR platforms. Two PDFs linked from those pages (`content/dam`) were also read: the Flight RB5 brief and the X2 Elite brief.

## Gaps and uncertain points

- **Not found publicly:**
  - Snapdragon Cockpit / Ride (ADAS) and the FSM small cell have no brief in the docs sitemap and no `.md` page. The only Ride hit was a university-program page, which was not used.
  - The satellite NTN handset is covered only by the 9205S IoT-NTN and Wear Elite NB-NTN entries.
  - No mesh-specific brief was found; NPro A7 is used for the home router / mesh node.
  - The S7 sound platform brief was not in the sitemap; S5 Gen 1 is used instead.
- **PMM8650AU / PMM8620AU data sheet (80-82720-1)** is publicly downloadable, but its footer says "Confidential - Qualcomm Technologies ... May Contain Trade Secrets". It was **not used**. PMM8650AU is cited only from the QCS9100 data sheet figure and the IQ-9075 brief, which name it.
- **PMIC roles in the XR and AR kits:** the briefs list PMK2230, PMXR2230(VS/VE), PM8010, PMAR2130, PMXR130 and PM8008 without saying what each does. They were grouped as PMICs by their `PM*` prefix. XRC130's role is not stated.
- **Wi-Fi part roles:** WCN7850 / WCN7851 were assigned to Wi-Fi/BT based on the platform briefs (FastConnect 7800) and the WCN naming. The briefs do not state this mapping.
- **Front-end parts not shown in briefs:** the Qualcomm briefs do not draw a GNSS LNA or Wi-Fi FEMs on the SoC platforms (W5, Wear Elite, QCS610, laptop). Those groups say "LNA not stated" in their source string. The only named third-party FEMs are the SG Micro SGM22001 / SGM23001 in the QCC730 xPA reference schematic.
- **Laptop power:** the X Elite and X2 Elite briefs list no PMIC, charger or power parts, so the laptop entry has no power group.
- **QCX216 crystals:** the diagram draws crystal symbols, but their count and frequencies are not given.
- **Platform-bundled RF front end:** the FiberPro A8 and NPro A7 front ends are named by Qualcomm as part of the platform ("front-end modules, and filters"), so they are competitive sockets, as in `rf_platforms.md`.
- **Link directions:** for spec-table applications, links are the interfaces the table names. Their direction is a reading of the table, not a drawn arrow.
