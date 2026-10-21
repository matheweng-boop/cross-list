import json, math, statistics as st, sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[3].as_posix())
from app.services import price_model as pm
ti = {k: [(int(q), p) for q, p in v["breaks"]] for k, v in pm.list_prices().items()}
mc = {k: [tuple(x) for x in v] for k, v in json.load(open(sys.argv[1])).items()}
def seg_slope(pts, lo, hi):
    a = [p for q, p in pts if q == lo]; b = [p for q, p in pts if q == hi]
    return math.log(b[0] / a[0]) / math.log(hi / lo) if a and b else None
def top_slope(pts, qmax=1000):
    """slope of the last segment at or below qmax (the 'upper' part of the curve that we extend)"""
    use = [x for x in pts if x[0] <= qmax]
    (q1, p1), (q2, p2) = use[-2], use[-1]
    return math.log(p2 / p1) / math.log(q2 / q1)
def ext_slope(pts):
    """actual slope beyond 1k (truth for validation)"""
    beyond = [x for x in pts if x[0] > 1000]; base = [x for x in pts if x[0] == 1000]
    if not beyond or not base: return None
    q, p = beyond[-1]; return math.log(p / base[0][1]) / math.log(q / 1000)
print("TI       upper slope (250->1k):", round(st.mean(top_slope(v) for v in ti.values()), 3), "sd", round(st.stdev(top_slope(v) for v in ti.values()), 3), "n", len(ti))
mcu = [top_slope(v) for v in mc.values()]
print("Mini-C.  upper slope (500->1k):", round(st.mean(mcu), 3), "sd", round(st.stdev(mcu), 3), "n", len(mc))
ext = {k: ext_slope(v) for k, v in mc.items() if ext_slope(v) is not None}
print("Mini-C.  actual slope past 1k :", round(st.mean(ext.values()), 3), "sd", round(st.stdev(ext.values()), 3), "n", len(ext))
print("ratio past-1k slope / upper slope (Mini-C.):", round(st.mean(ext[k] / top_slope(mc[k]) for k in ext), 2))
# hold-out: predict the largest Mini-Circuits break from the 1k price with (a) its own upper slope, (b) TI's upper slope, (c) a flat cap -0.08
ti_s = st.mean(top_slope(v) for v in ti.values())
for name, sl in (("own upper slope", None), ("TI upper slope", ti_s), ("old cap -0.08", -0.08)):
    errs = []
    for k in ext:
        pts = mc[k]; p1k = [p for q, p in pts if q == 1000][0]; q, p = [x for x in pts if x[0] > 1000][-1]
        s = top_slope(pts) if sl is None else sl
        errs.append((p1k * (q / 1000) ** s - p) / p * 100)
    print(f"predict top break from 1k with {name:16s}: mean error {st.mean(errs):+.1f} %, mean abs {st.mean(abs(e) for e in errs):.1f} %")
pooled = st.mean(list(ext.values()))
for name, rule in (("0.6 x own upper", lambda pts: 0.6 * top_slope(pts)), ("pooled -0.17", lambda pts: -0.17),
                   ("mean(TI upper, 0.6x own)", lambda pts: (ti_s + 0.6 * top_slope(pts)) / 2)):
    errs = []
    for k in ext:
        pts = mc[k]; p1k = [p for q, p in pts if q == 1000][0]; q, p = [x for x in pts if x[0] > 1000][-1]
        errs.append((p1k * (q / 1000) ** rule(pts) - p) / p * 100)
    print(f"{name:26s}: mean error {st.mean(errs):+.1f} %, mean abs {st.mean(abs(e) for e in errs):.1f} %, worst {max(abs(e) for e in errs):.1f} %")
