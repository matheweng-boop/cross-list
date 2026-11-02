// Interactive UWB positioning visuals (owner, 2 Nov 2026: "interactive visuals for the engineering knowledge on
// ultra-wideband, specifically two-way ranging, time difference of arrival, lightweight time difference of arrival, and
// phase difference of arrival ... packed into a single page, along with visuals"). Four visuals, group "UWB":
//   uwbtwr    two-way ranging: animated poll / response / final ladder, single- vs double-sided clock error
//   uwbtdoa   TDoA: floor plan with draggable anchors and tag, hyperbolas, sync-error bands, position spread
//   uwbltdoa  "lightweight TDoA" as we read it (est): what a tag spends per fix and how many tags share the air
//   uwbpdoa   PDoA: two antennas, phase difference, ambiguity above λ/2, angle error against angle, range + angle
// They register with the visuals engine in visuals.js (window.VZ_ADD) for /visuals, and mount themselves on the
// knowledge page /engineering/uwb_positioning (elements with data-uwp="<id>") with the same controls and outputs.
// The maths is in window.VZ_UWBPOS (plain functions, checked by tests/test_uwb_positioning.py). Figures marked est
// are our own simplifications; currents and frame times are the DW3000 datasheet figures on our review page.
(() => {
  const C0 = 299792458;
  const FC = {"5": 6489.6e6, "9": 7987.2e6};  // HRP UWB channel centres (IEEE 802.15.4z), Hz
  const C = {blue: "#1f5fa8", orange: "#c2410c", green: "#2e7d4f", grey: "#8a94a3", purple: "#6b46c1", red: "#b42318", teal: "#0f766e"};
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  const num = (x, d = 3) => (!isFinite(x) ? "–" : Math.abs(x) >= 1e4 || (Math.abs(x) < 1e-3 && x !== 0) ? x.toExponential(d - 1) : (+x.toPrecision(d)).toString());
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const deg = r => (r * 180) / Math.PI, rad = d => (d * Math.PI) / 180;
  const EST = '<span class="kn-est" title="BizDev\'s own reasoning or simplification, not from a source">est</span>';
  const len = m => {  // a length with a sensible unit
    const a = Math.abs(m);
    if (!isFinite(m)) return "–";
    if (a >= 1) return `${num(m)} m`;
    if (a >= 0.01) return `${num(m * 100)} cm`;
    if (a >= 1e-3) return `${num(m * 1000)} mm`;
    if (a >= 1e-6) return `${num(m * 1e6)} µm`;
    return a === 0 ? "0 mm" : "below 1 µm";
  };
  const slen = m => (m > 0 ? "+" : m < 0 ? "−" : "") + len(Math.abs(m));
  const years = h => (h >= 2 * 8766 ? `${num(h / 8766, 2)} years` : h >= 24 * 60 ? `${num(h / 730.5, 2)} months` : `${num(h / 24, 2)} days`);

  // ================================================================ maths (window.VZ_UWBPOS)
  const lambda = fHz => C0 / fHz;

  // Two-way ranging between a tag (initiator, clock 1 + ppmTag) and an anchor (responder, clock 1 + ppmAnchor).
  // reply1: the anchor's true reply time (poll in, response out); reply2: the tag's true reply time before the final.
  function twr({d, reply1, reply2, ppmTag, ppmAnchor}) {
    const tof = d / C0, kA = 1 + ppmTag * 1e-6, kB = 1 + ppmAnchor * 1e-6;
    const Tround1 = kA * (2 * tof + reply1), Treply1 = kB * reply1;  // as each side's own clock counts them
    const Tround2 = kB * (2 * tof + reply2), Treply2 = kA * reply2;
    const ss = (Tround1 - Treply1) / 2;
    const ds = (Tround1 * Tround2 - Treply1 * Treply2) / (Tround1 + Tround2 + Treply1 + Treply2);  // asymmetric DS-TWR
    const avg = (Tround1 - Treply1 + Tround2 - Treply2) / 4;  // the plain (symmetric) double-sided average
    return {
      tof, Tround1, Treply1, Tround2, Treply2, ss, ds, avg,
      errSS: (ss - tof) * C0, errDS: (ds - tof) * C0, errAvg: (avg - tof) * C0,
      // closed forms: SS ≈ e_tag·ToF + (e_tag − e_anchor)·reply1 / 2; DS exactly ToF·(2·kA·kB / (kA + kB) − 1),
      // independent of both reply times; the plain average adds (e_tag − e_anchor)·(reply1 − reply2) / 4
      approxSS: (ppmTag * 1e-6 * tof + ((ppmTag - ppmAnchor) * 1e-6 * reply1) / 2) * C0,
      exactDS: tof * ((2 * kA * kB) / (kA + kB) - 1) * C0,
      approxAvg: (tof * ((kA + kB) / 2 - 1) + ((ppmTag - ppmAnchor) * 1e-6 * (reply1 - reply2)) / 4) * C0,
    };
  }
  const twrMessages = n => ({ss: 2 * n, ds: 3 * n, oneToMany: n + 2});  // per 2-D fix with n anchors

  // TDoA: range differences against anchor 0, their Jacobian, the position covariance and a least-squares solver
  const dist = (p, a) => Math.hypot(p[0] - a[0], p[1] - a[1]);
  const rangeDiffs = (p, A) => A.slice(1).map(a => dist(p, a) - dist(p, A[0]));
  const timeDiffs = (p, A) => rangeDiffs(p, A).map(x => x / C0);
  function tdoaJac(p, A) {
    const u = a => { const r = dist(p, a) || 1e-9; return [(p[0] - a[0]) / r, (p[1] - a[1]) / r]; };
    const u0 = u(A[0]);
    return A.slice(1).map(a => { const ui = u(a); return [ui[0] - u0[0], ui[1] - u0[1]]; });
  }
  // covariance (m²) of the position for an independent timing error of sigma (m, i.e. c·σt) at every anchor; the
  // differences share anchor 0, so R = σ²(I + 11ᵀ) and R⁻¹ = (I − 11ᵀ / (1 + m)) / σ²
  function tdoaCov(p, A, sigma) {
    const H = tdoaJac(p, A), m = H.length;
    let a = 0, b = 0, c = 0;
    for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) {
      const w = (i === j ? 1 : 0) - 1 / (1 + m);
      a += H[i][0] * w * H[j][0]; b += H[i][0] * w * H[j][1]; c += H[i][1] * w * H[j][1];
    }
    const det = a * c - b * b;
    if (!(det > 1e-9)) return null;  // the anchors give no fix here (in a line with the tag)
    const s2 = sigma * sigma;
    return [[(c / det) * s2, (-b / det) * s2], [(-b / det) * s2, (a / det) * s2]];
  }
  function tdoaSolve(A, dd, start) {
    let [x, y] = start;
    for (let it = 0; it < 60; it++) {
      const p = [x, y], f = rangeDiffs(p, A), H = tdoaJac(p, A);
      let a = 0, b = 0, c = 0, u = 0, w = 0;
      H.forEach((h, i) => { const r = dd[i] - f[i]; a += h[0] * h[0]; b += h[0] * h[1]; c += h[1] * h[1]; u += h[0] * r; w += h[1] * r; });
      const det = a * c - b * b;
      if (Math.abs(det) < 1e-12) break;
      const dx = (c * u - b * w) / det, dy = (a * w - b * u) / det;
      x += dx; y += dy;
      if (Math.hypot(dx, dy) < 1e-10) break;
    }
    return {x, y};
  }
  // points p with |p − F2| − |p − F1| = dd (one branch of a hyperbola with foci F1, F2), ordered along the branch
  function hyperbola(F1, F2, dd, reach = 80, n = 120) {
    const ch = dist(F1, F2) / 2;
    if (ch < 1e-9) return [];
    const mx = (F1[0] + F2[0]) / 2, my = (F1[1] + F2[1]) / 2, ux = (F2[0] - F1[0]) / (2 * ch), uy = (F2[1] - F1[1]) / (2 * ch);
    const a = clamp(dd, -2 * ch * 0.9999, 2 * ch * 0.9999) / 2, b = Math.sqrt(Math.max(ch * ch - a * a, 1e-12));
    const T = Math.asinh(reach / b), pts = [];
    for (let i = 0; i <= n; i++) {
      const t = -T + (2 * T * i) / n, x = -a * Math.cosh(t), y = b * Math.sinh(t);
      pts.push([mx + x * ux - y * uy, my + x * uy + y * ux]);
    }
    return pts;
  }
  function ellipse(P) {  // 1-σ axes (m) and the angle of the major axis (degrees, from +x towards +y)
    const [[a, b], [, c]] = P, tr = a + c, det = a * c - b * b, s = Math.sqrt(Math.max(0, (tr * tr) / 4 - det));
    const l1 = tr / 2 + s, l2 = tr / 2 - s;
    return {a: Math.sqrt(Math.max(l1, 0)), b: Math.sqrt(Math.max(l2, 0)), ang: deg(Math.atan2(l1 - a, b || 1e-15))};
  }

  // PDoA: phase difference of a plane wave at two antennas d apart, the angle read back from the wrapped phase and
  // every angle that fits the same wrapped phase (more than one once d > λ/2)
  const wrap = x => { let y = ((x + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI; if (y === -Math.PI && x > 0) y = Math.PI; return y; };
  function pdoa(thetaDeg, dMm, fHz, sigmaPhiDeg = 0) {
    const lam = lambda(fHz), d = dMm / 1000, th = rad(thetaDeg);
    const dphi = (2 * Math.PI * d * Math.sin(th)) / lam, meas = wrap(dphi);
    const est = deg(Math.asin(clamp((meas * lam) / (2 * Math.PI * d), -1, 1)));
    const candidates = [];
    for (let k = -6; k <= 6; k++) {
      const s = ((meas + 2 * Math.PI * k) * lam) / (2 * Math.PI * d);
      if (Math.abs(s) <= 1 + 1e-12) candidates.push(deg(Math.asin(clamp(s, -1, 1))));
    }
    candidates.sort((x, y) => x - y);
    const cos = Math.cos(th), sigmaTheta = deg((rad(sigmaPhiDeg) * lam) / (2 * Math.PI * d * Math.max(Math.abs(cos), 1e-6)));
    return {lam, dphi, meas, est, candidates, ambiguous: candidates.length > 1, unique: d <= lam / 2, sigmaTheta};
  }
  // one anchor: TWR distance r plus angle θ (0 = straight ahead) gives a position; 1-σ error along and across the ray
  const polarFix = (r, thetaDeg, sigmaR, sigmaThetaDeg) => ({x: r * Math.sin(rad(thetaDeg)), y: r * Math.cos(rad(thetaDeg)), along: sigmaR, across: r * rad(sigmaThetaDeg)});

  // tag energy per fix and battery life (est): DW3000 datasheet figures from our review (receive 72 mA on channel 5 and
  // 88 mA on channel 9, frames about 170 µs, about 1 ms start-up, idle on the RC clock 8 mA, deep sleep 260 nA);
  // transmit about 30 mA (est, from 23-35 mA per rail); start-up taken at the RC-clock idle current; host MCU not counted
  const RADIO = {tx: 0.030, rx: {"5": 0.072, "9": 0.088}, wake: 0.008, tWake: 1e-3, guard: 80e-6, sleep: 260e-9, V: 3.0};
  function tagFix(kind, {ch = "9", msg = 170e-6, anchors = 4, listen = 1e-3} = {}) {
    const rxFrame = msg + RADIO.guard;
    let tx = 0, rx = 0;
    if (kind === "twr") { tx = 2 * msg; rx = anchors * rxFrame; }  // poll + final out, one response from each anchor in
    else if (kind === "classic") { tx = msg; rx = listen; }  // listens for its slot or commands, then sends (est)
    else if (kind === "light") { tx = msg; }  // one short blink, never listens
    else if (kind === "dl") { rx = anchors * rxFrame; }  // hears every anchor's message, sends nothing
    const charge = RADIO.wake * RADIO.tWake + RADIO.tx * tx + RADIO.rx[ch] * rx;  // coulombs per fix
    return {tx, rx, charge, energy: charge * RADIO.V};
  }
  function batteryHours(chargePerFix, rateHz, mAh = 220) {
    const iAvg = chargePerFix * rateHz + RADIO.sleep;  // A
    return (mAh / 1000) / iAvg;
  }
  // random (unscheduled) blinks: pure ALOHA, a blink survives if no other starts within ± its own length
  function aloha(tags, rateHz, airtime) {
    const G = tags * rateHz * airtime;
    return {G, success: Math.exp(-2 * G), tags90: Math.log(1 / 0.9) / (2 * rateHz * airtime)};
  }
  const SLOT = 1e-3;  // one scheduled message slot (est)
  const scheduledTags = (rateHz, slotsPerFix = 1) => 1 / (rateHz * slotsPerFix * SLOT);

  window.VZ_UWBPOS = {C0, FC, lambda, twr, twrMessages, rangeDiffs, timeDiffs, tdoaJac, tdoaCov, tdoaSolve, hyperbola, ellipse,
    wrap, pdoa, polarFix, tagFix, batteryHours, aloha, scheduledTags, RADIO};

  // ================================================================ shared bits for the pictures
  const svgOpen = (w, h, label, cls = "", role = "img") => `<svg viewBox="0 0 ${w} ${h}" class="uwp-svg ${cls}" role="${role}" aria-label="${esc(label)}" font-size="13">`;
  const txt = (x, y, s, a = "start", extra = "") => `<text x="${x}" y="${y}" text-anchor="${a}" fill="currentColor" ${extra}>${s}</text>`;
  const arrowDefs = id => `<defs><marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>`;
  const reduced = () => { try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; } };
  let uid = 0;
  const links = `<p class="small">More: <a href="/engineering/uwb_positioning">UWB positioning: TWR, TDoA, lightweight TDoA and PDoA</a> · <a href="/reviews/how/uwb">Part knowledge: UWB</a> · <a href="/visuals#uwb">UWB range, time of flight and first path</a></p>`;
  // pointer position in the SVG's own units
  const svgPoint = (svg, e) => { const m = svg.getScreenCTM(); if (!m) return null; const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse()); return [p.x, p.y]; };

  // ================================================================ 1 · two-way ranging
  function twrLadder(v, r, t) {  // t: animation progress, 0..3 messages (3 = all drawn)
    const W = 600, H = 350, xT = 205, xA = 395, fl = 28, id = `uwpa${++uid}`;
    const sc = x => 34 + 70 * clamp(Math.log10(x / 100e-6) / Math.log10(50), 0, 1);  // 0.1-5 ms of reply → 34-104 px
    const y0 = 62, y1 = y0 + fl, y2 = y1 + sc(v.r1 * 1e-6), y3 = y2 + fl, y4 = y3 + sc(v.r2 * 1e-6), y5 = y4 + fl;
    let s = svgOpen(W, H, "Two-way ranging timing ladder between a tag and an anchor", "uwp-ladder") + arrowDefs(id);
    s += txt(xT, 24, "Tag (starts)", "middle", 'font-weight="600"') + txt(xA, 24, "Anchor", "middle", 'font-weight="600"');
    s += txt(xT, 42, `crystal ${v.ea >= 0 ? "+" : ""}${num(v.ea)} ppm`, "middle", 'font-size="12" opacity=".75"') + txt(xA, 42, `crystal ${v.eb >= 0 ? "+" : ""}${num(v.eb)} ppm`, "middle", 'font-size="12" opacity=".75"');
    s += `<line x1="${xT}" y1="50" x2="${xT}" y2="${y5 + 26}" stroke="currentColor" stroke-width="2" opacity=".6"/><line x1="${xA}" y1="50" x2="${xA}" y2="${y5 + 26}" stroke="currentColor" stroke-width="2" opacity=".6"/>`;
    s += txt(W - 8, y5 + 40, "time runs down · not to scale", "end", 'font-size="11" opacity=".65"');
    const msgs = [["Poll", xT, y0, xA, y1, C.blue], ["Response", xA, y2, xT, y3, C.teal], ["Final", xT, y4, xA, y5, C.purple]];
    msgs.forEach(([lab, xa, ya, xb, yb, col], k) => {
      const f = clamp(t - k, 0, 1), g = clamp(f / 0.6, 0, 1);  // 60 % of each step in flight, 40 % waiting to reply
      if (f <= 0) return;
      const xe = xa + (xb - xa) * g, ye = ya + (yb - ya) * g;
      s += `<line x1="${xa}" y1="${ya}" x2="${xe}" y2="${ye}" stroke="${col}" stroke-width="2.5"${g >= 1 ? ` marker-end="url(#${id})"` : ""} style="color:${col}"/>`;
      s += txt((xa + xb) / 2, (ya + yb) / 2 - 7, lab, "middle", `font-weight="600" fill="${col}" style="fill:${col}"`);
      if (g < 1) s += `<circle cx="${xe}" cy="${ye}" r="6" fill="${col}"/>`;
    });
    const stamp = (x, y, lab, side) => `<circle cx="${x}" cy="${y}" r="3.5" fill="currentColor"/>` + txt(x + (side < 0 ? -8 : 8), y + 4, lab, side < 0 ? "end" : "start", 'font-size="12"');
    if (t > 0) s += stamp(xT, y0, "t1", -1);
    if (t >= 0.6) s += stamp(xA, y1, "t2", 1);
    if (t >= 1) s += stamp(xA, y2, "t3", 1);
    if (t >= 1.6) s += stamp(xT, y3, "t4", -1);
    if (t >= 2) s += stamp(xT, y4, "t5", -1);
    if (t >= 2.6) s += stamp(xA, y5, "t6", 1);
    const brk = (x, ya, yb, name, val, side, col) => {  // a bracket with its name and value on two lines
      const dx = side * 10, a = side < 0 ? "end" : "start", st = `fill="${col}" style="fill:${col}"`, ym = (ya + yb) / 2;
      return `<path d="M${x + dx / 2} ${ya}H${x + dx}V${yb}H${x + dx / 2}" fill="none" stroke="${col}" stroke-width="1.6"/>`
        + txt(x + dx + side * 6, ym - 9, `T<tspan baseline-shift="sub" font-size="9">${name}</tspan>`, a, `font-size="13" font-weight="600" ${st}`)
        + txt(x + dx + side * 6, ym + 13, `${(val * 1e6).toFixed(4)} µs`, a, `font-size="12" ${st}`);
    };
    if (t >= 0.6 + 1) s += brk(xT - 34, y0, y3, "round1", r.Tround1, -1, C.blue);
    if (t >= 1) s += brk(xA + 34, y1, y2, "reply1", r.Treply1, 1, C.teal);
    if (t >= 2) s += brk(xT - 34, y3, y4, "reply2", r.Treply2, -1, C.purple);
    if (t >= 2.6) s += brk(xA + 34, y2, y5, "round2", r.Tround2, 1, C.orange);
    if (t >= 1.6) s += txt((xT + xA) / 2, y3 + 18, "single-sided result ready here", "middle", 'font-size="11.5" opacity=".75"');
    if (t >= 2.6) s += txt((xT + xA) / 2, y5 + 20, "double-sided result ready here", "middle", 'font-size="11.5" opacity=".75"');
    return s + "</svg>";
  }
  function twrChart(v) {  // distance error against the anchor's reply time, log-log
    const W = 600, H = 250, x0 = 70, x1 = 585, yT = 16, yB = 200;
    const lx = [50e-6, 10e-3], ly = [1e-4, 10];
    const X = s => x0 + ((Math.log10(s) - Math.log10(lx[0])) / (Math.log10(lx[1]) - Math.log10(lx[0]))) * (x1 - x0);
    const Y = m => yB - ((Math.log10(clamp(m, ly[0], ly[1])) - Math.log10(ly[0])) / (Math.log10(ly[1]) - Math.log10(ly[0]))) * (yB - yT);
    let s = svgOpen(W, H, "Distance error against reply time for single- and double-sided ranging", "uwp-chart");
    s += `<rect x="${x0}" y="${yT}" width="${x1 - x0}" height="${yB - yT}" fill="none" stroke="currentColor" opacity=".25"/>`;
    for (const m of [1e-4, 1e-3, 1e-2, 0.1, 1, 10]) s += `<line x1="${x0}" x2="${x1}" y1="${Y(m)}" y2="${Y(m)}" stroke="currentColor" opacity=".08"/>` + txt(x0 - 6, Y(m) + 4, len(m), "end", 'font-size="11" opacity=".8"');
    for (const sx of [50e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]) s += txt(X(sx), yB + 16, sx < 1e-3 ? `${num(sx * 1e6)} µs` : `${num(sx * 1e3)} ms`, "middle", 'font-size="11" opacity=".8"');
    s += txt((x0 + x1) / 2, yB + 34, "anchor's reply time (log scale)", "middle", 'font-size="12"');
    s += `<line x1="${x0}" x2="${x1}" y1="${Y(0.1)}" y2="${Y(0.1)}" stroke="${C.green}" stroke-dasharray="5 4"/>` + txt(x1 - 4, Y(0.1) - 5, "10 cm: what UWB promises", "end", `font-size="11" fill="${C.green}" style="fill:${C.green}"`);
    const pts = [], n = 60;
    for (let i = 0; i <= n; i++) {
      const rr = 10 ** (Math.log10(lx[0]) + (i / n) * (Math.log10(lx[1]) - Math.log10(lx[0])));
      const e = Math.abs(twr({d: v.d, reply1: rr, reply2: v.r2 * 1e-6, ppmTag: v.ea, ppmAnchor: v.eb}).approxSS);
      pts.push(`${X(rr).toFixed(1)},${Y(e).toFixed(1)}`);
    }
    s += `<polyline points="${pts.join(" ")}" fill="none" stroke="${C.red}" stroke-width="2.5"/>`;
    const cur = twr({d: v.d, reply1: v.r1 * 1e-6, reply2: v.r2 * 1e-6, ppmTag: v.ea, ppmAnchor: v.eb});
    const dsE = Math.abs(cur.exactDS);
    s += `<line x1="${x0}" x2="${x1}" y1="${Y(dsE)}" y2="${Y(dsE)}" stroke="${C.blue}" stroke-width="2.5"/>`;
    s += txt(x0 + 6, Y(Math.abs(cur.approxSS)) > yT + 30 ? yT + 16 : yB - 8, "red: single-sided · blue: double-sided (asymmetric)", "start", 'font-size="11.5"');
    s += `<circle cx="${X(v.r1 * 1e-6)}" cy="${Y(Math.abs(cur.approxSS))}" r="5" fill="${C.red}"/><circle cx="${X(v.r1 * 1e-6)}" cy="${Y(dsE)}" r="5" fill="${C.blue}"/>`;
    if (dsE < ly[0]) s += txt(x1 - 4, yB - 6, "double-sided error below 0.1 mm", "end", `font-size="11" fill="${C.blue}" style="fill:${C.blue}"`);
    return s + "</svg>";
  }
  function twrSetup(S) {
    return (el, rerender) => {
      el.innerHTML = `<div class="uwp-twr"><div class="uwp-ladder-wrap"></div><button type="button" class="small-btn outline uwp-play">▶ Play the exchange</button><div class="uwp-chart-wrap"></div></div>`;
      const lad = el.querySelector(".uwp-ladder-wrap"), chart = el.querySelector(".uwp-chart-wrap"), play = el.querySelector(".uwp-play");
      let t = reduced() ? 3 : 0, raf = 0, last = 0;
      const draw = () => { if (S.v && S.r) { lad.innerHTML = twrLadder(S.v, S.r, t); chart.innerHTML = twrChart(S.v); } };
      const step = now => {
        raf = 0;
        if (!el.isConnected) return;
        const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
        last = now; t = Math.min(3, t + dt / 1.3);
        if (S.v && S.r) lad.innerHTML = twrLadder(S.v, S.r, t);
        if (t < 3) raf = requestAnimationFrame(step); else play.textContent = "▶ Play again";
      };
      const start = () => { t = 0; last = 0; play.textContent = "▶ Playing…"; if (!raf) raf = requestAnimationFrame(step); };
      play.addEventListener("click", start);
      S.redraw = draw;
      if (t < 3) start();
      draw();
    };
  }

  // ================================================================ 2 · TDoA
  const PLAN = {w: 24, h: 14, k: 25, ox: 20, oy: 20};  // metres; px per metre; margins
  const ANCH = [[2, 2], [22, 2], [22, 12], [2, 12]];
  const PAIR = [C.blue, C.teal, C.purple];
  const PX = ([x, y]) => [PLAN.ox + x * PLAN.k, PLAN.oy + y * PLAN.k];
  const rnd = seed => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  function gauss(r) { const u = Math.max(1e-9, r()), w = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * w); }
  function tdoaSvg(S, v) {
    const n = +v.n, A = S.anchors.slice(0, n), p = S.tag, sig = v.sync * 1e-9 * C0, band = sig * Math.SQRT2;
    const W = PLAN.ox * 2 + PLAN.w * PLAN.k, H = PLAN.oy * 2 + PLAN.h * PLAN.k, id = `uwpc${++uid}`, ida = `uwpd${uid}`;
    let s = svgOpen(W, H, `Floor plan with ${n} anchors, the tag and the TDoA hyperbolas`, "uwp-plan", "group") + arrowDefs(ida);
    s += `<defs><clipPath id="${id}"><rect x="${PLAN.ox}" y="${PLAN.oy}" width="${PLAN.w * PLAN.k}" height="${PLAN.h * PLAN.k}"/></clipPath></defs>`;
    s += `<rect class="uwp-floor" x="${PLAN.ox}" y="${PLAN.oy}" width="${PLAN.w * PLAN.k}" height="${PLAN.h * PLAN.k}" rx="6" fill="${C.grey}" fill-opacity=".07" stroke="currentColor" stroke-opacity=".35"/>`;
    for (let x = 2; x < PLAN.w; x += 2) s += `<line x1="${PX([x, 0])[0]}" x2="${PX([x, 0])[0]}" y1="${PLAN.oy}" y2="${PLAN.oy + PLAN.h * PLAN.k}" stroke="currentColor" opacity=".06"/>`;
    for (let y = 2; y < PLAN.h; y += 2) s += `<line y1="${PX([0, y])[1]}" y2="${PX([0, y])[1]}" x1="${PLAN.ox}" x2="${PLAN.ox + PLAN.w * PLAN.k}" stroke="currentColor" opacity=".06"/>`;
    s += txt(PLAN.ox + 4, H - 5, "2 m grid", "start", 'font-size="11" opacity=".7"');
    s += `<g clip-path="url(#${id})">`;
    const path = pts => pts.map(([x, y], i) => `${i ? "L" : "M"}${PX([x, y])[0].toFixed(1)} ${PX([x, y])[1].toFixed(1)}`).join("");
    rangeDiffs(p, A).forEach((dd, i) => {
      const col = PAIR[i % PAIR.length];
      if (band > 0) {
        const lo = hyperbola(A[0], A[i + 1], dd - band), hi = hyperbola(A[0], A[i + 1], dd + band);
        s += `<path d="${path(lo)}${path(hi.reverse()).replace(/^M/, "L")}Z" fill="${col}" fill-opacity=".16" stroke="none"/>`;
      }
      s += `<path d="${path(hyperbola(A[0], A[i + 1], dd))}" fill="none" stroke="${col}" stroke-width="2.2"/>`;
    });
    // position spread: 1-σ ellipse and a cloud of linearised estimates (deterministic noise), drawn MAG times larger
    const P = sig > 0 ? tdoaCov(p, A, sig) : null, MAG = 5, sk = PLAN.k * MAG;
    if (P) {
      const e = ellipse(P), r = rnd(11), [cx, cy] = PX(p);
      const L = [[Math.sqrt(Math.max(P[0][0], 0)), 0], [P[0][1] / (Math.sqrt(Math.max(P[0][0], 1e-30))), 0]];
      L[1][1] = Math.sqrt(Math.max(P[1][1] - L[1][0] ** 2, 0));
      for (let k = 0; k < 140; k++) {
        const z1 = gauss(r), z2 = gauss(r), dx = L[0][0] * z1, dy = L[1][0] * z1 + L[1][1] * z2;
        s += `<circle cx="${(cx + dx * sk).toFixed(1)}" cy="${(cy + dy * sk).toFixed(1)}" r="1.8" fill="${C.orange}" opacity=".5"/>`;
      }
      s += `<ellipse cx="${cx}" cy="${cy}" rx="${Math.max(1, e.a * sk)}" ry="${Math.max(1, e.b * sk)}" transform="rotate(${e.ang.toFixed(1)} ${cx} ${cy})" fill="${C.orange}" fill-opacity=".18" stroke="${C.orange}" stroke-width="2"/>`;
    }
    s += "</g>";
    if (P) s += txt(W - PLAN.ox - 4, H - 5, `orange: position spread, drawn ${MAG}× larger`, "end", `font-size="12" fill="${C.orange}" style="fill:${C.orange}"`);
    // who talks: blinks to the anchors (uplink) or anchor messages to the tag (downlink); sync to anchor 1
    const [tx, ty] = PX(p);
    A.forEach((a, i) => {
      const [ax, ay] = PX(a);
      if (i > 0) s += `<line x1="${PX(A[0])[0]}" y1="${PX(A[0])[1]}" x2="${ax}" y2="${ay}" stroke="currentColor" stroke-dasharray="2 5" opacity=".35"/>`;
      const fx = v.mode === "dl" ? ax : tx, fy = v.mode === "dl" ? ay : ty, gx = v.mode === "dl" ? tx : ax, gy = v.mode === "dl" ? ty : ay;
      const L = Math.hypot(gx - fx, gy - fy) || 1, sh = 16 / L;
      s += `<line x1="${fx + (gx - fx) * sh}" y1="${fy + (gy - fy) * sh}" x2="${gx - (gx - fx) * sh}" y2="${gy - (gy - fy) * sh}" stroke="currentColor" stroke-width="1.2" opacity=".55" stroke-dasharray="6 4" marker-end="url(#${ida})"/>`;
    });
    if (v.mode !== "dl") {  // uplink: anchors report their timestamps to a location server over a backhaul
      const sx = PLAN.ox + PLAN.w * PLAN.k / 2, sy = PLAN.oy + 8;
      A.forEach(a => { const [ax, ay] = PX(a); s += `<line x1="${ax}" y1="${ay}" x2="${sx}" y2="${sy + 14}" stroke="${C.grey}" stroke-width="1" opacity=".6"/>`; });
      s += `<rect x="${sx - 58}" y="${sy}" width="116" height="22" rx="4" fill="${C.grey}" fill-opacity=".25" stroke="currentColor" stroke-opacity=".5"/>` + txt(sx, sy + 15, "location server", "middle", 'font-size="12"');
    }
    A.forEach((a, i) => {
      const [ax, ay] = PX(a), lab = `Anchor ${i + 1}${i === 0 ? " (reference)" : ""}, at ${num(a[0])} m, ${num(a[1])} m. Arrow keys move it.`;
      s += `<g class="uwp-h" data-h="a${i}" tabindex="0" role="button" aria-label="${esc(lab)}"><circle cx="${ax}" cy="${ay}" r="22" fill="transparent"/><rect x="${ax - 13}" y="${ay - 13}" width="26" height="26" rx="4" fill="${i === 0 ? C.green : C.grey}" stroke="currentColor" stroke-width="1.5" class="uwp-ring"/>${txt(ax, ay + 5, `A${i + 1}`, "middle", 'font-size="13" font-weight="700" fill="#fff" style="fill:#fff"')}</g>`;
    });
    const tagLab = `Tag at ${num(p[0])} m, ${num(p[1])} m. Arrow keys move it; tap the plan to place it.`;
    s += `<g class="uwp-h" data-h="tag" tabindex="0" role="button" aria-label="${esc(tagLab)}"><circle cx="${tx}" cy="${ty}" r="24" fill="transparent"/><circle cx="${tx}" cy="${ty}" r="10" fill="${C.red}" stroke="#fff" stroke-width="2" class="uwp-ring"/></g>`;
    s += txt(tx + 14, ty - 12, v.mode === "dl" ? "tag (listens, computes)" : "tag (blinks)", "start", 'font-size="13" font-weight="600" class="uwp-halo"');
    return s + "</svg>";
  }
  function dragSetup(el, svgSel, S, onMove, onKey) {  // pointer drag of [data-h] handles, tap on the plan, arrow keys
    let drag = null, down = null;
    el.addEventListener("pointerdown", e => {
      const svg = el.querySelector(svgSel);
      if (!svg || !svg.contains(e.target)) return;
      const h = e.target.closest("[data-h]");
      if (h) { drag = h.dataset.h; e.preventDefault(); try { el.setPointerCapture(e.pointerId); } catch (err) { /* capture is optional */ } }
      else down = [e.clientX, e.clientY];
    });
    el.addEventListener("pointermove", e => {
      if (!drag) return;
      const svg = el.querySelector(svgSel), pt = svg && svgPoint(svg, e);
      if (pt) onMove(drag, pt);
    });
    const end = e => {
      if (!drag && down && e.type === "pointerup" && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 8) {
        const svg = el.querySelector(svgSel), pt = svg && svg.contains(e.target) && svgPoint(svg, e);
        if (pt) onMove(null, pt);  // a tap on the plan: move the default handle there
      }
      drag = null; down = null;
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("keydown", e => {
      const h = e.target.closest && e.target.closest("[data-h]");
      const d = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key];
      if (!h || !d) return;
      e.preventDefault();
      onKey(h.dataset.h, d, e.shiftKey);
    });
  }
  const refocus = (el, key) => { if (!key) return; const h = el.querySelector(`[data-h="${key}"]`); if (h) h.focus({preventScroll: true}); };
  function tdoaSetupFn(S) {
    return (el, rerender) => {
      S.anchors = ANCH.map(a => a.slice());
      S.tag = [9, 6];
      el.innerHTML = '<div class="uwp-plan-wrap"></div><p class="small muted uwp-hint">Drag the anchors (squares) and the tag (red dot), or tap the plan to move the tag. Keyboard: Tab to a point, then the arrow keys (Shift for 1 m steps).</p>';
      const wrap = el.querySelector(".uwp-plan-wrap");
      S.redraw = () => {
        if (!S.v) return;
        const f = document.activeElement && wrap.contains(document.activeElement) ? document.activeElement.closest("[data-h]") : null;
        wrap.innerHTML = tdoaSvg(S, S.v);
        refocus(wrap, f && f.dataset.h);
      };
      const toM = ([x, y]) => [clamp((x - PLAN.ox) / PLAN.k, 0.3, PLAN.w - 0.3), clamp((y - PLAN.oy) / PLAN.k, 0.3, PLAN.h - 0.3)];
      const set = (key, m) => { if (key === "tag") S.tag = m; else S.anchors[+key.slice(1)] = m; rerender(); };
      dragSetup(el, ".uwp-plan", S, (key, pt) => set(key || "tag", toM(pt)), (key, [dx, dy], big) => {
        const cur = key === "tag" ? S.tag : S.anchors[+key.slice(1)], st = big ? 1 : 0.25;
        set(key, [clamp(cur[0] + dx * st, 0.3, PLAN.w - 0.3), clamp(cur[1] + dy * st, 0.3, PLAN.h - 0.3)]);
      });
      if (S.v) S.redraw();
    };
  }

  // ================================================================ 3 · lightweight TDoA (our reading, est)
  const KINDS = [["twr", "TWR tag"], ["classic", "Classic TDoA tag (est)"], ["light", "Lightweight tag (blink only)"], ["dl", "DL-TDoA tag (listens)"]];
  function lightSvg(v, fixes) {
    const W = 640, rowH = 36, top = 34, left = 210, axisW = 270, tMax = Math.max(6e-3, RADIO.tWake + (v.na + 2) * SLOT, RADIO.tWake + v.listen * 1e-3 + v.msg * 1e-6 + 2e-4);
    const X = s => left + (s / tMax) * axisW;
    const H = top + KINDS.length * rowH + 150;
    let s = svgOpen(W, H, "What each kind of tag does in one position fix, and how blinks share the air", "uwp-light");
    s += txt(left, 18, "one fix: grey wake-up · orange transmit · blue receive", "start", 'font-size="12"') + txt(W - 8, 18, "coin cell (est)", "end", 'font-size="12"');
    KINDS.forEach(([k, lab], i) => {
      const y = top + i * rowH, f = fixes[k], lw = k === "light";
      s += `<rect x="4" y="${y - 2}" width="${W - 8}" height="${rowH - 4}" rx="5" fill="${lw ? C.green : C.grey}" fill-opacity="${lw ? 0.1 : 0.05}"/>`;
      s += txt(10, y + 19, esc(lab), "start", `font-size="12.5"${lw ? ' font-weight="700"' : ""}`);
      s += `<rect x="${X(0)}" y="${y + 6}" width="${X(RADIO.tWake) - X(0)}" height="18" fill="${C.grey}" opacity=".6"/>`;
      const blk = (t0, d, col) => `<rect x="${X(t0)}" y="${y + 6}" width="${Math.max(2, X(t0 + d) - X(t0))}" height="18" fill="${col}"/>`;
      const msg = v.msg * 1e-6, rxf = msg + RADIO.guard, t0 = RADIO.tWake;
      if (k === "twr") { s += blk(t0, msg, C.orange); for (let a = 1; a <= v.na; a++) s += blk(t0 + a * SLOT, rxf, C.blue); s += blk(t0 + (v.na + 1) * SLOT, msg, C.orange); }
      if (k === "classic") { s += blk(t0, v.listen * 1e-3, C.blue); s += blk(t0 + v.listen * 1e-3, msg, C.orange); }
      if (k === "light") s += blk(t0, msg, C.orange);
      if (k === "dl") for (let a = 0; a < v.na; a++) s += blk(t0 + a * SLOT, rxf, C.blue);
      s += txt(W - 8, y + 19, years(batteryHours(f.charge, v.rate)), "end", `font-size="12.5" font-weight="700"`);
    });
    const yA = top + KINDS.length * rowH + 6;
    for (const ms of [0, 2, 4, 6, 8, 10].filter(m => m * 1e-3 <= tMax)) s += txt(X(ms * 1e-3), yA + 8, `${ms} ms`, "middle", 'font-size="11" opacity=".75"');
    // the air for 20 ms: random blinks (lightweight) against scheduled slots (classic)
    const win = 20e-3, aX = 10, aW = W - 20, ax = s2 => aX + (s2 / win) * aW, y1 = yA + 34, y2 = y1 + 50;
    s += txt(aX, y1 - 6, "20 ms of air, lightweight tags: random blinks (red = collided)", "start", 'font-size="12"');
    s += `<rect x="${aX}" y="${y1}" width="${aW}" height="22" fill="none" stroke="currentColor" opacity=".35"/>`;
    const msg = v.msg * 1e-6, expect = v.tags * v.rate * win, K = Math.min(400, Math.round(expect)), r = rnd(5);
    const st = Array.from({length: K}, () => r() * win).sort((a, b) => a - b);
    st.forEach((t0, i) => {
      const hit = (i > 0 && t0 - st[i - 1] < msg) || (i < K - 1 && st[i + 1] - t0 < msg);
      s += `<rect x="${ax(t0)}" y="${y1 + 2}" width="${Math.max(1.5, ax(t0 + msg) - ax(t0))}" height="18" fill="${hit ? C.red : C.orange}" opacity=".85"/>`;
    });
    if (expect > K) s += txt(aX + aW, y1 + 36, `showing 400 of about ${num(expect)} blinks`, "end", 'font-size="11" opacity=".75"');
    s += txt(aX, y2 - 6, "classic tags: one 1 ms slot each, assigned in advance (est)", "start", 'font-size="12"');
    s += `<rect x="${aX}" y="${y2}" width="${aW}" height="22" fill="none" stroke="currentColor" opacity=".35"/>`;
    const used = Math.min(20, Math.round(expect));
    for (let k = 0; k < 20; k++) {
      s += `<line x1="${ax(k * SLOT)}" x2="${ax(k * SLOT)}" y1="${y2}" y2="${y2 + 22}" stroke="currentColor" opacity=".15"/>`;
      if (k < used) s += `<rect x="${ax(k * SLOT + 0.1e-3)}" y="${y2 + 2}" width="${Math.max(1.5, ax(msg) - ax(0))}" height="18" fill="${C.orange}" opacity=".85"/>`;
    }
    if (expect > 20) s += txt(aX + aW, y2 + 36, "slots full: more tags than slots", "end", `font-size="11.5" font-weight="700" fill="${C.red}" style="fill:${C.red}"`);
    return s + "</svg>";
  }

  // ================================================================ 4 · PDoA
  function pdoaSvg(v, q) {
    const W = 600, H = 330, cx = 300, cy = 286, R = 220, dpx = v.d * 4, lam = q.lam * 1000;
    let s = svgOpen(W, H, `Two antennas ${num(v.d)} mm apart and a tag at ${num(v.th)} degrees`, "uwp-pdoa", "group");
    s += `<path d="M${cx - R} ${cy}A${R} ${R} 0 0 1 ${cx + R} ${cy}" fill="none" stroke="currentColor" opacity=".3"/>`;
    for (const a of [-90, -60, -30, 0, 30, 60, 90]) {
      const x = cx + (R + 14) * Math.sin(rad(a)), y = cy - (R + 14) * Math.cos(rad(a));
      s += `<line x1="${cx + (R - 6) * Math.sin(rad(a))}" y1="${cy - (R - 6) * Math.cos(rad(a))}" x2="${cx + R * Math.sin(rad(a))}" y2="${cy - R * Math.cos(rad(a))}" stroke="currentColor" opacity=".4"/>` + txt(x, y + 4, `${a}°`, "middle", 'font-size="11" opacity=".75"');
    }
    s += txt(cx, cy - R - 26, "straight ahead (0°)", "middle", 'font-size="11.5" opacity=".75"');
    // uncertainty wedge
    const sw = clamp(q.sigmaTheta, 0, 89);
    if (v.sp > 0) {
      const a1 = clamp(v.th - sw, -90, 90), a2 = clamp(v.th + sw, -90, 90);
      s += `<path d="M${cx} ${cy}L${cx + R * Math.sin(rad(a1))} ${cy - R * Math.cos(rad(a1))}A${R} ${R} 0 0 1 ${cx + R * Math.sin(rad(a2))} ${cy - R * Math.cos(rad(a2))}Z" fill="${C.orange}" fill-opacity=".16" stroke="${C.orange}" stroke-opacity=".5"/>`;
    }
    // other angles that give the same measured phase (ambiguity)
    q.candidates.filter(a => Math.abs(a - v.th) > 0.5).forEach(a => {
      const x = cx + R * Math.sin(rad(a)), y = cy - R * Math.cos(rad(a));
      s += `<circle cx="${x}" cy="${y}" r="9" fill="none" stroke="${C.red}" stroke-width="2" stroke-dasharray="3 3"/>` + txt(x, y - 14, "also fits", "middle", `font-size="11" fill="${C.red}" style="fill:${C.red}"`);
    });
    // incoming plane wave and the extra path d·sinθ
    const ux = Math.sin(rad(v.th)), uy = -Math.cos(rad(v.th)), a1x = cx - dpx / 2, a2x = cx + dpx / 2;
    const near = ux >= 0 ? a2x : a1x, far = ux >= 0 ? a1x : a2x, p = Math.abs(dpx * ux);
    for (const k of [0, 1, 2]) {  // wavefronts: the first one passes through the near antenna and the end of the extra path
      const bx = near + ux * k * 40, by = cy + uy * k * 40;
      s += `<line x1="${bx - uy * 70}" y1="${by + ux * 70}" x2="${bx + uy * 70}" y2="${by - ux * 70}" stroke="${C.blue}" opacity="${0.55 - k * 0.15}"/>`;
    }
    s += `<line x1="${far}" y1="${cy}" x2="${far + ux * p}" y2="${cy + uy * p}" stroke="${C.red}" stroke-width="3"/>`;
    if (p > 14) s += txt(far + ux * p / 2 + (ux >= 0 ? -8 : 8), cy + uy * p / 2 - 6, "extra path", ux >= 0 ? "end" : "start", `font-size="11" fill="${C.red}" style="fill:${C.red}"`);
    s += `<line x1="${a1x}" y1="${cy + 18}" x2="${a2x}" y2="${cy + 18}" stroke="currentColor"/>` + txt(cx, cy + 34, `d = ${num(v.d)} mm (λ/2 = ${num(lam / 2)} mm)`, "middle", 'font-size="12"');
    s += `<line x1="${cx - (lam / 2) * 2}" y1="${cy + 40}" x2="${cx + (lam / 2) * 2}" y2="${cy + 40}" stroke="${C.green}" stroke-width="3" opacity=".6"/>`;
    for (const x of [a1x, a2x]) s += `<path d="M${x} ${cy}l-7 12h14z" fill="${C.purple}"/><line x1="${x}" y1="${cy}" x2="${x}" y2="${cy - 12}" stroke="${C.purple}" stroke-width="2"/>`;
    const tx = cx + R * ux, ty = cy + R * uy;
    s += `<line x1="${cx}" y1="${cy}" x2="${tx}" y2="${ty}" stroke="currentColor" stroke-dasharray="4 4" opacity=".5"/>`;
    s += `<g class="uwp-h" data-h="tag" tabindex="0" role="button" aria-label="Tag at ${num(v.th)} degrees. Arrow keys turn it; Shift for 5 degree steps."><circle cx="${tx}" cy="${ty}" r="24" fill="transparent"/><circle cx="${tx}" cy="${ty}" r="10" fill="${C.red}" stroke="#fff" stroke-width="2" class="uwp-ring"/></g>`;
    return s + "</svg>";
  }
  function pdoaChart(v, q) {  // angle error (1σ) against the tag angle
    const W = 300, H = 210, x0 = 40, x1 = 290, yT = 12, yB = 170, yMax = 30;
    const X = a => x0 + ((a + 90) / 180) * (x1 - x0), Y = e => yB - (clamp(e, 0, yMax) / yMax) * (yB - yT);
    let s = svgOpen(W, H, "Angle error against the tag angle", "uwp-small");
    s += `<rect x="${X(-45)}" y="${yT}" width="${X(45) - X(-45)}" height="${yB - yT}" fill="${C.green}" fill-opacity=".08"/>`;
    s += `<rect x="${x0}" y="${yT}" width="${x1 - x0}" height="${yB - yT}" fill="none" stroke="currentColor" opacity=".3"/>`;
    for (const e of [0, 10, 20, 30]) s += txt(x0 - 5, Y(e) + 4, `${e}°`, "end", 'font-size="10.5" opacity=".8"');
    for (const a of [-90, -45, 0, 45, 90]) s += txt(X(a), yB + 14, `${a}°`, "middle", 'font-size="10.5" opacity=".8"');
    s += txt((x0 + x1) / 2, yB + 30, "tag angle · green: ±45°", "middle", 'font-size="11"');
    const pts = [];
    for (let a = -89.5; a <= 89.5; a += 1) pts.push(`${X(a).toFixed(1)},${Y(pdoa(a, v.d, FC[v.ch], v.sp).sigmaTheta).toFixed(1)}`);
    s += `<polyline points="${pts.join(" ")}" fill="none" stroke="${C.orange}" stroke-width="2.2"/>`;
    s += `<circle cx="${X(v.th)}" cy="${Y(q.sigmaTheta)}" r="4.5" fill="${C.red}"/>`;
    s += txt(x0 + 4, yT + 14, "angle error, 1σ", "start", 'font-size="11"');
    return s + "</svg>";
  }
  function fixSvg(v, q, f) {  // one anchor: distance plus angle → position, with its error ellipse
    const W = 300, H = 210, cx = 150, cy = 196, k = 170 / Math.max(5, v.r * 1.05);
    let s = svgOpen(W, H, "One anchor locates the tag from distance and angle", "uwp-small");
    s += `<path d="M${cx - 170} ${cy}A170 170 0 0 1 ${cx + 170} ${cy}" fill="${C.grey}" fill-opacity=".06" stroke="currentColor" opacity=".25"/>`;
    const px = cx + f.x * k, py = cy - f.y * k;  // the across-error is perpendicular to the ray
    s += `<line x1="${cx}" y1="${cy}" x2="${px}" y2="${py}" stroke="currentColor" stroke-dasharray="4 4" opacity=".55"/>`;
    s += `<ellipse cx="${px}" cy="${py}" rx="${clamp(f.across * k, 1.5, 400)}" ry="${clamp(f.along * k, 1.5, 400)}" transform="rotate(${v.th} ${px} ${py})" fill="${C.orange}" fill-opacity=".25" stroke="${C.orange}" stroke-width="1.5"/>`;
    s += `<circle cx="${px}" cy="${py}" r="4.5" fill="${C.red}"/><rect x="${cx - 7}" y="${cy - 7}" width="14" height="14" rx="2" fill="${C.green}"/>`;
    s += txt(cx + 12, cy - 4, "anchor, 2 antennas", "start", 'font-size="11"') + txt(8, 16, `tag ${num(v.r)} m away at ${num(v.th)}°`, "start", 'font-size="11.5"');
    return s + "</svg>";
  }
  function pdoaSetupFn(S) {
    return (el, rerender, setVals) => {
      el.innerHTML = '<div class="uwp-pdoa-wrap"></div><p class="small muted uwp-hint">Drag the red tag around the arc, or Tab to it and use the arrow keys; the angle slider does the same. Antenna spacing drawn enlarged; the green bar is λ/2 at the same scale.</p><div class="uwp-two"><div class="uwp-pchart"></div><div class="uwp-pfix"></div></div>';
      const wrap = el.querySelector(".uwp-pdoa-wrap"), chart = el.querySelector(".uwp-pchart"), fix = el.querySelector(".uwp-pfix");
      S.redraw = () => {
        if (!S.v || !S.q) return;
        const f = document.activeElement && wrap.contains(document.activeElement);
        wrap.innerHTML = pdoaSvg(S.v, S.q);
        chart.innerHTML = pdoaChart(S.v, S.q);
        fix.innerHTML = fixSvg(S.v, S.q, S.f);
        if (f) refocus(wrap, "tag");
      };
      const setAngle = a => { setVals({th: Math.round(clamp(a, -90, 90))}); rerender(); };
      dragSetup(el, ".uwp-pdoa", S, (key, [x, y]) => setAngle(deg(Math.atan2(x - 300, 286 - y))), (key, [dx, dy], big) => {
        setAngle(S.v.th + (dx || -dy) * (big ? 5 : 1));
      });
      if (S.v) S.redraw();
    };
  }

  // ================================================================ definitions (shared by /visuals and the page)
  function defs() {
    const sTwr = {}, sTdoa = {}, sLight = {}, sPdoa = {};
    const related = [["Two-way ranging", "#uwbtwr"], ["TDoA", "#uwbtdoa"], ["Lightweight TDoA", "#uwbltdoa"], ["PDoA", "#uwbpdoa"], ["UWB range and first path", "#uwb"]];
    const explains = [["UWB positioning: one page", "/engineering/uwb_positioning"], ["Part knowledge: UWB", "/reviews/how/uwb"]];
    return [
      {
        id: "uwbtwr", group: "UWB", title: "UWB two-way ranging: single- vs double-sided, clock error and cost",
        explains, related: related.filter(r => r[1] !== "#uwbtwr"),
        lead: "A tag and an anchor swap timed messages. Each crystal runs a few ppm off; single-sided ranging turns that into an error that grows with the reply time, double-sided ranging cancels it.",
        controls: [
          {k: "d", label: "Distance tag to anchor", min: 0.5, max: 100, value: 10, unit: "m", log: true},
          {k: "r1", label: "Anchor's reply time (poll in, response out)", min: 100, max: 5000, value: 400, unit: "µs", log: true},
          {k: "r2", label: "Tag's reply time before the final", min: 100, max: 5000, value: 900, unit: "µs", log: true},
          {k: "ea", label: "Tag crystal error", min: -20, max: 20, step: 0.5, value: 10, unit: "ppm"},
          {k: "eb", label: "Anchor crystal error", min: -20, max: 20, step: 0.5, value: -5, unit: "ppm"},
          {k: "n", label: "Anchors per position fix", type: "select", options: [["3", "3 (2-D)"], ["4", "4 (3-D, or 2-D with a spare)"], ["6", "6 (large room)"]], value: "4"},
        ],
        setup: twrSetup(sTwr),
        compute(v) {
          const r = twr({d: v.d, reply1: v.r1 * 1e-6, reply2: v.r2 * 1e-6, ppmTag: v.ea, ppmAnchor: v.eb});
          sTwr.v = {...v}; sTwr.r = r;
          if (sTwr.redraw) sTwr.redraw();
          const n = +v.n, m = twrMessages(n), us = x => `${(x * 1e6).toFixed(5)} µs`, ns = x => `${(x * 1e9).toFixed(4)} ns`;
          const tone = e => (Math.abs(e) > 0.1 ? "bad" : Math.abs(e) > 0.02 ? "warn" : "ok");
          const air = (n + 2) * 170e-6, fixesPerS = 1 / ((n + 2) * SLOT);
          return {
            nochart: true,
            outputs: [["Time of flight", `${num(r.tof * 1e9)} ns`], ["Single-sided error (poll + response)", slen(r.errSS), tone(r.errSS)],
              ["Double-sided error (asymmetric formula)", slen(r.errDS), tone(r.errDS)], ["Double-sided, plain average of the two", slen(r.errAvg), tone(r.errAvg)],
              [`Messages per fix, ${n} anchors`, `SS ${m.ss} · DS ${m.ds} · DS one-to-many ${m.oneToMany}`], ["Fixes per second on one channel (est)", `about ${num(fixesPerS)} (1 ms slots)`]],
            eq: "SS-TWR: ToF = (T<sub>round1</sub> − T<sub>reply1</sub>) / 2 &nbsp;·&nbsp; DS-TWR: ToF = (T<sub>round1</sub>·T<sub>round2</sub> − T<sub>reply1</sub>·T<sub>reply2</sub>) / (T<sub>round1</sub> + T<sub>round2</sub> + T<sub>reply1</sub> + T<sub>reply2</sub>) &nbsp;·&nbsp; error<sub>SS</sub> ≈ c·T<sub>reply1</sub>·(e<sub>tag</sub> − e<sub>anchor</sub>) / 2, error<sub>DS</sub> ≈ c·ToF·(e<sub>tag</sub> + e<sub>anchor</sub>) / 2",
            eqn: `T<sub>round1</sub> = ${us(r.Tround1)} (tag clock) · T<sub>reply1</sub> = ${us(r.Treply1)} (anchor clock) · T<sub>round2</sub> = ${us(r.Tround2)} (anchor) · T<sub>reply2</sub> = ${us(r.Treply2)} (tag) → SS: ToF = ${ns(r.ss)}, DS: ToF = ${ns(r.ds)}, true ${ns(r.tof)}`,
            html: `<div class="uwp-cmp" aria-label="Single- and double-sided results side by side"><div class="uwp-cmp-c t-${tone(r.errSS)}"><b>Single-sided</b><span>2 messages per anchor</span><span>distance ${num(r.ss * C0)} m</span><span>error ${slen(r.errSS)}</span><span class="small muted">grows with reply time × crystal difference</span></div><div class="uwp-cmp-c t-${tone(r.errDS)}"><b>Double-sided (asymmetric)</b><span>3 messages per anchor</span><span>distance ${num(r.ds * C0)} m</span><span>error ${slen(r.errDS)}</span><span class="small muted">independent of both reply times</span></div></div>
              <p class="small"><b>What it costs.</b> Each fix needs an exchange with every anchor: about ${m.ds} messages for ${n} anchors one by one, or ${m.oneToMany} when one poll is answered by all anchors in turn. The tag transmits and receives in every exchange, and receiving is the expensive part (72-88 mA on a DW3000); about ${num(air * 1e6)} µs on air per fix and about ${num(fixesPerS)} fixes per second fit on one channel, so a few hundred tags at one fix per second share a channel ${EST}.</p>${links}`,
            note: "Clock errors held constant during one exchange; ToF and timestamp noise not included. The plain average (T_round − T_reply on both sides, divided by 4) only cancels the clock error when both reply times are equal; the asymmetric formula does not need that.",
          };
        },
      },
      {
        id: "uwbtdoa", group: "UWB", title: "UWB time difference of arrival (TDoA): hyperbolas, anchor sync and position spread",
        explains, related: related.filter(r => r[1] !== "#uwbtdoa"),
        lead: "One message, several synchronised anchors: each time difference puts the tag on a hyperbola, and the crossing is the position. Sync error between anchors widens every line into a band.",
        controls: [
          {k: "n", label: "Anchors", type: "select", options: [["3", "3 anchors (2-D minimum)"], ["4", "4 anchors"]], value: "4"},
          {k: "sync", label: "Anchor sync error (1 σ per anchor)", min: 0, max: 3, step: 0.05, value: 0.5, unit: "ns"},
          {k: "mode", label: "Who transmits", type: "select", options: [["ul", "UL-TDoA: the tag blinks, anchors listen"], ["dl", "DL-TDoA: anchors transmit, the tag listens"]], value: "ul"},
        ],
        setup: tdoaSetupFn(sTdoa),
        compute(v) {
          sTdoa.v = {...v};
          if (!sTdoa.anchors) { sTdoa.anchors = ANCH.map(a => a.slice()); sTdoa.tag = [9, 6]; }
          if (sTdoa.redraw) sTdoa.redraw();
          const n = +v.n, A = sTdoa.anchors.slice(0, n), p = sTdoa.tag, sig = v.sync * 1e-9 * C0;
          const dd = rangeDiffs(p, A), P1 = tdoaCov(p, A, 1), g = P1 ? Math.sqrt(P1[0][0] + P1[1][1]) : NaN, spread = g * sig;
          const ul = v.mode !== "dl";
          return {
            nochart: true,
            outputs: [...dd.map((x, i) => [`Anchor ${i + 2} − anchor 1`, `${num((x / C0) * 1e9)} ns = ${num(x)} m`]),
              ["Range-difference error (1 σ)", len(sig * Math.SQRT2)], ["Position spread (1 σ, est)", isFinite(spread) ? len(spread) : "no fix", !isFinite(g) ? "bad" : spread > 0.3 ? "bad" : spread > 0.1 ? "warn" : "ok"],
              ["Geometry factor (spread ÷ timing error)", isFinite(g) ? num(g) : "no fix", !isFinite(g) ? "bad" : g > 3 ? "warn" : "ok"],
              ["Tag", `at ${num(p[0])} m, ${num(p[1])} m`], ["Computes the position", ul ? "the location server" : "the tag itself"]],
            eq: "Δt<sub>i1</sub> = (|p − A<sub>i</sub>| − |p − A<sub>1</sub>|) / c: one hyperbola per anchor pair &nbsp;·&nbsp; 1 ns of sync error = 30 cm of range difference &nbsp;·&nbsp; spread ≈ geometry factor × c·σ<sub>sync</sub>",
            eqn: `${dd.map((x, i) => `Δt<sub>${i + 2}1</sub> = ${num((x / C0) * 1e9)} ns`).join(" · ")} · σ = ${num(v.sync)} ns → ±${len(sig * Math.SQRT2)} per difference → spread ${isFinite(spread) ? len(spread) : "–"}`,
            html: `<p class="small">${ul ? "<b>UL-TDoA.</b> The tag only sends a short blink and goes back to sleep; every anchor that hears it notes the arrival time, and a location server compares them. Very low tag power and thousands of tags, but the anchors need nanosecond sync (cables or sync messages) and a backhaul to the server, and the infrastructure always knows where each tag is." : "<b>DL-TDoA.</b> The anchors take turns to send; the tag only listens, notes the arrival times and computes its own position, like a GPS receiver. Any number of tags, and nobody else learns where the tag is (privacy), but the tag must keep its receiver on, which costs more than a short blink."} The anchors need the same synchronisation either way. Drag the tag outside the anchors: the hyperbolas cross at shallow angles and the spread grows.</p>${links}`,
            note: "2-D floor plan, line of sight, one independent timing error per anchor (the differences share anchor 1); the spread is the linearised 1-σ estimate (est). Real systems add multipath and antenna delays; anchor positions must be surveyed to a few centimetres.",
          };
        },
      },
      {
        id: "uwbltdoa", group: "UWB", title: "Lightweight TDoA (our reading, est): the blink-only tag, battery and how many tags fit",
        explains, related: related.filter(r => r[1] !== "#uwbltdoa"),
        lead: "Our reading of lightweight TDoA (est): the tag is cut to one short blink per fix. Compare its battery life and air use with tags that also listen or range.",
        controls: [
          {k: "rate", label: "Position updates per tag", min: 0.1, max: 10, value: 1, unit: "per s", log: true},
          {k: "tags", label: "Tags sharing the channel", min: 10, max: 10000, value: 500, unit: "", log: true},
          {k: "msg", label: "Message (blink) length on air", min: 60, max: 400, step: 5, value: 150, unit: "µs"},
          {k: "listen", label: "Classic tag: listen window per fix", min: 0, max: 5, step: 0.1, value: 1, unit: "ms"},
          {k: "na", label: "Anchors heard (TWR and DL-TDoA)", min: 3, max: 8, step: 1, value: 4, unit: ""},
          {k: "ch", label: "UWB channel", type: "select", options: [["9", "Channel 9 (8 GHz, receive 88 mA)"], ["5", "Channel 5 (6.5 GHz, receive 72 mA)"]], value: "9"},
        ],
        setup(el) { el.innerHTML = '<div class="uwp-light-wrap"></div>'; sLight.wrap = el.querySelector(".uwp-light-wrap"); if (sLight.html) sLight.wrap.innerHTML = sLight.html; },
        compute(v) {
          const o = {ch: v.ch, msg: v.msg * 1e-6, anchors: v.na, listen: v.listen * 1e-3};
          const fixes = Object.fromEntries(KINDS.map(([k]) => [k, tagFix(k, o)]));
          const life = k => batteryHours(fixes[k].charge, v.rate), al = aloha(v.tags, v.rate, v.msg * 1e-6);
          const sched = scheduledTags(v.rate), twrCap = scheduledTags(v.rate, v.na + 2);
          sLight.html = lightSvg(v, fixes);
          if (sLight.wrap && sLight.wrap.isConnected) sLight.wrap.innerHTML = sLight.html;
          const pct = x => `${num(100 * x)} %`;
          return {
            nochart: true,
            outputs: [["Lightweight tag battery (CR2032, est)", years(life("light")), "ok"], ["Classic TDoA tag battery (est)", years(life("classic"))],
              ["TWR tag battery (est)", years(life("twr"))], ["DL-TDoA tag battery (est)", years(life("dl"))],
              ["Air used by blinks (G)", pct(al.G)], ["Blinks that get through (random)", pct(al.success), al.success > 0.9 ? "ok" : al.success > 0.7 ? "warn" : "bad"],
              ["Tags at 90 % success (random)", num(al.tags90)], ["Tags with 1 ms scheduled slots (est)", `${num(sched)} (TWR: ${num(twrCap)})`, v.tags > sched ? "bad" : "ok"]],
            eq: "charge per fix = I<sub>wake</sub>·t<sub>wake</sub> + I<sub>tx</sub>·t<sub>tx</sub> + I<sub>rx</sub>·t<sub>rx</sub> &nbsp;·&nbsp; life = capacity / (charge × rate + I<sub>sleep</sub>) &nbsp;·&nbsp; random blinks: P(no collision) = e<sup>−2G</sup>, G = tags × rate × length",
            eqn: `lightweight: ${num(fixes.light.charge * 1e6)} µC per fix · classic: ${num(fixes.classic.charge * 1e6)} µC · TWR: ${num(fixes.twr.charge * 1e6)} µC · DL-TDoA: ${num(fixes.dl.charge * 1e6)} µC · G = ${num(v.tags)} × ${num(v.rate)} × ${num(v.msg)} µs = ${num(al.G, 3)} → e<sup>−2G</sup> = ${pct(al.success)}`,
            html: `<p class="small">Receiving costs about three times as much current as transmitting, and a tag that listens has to keep its receiver on while it waits. The light tag never listens: it wakes, sends one blink and sleeps, so the wake-up and one short transmission are all it pays for. The price is on the air and in the anchors: blinks are not scheduled, so with many tags some collide and are lost (that fix is simply skipped), and nothing can be sent back to the tag ${EST}.</p>${links}`,
            note: "Our model (est): DW3000 datasheet currents from our review (receive 72 / 88 mA, start-up about 1 ms at the 8 mA idle current, deep sleep 260 nA), transmit about 30 mA, a 220 mAh coin cell at 3 V, host MCU and sensors not counted; pure-ALOHA collisions; 1 ms slots for scheduled tags. Real tags differ; the ratios are the point.",
          };
        },
      },
      {
        id: "uwbpdoa", group: "UWB", title: "UWB phase difference of arrival (PDoA): angle, ambiguity and accuracy",
        explains, related: related.filter(r => r[1] !== "#uwbpdoa"),
        lead: "One receiver, two antennas a little apart: the signal reaches the far antenna a fraction of a wavelength later, and that phase difference gives the angle. Add the TWR distance and one anchor gives a position.",
        controls: [
          {k: "ch", label: "UWB channel", type: "select", options: [["9", "Channel 9: 7987.2 MHz, λ = 37.5 mm"], ["5", "Channel 5: 6489.6 MHz, λ = 46.2 mm"]], value: "9"},
          {k: "d", label: "Antenna spacing d", min: 5, max: 60, step: 0.5, value: 18, unit: "mm"},
          {k: "th", label: "Tag angle (0° = straight ahead)", min: -90, max: 90, step: 1, value: 30, unit: "°"},
          {k: "sp", label: "Phase noise (1 σ)", min: 0, max: 40, step: 1, value: 10, unit: "°"},
          {k: "r", label: "Distance from the anchor (TWR)", min: 0.5, max: 20, value: 5, unit: "m", log: true},
        ],
        setup: pdoaSetupFn(sPdoa),
        compute(v) {
          const q = pdoa(v.th, v.d, FC[v.ch], v.sp), f = polarFix(v.r, v.th, 0.1, q.sigmaTheta);
          sPdoa.v = {...v}; sPdoa.q = q; sPdoa.f = f;
          if (sPdoa.redraw) sPdoa.redraw();
          const lamMm = q.lam * 1000, tone = q.sigmaTheta > 10 ? "bad" : q.sigmaTheta > 5 ? "warn" : "ok";
          return {
            nochart: true,
            outputs: [["Wavelength λ", `${num(lamMm)} mm`], ["Spacing d / λ", `${num(v.d / lamMm)} ${v.d <= lamMm / 2 ? "(≤ ½: unique)" : "(> ½: ambiguous)"}`, v.d <= lamMm / 2 ? "ok" : "bad"],
              ["Phase difference Δφ", `${num(deg(q.dphi))}°`], ["Measured (wrapped to ±180°)", `${num(deg(q.meas))}°`],
              ["Angle read back", `${num(q.est)}°`, Math.abs(q.est - v.th) > 1 ? "bad" : "ok"], ["Angles that fit this phase", q.candidates.map(a => `${num(a)}°`).join(", "), q.ambiguous ? "bad" : "ok"],
              ["Angle error here (1 σ)", `${num(q.sigmaTheta)}°`, tone], ["Position error across the ray", len(f.across), f.across > 0.5 ? "bad" : f.across > 0.2 ? "warn" : "ok"]],
            eq: "Δφ = 2π·d·sin θ / λ &nbsp;·&nbsp; θ = arcsin(λ·Δφ / (2π·d)) &nbsp;·&nbsp; unique only if d ≤ λ/2 &nbsp;·&nbsp; σ<sub>θ</sub> ≈ λ·σ<sub>φ</sub> / (2π·d·cos θ) &nbsp;·&nbsp; position: x = r·sin θ, y = r·cos θ",
            eqn: `λ = c / ${v.ch === "9" ? "7987.2" : "6489.6"} MHz = ${num(lamMm)} mm · Δφ = 360° × ${num(v.d)} × sin ${num(v.th)}° / ${num(lamMm)} = ${num(deg(q.dphi))}° → wrapped ${num(deg(q.meas))}° → θ = ${num(q.est)}° · σ<sub>θ</sub> = ${num(q.sigmaTheta)}° · across error = ${num(v.r)} m × ${num(rad(q.sigmaTheta), 3)} rad = ${len(f.across)}`,
            html: `<p class="small">${q.ambiguous ? `<b>Ambiguous:</b> with d = ${num(v.d)} mm, more than half a wavelength, the phase wraps round and ${q.candidates.length} angles give the same reading (red rings). Keep d at or below λ/2 (${num(lamMm / 2)} mm here) or add a third antenna. ` : ""}Straight ahead the phase changes fastest with angle; towards ±90° it hardly changes, so the same phase noise means a much larger angle error (the curve). A two-antenna array also cannot tell front from back. Distance from TWR plus the angle gives the position from one anchor: phone finding a tag, or a car anchor telling which side the key is on.</p>${links}`,
            note: "Plane wave, one path, ideal antennas with no coupling (est); real arrays need calibration of the phase offset between the two receive paths and lose accuracy in multipath. The ±10 cm range error used for the ellipse along the ray is our assumption.",
          };
        },
      },
    ];
  }

  // ================================================================ /visuals (engine) and the knowledge page
  (window.VZ_ADD = window.VZ_ADD || []).push(({V}) => { for (const d of defs()) V.push(d); });

  const toPos = (c, x) => (c.log ? Math.round((1000 * (Math.log10(x) - Math.log10(c.min))) / (Math.log10(c.max) - Math.log10(c.min))) : x);
  const fromPos = (c, p) => (c.log ? +(10 ** (Math.log10(c.min) + ((Math.log10(c.max) - Math.log10(c.min)) * p) / 1000)).toPrecision(3) : +p);
  const show = (c, x) => (c.type === "select" ? "" : `${num(x)}${c.unit ? " " + c.unit : ""}`);
  function mount(el, def) {  // the same controls, outputs and equations as the engine on /visuals, for one visual
    let vals = {};
    const build = () => {
      vals = Object.fromEntries(def.controls.map(c => [c.k, c.value]));
      el.innerHTML = `<div class="vz-extra"></div><div class="vz-body"><div class="vz-ctl">${def.controls.map(c => c.type === "select"
        ? `<label class="vz-c" data-c="${c.k}"><span>${esc(c.label)}</span><select data-k="${c.k}">${c.options.map(([k, l]) => `<option value="${k}"${k === c.value ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`
        : `<label class="vz-c" data-c="${c.k}"><span>${esc(c.label)} <output data-o="${c.k}">${show(c, c.value)}</output></span><input type="range" data-k="${c.k}" min="${c.log ? 0 : c.min}" max="${c.log ? 1000 : c.max}" step="${c.log ? 1 : c.step || (c.max - c.min) / 200}" value="${toPos(c, c.value)}" aria-valuetext="${esc(show(c, c.value))}"></label>`).join("")}
        <div class="vz-btns"><button type="button" class="outline secondary small-btn vz-reset">Reset</button></div></div>
        <div class="vz-out"><div class="vz-kpis" aria-live="polite"></div></div></div>
        <div class="vz-eq"><div class="vz-eq-sym"></div><div class="vz-eq-num"></div></div><div class="vz-more"></div><p class="vz-note"></p>`;
      el.querySelectorAll("[data-k]").forEach(inp => inp.addEventListener("input", () => {
        const c = def.controls.find(x => x.k === inp.dataset.k);
        vals[c.k] = c.type === "select" ? inp.value : fromPos(c, inp.value);
        const o = el.querySelector(`[data-o="${c.k}"]`);
        if (o) o.textContent = show(c, vals[c.k]);
        if (c.type !== "select") inp.setAttribute("aria-valuetext", show(c, vals[c.k]));
        render();
      }));
      el.querySelector(".vz-reset").addEventListener("click", build);
      if (def.setup) def.setup(el.querySelector(".vz-extra"), render, setVals);
      render();
    };
    function setVals(values) {
      Object.assign(vals, values);
      for (const c of def.controls) {
        const inp = el.querySelector(`[data-k="${c.k}"]`);
        if (!inp || !(c.k in values)) continue;
        inp.value = c.type === "select" ? vals[c.k] : toPos(c, vals[c.k]);
        const o = el.querySelector(`[data-o="${c.k}"]`);
        if (o) o.textContent = show(c, vals[c.k]);
        if (c.type !== "select") inp.setAttribute("aria-valuetext", show(c, vals[c.k]));
      }
    }
    function render() {
      const r = def.compute(vals);
      el.querySelector(".vz-kpis").innerHTML = r.outputs.map(([l, val, tone]) => `<div class="vz-kpi${tone ? " t-" + tone : ""}${String(val).length > 22 ? " wide" : ""}"><span>${esc(l)}</span><b>${esc(val)}</b></div>`).join("");
      el.querySelector(".vz-eq-sym").innerHTML = r.eq;
      el.querySelector(".vz-eq-num").innerHTML = r.eqn;
      el.querySelector(".vz-note").textContent = r.note;
      el.querySelector(".vz-more").innerHTML = r.html || "";
    }
    build();
  }
  function mountAll() {
    const spots = document.querySelectorAll("[data-uwp]");
    if (!spots.length) return;
    const all = defs();
    spots.forEach(el => { const d = all.find(x => x.id === el.dataset.uwp); if (d) { el.classList.add("uwp-on"); mount(el, d); } });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountAll); else mountAll();
})();
