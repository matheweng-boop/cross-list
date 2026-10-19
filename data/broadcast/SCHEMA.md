# Broadcast device files

One YAML file per Skyworks data short / product summary, in `data/broadcast/devices/<document stem>.yaml`.
Everything must come from that document; anything it does not state is left out (or `null`), never guessed.

```yaml
source:
  title: "Si47961-62 Data Short"
  url: "https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-shorts/Si47961-62-short.pdf"
  revision: "Rev. 1.3, December 6, 2021"
family: Si4796x                # family name as the document uses it
description: "High-Performance Automotive Dual AM/FM Radio Receiver and HD Radio/DAB/DAB+/DMB/DRM Tuner"
role: tuner                    # tuner       = RF front end whose digital standards need a coprocessor (I/Q out)
                               # receiver    = single-chip radio that outputs audio by itself (may also decode digital)
                               # coprocessor = digital radio demodulator/decoder fed with I/Q from tuners
package: {type: QFN, pins: 56, body_mm: "8 x 8 x 0.85", pitch_mm: 0.5, epad: true}
aec_q100: true                 # true / false / null when the document does not say
supplies:                      # supply rails as the document states them
  - {pins: [VA1, VA2], volts: "3.3", note: "analog"}
  - {pins: [VD], volts: "1.8", note: "digital"}
  - {pins: [VIO1, VIO2], volts: "1.8 or 3.3", note: "digital I/O"}
features: ["Dual worldwide FM band support (64-108 MHz)", "..."]   # short list, copied from the document
parts:                         # every orderable variant the document distinguishes (standards / licensing)
  - mpn: Si47961
    tuners: 2                  # receive paths (tuner/receiver); null for a coprocessor
    channels: null             # decode channels (coprocessor); null otherwise
    analog: [AM, FM, LW, SW, WB, RDS]     # demodulated on chip. Codes: AM FM LW SW WB(NOAA weather) RDS
    digital_decode: []         # decoded on chip. Codes: HD DAB DMB DRM CDR
    digital_iq: [HD]           # digital standards it can tune and pass as I/Q to a coprocessor
    options: []                # other licensing/feature options, e.g. "Seamless blending (C suffix)", "Audio DSP"
    note: null
  - mpn: Si47962
    ...
pins:                          # EVERY pin of the package in pin-number order, exactly as named in the pinout
  - {n: 1, name: XTALO, fn: xtal}
  - {n: 4, name: FMA, fn: rf_in, band: FM}
  - {n: 40, name: DOUT1, fn: i2s_out, bus: "I2S out 1"}
  - {n: 57, name: GND, fn: ground, note: "exposed pad"}   # exposed pad as an extra pin if the document shows one
```

## Pin functions (`fn`)

| fn | Meaning | Examples |
|---|---|---|
| `power` | supply input (add `volts` if the document gives it) | VA, VD, VIO, VDD |
| `ground` | ground | GND, VSS, exposed pad |
| `bypass` | decoupling / reference / bias pin that takes an external capacitor | DBYP, ABYP, DACREF, AMVAG |
| `xtal` | crystal oscillator pin | XTALI, XTALO |
| `refclk` | reference-clock input | REFCLK, DCLK when used as clock input |
| `clock_out` | clock output to another chip | CLKO |
| `rf_in` | antenna / RF input; add `band`: FM, AM, DAB (Band III), WB, LW, SW, or a slash list | FMA, AMI, B3A |
| `rf_aux` | RF-side helper pin (AGC output, PIN-diode drive, LNA control, tracking filter) | AGC pins, LTA, LTB |
| `iq_out` | digital I/Q (ZIF) output to a coprocessor; set `bus` | ZIFCLK, ZIFFS, ZIFI0, ZIFQ0 |
| `iq_in` | digital I/Q (ZIF) input from a tuner; set `bus` | (coprocessor ZIF inputs) |
| `i2s_out` | digital audio output (data, bit clock, frame sync); set `bus` | DOUT0, DCLK0, DFS0 |
| `i2s_in` | digital audio input; set `bus` | DIN0, DICLK0, DIFS0 |
| `audio_out` | analog audio output | AOUT0, ROUT, LOUT |
| `audio_in` | analog audio input | ICP, ICN, LIN |
| `host` | host control interface (SPI / I2C / UART); set `bus: "Host"` | MOSI/SDA, SCLK/SCL, SSB/A1 |
| `flash` | SPI master to an external NVM / flash; set `bus: "Flash"` | NVMISO, NVMOSI, NVSCLK, NVSSB |
| `memory` | external memory interface (SDRAM etc.); set `bus` | |
| `reset` | reset input | RSTB, RST |
| `interrupt` | interrupt output to host | INTB |
| `gpio` | general purpose I/O | GP0, GPIO1 |
| `mode` | strap / mode-select pin | SMODE |
| `debug` | debug / test | DEBUGP, TEST |
| `nc` | no connect / reserved | NC, RSVD |
| `other` | anything else; explain in `note` | |

`bus` groups pins that belong to one interface so a single click can connect all of them
("I2S out 0", "I2S in 0", "ZIF I/Q", "ZIF I/Q 0", "Host", "Flash", ...). Use the same bus names
the document implies by its pin numbering (DOUT0/DCLK0/DFS0 -> "I2S out 0").
Pins with two functions (e.g. `DCLK/GP0`) keep the full name and get the primary function;
mention the alternate in `note`.
