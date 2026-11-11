# ADAS and sensing: radar, cameras, lidar and the domain controller (deep dive, key `auto_adas`)

Researched 2026-11-11 (weekly deep dive). The summaries are our own wording. Short quotes are marked and cited. The YAML
for the app is in `auto_adas.yaml`. Figures marked "est" are our own reasoning.

## References (6)

| id | Document | Type | Why | Read |
|---|---|---|---|---|
| r1 | TI, *ADAS domain controller* solution page (block diagram + subsystem list) | reference design | Public partition of a domain controller | Reused: read 19 Oct 2026 for the Block diagram library (`data/blocks/research/ti_block_diagrams.yaml`) |
| r2 | TI, *Imaging Radar Using Cascaded mmWave Sensor Reference Design*, TIDEP-01012 (TIDUEN5A, Mar 2020) | reference design | 4-chip imaging radar: LO, clock, sync, array, data, power, calibration | §1-2.3.3, 3.3 (new download) |
| r3 | ETSI EN 302 264 V2.1.1 (2017-05), short range radar 77-81 GHz | standard | EU limits for car radar | §4.3-4.5 (new download) |
| r4 | arXiv:2306.04242v4, *4D Millimeter-Wave Radar in Autonomous Driving: A Survey* (Tsinghua / Changan, 2024), CC BY 4.0 | paper | How 4D radar works, data volume, trends | Abstract, §I-II, Table I, §VII (new download: abstract page + PDF) |
| r5 | Skyworks Si5332-AM data sheet 206325A (Jul 2022) | vendor data sheet | Our automotive clock generator | Front page, features, §3 (SmartClock, spread spectrum) (new download) |
| r6 | TI, *Automotive in-cabin radar module* solution page | reference design | 60 GHz cabin radar partition | Reused: read 19 Oct 2026 (`data/blocks/research/ti_more_block_diagrams.yaml`) |

Background, not in the six (reused, read 2 Nov 2026 for the Block diagram library): Nisshinbo Micro Devices, Safety
(ADAS, parking assist), Camera Sensing (parking assist) and Corner Sensor ECU pages. They show the low end: analog
cameras with video amplifiers, corner sensors with an ASIC and op-amp, a sensor ECU with MCU, memory and CAN.

Also reused: the automotive clock-tree case (`data/business/cases/auto-clock-tree.yaml`: Yole radar-module figure,
TI / SiTime clock positions, "radar timing is captive") and the child-presence case (`auto-uwb-cpd`).

New documents fetched (polite reader, robots.txt first, one at a time): r2 (ti.com, one 302 from /lit/pdf/tiduen5 to the
tiduen5a PDF, followed after checking robots.txt), r3 (etsi.org), r4 (arxiv.org abstract page and PDF), r5
(skyworksinc.com). No block, no 403/429.

## Block diagram (our drawing, based on r1-r6)

```
 [Front / corner radar, 1 chip]   antenna 3TX/4RX - radar SoC (VCO, PA, LNA, ADC, DSP) - 40 MHz xtal - PMIC
        └── CAN-FD / T1 Ethernet: object lists ─────────────────────────────┐
 [4D imaging radar, 2-4 chips]    master chip ── 20 GHz LO (passive Wilkinson, delay matched) ──► slaves
                                  40 MHz xtal at master ─► fan-out buffer ─► 40 MHz + frame sync to all chips
                                  2 quad bucks (5 V / 8 A in), temp sensors
        └── CSI-2 (2.4 Gb/s per chip) ─► serializer / Ethernet: raw data ──►│
 [Cameras]  image sensor ─► serializer (FPD-Link / GMSL / A-PHY) ◄─ power over coax ─►│  ADAS DOMAIN CONTROLLER
 [Lidar]    laser driver, APD/SPAD + TIA, ADC/TDC, processor ─► Ethernet ─────────►│  deserializers + PoC switches
 [Ultrasonic corners] transducer AFE ─► LIN / DSI3 / CAN ─────────────────────────►│  sensor SoC + fusion SoC
 [GNSS L1+L5 front end] ──────────────────────────────────────────────────────────►│  safety MCU, DDR / flash
 [Cabin] 60 GHz radar module or interior UWB anchor ─► CAN ───────────────────────►│  PCIe switch, Ethernet switch
                                                                                   │  multiphase core, PMIC
       clock tree: crystal/XO ─► clock generator ─► PCIe buffer / any-format buffer ─┘  (faults ─► safety MCU)
```

## Notes per reference

### r2 TI cascade imaging radar (TIDEP-01012)
- Four AWR2243 76-81 GHz chips (each 3 TX / 4 RX, on-chip VCO, LO distribution, PA, LNA, ADC) make 12 TX / 16 RX.
  MIMO azimuth array: 86 virtual elements, about 1.4 degrees; elevation 4 virtual elements, about 18 degrees.
- Why: a typical front radar resolves about 5 degrees, so objects closer than 8.5 m at 100 m merge; radar is therefore
  "the secondary sensor" and the car acts only after the camera confirms (their words, short quote). Cascade: objects
  beyond 350 m, 35 cm range resolution, pedestrians at 150 m.
