# Gate-driver real data: shared conventions

Files: `data/real/skyworks_si823x.yaml` (reference) and `data/real/ti_gate_drivers.yaml` (competitor), same layout
as `data/real/skyworks_si86.yaml` (manufacturers, packages, datasheets, parts). `family: gate_driver`.
Parameters are the keys in `rules/gate_driver.yaml`. Only values the datasheet states; omit a key otherwise and
record the page in `param_sources`.

## Vocabulary (use exactly these strings so both manufacturers compare)
- `channel_config`: `dual` (two isolated outputs), `single`.
- `input_type`: `dual input` (one input per channel: INA/INB or VIA/VIB), `PWM input` (one PWM input generating
  high/low-side outputs), `PWM + dual input` if the datasheet offers both on one part.
  Single-channel drivers: `single input` (one logic input, e.g. VI with EN/DIS, VI+/VI-, IN+/IN-), or
  `LED emulator` for optocoupler-compatible inputs (anode/cathode, driven by forward current). Use exactly these
  strings for every vendor (not `opto-compatible input`).
- Peak currents: state the test condition you used in the file header (e.g. the VDD = 18 V row) when a datasheet
  gives several.
- `deadtime`: `programmable` (DT pin / resistor), `fixed`, `none`.
- `protection`: a list from `UVLO`, `overlap protection`, `disable`, `enable`, `programmable dead time`,
  `input glitch filter`, `Miller clamp`, `desaturation`, `overcurrent` (an OC-pin short-circuit detector that is not
  DESAT), `soft shutdown`.
- `isolation_class`: `basic` or `reinforced`.
- `qualification`: `automotive` (AEC-Q100 stated for that ordering code), else `industrial`.
- `uvlo_v`: the output-side UVLO rising threshold as a number in V (e.g. 5, 8, 12), from the ordering code.
- `peak_source_a`, `peak_sink_a`: typical peak currents in A. `cmti_kv_us`: minimum CMTI.
- `isolation_rating_kvrms`, `creepage_mm` (package creepage), `output_supply_v` [min, max], `prop_delay_ns` (max),
  `temp_range_c` [min, max], `theta_ja_c_w`, `iq_ma`, `rise_time_ns`, `fall_time_ns`, `pwd_ns` (max).

## Packages
- One package entry per distinct body. Leadless packages (LGA): `span_mm` = body width (no leads),
  `exposed_pad: false` unless there is a thermal pad.
- When a package leaves pin positions empty (e.g. a 13-pin LGA on a 14-position grid), set
  `positions_total` to the number of positions and `pin_positions` to the position of each numbered pin, in pin
  order. The pinout then lists only the real pins, in pin-number order. State in `notes` which position is empty and
  where that is in the datasheet.
- Codes must be unique across all files: prefix LGA codes with the vendor package name, e.g. `LGA-14 (5x5)` for
  Skyworks and `LGA-13 NPL (5x5)` for TI, unless the bodies are identical.
- Pin names exactly as in the datasheet; NC pins as `NC`.

Also add the package's land pattern / pad data to `data/mechanical.yaml` style in a new file
`data/mechanical_si823x.yaml` (Skyworks) or `data/mechanical_ti_gate_drivers.yaml` (TI), format as in `data/mechanical.yaml` (see its header, and `data/mechanical_skyworks_switches.yaml` for LGA/QFN-style pads), when the datasheet gives it.
