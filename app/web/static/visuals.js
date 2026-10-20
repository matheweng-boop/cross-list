// Engineering knowledge > Interactive visuals: sliders, live graphs and equations with the numbers filled in.
// Each visual is a definition: controls (sliders / selects), a compute(v) that returns the outputs, the equation
// with numbers, a chart spec and a short "what to notice"; the engine below draws them. No external libraries.
(() => {
  const DATA = JSON.parse(document.getElementById("vz-data").textContent);
  const $ = s => document.querySelector(s);
  const C = {blue: "#1f5fa8", orange: "#c2410c", green: "#2e7d4f", grey: "#8a94a3", purple: "#6b46c1", red: "#b42318", teal: "#0f766e"};
  const log10 = Math.log10, clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);

  // numbers: 3 significant digits, SI prefixes where a unit is given
  const PFX = [[1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"], [1e-15, "f"]];
  const num = (x, d = 3) => (!isFinite(x) ? "–" : Math.abs(x) >= 1e4 || (Math.abs(x) < 1e-3 && x !== 0) ? x.toExponential(d - 1) : (+x.toPrecision(d)).toString());
  function si(x, unit) {
    if (!isFinite(x)) return "–";
    if (x === 0) return `0 ${unit}`;
    const p = PFX.find(([f]) => Math.abs(x) >= f * 0.9995) || PFX[PFX.length - 1];
    return `${+(x / p[0]).toPrecision(3)} ${p[1]}${unit}`;
  }
  const db = x => 10 * log10(x), undb = x => 10 ** (x / 10);

  // ------------------------------------------------------------------ chart engine
  function ticksFor(ax) {
    if (ax.log) {
      const out = [], span = log10(ax.max) - log10(ax.min);
      const ms = span <= 1.2 ? [1, 2, 3, 5, 7] : span <= 3 ? [1, 2, 5] : [1];
      const step = Math.max(1, Math.ceil(span / 8));
      for (let e = Math.floor(log10(ax.min)); e <= Math.ceil(log10(ax.max)); e += ms.length > 1 ? 1 : step)
        for (const m of ms) { const v = m * 10 ** e; if (v >= ax.min * 0.999 && v <= ax.max * 1.001) out.push(v); }
      return out;
    }
    const raw = (ax.max - ax.min) / 6, mag = 10 ** Math.floor(log10(raw)), st = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const out = [];
    for (let v = Math.ceil(ax.min / st) * st; v <= ax.max + st * 1e-6; v += st) out.push(+v.toFixed(10));
    return out;
  }
  function plot(el, spec) {
    const W = Math.max(el.parentElement.clientWidth, 300), H = spec.height || Math.round(Math.min(440, Math.max(280, W * 0.55)));
    const L = 62, R = 16, T = 18, B = 46;
    const X = spec.x, Y = spec.y;
    const sx = v => L + (X.log ? (log10(v) - log10(X.min)) / (log10(X.max) - log10(X.min)) : (v - X.min) / (X.max - X.min)) * (W - L - R);
    const sy = v => H - B - (Y.log ? (log10(v) - log10(Y.min)) / (log10(Y.max) - log10(Y.min)) : (v - Y.min) / (Y.max - Y.min)) * (H - T - B);
    const ok = (x, y) => isFinite(x) && isFinite(y) && (!X.log || x > 0) && (!Y.log || y > 0);
    const o = [];
    o.push(`<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" class="vz-plot"/>`);
    for (const b of spec.bands || []) {
      const a = sx(clamp(b.x0, X.min, X.max)), z = sx(clamp(b.x1, X.min, X.max));
      o.push(`<rect x="${a}" y="${T}" width="${Math.max(0, z - a)}" height="${H - T - B}" fill="${b.color || C.grey}" opacity="${b.opacity || 0.1}"/>`);
      if (b.label) o.push(`<text class="vz-bl" x="${(a + z) / 2}" y="${H - B - 8}" text-anchor="middle">${esc(b.label)}</text>`);
    }
    for (const t of ticksFor(X)) o.push(`<line class="vz-grid" x1="${sx(t)}" x2="${sx(t)}" y1="${T}" y2="${H - B}"/><text class="vz-tick" x="${sx(t)}" y="${H - B + 16}" text-anchor="middle">${esc((X.fmt || num)(t))}</text>`);
    for (const t of ticksFor(Y)) o.push(`<line class="vz-grid" x1="${L}" x2="${W - R}" y1="${sy(t)}" y2="${sy(t)}"/><text class="vz-tick" x="${L - 6}" y="${sy(t) + 4}" text-anchor="end">${esc((Y.fmt || num)(t))}</text>`);
    o.push(`<text class="vz-axis" x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">${esc(X.label)}</text>`);
    o.push(`<text class="vz-axis" transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">${esc(Y.label)}</text>`);
    o.push(`<clipPath id="vzc"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath><g clip-path="url(#vzc)">`);
    for (const h of spec.hlines || []) {
      if (h.y < Y.min || h.y > Y.max) continue;
      o.push(`<line x1="${L}" x2="${W - R}" y1="${sy(h.y)}" y2="${sy(h.y)}" stroke="${h.color || C.grey}" stroke-width="${h.width || 1.5}" stroke-dasharray="${h.dash || "5 4"}"/>`);
    }
    for (const v of spec.vlines || []) {
      if (v.x < X.min || v.x > X.max) continue;
      o.push(`<line x1="${sx(v.x)}" x2="${sx(v.x)}" y1="${T}" y2="${H - B}" stroke="${v.color || C.grey}" stroke-width="${v.width || 1.5}" stroke-dasharray="${v.dash || "5 4"}"/>`);
    }
    for (const s of spec.series || []) {
      const pts = s.pts.filter(([x, y]) => ok(x, y)).map(([x, y]) => `${sx(x).toFixed(1)},${sy(clamp(y, Y.log ? Y.min / 10 : Y.min - (Y.max - Y.min), Y.log ? Y.max * 10 : Y.max + (Y.max - Y.min))).toFixed(1)}`);
      if (pts.length > 1) o.push(`<polyline points="${pts.join(" ")}" fill="none" stroke="${s.color || C.blue}" stroke-width="${s.width || 2.5}" stroke-dasharray="${s.dash || ""}" opacity="${s.opacity || 1}" stroke-linejoin="round"/>`);
    }
    o.push("</g>");
    // labels for reference lines (outside the clip so they stay readable)
    const placed = {r: [], l: []};
    for (const h of (spec.hlines || []).filter(h => h.label && h.y >= Y.min && h.y <= Y.max).sort((a, b) => sy(a.y) - sy(b.y))) {
      let y = sy(h.y) - 4, side = "r";
      const clash = (arr, yy) => arr.some(p => Math.abs(p - yy) < 13);
      if (clash(placed.r, y)) side = clash(placed.l, y) ? "r" : "l";
      while (clash(placed[side], y)) y += 13;
      placed[side].push(y);
      o.push(`<text class="vz-rl" x="${side === "r" ? W - R - 4 : L + 6}" y="${y}" text-anchor="${side === "r" ? "end" : "start"}" fill="${h.color || C.grey}">${esc(h.label)}</text>`);
    }
    for (const v of spec.vlines || []) if (v.label && v.x >= X.min && v.x <= X.max) o.push(`<text class="vz-rl" x="${sx(v.x) + 4}" y="${T + 14 + (v.row || 0) * 14}" fill="${v.color || C.grey}">${esc(v.label)}</text>`);
    for (const m of spec.marks || []) {
      if (!ok(m.x, m.y) || m.x < X.min || m.x > X.max || m.y < Y.min || m.y > Y.max) continue;
      const x = sx(m.x), y = sy(m.y), right = x < W - 170;
      o.push(`<circle cx="${x}" cy="${y}" r="${m.r || 6}" fill="${m.color || C.orange}" stroke="#fff" stroke-width="2"/>`);
      if (m.label) o.push(`<text class="vz-ml" x="${right ? x + 10 : x - 10}" y="${y - 10}" text-anchor="${right ? "start" : "end"}">${esc(m.label)}</text>`);
    }
    // legend
    const leg = (spec.series || []).filter(s => s.label);
    if (leg.length) {
      let lx = L + 8;
      const ly = T + 8;
      o.push(`<g class="vz-leg">`);
      for (const s of leg) {
        const w = s.label.length * 6.4 + 28;
        o.push(`<rect x="${lx - 4}" y="${ly - 2}" width="${w}" height="18" rx="3" fill="#fff" opacity=".85"/><line x1="${lx}" x2="${lx + 16}" y1="${ly + 7}" y2="${ly + 7}" stroke="${s.color || C.blue}" stroke-width="3" stroke-dasharray="${s.dash || ""}"/><text x="${lx + 20}" y="${ly + 11}">${esc(s.label)}</text>`);
        lx += w + 6;
      }
      o.push("</g>");
    }
    el.setAttribute("viewBox", `0 0 ${W} ${H}`); el.setAttribute("width", W); el.setAttribute("height", H);
    el.innerHTML = o.join("");
  }
  function bars(el, items, opts = {}) {
    const W = Math.max(el.parentElement.clientWidth, 300), RH = 34, L = Math.min(150, W * 0.3), R = 120, H = items.length * RH + 30;
    const max = opts.max || Math.max(...items.map(i => i.value), 1e-9);
    const o = [];
    items.forEach((it, i) => {
      const y = 10 + i * RH, w = Math.max(2, (it.value / max) * (W - L - R));
      o.push(`<text class="vz-tick" x="${L - 8}" y="${y + 19}" text-anchor="end">${esc(it.label)}</text><rect x="${L}" y="${y + 4}" width="${w}" height="22" rx="3" fill="${it.color || C.blue}"/><text class="vz-ml" x="${L + w + 6}" y="${y + 20}">${esc(it.text)}</text>`);
    });
    el.setAttribute("viewBox", `0 0 ${W} ${H}`); el.setAttribute("width", W); el.setAttribute("height", H);
    el.innerHTML = o.join("");
  }
  const range = (a, b, n, log) => Array.from({length: n}, (_, i) => (log ? a * (b / a) ** (i / (n - 1)) : a + ((b - a) * i) / (n - 1)));

  // ------------------------------------------------------------------ the visuals
  const V = [];

  V.push({
    id: "dbm", group: "RF links", title: "dBm: the power ladder",
    lead: "Every RF power on one logarithmic scale, from a GNSS signal at the antenna to a radar transmitter.",
    controls: [{k: "p", label: "Power", min: -140, max: 70, step: 1, value: 20, unit: "dBm"}],
    compute(v) {
      const w = 1e-3 * undb(v.p), vr = Math.sqrt(w * 50);
      const refs = [[-130, "GNSS at antenna"], [-95, "BLE sensitivity"], [0, "1 mW"], [20, "Wi-Fi client"], [24, "Phone PA"], [30, "1 W"], [46, "Macro cell 40 W"], [60, "Radar 1 kW"]];
      return {
        outputs: [["Power", si(w, "W")], ["dBW", `${num(v.p - 30)} dBW`], ["Voltage into 50 Ω", si(vr, "V") + " rms"]],
        eq: `P<sub>dBm</sub> = 10 · log<sub>10</sub>( P / 1 mW )`,
        eqn: `${num(v.p)} dBm = 10 · log<sub>10</sub>( ${si(w, "W")} / 1 mW )`,
        chart: {x: {min: -140, max: 70, label: "Power (dBm)"}, y: {min: 1e-18, max: 1e5, log: true, label: "Power (W)", fmt: x => si(x, "W")},
          series: [{pts: range(-140, 70, 60).map(p => [p, 1e-3 * undb(p)])}],
          vlines: refs.map(([p, l], i) => ({x: p, label: l, row: i % 4, color: C.grey})), marks: [{x: v.p, y: w, label: `${num(v.p)} dBm = ${si(w, "W")}`}]},
        note: "Every 10 dB is a factor of 10 in power, every 3 dB a factor of 2. A receiver handles signals 20 orders of magnitude below what the transmitter next to it sends: that is why filters, isolation and linearity matter.",
      };
    },
  });

  V.push({
    id: "link", group: "RF links", title: "Link budget and range",
    lead: "How far a link reaches in free space: transmit power, antenna gains and receiver sensitivity against the path loss.",
    controls: [
      {k: "f", label: "Frequency", min: 0.1, max: 100, value: 2.4, unit: "GHz", log: true},
      {k: "d", label: "Distance", min: 0.001, max: 100, value: 0.5, unit: "km", log: true},
      {k: "pt", label: "Transmit power", min: -10, max: 60, step: 1, value: 20, unit: "dBm"},
      {k: "g", label: "Antenna gains (Tx + Rx)", min: 0, max: 60, step: 1, value: 4, unit: "dBi"},
      {k: "s", label: "Receiver sensitivity", min: -130, max: -40, step: 1, value: -90, unit: "dBm"},
    ],
    compute(v) {
      const fspl = (d, f) => 20 * log10(d) + 20 * log10(f * 1000) + 32.44;
      const pr = d => v.pt + v.g - fspl(d, v.f), L = fspl(v.d, v.f), margin = pr(v.d) - v.s;
      const dmax = 10 ** ((v.pt + v.g - v.s - 20 * log10(v.f * 1000) - 32.44) / 20);
      const ds = range(0.001, 100, 80, true);
      return {
        outputs: [["Path loss", `${num(L)} dB`], ["Received", `${num(pr(v.d))} dBm`], ["Margin", `${num(margin)} dB`, margin < 0 ? "bad" : margin < 10 ? "warn" : "ok"], ["Free-space range", si(dmax * 1000, "m")]],
        eq: `FSPL = 20 log<sub>10</sub>(d<sub>km</sub>) + 20 log<sub>10</sub>(f<sub>MHz</sub>) + 32.44 &nbsp;·&nbsp; P<sub>rx</sub> = P<sub>tx</sub> + G − FSPL`,
        eqn: `${num(L)} dB = 20 log(${num(v.d)}) + 20 log(${num(v.f * 1000)}) + 32.44 &nbsp;·&nbsp; ${num(pr(v.d))} dBm = ${v.pt} + ${v.g} − ${num(L)}`,
        chart: {x: {min: 0.001, max: 100, log: true, label: "Distance (km)", fmt: x => si(x * 1000, "m")}, y: {min: -160, max: 40, label: "Received power (dBm)"},
          series: [[0.9, C.grey], [5.8, C.purple], [28, C.teal]].filter(([f]) => Math.abs(f - v.f) > 0.05).map(([f, c]) => ({pts: ds.map(d => [d, v.pt + v.g - fspl(d, f)]), color: c, width: 1.5, dash: "4 3", label: `${f} GHz`}))
            .concat([{pts: ds.map(d => [d, pr(d)]), color: C.blue, width: 3, label: `${num(v.f)} GHz`}]),
          hlines: [{y: v.s, label: `sensitivity ${v.s} dBm`, color: C.red}], marks: [{x: v.d, y: pr(v.d), label: `${num(pr(v.d))} dBm at ${si(v.d * 1000, "m")}`}]},
        note: "Each doubling of distance or frequency costs 6 dB. Higher bands lose more with fixed antenna gains, but an antenna of the same size has more gain at a higher frequency, which is how mmWave links close. Real paths add walls, rain and fading on top of this free-space line.",
      };
    },
    related: [["RF bands", "/rf-bands"]],
  });

  V.push({
    id: "wave", group: "RF links", title: "Wavelength and antenna size",
    lead: "Wavelength sets antenna size and tells you when a PCB trace starts behaving like a transmission line.",
    controls: [{k: "f", label: "Frequency", min: 0.001, max: 100, value: 2.4, unit: "GHz", log: true}],
    compute(v) {
      const lam = 0.299792458 / v.f, pcb = lam / Math.sqrt(3.3);
      return {
        outputs: [["Wavelength λ", si(lam, "m")], ["λ/4 monopole", si(lam / 4, "m")], ["λ/2 dipole", si(lam / 2, "m")], ["λ on FR-4 microstrip", si(pcb, "m")], ["Trace is a line above ≈ λ/10", si(pcb / 10, "m")]],
        eq: `λ = c / f &nbsp;·&nbsp; λ<sub>PCB</sub> ≈ λ / √ε<sub>r,eff</sub> (FR-4 microstrip ε<sub>r,eff</sub> ≈ 3.3)`,
        eqn: `${si(lam, "m")} = 3·10<sup>8</sup> m/s / ${si(v.f * 1e9, "Hz")}`,
        chart: {x: {min: 0.001, max: 100, log: true, label: "Frequency", fmt: x => si(x * 1e9, "Hz")}, y: {min: 1e-3, max: 300, log: true, label: "Length", fmt: x => si(x, "m")},
          series: [{pts: range(0.001, 100, 40, true).map(f => [f, 0.299792458 / f]), label: "λ in air"}, {pts: range(0.001, 100, 40, true).map(f => [f, 0.299792458 / f / 4]), color: C.orange, dash: "6 4", label: "λ/4 antenna"}],
          vlines: [[0.1, "FM"], [0.9, "LTE 900"], [2.4, "Wi-Fi"], [5.8, "5.8 GHz"], [28, "n257"], [77, "car radar"]].map(([f, l], i) => ({x: f, label: l, row: i % 3})),
          marks: [{x: v.f, y: lam, label: `λ = ${si(lam, "m")}`}]},
        note: "At 2.4 GHz a quarter-wave antenna is 31 mm; at 28 GHz it is under 3 mm, small enough to put arrays of them in a package (antenna-in-package). Above λ/10 a trace needs controlled impedance.",
      };
    },
  });

  V.push({
    id: "nf", group: "Receivers", title: "Cascaded noise figure and sensitivity",
    lead: "Why the first stage decides the receiver: a lossy filter in front of the LNA adds its loss straight to the noise figure.",
    controls: [
      {k: "l", label: "Filter loss before the LNA", min: 0, max: 4, step: 0.1, value: 1, unit: "dB"},
      {k: "g1", label: "LNA gain", min: 0, max: 30, step: 0.5, value: 18, unit: "dB"},
      {k: "f1", label: "LNA noise figure", min: 0.3, max: 6, step: 0.05, value: 0.8, unit: "dB"},
      {k: "f2", label: "2nd stage (mixer) NF", min: 2, max: 15, step: 0.5, value: 9, unit: "dB"},
      {k: "g2", label: "2nd stage gain", min: -10, max: 25, step: 0.5, value: 8, unit: "dB"},
      {k: "f3", label: "3rd stage (ADC / IF) NF", min: 5, max: 30, step: 0.5, value: 20, unit: "dB"},
      {k: "bw", label: "Channel bandwidth", min: 0.01, max: 400, value: 20, unit: "MHz", log: true},
      {k: "snr", label: "SNR the demodulator needs", min: -5, max: 30, step: 0.5, value: 10, unit: "dB"},
    ],
    compute(v) {
      const st = [["Filter", -v.l, v.l, C.grey], ["LNA", v.g1, v.f1, C.blue], ["Mixer", v.g2, v.f2, C.orange], ["ADC / IF", 0, v.f3, C.purple]];
      let G = 1, F = 0;
      const terms = st.map(([n, g, nf, c], i) => { const t = i === 0 ? undb(nf) : (undb(nf) - 1) / G; G *= undb(g); F += t; return {n, t, c}; });
      const nf = db(F), sens = -174 + nf + db(v.bw * 1e6) + v.snr;
      const extra = terms.map((t, i) => (i === 0 ? t.t - 1 : t.t));
      const tot = extra.reduce((a, b) => a + b, 0);
      return {
        outputs: [["System noise figure", `${num(nf)} dB`], ["Noise floor", `${num(-174 + db(v.bw * 1e6) + nf)} dBm`], ["Sensitivity", `${num(sens)} dBm`]],
        eq: `F = F<sub>1</sub> + (F<sub>2</sub> − 1)/G<sub>1</sub> + (F<sub>3</sub> − 1)/(G<sub>1</sub>G<sub>2</sub>) + … &nbsp;·&nbsp; S = −174 dBm/Hz + NF + 10 log<sub>10</sub>(BW) + SNR`,
        eqn: `S = −174 + ${num(nf)} + ${num(db(v.bw * 1e6))} + ${v.snr} = ${num(sens)} dBm`,
        bars: terms.map((t, i) => ({label: t.n, value: extra[i], color: t.c, text: `${num((100 * extra[i]) / tot, 2)} %`})),
        note: "Move the filter loss: every 0.1 dB in front of the LNA is 0.1 dB of sensitivity, which is why low-loss BAW filters and LNAs with integrated filters sell. Raise the LNA gain and watch the mixer and ADC contributions shrink.",
      };
    },
    related: [["LNAs on the RF coverage page", "/business/rf-coverage"]],
  });

  V.push({
    id: "ip3", group: "Receivers", title: "IP3 and intermodulation",
    lead: "Two strong signals create third-order products that grow three times as fast as the signals themselves.",
    controls: [
      {k: "g", label: "Gain", min: 0, max: 40, step: 0.5, value: 15, unit: "dB"},
      {k: "oip3", label: "Output IP3", min: 0, max: 55, step: 0.5, value: 32, unit: "dBm"},
      {k: "pin", label: "Input power per tone", min: -60, max: 10, step: 0.5, value: -20, unit: "dBm"},
    ],
    compute(v) {
      const iip3 = v.oip3 - v.g, pf = v.pin + v.g, pim = 3 * v.pin + v.g - 2 * iip3, xs = range(-60, iip3 + 8, 40);
      return {
        outputs: [["Input IP3", `${num(iip3)} dBm`], ["Output per tone", `${num(pf)} dBm`], ["IM3 product", `${num(pim)} dBm`], ["IM3 below the tones", `${num(pf - pim)} dBc`], ["P1dB (≈ OIP3 − 10)", `${num(v.oip3 - 10)} dBm`]],
        eq: `P<sub>IM3</sub> = 3·P<sub>in</sub> + G − 2·IIP3 &nbsp;·&nbsp; ΔIM3 = 2·(OIP3 − P<sub>out</sub>)`,
        eqn: `${num(pim)} dBm = 3·(${num(v.pin)}) + ${num(v.g)} − 2·(${num(iip3)})`,
        chart: {x: {min: -60, max: Math.max(iip3 + 8, 0), label: "Input power per tone (dBm)"}, y: {min: -140, max: v.oip3 + 10, label: "Output power (dBm)"},
          series: [{pts: xs.map(p => [p, p + v.g]), label: "Fundamental (slope 1)"}, {pts: xs.map(p => [p, 3 * p + v.g - 2 * iip3]), color: C.orange, label: "IM3 (slope 3)"}],
          vlines: [{x: v.oip3 - 10 - v.g + 1, label: "≈ 1 dB compression", color: C.red}],
          marks: [{x: v.pin, y: pf, label: `tones ${num(pf)} dBm`, color: C.blue}, {x: v.pin, y: pim, label: `IM3 ${num(pim)} dBm`}, {x: iip3, y: v.oip3, label: `IP3 (${num(iip3)}, ${num(v.oip3)})`, color: C.grey}]},
        note: "Lower the input by 1 dB and the IM3 product falls 3 dB, so the gap improves by 2 dB. IP3 is an extrapolation: the real amplifier compresses about 10 dB below it.",
      };
    },
  });

  V.push({
    id: "vswr", group: "Matching and filters", title: "Mismatch, VSWR and the standing wave",
    lead: "A load that is not 50 Ω reflects part of the wave; the reflection and the forward wave add up to a standing wave.",
    controls: [
      {k: "r", label: "Load resistance", min: 1, max: 1000, value: 100, unit: "Ω", log: true},
      {k: "x", label: "Load reactance", min: -200, max: 200, step: 1, value: 0, unit: "Ω"},
    ],
    animate: true,
    compute(v, t = 0) {
      const z0 = 50, nr = v.r - z0, ni = v.x, dr = v.r + z0, di = v.x, den = dr * dr + di * di;
      const gr = (nr * dr + ni * di) / den, gi = (ni * dr - nr * di) / den, m = Math.hypot(gr, gi), ang = Math.atan2(gi, gr);
      const vswr = (1 + m) / (1 - m), rl = -20 * log10(m), ml = -10 * log10(1 - m * m);
      const xs = range(0, 1, 120);
      return {
        outputs: [["|Γ|", num(m)], ["VSWR", `${num(vswr)} : 1`, vswr > 2 ? "bad" : vswr > 1.5 ? "warn" : "ok"], ["Return loss", `${num(rl)} dB`], ["Mismatch loss", `${num(ml)} dB`], ["Power reflected", `${num(100 * m * m, 2)} %`]],
        eq: `Γ = (Z<sub>L</sub> − Z<sub>0</sub>)/(Z<sub>L</sub> + Z<sub>0</sub>) &nbsp;·&nbsp; VSWR = (1 + |Γ|)/(1 − |Γ|) &nbsp;·&nbsp; RL = −20 log|Γ| &nbsp;·&nbsp; ML = −10 log(1 − |Γ|²)`,
        eqn: `Γ = (${num(v.r)} ${v.x < 0 ? "−" : "+"} j${num(Math.abs(v.x))} − 50)/(${num(v.r)} ${v.x < 0 ? "−" : "+"} j${num(Math.abs(v.x))} + 50) = ${num(m)} ∠ ${num((ang * 180) / Math.PI)}°`,
        chart: {x: {min: 0, max: 1, label: "Distance from the load (wavelengths)"}, y: {min: -2, max: 2.2, label: "V / V forward"},
          // V(d) = e^{j2πd} + Γ e^{−j2πd} (d in wavelengths from the load); the instantaneous wave is Re{V(d)·e^{jωt}}
          series: [{pts: xs.map(d => [d, Math.hypot(1 + m * Math.cos(ang - 4 * Math.PI * d), m * Math.sin(ang - 4 * Math.PI * d))]), width: 3, label: "envelope |V|"},
            {pts: xs.map(d => [d, Math.cos(2 * Math.PI * d + t) + m * Math.cos(ang - 2 * Math.PI * d + t)]), color: C.orange, width: 2, label: "wave at this instant"},
            {pts: xs.map(d => [d, -Math.hypot(1 + m * Math.cos(ang - 4 * Math.PI * d), m * Math.sin(ang - 4 * Math.PI * d))]), width: 1.5, dash: "3 3", opacity: 0.6}],
          hlines: [{y: 1 + m, label: `max ${num(1 + m)}`, color: C.orange}, {y: 1 - m, label: `min ${num(1 - m)}`, color: C.orange}, {y: 1, label: "matched", color: C.grey}]},
        note: "Press Play: the wave moves inside the envelope, and where the envelope is narrowest (the nodes) the voltage barely changes. VSWR is the ratio of the envelope maximum to its minimum. 2:1 reflects 11 % of the power (0.5 dB lost); data sheets quote return loss, often 10–15 dB for switches and filters.",
      };
    },
  });

  V.push({
    id: "filter", group: "Matching and filters", title: "Band-pass filter: order, bandwidth, rejection",
    lead: "How much a blocker next to the band is rejected, and why wide fractional bandwidths need other filter technologies.",
    controls: [
      {k: "type", label: "Response", type: "select", options: [["bw", "Butterworth (flat)"], ["ch", "Chebyshev 0.5 dB ripple (steeper)"]], value: "ch"},
      {k: "n", label: "Order (resonators)", min: 1, max: 9, step: 1, value: 5, unit: ""},
      {k: "f0", label: "Centre frequency", min: 0.5, max: 40, value: 5.5, unit: "GHz", log: true},
      {k: "fbw", label: "Fractional bandwidth", min: 1, max: 60, step: 0.5, value: 13, unit: "%"},
      {k: "fb", label: "Blocker frequency", min: 0.5, max: 40, value: 6.2, unit: "GHz", log: true},
    ],
    compute(v) {
      const n = Math.round(v.n), fbw = v.fbw / 100, eps2 = undb(0.5) - 1;
      const att = f => {
        const w = Math.abs(f / v.f0 - v.f0 / f) / fbw;
        if (v.type === "bw") return db(1 + w ** (2 * n));
        const t = w <= 1 ? Math.cos(n * Math.acos(w)) : Math.cosh(n * Math.acosh(w));
        return db(1 + eps2 * t * t);
      };
      const fs = range(v.f0 / 2.5, v.f0 * 2.5, 300, true), rej = att(v.fb);
      const tech = v.fbw <= 7 ? "SAW / BAW (acoustic) can do it" : v.fbw <= 18 ? "Scandium-doped BAW or XBAR at the edge; ceramic / LTCC / IPD safe" : v.fbw <= 25 ? "XBAR at its limit; LTCC, IPD, ceramic or cavity" : "Not acoustic: LTCC, IPD, lumped LC or cavity";
      return {
        outputs: [["Passband", `${num(v.f0 * (1 - fbw / 2))}–${num(v.f0 * (1 + fbw / 2))} GHz`], ["Rejection at the blocker", `${num(rej)} dB`, rej < 20 ? "bad" : rej < 40 ? "warn" : "ok"], ["Technology hint", tech]],
        eq: `Ω = (f/f<sub>0</sub> − f<sub>0</sub>/f) / FBW &nbsp;·&nbsp; A(Ω) = 10 log<sub>10</sub>(1 + ε² T<sub>n</sub>²(Ω)) &nbsp;(Butterworth: 1 + Ω<sup>2n</sup>)`,
        eqn: `blocker ${num(v.fb)} GHz → Ω = ${num(Math.abs(v.fb / v.f0 - v.f0 / v.fb) / fbw)} → ${num(rej)} dB with n = ${n}`,
        chart: {x: {min: v.f0 / 2.5, max: v.f0 * 2.5, log: true, label: "Frequency (GHz)"}, y: {min: -100, max: 5, label: "Response (dB)"},
          bands: [{x0: v.f0 * (1 - fbw / 2), x1: v.f0 * (1 + fbw / 2), color: C.blue, opacity: 0.08, label: "passband"}],
          series: [{pts: fs.map(f => [f, -att(f)]), width: 3}], vlines: [{x: v.fb, label: "blocker", color: C.orange}], marks: [{x: v.fb, y: -rej, label: `−${num(rej)} dB`}]},
        note: "Ideal lossless prototype: real filters add insertion loss set by the resonator Q. Try the Wi-Fi 5 / 6 GHz case (5.5 GHz, 13 %, blocker at 6.2 GHz): rejection rises quickly with order, but a 25 %+ bandwidth (full n77, UWB) is out of reach of acoustic filters, as the filter report explains.",
      };
    },
    related: [["Filter report (1–11 GHz)", "/business/reports/filters-1-11ghz"], ["RF bands", "/rf-bands"]],
  });

  V.push({
    id: "lc", group: "Matching and filters", title: "LC resonance and Q",
    lead: "An inductor and a capacitor resonate where their reactances cancel; the Q sets how sharp the peak is.",
    controls: [
      {k: "l", label: "Inductance", min: 0.1, max: 1000, value: 3.3, unit: "nH", log: true},
      {k: "c", label: "Capacitance", min: 0.1, max: 1000, value: 1.2, unit: "pF", log: true},
      {k: "q", label: "Loaded Q", min: 2, max: 500, value: 40, unit: "", log: true},
    ],
    compute(v) {
      const L = v.l * 1e-9, Cc = v.c * 1e-12, f0 = 1 / (2 * Math.PI * Math.sqrt(L * Cc)), bw = f0 / v.q;
      const fs = range(f0 / 3, f0 * 3, 300, true);
      return {
        outputs: [["Resonance f₀", si(f0, "Hz")], ["3 dB bandwidth", si(bw, "Hz")], ["X_L = X_C at f₀", si(2 * Math.PI * f0 * L, "Ω")], ["Characteristic impedance √(L/C)", si(Math.sqrt(L / Cc), "Ω")]],
        eq: `f<sub>0</sub> = 1 / (2π √(LC)) &nbsp;·&nbsp; BW = f<sub>0</sub> / Q &nbsp;·&nbsp; |H| = 1 / √(1 + Q²(f/f<sub>0</sub> − f<sub>0</sub>/f)²)`,
        eqn: `f<sub>0</sub> = 1 / (2π √(${si(L, "H")} · ${si(Cc, "F")})) = ${si(f0, "Hz")}`,
        chart: {x: {min: f0 / 3, max: f0 * 3, log: true, label: "Frequency", fmt: x => si(x, "Hz")}, y: {min: -50, max: 3, label: "Response (dB)"},
          series: [{pts: fs.map(f => [f, -db(1 + v.q * v.q * (f / f0 - f0 / f) ** 2)]), width: 3}], hlines: [{y: -3, label: "−3 dB", color: C.grey}], marks: [{x: f0, y: 0, label: si(f0, "Hz")}]},
        note: "Chip inductors reach Q of 30–80 at GHz frequencies; acoustic resonators (BAW, SAW) reach 1,000 or more, which is why they make the steepest filters. A ceramic resonator sits in between.",
      };
    },
  });

  const MAT = {cu: [1.68e-8, "Copper"], ag: [1.59e-8, "Silver"], au: [2.44e-8, "Gold"], al: [2.65e-8, "Aluminium"]};
  V.push({
    id: "skin", group: "Matching and filters", title: "Skin depth",
    lead: "At high frequency the current crowds into a thin layer at the conductor surface.",
    controls: [
      {k: "f", label: "Frequency", min: 1e-6, max: 100, value: 2.4, unit: "GHz", log: true},
      {k: "m", label: "Conductor", type: "select", options: Object.entries(MAT).map(([k, [, n]]) => [k, n]), value: "cu"},
    ],
    compute(v) {
      const mu0 = 4e-7 * Math.PI, d = (rho, f) => Math.sqrt(rho / (Math.PI * f * 1e9 * mu0)), rho = MAT[v.m][0], dd = d(rho, v.f);
      const fs = range(1e-6, 100, 60, true);
      return {
        outputs: [["Skin depth δ", si(dd, "m")], ["Carries ~99 % of the current", `top ${si(5 * dd, "m")}`], ["vs 1 oz copper foil (35 µm)", dd < 35e-6 / 5 ? "current only in the surface" : "whole foil carries current"]],
        eq: `δ = √( ρ / (π f μ<sub>0</sub>) )`,
        eqn: `δ = √( ${num(rho)} Ω·m / (π · ${si(v.f * 1e9, "Hz")} · 4π·10<sup>−7</sup>) ) = ${si(dd, "m")}`,
        chart: {x: {min: 1e-6, max: 100, log: true, label: "Frequency", fmt: x => si(x * 1e9, "Hz")}, y: {min: 1e-7, max: 1e-2, log: true, label: "Skin depth", fmt: x => si(x, "m")},
          series: Object.entries(MAT).map(([k, [r, n]], i) => ({pts: fs.map(f => [f, d(r, f)]), color: [C.orange, C.grey, C.purple, C.teal][i], width: k === v.m ? 3 : 1.5, label: n})),
          hlines: [{y: 35e-6, label: "1 oz Cu foil 35 µm"}, {y: 1e-6, label: "1 µm (plating)"}], marks: [{x: v.f, y: dd, label: si(dd, "m")}]},
        note: "At 2.4 GHz copper conducts in the top 1.3 µm, so surface roughness and plating (nickel under gold, ENIG) add loss at RF. At 50 Hz the skin depth is about 9 mm.",
      };
    },
  });

  V.push({
    id: "cmti", group: "Isolation and power", title: "CMTI against the switching edge",
    lead: "The isolator must ride through the voltage slew of the power stage it sits across. Faster SiC and GaN edges need higher CMTI.",
    controls: [
      {k: "v", label: "Switched voltage (bus)", min: 12, max: 2000, value: 800, unit: "V", log: true},
      {k: "t", label: "Edge time (10–90 %)", min: 1, max: 1000, value: 20, unit: "ns", log: true},
      {k: "k", label: "Design margin", min: 1, max: 4, step: 0.5, value: 2, unit: "×"},
    ],
    compute(v) {
      const dvdt = v.v / v.t, need = dvdt * v.k, ts = range(1, 1000, 60, true);
      const refs = DATA.cmti, pass = refs.filter(r => r.kvus >= need).map(r => r.name);
      return {
        outputs: [["Edge slew dV/dt", `${num(dvdt)} kV/µs`], ["CMTI needed with margin", `${num(need)} kV/µs`], ["Isolators that pass", pass.length ? pass.join(", ") : "none of the listed", pass.length ? "ok" : "bad"]],
        eq: `dV/dt = ΔV / t<sub>edge</sub> &nbsp;·&nbsp; CMTI<sub>min</sub> ≥ k · dV/dt`,
        eqn: `${num(dvdt)} kV/µs = ${num(v.v)} V / ${num(v.t)} ns &nbsp;·&nbsp; × ${v.k} = ${num(need)} kV/µs`,
        chart: {x: {min: 1, max: 1000, log: true, label: "Edge time (ns)"}, y: {min: 0.1, max: 3000, log: true, label: "dV/dt (kV/µs)"},
          bands: [{x0: 1, x1: 10, label: "GaN", color: C.purple}, {x0: 10, x1: 50, label: "SiC", color: C.teal}, {x0: 50, x1: 300, label: "Si IGBT / MOSFET", color: C.grey}],
          series: [{pts: ts.map(t => [t, v.v / t]), width: 3, label: `${num(v.v)} V edge`}, {pts: ts.map(t => [t, (v.v / t) * v.k]), color: C.orange, dash: "6 4", label: `× ${v.k} margin`}],
          hlines: refs.map(r => ({y: r.kvus, label: `${r.name} ${r.kvus}`, color: r.ours ? C.blue : C.grey, dash: r.ours ? "" : "4 4", width: r.ours ? 2 : 1.2})),
          marks: [{x: v.t, y: need, label: `needs ${num(need)} kV/µs`}]},
        note: "800 V switched in 20 ns is 40 kV/µs: the older Si86xx (35 kV/µs minimum) is already short, the Si86S (100) and Si82Ex (200) have room. CMTI values are data-sheet minimums from the cross lists; check the test method (static vs dynamic) when comparing.",
      };
    },
    related: [["Skyworks + Qorvo: isolation", "/portfolio#pick"], ["Search isolators", "/parts?cat=isolation"]],
  });

  // IEC 60664-1 Table F.5, pollution degree 2, basic insulation (mm): voltage → [MG I, MG II, MG III]
  const CREEP = [[50, .6, .85, 1.2], [63, .63, .9, 1.25], [80, .67, .95, 1.3], [100, .71, 1, 1.4], [125, .75, 1.05, 1.5], [160, .8, 1.1, 1.6], [200, 1, 1.4, 2], [250, 1.25, 1.8, 2.5], [320, 1.6, 2.2, 3.2], [400, 2, 2.8, 4], [500, 2.5, 3.6, 5], [630, 3.2, 4.5, 6.3], [800, 4, 5.6, 8], [1000, 5, 7.1, 10]];
  const creep = (u, g) => {
    if (u <= CREEP[0][0]) return CREEP[0][g];
    for (let i = 1; i < CREEP.length; i++) if (u <= CREEP[i][0]) { const [a, b] = [CREEP[i - 1], CREEP[i]]; return a[g] + ((b[g] - a[g]) * (u - a[0])) / (b[0] - a[0]); }
    return CREEP[CREEP.length - 1][g];
  };
  V.push({
    id: "creep", group: "Isolation and power", title: "Creepage against working voltage",
    lead: "The distance along the package surface between the two sides must grow with the working voltage, the pollution and the insulating material.",
    controls: [
      {k: "u", label: "Working voltage", min: 50, max: 1000, step: 10, value: 400, unit: "V rms"},
      {k: "g", label: "Mold compound (material group)", type: "select", options: [["1", "I (CTI ≥ 600)"], ["2", "II (CTI 400–600)"], ["3", "III (CTI 175–400)"]], value: "1"},
      {k: "ins", label: "Insulation", type: "select", options: [["1", "Basic"], ["2", "Reinforced (2×)"]], value: "2"},
    ],
    compute(v) {
      const g = +v.g, k = +v.ins, need = creep(v.u, g) * k, us = range(50, 1000, 60);
      const pk = DATA.creepage, fit = pk.filter(p => p.mm >= need).map(p => `${p.code} (${p.mm} mm)`);
      return {
        outputs: [["Creepage required", `${num(need)} mm`], ["Packages that reach it", fit.length ? fit.slice(0, 4).join(", ") : "none of the listed", fit.length ? "ok" : "bad"]],
        eq: `creepage ≥ table value (U<sub>rms</sub>, pollution degree, material group) × 2 for reinforced`,
        eqn: `${num(v.u)} V rms, PD2, group ${["", "I", "II", "III"][g]} → ${num(creep(v.u, g))} mm${k === 2 ? ` × 2 = ${num(need)} mm` : ""}`,
        chart: {x: {min: 50, max: 1000, label: "Working voltage (V rms)"}, y: {min: 0, max: 22, label: "Creepage (mm)"},
          series: [1, 2, 3].map(gr => ({pts: us.map(u => [u, creep(u, gr) * k]), color: [C.blue, C.orange, C.purple][gr - 1], width: gr === g ? 3 : 1.5, dash: gr === g ? "" : "5 4", label: `group ${["", "I", "II", "III"][gr]}`})),
          hlines: pk.map(p => ({y: p.mm, label: `${p.code} ${p.mm} mm`, color: C.grey})), marks: [{x: v.u, y: need, label: `${num(need)} mm`}]},
        note: "Values from IEC 60664-1 (Table F.5, pollution degree 2), linearly interpolated: indicative only, the end-product standard (IEC 62368-1, 61800-5-1, 60664-1 edition) decides. Package creepage is what the data sheets in our cross lists state; wide bodies (8 mm) and extra-wide (14.5 mm) exist for 800 V+ systems.",
      };
    },
    related: [["Specification guides", "/engineering"]],
  });

  V.push({
    id: "gate", group: "Isolation and power", title: "Gate-drive current and power",
    lead: "How much peak current the driver must deliver to charge the power transistor's gate fast enough, and what it costs in driver power.",
    controls: [
      {k: "qg", label: "Total gate charge Qg", min: 5, max: 2000, value: 120, unit: "nC", log: true},
      {k: "dv", label: "Gate swing (e.g. −4…+18 V = 22 V)", min: 5, max: 30, step: 0.5, value: 22, unit: "V"},
      {k: "rg", label: "Total gate resistance", min: 0.5, max: 30, step: 0.1, value: 4, unit: "Ω"},
      {k: "fs", label: "Switching frequency", min: 1, max: 1000, value: 50, unit: "kHz", log: true},
    ],
    compute(v) {
      const ipk = v.dv / v.rg, t = (v.qg * 1e-9) / ipk, p = v.qg * 1e-9 * v.dv * v.fs * 1e3, rs = range(0.5, 30, 60);
      const refs = DATA.drivers, ok = refs.filter(r => r.a >= ipk).map(r => r.name);
      return {
        outputs: [["Peak current", `${num(ipk)} A`], ["Gate charge time ≈", si(t, "s")], ["Driver power", si(p, "W")], ["Drivers with enough peak current", ok.length ? ok.join(", ") : "add a booster stage", ok.length ? "ok" : "bad"]],
        eq: `I<sub>pk</sub> = ΔV<sub>G</sub> / R<sub>G</sub> &nbsp;·&nbsp; t ≈ Q<sub>G</sub> / I<sub>pk</sub> &nbsp;·&nbsp; P = Q<sub>G</sub> · ΔV<sub>G</sub> · f<sub>sw</sub>`,
        eqn: `${num(ipk)} A = ${num(v.dv)} V / ${num(v.rg)} Ω &nbsp;·&nbsp; P = ${num(v.qg)} nC · ${num(v.dv)} V · ${num(v.fs)} kHz = ${si(p, "W")}`,
        chart: {x: {min: 0.5, max: 30, label: "Total gate resistance (Ω)"}, y: {min: 0, max: 20, label: "Peak current (A)"},
          series: [{pts: rs.map(r => [r, v.dv / r]), width: 3}], hlines: refs.map(r => ({y: r.a, label: `${r.name} ${r.a} A`, color: r.ours ? C.blue : C.grey})), marks: [{x: v.rg, y: ipk, label: `${num(ipk)} A`}]},
        note: "The time is a lower bound: the current falls as the gate charges. A larger gate resistor slows the edge, which lowers dV/dt (and the CMTI needed) at the cost of switching loss.",
      };
    },
    related: [["CMTI visual", "#cmti"]],
  });

  V.push({
    id: "thermal", group: "Isolation and power", title: "Junction temperature",
    lead: "The die temperature is the ambient plus the power times the package's thermal resistance.",
    controls: [
      {k: "p", label: "Power dissipated", min: 0, max: 3, step: 0.01, value: 0.4, unit: "W"},
      {k: "ta", label: "Ambient", min: -40, max: 125, step: 1, value: 85, unit: "°C"},
      {k: "th", label: "Thermal resistance θJA", min: 20, max: 250, step: 1, value: 110, unit: "°C/W"},
      {k: "tj", label: "Maximum junction", type: "select", options: [["125", "125 °C"], ["150", "150 °C"]], value: "150"},
    ],
    compute(v) {
      const tj = v.ta + v.p * v.th, max = +v.tj, pmax = (max - v.ta) / v.th, ps = range(0, 3, 30);
      return {
        outputs: [["Junction temperature", `${num(tj)} °C`, tj > max ? "bad" : tj > max - 15 ? "warn" : "ok"], ["Headroom", `${num(max - tj)} °C`], ["Maximum power here", si(Math.max(0, pmax), "W")]],
        eq: `T<sub>J</sub> = T<sub>A</sub> + P · θ<sub>JA</sub>`,
        eqn: `${num(tj)} °C = ${v.ta} °C + ${num(v.p)} W · ${v.th} °C/W`,
        chart: {x: {min: 0, max: 3, label: "Power (W)"}, y: {min: v.ta - 5, max: 220, label: "Junction temperature (°C)"},
          series: [[35, "QFN with pad ≈ 35", C.teal], [70, "SOIC-16W ≈ 70", C.purple], [120, "SOIC-8 ≈ 120", C.grey]].map(([th, l, c]) => ({pts: ps.map(p => [p, v.ta + p * th]), color: c, width: 1.5, dash: "5 4", label: l}))
            .concat([{pts: ps.map(p => [p, v.ta + p * v.th]), width: 3, label: `θJA ${v.th}`}]),
          hlines: [{y: max, label: `T_J max ${max} °C`, color: C.red}], marks: [{x: v.p, y: tj, label: `${num(tj)} °C`}]},
        note: "θJA depends on the board as much as the package (copper area, layers): data-sheet values use a JEDEC test board. Typical values shown are indicative.",
      };
    },
  });

  // ------------------------------------------------------------------ page
  const groups = [...new Set(V.map(v => v.group))];
  const nav = $("#vz-nav"), panel = $("#vz-panel");
  nav.innerHTML = groups.map(g => `<div class="vz-g"><b>${esc(g)}</b>${V.filter(v => v.group === g).map(v => `<a href="#${v.id}" data-id="${v.id}">${esc(v.title)}</a>`).join("")}</div>`).join("");
  let cur = null, vals = {}, anim = null, phase = 0;

  const toPos = (c, x) => (c.log ? Math.round((1000 * (log10(x) - log10(c.min))) / (log10(c.max) - log10(c.min))) : x);
  const fromPos = (c, p) => (c.log ? +(10 ** (log10(c.min) + ((log10(c.max) - log10(c.min)) * p) / 1000)).toPrecision(3) : +p);
  const show = (c, x) => (c.type === "select" ? "" : `${num(x)}${c.unit ? " " + c.unit : ""}`);

  function open(id) {
    if (anim) { cancelAnimationFrame(anim); anim = null; }
    phase = 0;
    cur = V.find(v => v.id === id) || V[0];
    vals = Object.fromEntries(cur.controls.map(c => [c.k, c.value]));
    nav.querySelectorAll("a").forEach(a => a.classList.toggle("on", a.dataset.id === cur.id));
    panel.innerHTML = `<h2>${esc(cur.title)}</h2><p class="vz-lead">${esc(cur.lead)}</p>
      <div class="vz-body"><div class="vz-ctl">${cur.controls.map(c => c.type === "select"
        ? `<label class="vz-c"><span>${esc(c.label)}</span><select data-k="${c.k}">${c.options.map(([k, l]) => `<option value="${k}"${k === c.value ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`
        : `<label class="vz-c"><span>${esc(c.label)} <output data-o="${c.k}">${show(c, c.value)}</output></span><input type="range" data-k="${c.k}" min="${c.log ? 0 : c.min}" max="${c.log ? 1000 : c.max}" step="${c.log ? 1 : c.step || (c.max - c.min) / 200}" value="${toPos(c, c.value)}"></label>`).join("")}
        <div class="vz-btns">${cur.animate ? '<button type="button" class="small-btn vz-play">▶ Play</button>' : ""}<button type="button" class="outline secondary small-btn vz-reset">Reset</button></div></div>
        <div class="vz-out"><div class="vz-kpis"></div></div></div>
      <div class="vz-chartwrap"><svg class="vz-chart" role="img" aria-label="${esc(cur.title)}"></svg></div>
      <div class="vz-eq"><div class="vz-eq-sym"></div><div class="vz-eq-num"></div></div>
      <p class="vz-note"></p>${cur.related ? `<p class="small">Related: ${cur.related.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ")}</p>` : ""}`;
    panel.querySelectorAll("[data-k]").forEach(el => el.addEventListener("input", () => {
      const c = cur.controls.find(x => x.k === el.dataset.k);
      vals[c.k] = c.type === "select" ? el.value : fromPos(c, el.value);
      const o = panel.querySelector(`[data-o="${c.k}"]`);
      if (o) o.textContent = show(c, vals[c.k]);
      render();
    }));
    panel.querySelector(".vz-reset").addEventListener("click", () => open(cur.id));
    const play = panel.querySelector(".vz-play");
    if (play) play.addEventListener("click", () => {
      if (anim) { cancelAnimationFrame(anim); anim = null; play.textContent = "▶ Play"; return; }
      play.textContent = "❚❚ Pause";
      const step = () => { phase = (phase + 0.06) % (2 * Math.PI); render(); anim = requestAnimationFrame(step); };
      anim = requestAnimationFrame(step);
    });
    render();
  }
  function render() {
    const r = cur.compute(vals, phase);
    panel.querySelector(".vz-kpis").innerHTML = r.outputs.map(([l, val, tone]) => `<div class="vz-kpi${tone ? " t-" + tone : ""}${String(val).length > 22 ? " wide" : ""}"><span>${esc(l)}</span><b>${esc(val)}</b></div>`).join("");
    panel.querySelector(".vz-eq-sym").innerHTML = r.eq;
    panel.querySelector(".vz-eq-num").innerHTML = r.eqn;
    panel.querySelector(".vz-note").textContent = r.note;
    const svg = panel.querySelector(".vz-chart");
    if (r.bars) bars(svg, r.bars); else plot(svg, r.chart);
  }
  const route = () => open((location.hash || "").slice(1) || V[0].id);
  window.addEventListener("hashchange", route);
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 120); });
  route();
})();
