# Data-center cooling and HVAC (deep dive, key `dc_cooling`)

Researched 2026-11-02 (owner, 2 Nov 2026: "Also add cooling and HVAC to data centers"). The summaries are our own
wording. The YAML for the app is in `dc_cooling.yaml`; the four block diagrams are in `data/blocks/templates.yaml`
(Data center > Cooling and HVAC).

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | TI ti.com/solution/liquid-cooling (CDU) | Subsystem list (13 subsystems with product families) and the block-diagram labels |
| r2 | OCP Project Deschutes: Data Center Facilities 1.0.0 (Google, effective 26 Feb 2026) | Sections 2-3 (summary, requirements), 6.1 pump, 7 power and controls, 18.8-18.12 rack power and rear doors, 20.9-20.11 validation |
| r3 | TI ti.com/solution/air-conditioner-outdoor-unit | Subsystem list (13 subsystems) and the block-diagram labels |
| r4 | TI ti.com/solution/fan-card-module | Subsystem list (3 subsystems) and the block-diagram labels |
| r5 | OCP Cooling Environments project page | Sub-project descriptions and the list of contributions |
| r6 | Skyworks AN1456 (data-center creepage and clearance) | Cached copy in var/appnotes, read 30 Oct 2026 for the creepage visual; zones and OVC re-read |

Also reused without a new request: TI ti.com/solution/hvac-motor-control (already in the library as
"HVAC motor control (AC input, PFC + 3-phase inverter) (TI)") and the TI / Infineon reference designs in
data/reference_designs/ (TIDA-010936 48 V GaN inverter tagged "Liquid cooling distribution unit (CDU)", TIDA-01353 EC
motor for HVAC blowers, TIDM-02010 dual motor control with interleaved PFC for HVAC).

## Key numbers taken

- r2 3.1: 2 MW heat load, 500 GPM IT and facility flow, 80-90 psi IT dP, 3 °C approach, 74 kW consumption, pump supply
  380-416 V AC, DI water or PG25.
- r2 3.2 / 6.1 / 7.3: N+1 pumps (37 kW, sealless), each with its own VFD (first source ABB ACH580-31-065A-4, 50 HP,
  power factor 0.98-1.00); leak rope in 3 zones read by the PLC; flow meter ±0.5 % of reading; telemetry of temperature
  and pressure on both sides, flow, pump speed and pump power.
- r2 7.1 / 7.2: 380-416 V three-phase ±10 %, 47-63 Hz, CBEMA ride-through, IEEE 519 (voltage THD < 8 %, < 5 % per
  harmonic, current THD < 20 % from 50 to 100 % load), 10 mA GFCI, 1N feed required and 2N desired, redundant parts
  replaceable in operation, short pins and interlocks; 38 kW at 342 V gives about 64 A, 80 A fuse (100 A max).
- r2 7.2.2: pump speed by fixed pressure difference (default), valve by fixed approach temperature; Modbus TCP over
  IPv4 and IPv6.
- r2 18.8: 90 kW per rack position, four feeds 3+1; 18.12: drip pan with leak detection into the building system for
  rear-door water pipes.
- r1: the CDU's subsystems and TI's part families per subsystem (fan driver with C2000 and GaN, RS-485 + isolators with
  integrated power, hot-swap controllers, temperature / humidity sensors, AFE, HMI).
- r6: OVC II (2500 V) in the white space, OVC III (4000 / 6000 V) on the main distribution, PD2, reinforced clearance
  8.0 mm at 6000 V.

## Our reasoning (est)

- Chillers, CRAC / CRAH units and row CDUs sit on the building's main distribution, so we treat them as OVC III;
  in-rack CDUs and fans as OVC II.
- Affinity laws (fan / pump power roughly with the cube of speed) explain why variable speed matters; not from a source
  read today.
- DESAT, soft shutdown and 100 kV/µs CMTI for SiC compressor inverters are our design judgement.
- The rear-door heat exchanger diagram is drawn by us: OCP describes the door heat exchanger work and Deschutes places
  the doors and their leak detection, but no public electronics diagram was found.
- All market lines are judgement; no market figures were read.

## Not read / not requested

- ASHRAE TC 9.9 thermal guidelines (paid documents; public pages not needed for this pass).
- Immersion-cooling control: no public electronics diagram found, so no separate diagram; covered as a trend.
- Qorvo data sheets for PAC5556 / PAC5253 (qorvo.com is behind a bot check): only our catalogue entries.
