# Skyworks cross reference vs our cross engine (10 Nov 2026)

Owner's request: "https://www.skyworksinc.com/cross-reference — check this and improve our cross reference."

**Source.** Skyworks' public cross reference, read on 9 Nov 2026 (55 polite GETs, robots.txt allows the page). The site
searches for the text anywhere in the competitor number and shows at most 10 rows per search, so the table is a
sample: 358 rows (TI 226, Novosense 58, ADI 57, Infineon 7, others 10), in `data/manage/skyworks_cross_reference.yaml`.
Not found there: Chipanalog CA-IS, TI AMC, LMK, Renesas 5P49, pSemi PE42, Infineon BGSA (no rows for those searches).

**Method.** Every official row whose competitor part is in our data was crossed with the same engine and columns as
Cross a list (drop-in, best functional fit, other Si86 / Si86S family), on a database with every `data/real` file.
"Top" = our drop-in, else our functional fit. Counts are per competitor part (230 compared; 35 not in our data).

## Counts

| | Before fixes | After fixes |
|---|---|---|
| Our top part is one of the official parts | 72 | 75 |
| An official part is shown (any of our three columns) | 107 | 110 |
| We give a drop-in (same package and pinout) | 159 | 190 |
| We give no cross | 0 | 0 |

The official table often lists several equal parts (default-low / high codes, Si86S6xx / Si86SLxx / H codes) where we
show one, so "top part agrees" stays low even where both answers are right. The groups below explain every case.

## What we fixed (data, from the datasheets)

1. **Novosense NSI82xx channels and defaults** (23 parts): the Novosense product table had NSI8221 as 2/1 (it is 1/1)
   and swapped default outputs on the SOW8 / SOWW16 codes. Now from the datasheets' order information: NSI82*nr*, last
   digit 0 = default low, 1 = high (`app/sources/novosense.py` applies the rule on the next import).
2. **Novosense pinouts** (88 parts: NSI8210, NSI822x in SOP8 / SOW8 / SOW16 / SOWW16, NSI824x in SOP16 / SSOP16 /
   SOWW16) from the cached datasheet pin tables. Before, these parts could never get a drop-in. 106 Novosense parts
   (NSI826x, NSI83xx, NSI812x) still lack a pinout: left for later.
3. **TI ISO6760L default low** (iso6760l.pdf function table; the TI product table said high).
4. **TI ISO7730-Q1 / ISO7731-Q1 and ISO6721** pinouts copied from their twins (same pin diagram in the -Q1 datasheet).

No rule was changed. 11 official pairs, each checked on both datasheets, are now known pairs (`source: skyworks_xref`
in `data/manage/cross_known_pairs.yaml`): 6 right, 5 wrong. All 11 pass.

## Disagreements by cause (after the fixes)

### Official row does not match the datasheets: we kept ours (27)

| Their part | Official | Why we kept ours |
|---|---|---|
| ISO7721DR, ISO7721FDR, -Q1 codes (9 rows) | Si86S621 / Si8621 | ISO7721 pin 2 is OUTA (iso7721.pdf Figure 5-4); Si8621 pin 2 is an input, Si8622 matches. The table itself gives Si86S622 for ADUM1201 and ISO6721, which have the same pinout. |
| NSI8221N0-DSPR, NSI8221W0/W1-DSWVR | Si86S621 | NSI8221 pin 2 is OUTA (NSI822x Figure 1.2); the N1 row gives Si86S622. |
| ISO7720 / ISO7721 …DWV (8-pin wide) | Si8620 / Si8621 …D (16-pin) | Different package; Si86S620 / Si86S622 …-IS4 / -AS4 are the 8-pin wide drop-ins. |
| ISO7342C-Q1 / ISO7342FC-Q1 | Si8642BD-AS / Si8642ED-AS | Default outputs swapped (C = high, FC = low). |
| ISO7740DWR | Si86S640EB-IU | DW is SOIC-16 wide, IU is QSOP-16. |
| ISO7742DBQR | Si86S662EB-IU | Si86S662 has six channels; Si86S642EB-IU is the 2/2 part. |
| ISO7761FDBQR, ISO7760FQDBQRQ1 | E (default-high) codes | F parts are default low. |
| ISO7762FDWR | Si86S662BC-IS1 | Narrow SOIC-16 for a wide one (Si86S662BE-IS2). |
| ISO7710QDWRQ1 | Si8620BD-AS | 2-channel, default-low part for a 1-channel, default-high part. |
| NSI8210…-Q1 (4 rows) | …-IS (industrial) | Automotive part; we give the -AS part. |
| UCC21540DWR | Si82E89ABE-IS3 | Si82E89 has one PWM input; UCC21540 has INA / INB (Si82E29ABE-IS3, which they also list). |

