# Timing backlog: datasheets for timing crosses

Owner, 22 Oct 2026: make timing crosses work like isolation and RF switches. The daily update run reads the next 2–3
datasheets from this list (docs/daily_update.md; they count toward the about 5 documents a run), public datasheets
only, polite access (robots.txt first, one request at a time, stop at the first block). Each datasheet goes into the
data file named, with the parameters of `rules/timing.yaml` (function_type, outputs, output_formats, freq_range_mhz,
vdd_range_v, jitter_fs, qualification, temp_range_c, pcie_gen, inputs, control, stability_ppm), its source URL,
sha256 and fetch date, and the package. Tick a line when its parts are in; note a blocked or missing datasheet
instead. Pin-to-pin drop-ins are rare across vendors in timing, so pinouts come after the parameters.

## Done (first batch, 22 Oct 2026: 19 datasheets)

- [x] Skyworks · `skyworks_timing.yaml` · si5332-datasheet.pdf · Si5332A-GM1, Si5332A-GM2, Si5332A-GM3
- [x] Skyworks · `skyworks_timing.yaml` · si5332-automotive-grade-datasheet.pdf · Si5332A-AM1, Si5332A-AM2, Si5332A-AM3
- [x] Skyworks · `skyworks_timing.yaml` · si5341-40-d-datasheet.pdf · Si5341A, Si5340A
- [x] Skyworks · `skyworks_timing.yaml` · si5345-44-42-d-datasheet.pdf · Si5345, Si5344, Si5342
- [x] Skyworks · `skyworks_timing.yaml` · si5395-94-92-a-datasheet.pdf · Si5395
- [x] Skyworks · `skyworks_timing.yaml` · si5397-96-a-datasheet.pdf · Si5397
- [x] Skyworks · `skyworks_timing.yaml` · si532xx-datasheet.pdf · Si53204-A01/-A02, Si53208-A01/-A02
- [x] Skyworks · `skyworks_timing.yaml` · si545-datasheet.pdf, si549-datasheet.pdf · Si545, Si549
- [x] TI · `ti_timing.yaml` · lmk03328.pdf, lmk3h0102-q1.pdf, cdce6214-q1.pdf, lmk04832.pdf, lmkdb1104.pdf · LMK03328,
  LMK3H0102-Q1, CDCE6214-Q1, LMK04832, LMKDB1104, LMKDB1108
- [x] SiTime · `sitime_timing.yaml` · SiT9365, SiT3521, SiT95211 datasheets
- [x] Renesas (timing now owned by SiTime) · `sitime_timing.yaml` · 5p49v6965-datasheet, 8a34001-datasheet · 5P49V6965, 8A34001

## Next: no new download needed (already fetched)

- [ ] Skyworks · `skyworks_timing.yaml` · si532xx-datasheet.pdf · Si53212-A01/-A02 (12-output PCIe buffer, 64-QFN)
- [ ] Skyworks · `skyworks_timing.yaml` · si5332 / si5341 / si5345 / si5395 / si5397 datasheets · the other grades
  (Si5332B/C/D, Si5341C/D, Si5340B/C/D: 200 / 350 MHz and integer-only variants), Si5394 / Si5392, Si5396
- [ ] TI · `ti_timing.yaml` · lmkdb1104.pdf · LMKDB1102, LMKDB1112, LMKDB1120 (2, 12 and 20 outputs)
- [ ] All first-batch parts · pinouts (pin tables are in the datasheets already fetched; only Si545, Si549 and SiT9365
  carry one now) and competitor package lead data (TI, SiTime, Renesas drawings are images: read them by hand)

## Skyworks families still to read (most sold first)

- [ ] Skyworks · `skyworks_timing.yaml` · Si5338.pdf · Si5338A–Si5338Q (4-output any-frequency clock generator)
- [ ] Skyworks · `skyworks_timing.yaml` · Si5351-B.pdf · Si5351A/B/C (consumer 3/8-output clock generator)
- [ ] Skyworks · `skyworks_timing.yaml` · si5347-46-d-datasheet.pdf · Si5347, Si5346 (quad / dual DSPLL jitter attenuators)
- [ ] Skyworks · `skyworks_timing.yaml` · si5391-datasheet.pdf · Si5391A–P (12-output clock generator for 56G SerDes)
- [ ] Skyworks · `skyworks_timing.yaml` · si5383-84-datasheet.pdf · Si5383, Si5384 (IEEE 1588 network synchronizers; the
  Skyworks answer to Renesas 8A34001 ClockMatrix and TI LMK05318B)
