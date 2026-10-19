# Data scan – 2026-10-19

15,701 of 20,649 automatic checks passed. Items for a person: 14 high, 23 medium, 14 low.

## Confirmed automatically

### Parts with full parameters (1,543 records)

| Check | Passed | Rule |
|---|---|---|
| Skyworks grade suffix (-A… automotive, -I… industrial) matches the qualification | 826 / 826 | ordering-code suffix |
| Parts named …-Q1 are AEC-Q100 | 258 / 258 | TI / competitor -Q1 suffix |
| Pinout length equals the package pin count | 1,287 / 1,287 | package pin count |
| Datasheet link present | 1,543 / 1,543 | source link |
| Priority 1 parameters present | 1,418 / 1,543 | rules/<family>.yaml priority 1 |

### Manufacturer catalogues (6,079 records)

| Check | Passed | Rule |
|---|---|---|
| Catalogue and datasheet agree on qualification | 568 / 884 | per-part datasheet value wins; catalogue flag is often per series |
| Catalogue and datasheet agree on lifecycle | 876 / 884 | comparison |
| Catalogue records with a stated automotive grade | 2,377 / 6,079 | catalogue field |
| Catalogue records mapped to a functional category | 6,072 / 6,079 | data/taxonomy.yaml |

### Function mapping and qualification (113 records)

| Check | Passed | Rule |
|---|---|---|
| Functions whose path says 'already sold' with all suggested parts decided | 0 / 7 | part-mapping decisions |
| Automotive-needed functions with a stated grade | 60 / 80 | three-state qualification |
| Radio parts with a stated AEC-Q100 grade | 56 / 70 | radio data |

### Block diagrams (153 records)

| Check | Passed | Rule |
|---|---|---|
| Every block uses a known function | 153 / 153 | functions.yaml |
| Library architectures with a cited source | 101 / 105 | sources field |

### Business evidence (738 records)

| Check | Passed | Rule |
|---|---|---|
| Technology rating: source-checked (confirmed or corrected) | 0 / 160 | opened public sources |
| Competition: source-checked (confirmed or corrected) | 0 / 111 | opened public sources |
| Customer segment: source-checked (confirmed or corrected) | 0 / 61 | opened public sources |
| Technology platform: source-checked (confirmed or corrected) | 0 / 46 | opened public sources |
| Path to product: source-checked (confirmed or corrected) | 0 / 69 | opened public sources |
| Patents: source-checked (confirmed or corrected) | 0 / 69 | opened public sources |
| Foundry route: source-checked (confirmed or corrected) | 0 / 69 | opened public sources |
| Competitor technology: source-checked (confirmed or corrected) | 55 / 69 | opened public sources |
| Market trend: source-checked (confirmed or corrected) | 51 / 69 | opened public sources |
| New-market idea: source-checked (confirmed or corrected) | 0 / 15 | opened public sources |

### Commercial inputs (0 records)

| Check | Passed | Rule |
|---|---|---|
| Functions with an ASP | 0 / 113 | your inputs |

## Needs a person