### Si86 / Si86S family choice (52)

Both families fit, and we show the other family in the third column. The official table prefers Si86S6xx for most
newer TI and Novosense parts (e.g. ISO7741DWR: theirs Si86S641EE-IS2; ours Si8641ET-IS, Si86SL41EE-IS2 as other
family) and Si86xx for older automotive codes (ISO7761QDWRQ1: theirs Si8661ED-AS; ours Si86S661EE-AS2, Si8661ED-AS
shown). Question for the owner below.

### Another Si86S variant on a tie (16)

Same channels, default and package; the engine picks the closest values, often the low-power Si86SL (e.g.
NSI8241N0-DSPNR: ours Si86SL41BC-IS1, theirs Si86S641BC-IS1) or the H / F deglitch codes.

### Theirs Si86xx D grade, ours T grade (18)

For TI reinforced parts (ISO7741DWR, ISO7720FQDWRQ1, …) the table gives the basic-insulation D grade (e.g.
Si8641ED-IS); we give the reinforced T grade (Si8641ET-IS: reinforced, 10 kV surge, CMTI 100 typ; si864x data sheet).
Kept ours.

### Base numbers without a package (11)

Rows such as ISO7720 → Si8620ED-IS name the device, not an ordering code; we cross the SOIC-8 code (ISO7720DR →
Si86S620EC-IS), so these are not real disagreements.

### ADuM grade rows (11) and ADuM1410 (1)

ADUM1400A/B/C → Si8640AB-IS / BB-IS (2.5 kV, default low; their note says "Si8xxx has failsafe low"); we give
default-high 6 kV Si86S640HE-IS2, as the ADuM outputs default high. ADuM1410 has output-enable pins: ours Si8645ET-IS
(with enable), theirs Si86S640 (no enable). Kept ours.

### Gate drivers (16)

| Their part | Ours (drop-in / functional) | Official |
|---|---|---|
| UCC21520DW, ADW, AQDWRQ1 | Si82E29ABE (drop-in) | Si82520AD (Functional) |
| UCC21530QDWKRQ1 | Si82E39BCE-AS3 | Si82520AD-AS3 |
| ISO5452 (4 rows) | Si8285CD (functional) | Si8286CD / Si8281CD (Functional) |
| 1EDI20I12AF / 20N12AF / 20I12MF / 30I12MF / 40I12AF | Si823H9 / Si82B4x (functional) | Si823H9 / Si82C50 |
| NSI6602B-DLAR / -DSPNR | Si82E29AB… | Si82E39BBC-IS1 |

Different functional picks among parts that both lists call functional; not changed without a datasheet check of
each (left for later).

## Import gaps

- Skyworks parts in the official table but not in our data: Si8642EB-AS (for ISO7342-Q1); Si8662BD-ASR (listed for
  ISO7763FQDWRQ1, probably meant Si8663BD-AS); "SkY82Sx" (a family, for 1EDI60I12AF).
- Competitor parts in the official table but not in our data: ADuM1201, ADuM1301, ADuM3401 (base numbers and grades),
  ISO6760LNDWR, UCC5350L-Q1, PUCC21551CQDFJRQ1, TI CDCE9xx clock generators (official: Si5351B, Functional).

## Questions for the owner

1. On a tie, should we prefer the standard Si86S6xx (as the official table does) over the low-power Si86SL and the
   Si86xx T grade? Today the closest values win.
2. The official table has wrong rows (ISO7721 / NSI8221 direction, ISO7342C defaults, package mix-ups above). Who
   should hear about them?
3. Should the official match type ("Drop-In", "Pin-to-Pin", "Functional") also go into the Excel download?
