import json, re, sys, glob, html
out = {}
for f in sorted(glob.glob(sys.argv[1] + "/mc_*.html")):
    raw = open(f, encoding="utf-8", errors="replace").read()
    i = raw.find('id="model_price_section"')
    if i < 0:
        continue
    seg = raw[i:i + 6000]
    seg = seg[:seg.find("Current Stock")] if "Current Stock" in seg else seg
    cells = [html.unescape(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S)]
    cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
    pairs = []
    for q, p in zip(cells[0::2], cells[1::2]):
        if re.fullmatch(r"\d+", q) and re.fullmatch(r"\$[0-9.,]+", p):
            pairs.append([int(q), float(p[1:].replace(",", ""))])
    m = re.search(r'model=([^"&]+)', raw)
    mpn = f.rsplit("/mc_", 1)[1][:-5] + "+"
    if len(pairs) >= 2:
        out[mpn] = pairs
json.dump(out, open(sys.argv[2], "w"), indent=1)
for k, v in out.items():
    print(k, v)
