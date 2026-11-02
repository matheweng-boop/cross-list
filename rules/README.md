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
| `unknown_ok` | an unknown value (stated by neither part, not derivable) raises no data gap (amber light) either. No unstated value counts as a deviation (owner, 2 Nov 2026) |
| `must_meet` | one-way requirement: a candidate below the reference (or without a value) is not listed; a better one is fine. Used for the automotive grade: an AEC-Q100 reference only gets AEC-Q100 candidates |
| `downgrade_tier` | a worse value is a downgrade that ranks the candidate below every candidate that is not worse there, whatever else differs (the isolation rating; owner, 2 Nov 2026) |
| `by_supply` | `number`: a curve parameter with the value at lower supplies ([[supply up to V, value], ...]); compared at the design's supply when one is given |
| `steer` | `set` only: items that steer the pick. When the reference has any of them, a candidate with none ranks below every candidate with one (gate drivers: `desaturation`, `overcurrent`, `short-circuit`; owner, 2 Nov 2026) |

Edit a file and restart the app to apply changes.

Rules that live in code rather than in these files:

- **Unstated values** (owner, 2 Nov 2026). A priority 1 value one side does not state never counts as a deviation:
  theirs is shown as "not stated by <maker> (info)", ours as "not stated in our datasheet: check". It still keeps a
  row amber (a missing priority 1 value), and a must-meet grade still has to be stated.

- **Control pins by what they do** (owner, 2 Nov 2026: "pins 7 and 10 (control pins), as one rule"). Pins with a
  role in `data/pin_roles.yaml` (one entry per datasheet pin, with its page: not connected, output enable,
  default-output control, refresh enable, input disable) are compared by role, not by name
  (`app/matching/pinroles.py`). Our NC pin takes any wiring of theirs. Our output enable (pulled up; tied low = outputs
  off) against their default-output control or NC pin is a **conditional fit**: never a drop-in, shown with the note
  "Works if pins 7 and 10 are tied high or left open on the board; tied low, our outputs switch off". Against their
  refresh enable (tied to ground in use) or input disable (opposite polarity) it is a pin mismatch, even with the same
  name. Where their default output follows the board (CTRL pins) and ours ignores those pins, the drop-in names both of
  our default-output variants. On Cross a list a conditional fit shows in the functional column (when the drop-in is
  also the best functional fit, the drop-in family's best conditional fit takes that column).
- **Data rate at the design's supply** (owner, 2 Nov 2026). `by_supply` names a curve parameter of
  [supply up to V, value] pairs (`data_rate_low_vdd`, from the datasheets that give a lower rate at low supply).
  With a supply voltage given on Cross a list or the part page, both parts' rates are read there; without one the
  headline rates are compared and the row notes "their data rate 100 Mbps up to 3 V supply".
- **Nearest part when there is no cross** (owner, 2 Nov 2026, rule 13). When no candidate is within the deviation
  limit, Cross a list keeps the row red and shows the nearest candidate (the usual order, no limit), marked
  "Nearest (not a drop-in): differs in …"; it never counts as a cross. It must pass the function-defining and
  must-meet checks: an AEC-Q100 part never gets an industrial one, not even as nearest.
- **The size of a shortfall counts** (owner, 2 Nov 2026, rule 12). With as many deviations, a candidate that falls
  less short ranks first: a worse number counts log2 of the ratio (2x short = 1, the weight of an option difference
  such as the default output state; a 1 Mbps part for a 150 Mbps socket = 7.2), a worse range its uncovered share.
  It sits after the deviation count (and, on the part page, after "same package" and "pin-to-pin"), below the
  isolation and protection tiers.
- **Ranges compared as numbers, the uncovered part named** (owner, 2 Nov 2026). An isolated amplifier's stated input
  range ("±250 mV", "0.25 to 4.3 V") is read as numbers (`input_range_v`, derived from `input_range`): ours covering
  theirs is fine, a narrower one is a deviation. A priority 1 range deviation says what is not covered ("partial: not
  covered 2.25 to 4.3 V"); for an RF frequency range that starts at 0 it says "DC" ("not covered DC to 0.1, 6 to 18
  GHz"). Whether a candidate covering less than the competitor's main band can still be a functional fit is open (the
  main band is not in the data).
- **Isolated-amplifier sides** (owner, 2 Nov 2026). We and TI number the input (sensing) side 1 / A; a datasheet in
  `data/pin_roles.yaml` `input_side` that numbers it 2 (Analog Devices ADuM3195 / 4195 / 4195-1) has its side-1 and
  side-2 supply and ground pins swapped before the pins are compared.

- **Both Skyworks isolator families** (owner, 27 Oct 2026: "always offer both families if both families are
  available"; "add a third option which shows the family equivalent and same goes if there is a package equivalent
  in another family"). When the parts offered for a cross are all Si86S or all Si86 (non-S), the other family's
  package drop-in, else its best functional fit, is offered as a cross of its own: a third row of the part on Cross
  a list, a result "Other family (package) equivalent" on the part page (`other_family` in
  `app/services/crosslist.py`).

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