| Priority | Area | What to check | Why a person | Impact if wrong |
|---|---|---|---|---|
| high | Parts | 91 Digital isolators parts miss priority 1 'creepage_mm' (e.g. NSI8120D0, NSI8120D1, NSI8121D0, NSI8121D1) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| high | Parts | 28 Digital isolators parts miss priority 1 'isolation_rating_kvrms' (e.g. NSI8120D0, NSI8121D0, SI8650BC-AS1, ISO6540QDBQRQ1) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| high | Evidence | Technology rating: 25 top-ranked functions without a confirming source (e.g. adc, amplifier, audio_codec, ble_soc) | No public source confirmed it automatically (blocked site, nothing found, or not checked yet). | These feed the top of the Opportunity explorer. |
| high | Evidence | Competition: 25 top-ranked functions without a confirming source (e.g. adc, amplifier, audio_codec, can_transceiver) | No public source confirmed it automatically (blocked site, nothing found, or not checked yet). | These feed the top of the Opportunity explorer. |
| high | Evidence | Path to product: 25 top-ranked functions without a confirming source (e.g. ble_soc, isolated_dcdc, gnss_lna, three_phase_gate_driver) | No public source confirmed it automatically (blocked site, nothing found, or not checked yet). | These feed the top of the Opportunity explorer. |
| high | Parts | 13 Digital isolators parts miss priority 1 'default_output' (e.g. ISOW6442DWERQ1, ISOW7742QDFMRQ1, ISOW7740DFMR, ISOW7744DFMR) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| high | Function mapping | Do these parts fill 'Bluetooth LE / 802.15.4 SoC'? (e.g. QPG6095, QPG6100, QPG6105, QPG6200L) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 5 in the explorer). |
| high | Function mapping | Do these parts fill 'Isolated DC-DC'? (e.g. Si88220BD-IS, Si88240BD-AS, Si88240BD-IS, Si88320BD-IS) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 9 in the explorer). |
| high | Function mapping | Do these parts fill 'GNSS LNA / front end'? (e.g. SKY55950-11, SKY55951-11, SKY5A2110, SKY65723-11) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 20 in the explorer). |
| high | Function mapping | Do these parts fill 'Diversity / RX front-end module'? (e.g. SKY53728-11, SKY53730-11, SKY53731-11, SKY53735-11) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 27 in the explorer). |
| high | Function mapping | Do these parts fill 'RF pre-driver amplifier'? (e.g. SKY66041-11, SKY66042-11, SKY66051-11, SKY66052-11) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 64 in the explorer). |
| high | Function mapping | Do these parts fill 'RF transceiver (RFIC)'? (e.g. AWMF-0210, AWMF-0224, QM33110W, RFFC2072A) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 30 in the explorer). |
| high | Evidence | Market trend: 9 top-ranked functions without a confirming source (e.g. pol_ldo, supervisor, sequencer, voltage_reference) | No public source confirmed it automatically (blocked site, nothing found, or not checked yet). | These feed the top of the Opportunity explorer. |
| high | Function mapping | Do these parts fill '3-phase gate driver (non-isolated)'? (e.g. ACT72350, PAC52710QM, PAC5523AQM, PAC5524QF) | Matching a part to a system function needs an engineer's judgement of the datasheet. | Confirming turns the gap into a portfolio function (rank 16 in the explorer). |
| medium | Commercial inputs | 113 functions without an ASP | Prices are commercial knowledge; nothing is estimated automatically. | Revenue and TAM cover only priced functions. |
| medium | Qualification | Wi-Fi front-end module: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Qualification | PMIC: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Block diagrams | 24 groups of possible architecture variants (e.g. adas domain controller, traction inverter, gate driver, bldc) | Whether two reference designs describe one application is a judgement, not a rule. | Until decided, counts are reference architectures, not unique applications. |
| medium | Qualification | Crystal / oscillator: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Qualification | LED driver: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Evidence | Patents: 25 top-ranked functions without a confirming source (e.g. pol_ldo, temperature_sensor, ble_soc, supervisor) | No public source confirmed it automatically (blocked site, nothing found, or not checked yet). | Shown as evidence for top-ranked functions. |
| medium | Evidence | Foundry route: 25 top-ranked functions without a confirming source (e.g. pol_ldo, temperature_sensor, ble_soc, supervisor) | No public source confirmed it automatically (blocked site, nothing found, or not checked yet). | Shown as evidence for top-ranked functions. |
| medium | Qualification | 14 radio parts without an AEC-Q100 statement (e.g. Si47992, Si4682-A10, Si4683-A10, Si4684-A10) | Their data sheets in the radio data do not state the grade. | Car-radio configurations may propose a part without a confirmed automotive grade. |
| medium | Catalogue | 8 parts with conflicting lifecycle (e.g. SI8600AD-IS (obsolete vs catalogue active), SI8605AD-IS (obsolete vs catalogue active), SI8621BC-IS (obsolete vs catalogue active), SI8630BD-IS (obsolete vs catalogue active)) | Two public sources disagree; only a current product page or PCN decides. | A part may be shown as active although it is NRND, or the reverse. |
| medium | Qualification | PoL buck: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Parts | 7 RF switches parts miss priority 1 'termination' (e.g. SKYA21024, SKY13562-670LF, SKY5A1007, SKY13699-21) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| medium | Parts | 6 Digital isolators parts miss priority 1 'integrated_power' (e.g. ISOW7741QDFMRQ1, ISOW7740DFMR, ISOW7743DFMR, ISOW7744DFMR) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| medium | Qualification | Wireless connectivity SoC (802.15.4 / BLE / UWB): automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Parts | 3 Digital isolators parts miss priority 1 'isolation_class' (e.g. NSI8120D0, NSI8121D0, ISO7221CDR) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| medium | Parts | 3 parts with unknown lifecycle (e.g. SI86SW41BC-AS1, SI86SW62BC-AS1, SKY13638-700LF) | Lifecycle comes from manufacturer pages that did not list these parts. | NRND / obsolete parts are listed last; an unknown one may be recommended. |
| medium | Qualification | Battery monitor / fuel gauge: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Qualification | Buck-boost controller: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Qualification | High-side / load switch: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Qualification | Audio amplifier: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Qualification | Bluetooth / 802.15.4 front end: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| medium | Parts | 1 RF switches parts miss priority 1 'max_input_power_dbm' (e.g. SKY19225-001) | The value is in the datasheet table or footnotes in formats a parser cannot read reliably. | Unknown priority 1 values count as deviations: crosses can be missed or downgraded. |
| medium | Qualification | Isolated current sensor: automotive needs it, our parts state no grade | The catalogue does not state AEC-Q100 for these parts; only a datasheet or the product team can. | Decides whether it is an existing automotive part or a qualification opportunity (Markets). |
| low | Catalogue | 316 parts: catalogue says automotive, datasheet ordering code says industrial (e.g. SI8600AB-IS, SI8600AC-IS, SI8600AD-IS, SI8602AB-IS) | Resolved by rule (the per-part datasheet value is used); a spot check of a few confirms the rule. | Wrong rule would mis-state the automotive grade in Browse products. |
| low | Parts | 256 parts without a pinout (e.g. NSI8120D0, NSI8120D1, NSI8121D0, NSI8121D1) | Pinouts come from datasheet pin tables; these were not extracted. | Pin-to-pin compatibility cannot be confirmed for them. |
| low | Evidence | Technology rating: 135 further items without a confirming source (e.g. active_antenna_amp, adas_processor, am_fm_tuner, antenna) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Competition: 86 further items without a confirming source (e.g. active_antenna_amp, am_fm_tuner, antenna_switch, antenna_tuner) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Customer segment: 61 further items without a confirming source (e.g. ev_traction_inverter, light_ev_drive, automotive_motor_drive, forklift_traction) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Technology platform: 46 further items without a confirming source (e.g. gaas_hbt, gaas_phemt, gan_on_sic, gan_on_si) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Path to product: 44 further items without a confirming source (e.g. diversity_rx_module, rf_predriver, rf_transceiver, ldo_tracker) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Patents: 44 further items without a confirming source (e.g. mcu, wifi_soc, rtc, motor_driver_brushed) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Foundry route: 44 further items without a confirming source (e.g. mcu, wifi_soc, rtc, motor_driver_brushed) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | New-market idea: 15 further items without a confirming source (e.g. wireless_audio, uwb, matter_thread, baw_filters) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Competitor technology: 14 further items without a confirming source (e.g. diversity_rx_module, relay_driver, ddr_flash, vehicle_sensors) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Evidence | Market trend: 9 further items without a confirming source (e.g. battery_protector, rtc, circulator_isolator, dac) | Same reason; lower impact. | Ranked lower or not scored. |
| low | Catalogue | 7 catalogue records without a functional category (e.g. 855399, 856293, 856450, CGA-0116) | Their source category is too generic ('Other') to map by rule. | They only appear under Unclassified in Browse products. |
| low | Block diagrams | 4 library architectures without a cited source (e.g. ADAS domain controller, Car radio tuner system, EV traction inverter, Industrial isolated I/O) | Drawn from experience before sources were recorded. | Their blocks cannot be traced to a document. |
