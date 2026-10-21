# Price-curve scripts (price model, data/business/price_model.yaml)

Run on pages saved by `tools/research/fetch.sh` (downloads are untrusted: run with `python3 -I`, paths as arguments).

- `ti_tiers.py DIR OUT.json`: TI store price tiers (1 / 100 / 250 / 1000+) of every orderable part on saved ti.com product pages.
- `mc_prices.py DIR OUT.json`: Mini-Circuits web-store price tables on saved minicircuits.com pages.
- `scaling.py MC.json`: checks of the scaling equation P(V) = P_last * (V / q_last) ** s (TI and Mini-Circuits slopes,
  hold-out predictions); the results go into `validation:` in price_model.yaml.
