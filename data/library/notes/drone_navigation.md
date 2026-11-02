# Drone navigation: multi-band GNSS, RTK and sensor fusion (deep dive, key `drone_navigation`)

Researched 2026-11-02 from reused sources (no new download). The YAML for the app is in `drone_navigation.yaml`.

## References (6, all reused)

| id | Document | From |
|---|---|---|
| r1 | Skyworks SKY55951-11 data sheet 205521I | drone radio-links deep dive (24 Oct 2026) |
| r2 | u-blox ZED-X20P integration manual R05 | automotive GNSS deep dive (21 Oct 2026) |
| r3 | Vana, Bisnath, NAVIGATION 70(2) 2023 | automotive GNSS deep dive |
| r4 | ETSI EN 303 413 V1.2.1 | automotive GNSS deep dive |
| r5 | 14 CFR 89.310 (Remote ID) | drone radio-links deep dive |
| r6 | Kazim, Darwich, Marais, arXiv 2602.12688 | automotive GNSS deep dive |

## How it splits with the other drone pages

- Navigation (this page): bands, RTK / PPP-RTK, gain window, antenna, Remote ID accuracy, fusion.
- Anti-jamming (`drone_antijam`): deliberate and strong interference, linearity, CRPA, spoofing, resilient link.
- The UWB positioning diagram (MobileKnowledge) is also assigned here for docking and indoor flight.
- Links: /engineering/gnss_how_it_works, /reviews/how/gnss, /visuals#gnssbands (in the knowledge box `drone_gnss_map`).

## Gaps

- No public source read on drone GNSS volumes or who buys the LNA (module maker or drone maker).
- No TCXO in our catalogue; the older Qorvo GPS SAWs (8571xx) and the L5 / L1 diplexer 890086 are discontinued.
