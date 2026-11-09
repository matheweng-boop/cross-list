# Data-center rack power (deep dive, key `dc_rack_power`)

Researched 2026-11-09 (owner, 9 Nov 2026: "Do a Data Center Rack Power deep dive in Systems & applications"). The
summaries are our own wording. The YAML for the app is in `dc_rack_power.yaml`; the five block diagrams are in
`data/blocks/templates.yaml` (Data center > Rack power): the three earlier ones (TI AC/DC PSU, Infineon 48 V IBC, 800 V
DC power) and two new ones drawn for this deep dive (Open Rack v3 power shelf with BBUs; AI compute tray from the
48 / 54 V busbar to the GPU core).

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | NVIDIA technical blog, 800 VDC architecture (20 May 2025, updated 31 Jul 2025) | Cached copy from the extra-wide isolation case (21 Oct 2026), re-read: 54 V limits, sidecar, SST, partners |
| r2 | NVIDIA technical blog, Building the 800 VDC ecosystem (13 Oct 2025) | Cached copy from the eFuse report (28 Oct 2026), re-read: load swings, storage layers, Kyber 64:1 LLC |
| r3 | OCP Open Rack V3 48V PSU Specification rev 1.0 (Meta, 10 Nov 2022) | New, 9 Nov 2026 (Word file): sections 2-3 (summary, electrical), 3.17-3.18 hold-up and BBU hand-over, 4 (communication, blackbox), 5.3 altitude, 8 (MTBF, safety) |
| r4 | OCP Open Rack V3 48V BBU Specification rev 1.4 (Meta, 12 Sep 2023) | New, 9 Nov 2026: overview, 4.2-4.3 battery pack, BMS and discharger table, 4.3.1 peak load |
| r5 | Infineon press release on VPD modules (10 Mar 2025) | New, 9 Nov 2026 (two redirects followed after a robots check) |
| r6 | Skyworks AN1456, data-center creepage and clearance (8 Sep 2026) | Cached copy (var/appnotes, 30 Oct 2026): zones, altitude, Table 7 |

Also used without a new request: the TI and Infineon eFuse / hot-swap pages read on 28 Oct 2026 for the eFuse research
report (TI TPS1685 / TPS1689: 9-80 V, 3.5 mΩ, 20 A, stackable, PMBus on TPS1689; Infineon XDP710 PMBus hot-swap
controller), the OCP Rack & Power project page (28 Oct 2026: the ORv3 document list and the "OCP Diablo 400: Power
Sidecar" course), eeNews Europe on TI's 800 VDC portfolio (19 Mar 2026: 800 V hot-swap controller, 800 V to 6 V GaN
bus converter at 97.6 % peak and over 2,000 W/in³, 6 V to below 1 V multiphase, 30 kW 800 V AC/DC supply, 800 V
supercapacitor bank units, 800 V to 12 V tray converter), and the TI / Infineon reference designs in
data/reference_designs/ (PMP23630 30 kW HVDC PSU with ISO77xx isolators and AMC isolated amplifiers; Infineon IBC,
BBU and XDP712 48 V hot-swap designs).

New request this run (one more, as a diagram source): TI PMP41155 (OCP ORv3 12 kW BBU reference design: six-phase
four-switch buck-boost with LM51770, 28.6-60 V in, 50 V out, 240 A, >99 % peak efficiency, INA296A current sense,
C2000 MCU). Four new documents in total; the OCP Academy page (Diablo 400) is a script-only page without a robots.txt
and was not read.

## Key numbers taken

- r3 2-3: 3 kW, 200-277 V AC (180-305 V), 47-63 Hz; output 51 V at no load, 50.5 V at full load (0.5 V droop), 48 V
  when commanded; set point ±0.25 %; ripple 500 mV p-p; efficiency >97.5 % peak / >96.5 % min at 30-100 % load
  (230-277 V), >96.5 / >95.5 % at 208 V, 94 % at 10-30 %; PF >0.98 (30-100 %); iTHD 15 / 10 / 5 % (5-10 / 10-30 /
  30-100 % load); inrush 30 A; dynamic response 0.5 / 1 / 1.5 V for 50 / 90 / 140 % steps at 1 A/µs, 3 ms settling;
  hold-up 20 ms at 100 % (60 J), BBU hand-over by a 3 V drop after 30 J; pulse power from 40 % (24 J) of the hold-up
  energy; current share ±2 % above 50 % load, Ishare bus 7 V full scale, 50 Hz; N+1 in the shelf; hot plug; PMBus
  100 kbps and Modbus 115 kbps; signal ground to the 48 V return through 10 Ω; blackbox; MTBF 500 k h; IEC / UL / EN
  62368-1; 0-3050 m operating. Narrow 48 V range chosen so 4:1 fixed-ratio converters and 12 V PoL stages can follow.
- r4: six BBUs per shelf, 5+1; 11S6P 18650 Li-ion (28.6-44 V); BMS balancing ±1 %, SOC, SOH, PCM; discharger 3 kW,
  63.2 A at 47.5 V, input up to 110 A; output 48.0 / 47.75 / 47.5 V at 0 / 50 / 100 % load; total regulation 46-49.5 V;
  ≥240 s at full power; 8-year life; ripple 300 mV; transient ±3 %, never below 46 V; start-up 2 ms; efficiency ≥97 %
  including fuse / hot-swap / ORing; peak load to 150 % (1 A/µs); Modbus, I2C, CAN bus mentioned for SOH signalling.
- r1: GB200 / GB300 NVL72 up to eight power shelves; 1 MW at 54 V would need 64 U of shelves and up to 200 kg of
  busbar; 800 V busways carry 85 % more power in the same conductor (45 % less copper); up to 5 % better end-to-end
  efficiency; 800 V sidecar at GTC 2025 for 576 Rubin Ultra GPUs; SST under study; production with Kyber in 2027.
- r2: GPU power +75 % and rack power density x3.4 from Hopper to Blackwell; rack power 30 % to 100 % in milliseconds;
  supercapacitors near racks (ms to s) and BESS at the interconnection (s to min); 800 V carries 157 % more power than
  415 V AC in the same wire gauge; three wires (POS, RTN, PE); Kyber 64:1 LLC 800 V to 12 V, 26 % less area.
- r5: TDM2454xx quad-phase VPD modules, 280 A in 10 x 9 mm, 2 A/mm², embedded capacitor layer, XDP controllers.
- r6: OVC III (4000 / 6000 V) for SST, 800 V / 1500 V DC links and ESS; OVC II (2500 V) for power shelves, BBUs and
  CBUs, often in a sidecar rack; 3000 m (ORv3) or 5000 m; 800 V reinforced at PD2: 8 mm on the package (material group
  I), 16 mm on FR4 (IIIa); slots at least 1 mm or a certified coating.

## Our reasoning (est)

- Where isolation sits: in the PSU (PFC to LLC primary across the barrier: control signals, PMBus, bus sensing, bias),
  in every 800 V converter and in sidecar storage. Not in the tray on a 48 V bus. The 800 V step moves the barrier into
  every compute tray, which is the growth case for our gate drivers and isolators.
- Parts named are from the BizDev catalogue only. Fit of PAC22140 / PAC25140 to an 11S BBU pack is our reading of the
  catalogue line "10s-20s"; the data sheets were not read.
- Market lines are units x content, all estimates; no public unit figure was read.
- CMTI numbers (100-200 kV/µs) and GaN edge rates are general knowledge, not from the six references.