- [ ] Skyworks · `skyworks_timing.yaml` · si5348-e-datasheet.pdf · Si5348 (SyncE / 1588 network synchronizer)
- [ ] Skyworks · `skyworks_timing.yaml` · si5381-82-revE-datasheet.pdf · Si5381, Si5382 (wireless jitter attenuators)
- [ ] Skyworks · `skyworks_timing.yaml` · si52212-si52208-si52204-si52202-datasheet.pdf · Si52202–Si52212 (PCIe clock
  generators)
- [ ] Skyworks · `skyworks_timing.yaml` · si5225x-datasheet.pdf, si5325x-datasheet.pdf, si5335x-datasheet.pdf ·
  automotive PCIe clock generators and buffers (Si52254/8-AM, Si53254/8-AM, Si53350–58-AM)
- [ ] Skyworks · `skyworks_timing.yaml` · si5118-smartclock-synthesizer-datasheet.pdf · Si5118A-AM2 (automotive)
- [ ] Skyworks · `skyworks_timing.yaml` · si5330x / Si5331x / Si5332x / Si5334x / si5336x datasheets · universal and
  LVPECL / LVDS / LVCMOS fanout buffers (Si53301–Si53365)
- [ ] Skyworks · `skyworks_timing.yaml` · si540 / si541 / si542 / si544 / si546 / si547 / si548 datasheets · Ultra
  Series XOs and VCXOs; si560–si569 · Ultra Series differential XOs
- [ ] Skyworks · `skyworks_timing.yaml` · SKY535x0-x1, SKY535x2-x3 datasheets · SKY535xx clock buffers
- [ ] Skyworks · `skyworks_timing.yaml` · SKY62101_datasheet.pdf, SKY63101-02-03, SKY63104-05-06 · newer SKY clock
  generator and jitter attenuators
- [ ] Skyworks · `skyworks_timing.yaml` · si5512 / si5518 / si540x / si5388-89 · network synchronizers (data shorts only:
  check what they state)

## Competitor families still to read

- [ ] TI · `ti_timing.yaml` · lmk05318b.pdf · LMK05318B (network synchronizer / jitter cleaner, against Si5345 / Si5383)
- [ ] TI · `ti_timing.yaml` · lmk5b33216.pdf · LMK5B33216 (BAW network synchronizer, against Si5395 / Si5383)
- [ ] TI · `ti_timing.yaml` · lmk3c0105.pdf, lmk03318.pdf · BAW and crystal clock generators (against Si5332)
- [ ] TI · `ti_timing.yaml` · lmk1c1104.pdf, cdclvp1208.pdf, lmk00334.pdf · LVCMOS / LVPECL / PCIe fanout buffers (against
  Si53301–Si53365 and Si53204)
- [ ] TI · `ti_timing.yaml` · lmk6c.pdf / lmk6d.pdf / lmk6h.pdf · BAW oscillators (against Si545 / Si549)
- [ ] SiTime · `sitime_timing.yaml` · SiT95145 / SiT95147 (Cascade jitter cleaners, against Si5345 / Si5395)
- [ ] SiTime · `sitime_timing.yaml` · SiT91211 or the Chorus SiT9128x family (clock generator with built-in MEMS
  reference, against Si5332); SiT9501 (check its product type first)
- [ ] SiTime · `sitime_timing.yaml` · SiT9366 / SiT9367 / SiT9375 (any-frequency differential XOs, against Si545 / Si549)
- [ ] SiTime · `sitime_timing.yaml` · SiT5356 (Super-TCXO; Skyworks has no TCXO in the catalogue: record as a gap)
- [ ] Renesas (SiTime) · `sitime_timing.yaml` · RC21008A (FemtoClock 3 clock generator, against Si5341 / Si5395)
- [ ] Renesas (SiTime) · `sitime_timing.yaml` · RC19008 / 9DBL04x1 PCIe buffers (against Si53204 / Si53208); the
  9DBL0441 product page answered 404 on 22 Oct 2026, find the current page name first
- [ ] Renesas (SiTime) · `sitime_timing.yaml` · 9FGV1006 / 5P35023 (PCIe and VersaClock 3S clock generators)

## Skipped (blocked hosts, never worked around)

- Microchip · microchip hosts are on the blocked list for this work (with analog.com and broadcom): ZL30733 and
  PL610 are not read; they wait for the owner's decision (docs/open_questions.md)
- Analog Devices · analog.com is blocked: AD9545, LTC6952 are not read
