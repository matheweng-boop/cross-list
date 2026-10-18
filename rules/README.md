# Matching rules

One YAML file per product family. Each parameter has:

| field | meaning |
|---|---|
| `key` | parameter id used in the data files |
| `label`, `unit` | display text |
| `priority` | 1 = must match, 2 = should match, 3 = informative |
| `kind` | `number`, `range` (`[min, max]`), `category`, `set` (list), `ordinal`, `bool` |
| `direction` | `number`: `higher` or `lower` is better. `bool`: `true_better` or `match` |
| `levels` | `ordinal` only: ordered worst → best |
| `tolerance` | `number`/`range`: relative difference still treated as equal (default 0.02) |
| `exclude` | `set` only: items shown but ignored when comparing (e.g. TUV) |
| `from` | derived `bool`: `{param: certifications, contains: TUV}` is true when that set contains the item |
| `hard` | defines the function: any mismatch means a different part, which is not listed at all |
| `must_meet` | one-way requirement: a candidate below the reference (or without a value) is not listed; a better one is fine. Used for the automotive grade: an AEC-Q100 reference only gets AEC-Q100 candidates |

Edit a file and restart the app to apply changes.
