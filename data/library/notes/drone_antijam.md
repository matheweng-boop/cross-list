# Drone anti-jamming and anti-spoofing (deep dive, key `drone_antijam`)

Researched 2026-11-02. Business and component level only: no jamming or spoofing methods. The YAML for the app is in
`drone_antijam.yaml`.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | 47 USC 333 (willful or malicious interference), Cornell LII | New, 2 Nov 2026 |
| r2 | Kazim, Darwich, Marais, arXiv 2602.12688 | Reused (automotive GNSS deep dive) |
| r3 | Skyworks SKY55951-11 data sheet 205521I | Reused (drone radio-links deep dive) |
| r4 | ETSI EN 303 413 V1.2.1 | Reused (automotive GNSS deep dive) |
| r5 | 47 CFR 15.247 | Reused (drone radio-links deep dive) |
| r6 | Steer, Microwave and RF Design IV, ch. 4 | Reused (roof coexistence deep dive) |

## Reasoning marked est

- CRPA: N elements null up to about N-1 interferers (standard adaptive-array result, not read in a source here).
- Spoofing checks (multi-constellation consistency, IMU cross-check, OSNMA): public practice, not read in a primary
  source in this run.
- Market split and content per drone: our estimates.

## Not read / blocked

- www.gps.gov/spectrum/jamming returned 404 (page moved); not searched further.
- EASA / FAA GNSS-interference guidance for drones not read; export control on CRPA not checked.
