# Robotics in Europe (deep dive, key `robotics_europe`)

Researched 2026-11-02 (owner, 3 Nov 2026 request: "For Factory automation, something for robotics would be good. Focus
on a Euro-centric view for this."). The summaries are our own wording. The YAML for the app is in
`robotics_europe.yaml`; the three new block diagrams are at the end of `data/blocks/templates.yaml`, and the
sub-system is "Robotics (European view)" under Industrial & energy in `data/blocks/systems.yaml`.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | IFR press release "Five Million Robots now Operate in Factories Globally" (World Robotics 2026, 24 Sep 2026) | Full page |
| r2 | IFR press release on the EU-27 (World Robotics 2026, PDF) | Full text |
| r3 | IFR press releases index page | Headlines and teasers, press photo captions |
| r4 | European Commission, DG GROW: Machinery page | Full page |
| r5 | European Commission: Cyber Resilience Act policy page | Full page |
| r6 | Skyworks product entries in data/catalog/skyworks_parts.yaml | Reused (collected 19 Oct 2026) |

Five new public documents were read (r1-r5), one request at a time with robots.txt first (ifr.org,
single-market-economy.ec.europa.eu, digital-strategy.ec.europa.eu all allow these paths). eur-lex.europa.eu is marked
blocked in data/library/sources.yaml (bot check) and was not requested; iso.org is blocked, so ISO 10218, ISO/TS 15066
and EN ISO 13849 were not read.

## Key numbers taken

- r1: global operational stock 5 million (+9%) in 2025; more than 600,000 installations (+11%); China 354,000 (59%);
  US about 38,500; Japan 36,219; Germany fifth worldwide, 41% of EU installations, fewer than 25,000 (-8%), CAGR 2%
  2020-2025; Italy about 7,800 (-11%); France almost 4,500 (-8%); Spain about 4,300 (-15%); forecast 655,000 in
  2026 and 806,000 in 2029; reshoring, labour shortage, AI, machine vision and easier programming as drivers.
- r2: EU-27 stock 712,000 (390,000 in 2015), 84% of Europe; EU installations 60,500 (-11%), CAGR 3% 2020-2025; Asia
  457,315 (+14%), Americas 57,044 (+14%); automotive 14,900 (-25%), metal 13,000 (-13%), plastics and chemicals
  7,400 (-3%), food and beverage 5,300 (+4%); Germany 24,800 (41%, automotive 23%, metal 21%); Italy 7,800 (13%, metal
  29%); France 4,500 (7%, automotive 21%, metal 18%); Spain 4,300 (7%, automotive 43%); OECD expects weak EU economy
  until 2027; Chinese suppliers set up European distribution hubs.
- r3: professional service robots +24% to almost 250,000 units in 2025, transport and logistics about 117,000 the top
  application; IFR press photos show NEURA Robotics humanoids in automotive assembly; IFR vice president Adrien
  Brouillard heads Stäubli's robotics division; IERA award 2026 to Verity (Switzerland) for warehouse drones.
- r4: Machinery Regulation (EU) 2023/1230 adopted 14 June 2023, mandatory from 20 January 2027; aligned with the New
  Legislative Framework; covers AI-powered safety functions, cyber-safety of compliance-relevant software and data and
  safety control systems, conformity assessment of higher-risk machinery, digital instructions and declaration of
  conformity; machinery placed on the market before 20 January 2027 under Directive 2006/42/EC.
- r5: CRA (Regulation (EU) 2024/2847) in force 10 Dec 2024; reporting obligations from 11 Sep 2026; main obligations
  from 11 Dec 2027; CE marking; some products need a notified body; guidance published 27 Jul 2026.

## Our reasoning (est)

- Ownership and locations of robot makers (KUKA owned by Midea since 2017, Universal Robots by Teradyne, Franka part
  of Agile Robots, the announced sale of ABB Robotics to SoftBank, NEURA 4NE-1) are general knowledge, not read here.
- EU AI Act: AI used as a safety component of a product under the Machinery Regulation is expected to be high-risk;
  the dates (August 2027) and any delay by the Digital Omnibus were not read.
- ISO 10218-1 / -2:2025 is understood to fold in the content of ISO/TS 15066; not read.
- Fieldbus preferences (EtherCAT for motion, PROFINET for Siemens-led plants, IO-Link for the last metre, SPE /
  10BASE-T1L, TSN IEC/IEEE 60802) are general knowledge; ethercat.org and io-link.com were not read to keep within the
  five-document limit.
- Socket value: USD 15-25 per servo axis (gate drivers, isolated current sense, isolators), USD 100-150 per six-axis
  robot, times 60,500 EU installations = about USD 6-9 million a year. Robots pull a much larger servo-drive, PLC and
  AMR market with the same parts.
