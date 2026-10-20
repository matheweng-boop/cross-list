# Matching rules

One YAML file per product family. Each parameter has:

| field | meaning |
|---|---|
| `key` | parameter id used in the data files |
| `label`, `unit` | display text |
| `priority` | 1 = must match, 2 = should match, 3 = informative |
| `kind` | `number`, `range` (`[min, max]`), `category`, `set` (list), `ordinal`, `bool` |
| `direction` | `number`: `higher` or `lower` is better, or `match` (neither is better: outside the tolerance the value differs). `bool`: `true_better` or `match` |
| `levels` | `ordinal` only: ordered worst → best |
| `tolerance` | `number`/`range`: relative difference still treated as equal (default 0.02) |
| `exclude` | `set` only: items shown but ignored when comparing (e.g. TUV) |
| `from` | derived `bool`: `{param: certifications, contains: TUV}` is true when that set contains the item |
| `hard` | defines the function: any mismatch means a different part, which is not listed at all |
| `default` | value assumed for a part that states none, e.g. `cmos` input for ordinary isolators, so only the exceptions need the parameter |
| `must_meet` | one-way requirement: a candidate below the reference (or without a value) is not listed; a better one is fine. Used for the automotive grade: an AEC-Q100 reference only gets AEC-Q100 candidates |

Edit a file and restart the app to apply changes.

## Shared vocabulary

Category values are compared as text, so every data file must use the same words:

| parameter | values |
|---|---|
| `qualification` | `commercial`, `industrial`, `automotive` (AEC-Q100 only; RF switches that state none count as `industrial`) |
| `isolation_class` | `functional`, `basic`, `reinforced` (functional isolators carry no component insulation standard) |
| `control_interface` (RF switches) | `GPIO` (CMOS logic inputs, with or without decoder), `MIPI` (RFFE), `negative` (direct negative-voltage gate control, GaAs), `none` (PIN-diode switches driven by bias current) |
| `uvlo_v` (gate drivers) | the option class (8, 12 V) or the rising threshold; values within 6 % count as the same variant |
| `default_output` (digital isolators) | `low`, `high`; `n/a` for LED-emulator inputs, which have no input-side supply |
