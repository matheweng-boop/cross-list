# Drone cellular link for BVLOS (deep dive, key `drone_cellular`)

Researched 2026-10-24. The summaries are our own wording. The YAML for the app is in `drone_cellular.yaml`.

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | arXiv:1804.02217, Zeng, Lyu, Zhang, Cellular-Connected UAV (2018) | Sections I-IV (requirements, spectrum, design considerations, technologies, simulation setup) |
| r2 | arXiv:2203.05634, RedCap overview (2022) | Reused from the TCU deep dive (read 21 Oct 2026) |
| r3 | arXiv:2412.16611, NTN tutorial (2024) | Reused from the TCU deep dive (read 21 Oct 2026) |
| r4 | Skyworks SKY55951-11 data sheet 205521I | Table 4 rejection and B13 notch |
| r5 | Skyworks SKY68040-11 product summary 206676B | Reused download from 20 Oct 2026 (first page) |
| r6 | FAA Remote ID page | Ways to comply |

## Key points taken

- r1 II-A: CNPC hundreds of kbps, ultra-reliable, secure, low latency; payload FHD several Mbps, 4K > 30 Mbps.
- r1 II-B: ICAO wants CNPC in protected aviation spectrum; WRC-12 made 5030-5091 MHz available for UAV CNPC;
  cellular spectrum can carry payload if aerial-ground interference is controlled.
- r1 III: base-station antennas tilt down; Qualcomm field measurements show satisfactory sidelobe coverage below
  120 m; LoS-dominated channels give strong downlink interference from many cells and an "exposed BS" uplink problem.
- r1 IV: directional antennas, 3D beamforming, multi-cell cooperation, NOMA.
- r5: LTE-M / NB-IoT low and mid bands plus B24 / n255 and B23 / n256, 2.8-4.2 V, 48 % efficiency, coupler.

## Not read / blocked

- 3GPP TR 36.777 (LTE aerial vehicles): the ETSI copy (TR 136 777 V15.0.0) returned 404 on 24 Oct 2026.
- Operator drone subscriptions, GSMA SGP.32 (IoT eSIM): not read; eSIM rule marked low confidence.
- Qualcomm public material: not used (www.qualcomm.com is not requested).
