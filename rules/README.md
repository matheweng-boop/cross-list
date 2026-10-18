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
| `hard` | a mismatch makes the parts functionally different: excluded from FFF, Upgrade and Downgrade |

Edit a file and restart the app to apply changes.
