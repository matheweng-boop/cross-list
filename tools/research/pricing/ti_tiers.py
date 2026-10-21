import json, re, sys, glob
out = {}
pat = re.compile(r'"orderablePartNumber":"([A-Z0-9-]+)".{0,400}?"baseQuantity":"1ku","basePrice":([0-9.]+),"tieredPriceList":(\[[^\]]*\]).{0,120}?"packageQuantity":(\d+),"packageCarrier":"([^"]*)"', re.S)
for f in sorted(glob.glob(sys.argv[1] + "/ti_*.html")):
    raw = open(f, encoding="utf-8", errors="replace").read()
    for m in pat.finditer(raw):
        mpn = m.group(1)
        if mpn in out:
            continue
        tiers = json.loads(m.group(3))
        out[mpn] = {"breaks": [[t["rangeFrom"], t["price"]] for t in tiers], "price_1ku": float(m.group(2)),
                    "reel": int(m.group(4)), "carrier": m.group(5), "page": "https://www.ti.com/product/" + f.rsplit("/ti_", 1)[1][:-5]}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(len(out))
for k, v in list(out.items())[:8]: print(k, v["breaks"], v["reel"], v["carrier"])
