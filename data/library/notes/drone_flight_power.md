# Drone flight control, ESC motor drives and battery power (deep dive, key `drone_flight_power`)

Researched 2026-10-24 (owner, 24 Oct 2026: "do a deep dive for Drones as well"). The summaries are our own wording.
The YAML for the app is in `drone_flight_power.yaml`.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | TI TIDUCF1, High-Speed Sensorless-FOC Reference Design for Drone ESCs (Dec 2016) | Sections 1.1-2.1 (system, key specs, power stage, sensing), skimmed test results |
| r2 | TI TIDA-00916 tool page | Overview, features, parts list, related designs |
| r3 | MIT 6.622 Lecture 38, gate drive and layout | Reused from the traction deep dive (read 21 Oct 2026) |
| r4 | Skyworks Si823x data sheet 206326B | Reused through data/real/skyworks_si823x.yaml (transcribed 19 Oct 2026) |
| r5 | Qorvo PAC5527 / PAC5532B / ACT72350 / PAC25140 catalogue entries | Our catalogue (store.qorvo.com listings, 19 Oct 2026); qorvo.com data sheets NOT read |
| r6 | 14 CFR 89.310 (Cornell LII) | Full section |

## Key numbers taken

- r1 Table 1: input 4.4-45 V (2-6 LiPo cells "or more"), PWM 45 kHz or higher (tested to 60 kHz), current loop and
  observer 22.5 kHz, current-loop bandwidth 2.5 kHz, speed -12 to +12 kRPM, acceleration up to 86 kRPM/s.
- r1 2.1.2: DRV8305 + six CSD18540Q5B (60 V, 1.8 mOhm), 15 A RMS / 20 A peak; up to 500 W in the motor (1.2.1).
- r1 2.1.3: seven sensed signals (four voltages, three currents, low-side shunts, amplifiers inside DRV8305).
- r1 1.1.2: low-end drones use brushed or open-loop trapezoidal motors, mid-range closed-loop trapezoidal, high-end
  sinusoidal; trend from trapezoidal to sinusoidal, so sensorless control matters.
- r6: self-test, take-off interlock, 1 s latency, 1 message/s, 100 ft / 150 ft / 15 ft accuracy.

## Our reasoning (est)

- 4.2 V per full LiPo cell: 6S 25.2 V, 10S 42 V, 12S 50.4 V, 14S 58.8 V; a 48 V-input controller therefore fits up to
  about 10S, PAC52710 (70 V) fits 14S with thin margin, PAC5532B / ACT72350 (160 V) fit 12S-14S and above.
- Gate-drive power example 50 nC x 10 V x 60 kHz = 30 mW per FET.
- No isolation needed below about 60 V DC (SELV); isolation becomes relevant for hybrid / tethered drones and eVTOL.
- Market rows are judgement: no public market figures were read.

## Not read / blocked

- FAA "drones by the numbers" page returned 404 (24 Oct 2026).
- qorvo.com (bot check since 19 Oct 2026): PAC data sheets not read; only store listings.
- No drone inrush / anti-spark application note read.
