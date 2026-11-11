# Car radio (deep dive, key `car_radio`)

Researched 2026-11-11 (weekly deep dive, Automotive > Car radio). The summaries are our own wording, with short quotes
only. The YAML for the app is in `car_radio.yaml`; the sub-system's block diagrams are in `data/blocks/templates.yaml`
(Automotive > Car radio: Car radio tuner system; TI head unit with radio tuner; NXP connected radio).

## References (6)

| id | Document | Read |
|---|---|---|
| r1 | Skyworks Si47961-62 data short, Rev. 1.3 (Dec 2021) | Cached copy in var/broadcast (the Broadcast configurator's source): feature list, bands, interfaces, supplies, package, AEC-Q100 |
| r2 | Skyworks Si469xx/xxC product summary 206592E (Dec 2025) | Cached copy in var/broadcast: features per standard, general features, sample rates, applications |
| r3 | Skyworks AMIC brochure (2023) | New request 11 Nov 2026: both pages |
| r4 | ETSI EN 303 345-3 V1.1.1 (2021-06), FM broadcast sound receivers | New request 11 Nov 2026: clauses 1, 4.1-4.4 (tables 1-4), annex C (why each test is or is not included) |
| r5 | WorldDAB in-car DAB user experience design guidelines, Version 2 (Feb 2019) | New request 11 Nov 2026: background, guiding principles, guidelines 5.1-5.6 with their hardware references, section 7 (performance), glossary |
| r6 | Hirschmann Car Communication off-the-shelf remote tuner module flyer (04-2024) | New request 11 Nov 2026: both pages (it was read once before for the radio-tuner-next background notes) |

Reused without a new request: the radio-tuner-next case and its background notes (market, competitors, prices,
software radio, remote tuner modules), the radio-auto-fit report (which parts are automotive), the Broadcast
configurator data (data/broadcast: device shorts, guidance, tuner features), the Si47971-72 data short in
var/broadcast, the engineering note phys_stereo_separation and the tuner deck content (app/services/tuner_deck.py).
Not used: AN851 (Si468x layout guide) in var/broadcast, because one of its schematic pages carries an NDA marking.

## Key numbers taken

- r4 table 2: FM sensitivity -90 dBm conducted (external antenna) or 50 dBµV/m radiated (67 dBµV/m with an integral
  antenna) at 98 MHz, for audio SNR >= 40 dB with no clicks over 10 s.
- r4 tables 3-4: adjacent channels at +/-N x 100 kHz (N = 2, 3, 4) and blocking at +/-800 kHz. External antenna,
  wanted -84 dBm: I/C +3, +17, +30 dB; blocking +30 dB. Integral antenna (wanted 56 dBµV/m): -15, -3, +8 dB; blocking
  +20 dB. The unwanted FM carries weighted noise at 15.9 kHz RMS deviation; the blocker is AM, 80 % depth.
- r4 4.4: conducted spurious emissions at the RF port to EN 55032 clause 13.4 for car radios (13.3 for others).
- r4 annex C: no spurious-response or co-channel test (the sensitivity test covers co-channel; spurious responses
  depend on the architecture).
- r1: FM 64-108 MHz, AM 520-1710 kHz, LW 144-288 kHz, SW 2.3-30 MHz, DAB 168-240 MHz (Si47962), NOAA; FM phase
  diversity and HD/DAB MRC with two tuners; two ZIF I/Q outputs; active buffers for background/data tuners; three I2S
  ports; 3.3 V analog, 1.8 V digital, 1.8 or 3.3 V I/O; QFN-56 8 x 8 mm; AEC-Q100 for A-grade parts.
- r2: 2-4 channel coprocessors per standard (x1 HD Radio, x2 DAB, x3 CDR, x4 DRM, 99 multistandard); seamless linking of
  up to four streams (FM/DAB/DAB/IP); MRC by software package; DDSI packs data for A2B or a DSP over I2S; three I2S/TDM
  in, two out; Quad-SPI flash with OTA, self-boot, no external RAM; sample rates 744.1875 kS/s (HD), 2.048 MS/s (DAB),
  192 kS/s (DRM); applications include remote tuner modules and smart antennas.
- r3: AMIC uses sideband symmetry to replace one-sided interference; 50 Hz-5 kHz; SINAD 5 dB -> 20 dB in lab tests with
  field-like noise; reacts within 10 ms; software licence on Si4796x, Si4797x and Si4798x; other measures listed: AM
  AGC step compensation, noise blanker, audio compression, servo mitigation.
- r5: 82 % would not buy a car without a radio and 75 % of in-car audio is live radio (survey figures quoted by
  WorldDAB); 4.4 M DAB+ cars sold in 2018; EECC: all new EU car radios digital by end 2020; "dual DAB tuners and a good
  DAB antenna implementation are required"; service following on by default (ETSI TS 103 176), with an importer option
  to turn off DAB-FM linking; non-rooftop antennas named as a performance risk.
- r6: EU / US / Global variants; FM phase diversity, DAB or HD MRC, data tuner, seamless linking in the module; A2B link
  (Ethernet on request) for control, audio, data and firmware update; 9-18 V with reverse-polarity protection; phantom
  supply 8-10 V; antenna diagnosis; 3.2-5 W; -40 to +85 °C full function, reduced to +95 °C; IP5K0; 190 g; 120 x 54 x
  15 mm; dual FAKRA input.

## Our reading (est)

- The EU limits (r4) are a floor that any automotive tuner clears; they matter more for aftermarket and software radios.
- The tuner socket survives software radio, the demodulator socket does not; keep the I/Q sample mode and partners.
- A switching regulator near the tuner should run above the AM band (2 MHz) or be filtered; the ACT4751 fits.

## Requests (11 Nov 2026)

robots.txt first on each host, one request at a time: www.skyworksinc.com (robots + AMIC brochure), www.etsi.org
(robots + EN 303 345-3), www.worlddab.org (robots + UX guidelines v2), hirschmann-car.com (robots + RTM flyer).
No host blocked. Four new documents.
