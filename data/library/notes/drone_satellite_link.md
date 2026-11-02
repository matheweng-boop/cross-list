# Drone satellite link: NTN, direct-to-cell, satellite modems (deep dive, key `drone_satellite_link`)

Researched 2026-11-02. The summaries are our own wording. The YAML for the app is in `drone_satellite_link.yaml`.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | 3GPP NTN technology page (J. Krause, MCC) | New, 2 Nov 2026: orbits, payloads, Rel-15 to Rel-19, bands n254 / n255 / n256, GNSS pre-compensation |
| r2 | 3GPP TS 38.101-5 V19.6.0 | Reused from the TCU deep dive (read 21 Oct 2026) |
| r3 | 5GAA NTN technical report v1.0 | Reused from the TCU deep dive (read 20 Oct 2026) |
| r4 | 47 CFR 25.125 (SCS), Cornell LII | New, 2 Nov 2026: lease with terrestrial licensee, certification under Parts 22 / 24 / 27 |
| r5 | Skyworks SKY68040-11 product summary 206676B | Reused from the drone cellular deep dive |
| r6 | 47 CFR 22.925 (airborne cellular), Cornell LII | New, 2 Nov 2026: cellular telephones must not be operated while airborne |

## Key points taken

- r1: LEO 500-2000 km, GEO 35 786 km; GEO delay up to a few hundred ms; transparent vs regenerative payload;
  Rel-17 first normative NTN (ASN.1 frozen June 2022), IoT-NTN (NB-IoT / eMTC); n255 (L) and n256 (S), 30 MHz
  channels added later; Rel-18 band n254 (UE transmits 1610-1626.5 MHz, satellite 2483.5-2500 MHz); Rel-19 RedCap over
  NTN, regenerative payload, store and forward. NTN UEs are GNSS-capable and pre-compensate TA and Doppler.
- r4: SCS applicant must lease from the terrestrial licensee(s) holding all co-channel licences in the GIA; SCS earth
  stations are licensed by rule and certified under Part 22, 24 or 27.
- r6: "Cellular telephones installed in or carried aboard airplanes, balloons or any other type of aircraft must not be
  operated while such aircraft are airborne."
- Link-budget arithmetic (ours, est): FSPL = 20 log(4 pi d / lambda); 1.6 GHz, 1100 km about 157 dB; 38 000 km about
  188 dB.

## Not read / blocked

- docs.fcc.gov returned 403 on robots.txt (2 Nov 2026): host stopped; the SCS Report and Order and the band list in
  47 CFR 2.106(d)(33)(i) were not read.
- starlink.com/business/direct-to-cell redirects to /business/mobile, which needs JavaScript (no text). AST SpaceMobile
  and Lynk pages not tried (document limit). Their descriptions in the diagram are est.
- 3gpp.org robots.txt disallows the ClaudeBot training crawler by name; our user-directed reader (one page) falls under
  the `*` rules, which allow the page, as in earlier runs.