- Master / slave: the master provides the 40 MHz clock, the 20 GHz LO and the digital frame sync to the three slaves.
  The LO goes through two passive Wilkinson dividers; the master also takes its own LO back through the network so
  delays are common. 6 dBm LO outputs make external LO amplifiers unnecessary. Clock and sync distribution use a TI
  LMK00804B low-jitter buffer.
- Data: each chip has a 4-lane CSI-2 transmitter, 600 Mb/s per lane, up to 2.4 Gb/s of ADC data per chip.
- Power: 5 V, 8 A max from the host; two LP87524P-Q1 quad bucks. TMP112 temperature sensors.
- Calibration: path-length matching against frequency mismatch, one-time boresight calibration with a corner reflector
  at 5 m or more (1-2 m² RCS); board-specific calibration recommended.

### r3 ETSI EN 302 264 (77-81 GHz SRR)
- Mean e.i.r.p. density -3 dBm/MHz; peak 55 dBm; out-of-band -30 dBm/MHz; spurious above 1 GHz -30 dBm e.i.r.p.,
  measured up to 162 GHz.
- Receiver: wanted performance with an in-band CW at 55 mV/m (10 dBm e.i.r.p. at 10 m) and out-of-band / remote-band
  signals at fc ± 4 GHz and fc ± 3 x 4 GHz at 173 mV/m (20 dBm e.i.r.p. at 10 m). Sensitivity deliberately not set.
- Installation: fixed position on the vehicle; at most -9 dBm/MHz e.i.r.p. outside the vehicle per radar (so the
  bumper / fascia loss matters). 76-77 GHz long-range radar is under EN 301 091-1 (not read).

### r4 4D radar survey (arXiv 2306.04242)
- 4D = range, azimuth, elevation, velocity. Elevation comes from hardware (cascading standard chips, more antennas per
  chip, metamaterial apertures) or software (virtual aperture as in SAR, learned super-resolution).
- Table I (our summary): 4D radar is high on range, velocity, lighting and weather robustness at moderate cost; lidar
  is very high on resolution but cannot measure velocity, is weather-sensitive and costly; RGB cameras are weak in
  light and weather.
- Data: one K-Radar 4D tensor frame is about 200 MB, so pre-CFAR data transport and real-time processing are limits.
- Trends: learning-based data generation replacing CFAR / beamforming, linear-complexity models over transformers,
  sparse-query perception, "detection by tracking" using Doppler; online extrinsic calibration still lacks robust
  methods. Names Continental ARS548, Oculii Eagle, Arbe, Huawei among 4D radar makers (survey's list).

### r5 Si5332-AM
- AEC-Q100 and AEC-Q006, Grade 2 (-40 to +105 C). 6 / 8 / 12 outputs (QFN32 / 40 / 48), any frequency up to 250 MHz
  (integer to 333.33 MHz), 190 fs RMS, PCIe Gen 1-5, LVDS / LVPECL / HCSL / LVCMOS per output, down and center spread
  0.1-2.5 %. Input crystal 16-50 MHz or clock 10-250 MHz.
- SmartClock: LOS and out-of-frequency (FOOF) outputs to a safety manager or ASIL MCU, input switch-over with external
  control, AlwaysOn within ±5 % if both references fail; fault handling in AN1292 (not read).
- Applications on its front page: ADAS ECUs, automated-driving ECUs, lidar / radar sensors, camera / vision systems,
  gateways, digital cockpit.

### r1 and r6 (reused TI pages)
- r1 subsystems: battery protection; system power; sensor power over the signal line (buck/boost + high-side switch);
  raw-data sensor interface (SerDes deserializers, Ethernet, ESD); object-data interface (Ethernet, CAN, LIN);
  sensor-processing SoC + memory; fusion SoC + memory; processor PMIC; multiphase core supply; safety MCU and safety
  power; vehicle interface; video output (serializer); diagnostics; clocking (oscillator, clock buffer, clock generator).
- r6: battery protection; PMIC (wide-VIN buck, buck, boost, LDO); 60 GHz radar SoC with oscillator, flash and antennas;
  CAN with ESD; supervisor and temperature sensor. Use cases: child presence, occupancy / seat-belt reminder,
  intrusion, driver vital signs.

## Where we sit (catalogue parts only)

- Computer clock tree: Si5332-AM generators, Si52254A / Si52258A-01AM PCIe generators, Si53254A / Si53258A-01AM PCIe
  buffers (Gen 1-6), Si5335x-AM any-format buffers.
- Cascaded radar: the 40 MHz / sync fan-out is a buffer socket (TI uses its own); single-chip radars keep their crystal.
- GNSS for lane-level positioning: SKY5A2110 (L1 + L5). Cabin sensing: QPF5100Q / DW3300Q UWB anchors.
- No radar MMIC: Qorvo's old TGC4702-FC (75-82 GHz IQ mixer) and TGC4703-FC (38 GHz doubler) are discontinued.
- Isolation: no socket found in ADAS (12 V domain, est).

## Not done / left open
- EN 301 091-1 (76-77 GHz), lidar timing, GMSL / A-PHY clocking and AN1292 were not read (document budget).
- Market: only the Yole figure quoted in the clock-tree case; the per-computer clock content is our estimate.
