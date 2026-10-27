# Matching rules

One YAML file per product family. Each parameter has:

| field | meaning |
|---|---|
| `key` | parameter id used in the data files |
| `label`, `unit` | display text |
| `priority` | 1 = must match, 2 = should match, 3 = informative |
| `kind` | `number`, `range` (`[min, max]`), `category`, `set` (list), `ordinal`, `bool`, `curve` (`[[condition, value], ...]`, shown only) |
| `direction` | `number`: `higher` or `lower` is better, or `match` (neither is better: outside the tolerance the value differs). `bool`: `true_better` or `match` |
| `levels` | `ordinal` only: ordered worst → best |
| `tolerance` | `number`/`range`: relative difference still treated as equal (default 0.02) |
| `exclude` | `set` only: items shown but ignored when comparing (e.g. TUV) |
| `from` | derived `bool`: `{param: certifications, contains: TUV}` is true when that set contains the item |
| `hard` | defines the function: any mismatch means a different part, which is not listed at all |
| `default` | value assumed for a part that states none, e.g. `cmos` input for ordinary isolators, so only the exceptions need the parameter |
| `derive` | name of a function in `app/matching/rules.py` (`DERIVE`) that works the value out when a part states none, e.g. `gate_output_config` reads the output option from the pinout |
| `at`, `curve` | `number`: the parameter holding the value's test condition (e.g. `peak_current_vdd_v`) and a `curve` parameter with the value at other conditions. Two parts stated at different conditions are compared at one: the part with a curve covering the other's condition is read off it there |
| `x_unit` | `curve` only: unit of the condition |
| `unknown_ok` | an unknown value (stated by neither part, not derivable) is shown as unknown but not counted as a deviation |
| `must_meet` | one-way requirement: a candidate below the reference (or without a value) is not listed; a better one is fine. Used for the automotive grade: an AEC-Q100 reference only gets AEC-Q100 candidates |

Edit a file and restart the app to apply changes.

Rules that live in code rather than in these files:

- **Both Skyworks isolator families** (owner, 27 Oct 2026: "always offer both families if both families are
  available"). When the parts offered for a cross are all Si86S or all Si86 (non-S), the best suitable part of the
  other family is offered as well (`other_family` in `app/services/crosslist.py`; Cross a list and the part page).

## Shared vocabulary

Category values are compared as text, so every data file must use the same words:

| parameter | values |
|---|---|
| `qualification` | `commercial`, `industrial`, `automotive` (AEC-Q100 only; RF switches that state none count as `industrial`) |
| `isolation_class` | `functional`, `basic`, `reinforced` (functional isolators carry no component insulation standard) |
| `control_interface` (RF switches) | `GPIO` (CMOS logic inputs, with or without decoder), `MIPI` (RFFE), `negative` (direct negative-voltage gate control, GaAs), `none` (PIN-diode switches driven by bias current) |
| `output_config` (gate drivers) | `split output` (OUTH / OUTL, VO+ / VO-), `Miller clamp` (one output plus a clamp pin), `split output + Miller clamp`, `UVLO to GND2` (one output, UVLO referred to a GND2 pin: TI UCC53x0E), `single output` (one output per channel, no clamp pin) (Novosense NSI6601S, with OUT and OUTF for two slew rates, counts as `single output` on its standard OUT: owner, 22 Oct 2026) |
| `uvlo_v` (gate drivers) | the option class (8, 12 V) or the rising threshold; values within 6 % count as the same variant |
| `default_output` (digital isolators) | `low`, `high`; `n/a` for LED-emulator inputs, which have no input-side supply |
| `function_type` (timing) | `clock_generator`, `jitter_attenuator`, `clock_buffer`, `pcie_buffer`, `crystal_oscillator` (the block-diagram function ids; a timing part fills the function it names) |
| `output_formats` (timing) | `LVPECL`, `LVDS`, `HCSL` (LP-HCSL and HCSL-fast too), `CML`, `LVCMOS` (dual CMOS too); vendor variants such as AC-LVPECL or LVDS-like are written as the plain format |
| `pcie_gen` (timing) | `none` (no PCIe compliance stated), `gen1` … `gen7`: the highest generation the datasheet states |
