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

  // Skyworks / Qorvo RF parts (gain, NF, IP3, loss, band) for part suggestions; fetched once, when a visual needs them
  let PARTS = null, partsLoading = false;
  function loadParts() {
    if (PARTS || partsLoading) return;
    partsLoading = true;
    fetch("/api/visuals/rf-parts").then(r => r.json()).then(d => { PARTS = d.parts || []; if (cur && cur.parts) render(); })
      .catch(() => { PARTS = []; });
  }
  const covers = (p, f) => p.fmin <= f * 1.02 && p.fmax >= f * 0.98;
  // up to n of our parts of a stage type at frequency f: those that meet `ok` first, ranked by `score` (lower is better)
  function suggest(stages, f, ok, score, n = 3) {
    if (!PARTS) return null;
    const c = PARTS.filter(p => stages.includes(p.stage) && covers(p, f));
    const meet = c.filter(ok).sort((a, b) => score(a) - score(b));
    return meet.length ? {meet: true, list: meet.slice(0, n)} : {meet: false, list: c.sort((a, b) => score(a) - score(b)).slice(0, n)};
  }
  const spec = p => [p.gain != null ? `G ${num(p.gain)} dB` : "", p.nf != null ? `NF ${num(p.nf)} dB` : "", p.il != null ? `IL ${num(p.il)} dB` : "",
    p.iip3 != null ? `IIP3 ${num(p.iip3)} dBm` : "", `${si(p.fmin * 1e9, "Hz")}–${si(p.fmax * 1e9, "Hz")}`].filter(Boolean).join(" · ");
  const partLink = p => `<a href="/find?q=${encodeURIComponent(p.mpn)}">${esc(p.mpn)}</a> <span class="muted">${esc(p.mfr)}${p.preview ? " · preview" : ""}</span><br><small>${esc(spec(p))}</small>`;
  function suggestionHtml(s, empty) {
    if (s === null) return '<span class="muted small">loading parts…</span>';
    if (!s.list.length) return `<span class="muted small">${esc(empty)}</span>`;
    return `${s.meet ? "" : '<span class="small vz-near">closest, does not meet the target:</span>'}<ul class="vz-parts">${s.list.map(p => `<li>${partLink(p)}</li>`).join("")}</ul>`;
  }

  // ------------------------------------------------------------------ the visuals
  const V = [];

  const BLOCKER = v => v.mode === "blocker", LADDER = v => v.mode !== "blocker";
  V.push({
    id: "dbm", group: "RF links", title: "dBm: the power ladder",
    lead: "Every RF power on one logarithmic scale, from a GNSS signal at the antenna to a radar transmitter. Switch to the blocker view to see what a strong signal next to the band does to a receiver, and what linearity fixes it.",
    presetLabel: "Blocker scenarios",
    presets: [
      {label: "Car roof: V2X next to Wi-Fi", values: {mode: "blocker", f: 5.8, pw: -75, pb: -10, rej: 20, nf: 4, bw: 20, snr: 10, ia: -5, ib: 15, pt: "lna"},
        note: "<b>Conditions:</b> a 5.9 GHz V2X transmitter (+23 dBm) and a 5.8 GHz Wi-Fi receiver share the shark fin; antenna isolation about 20–35 dB, so the Wi-Fi input sees about −10 dBm next to its band (typical, est). A BAW coexistence filter adds about 20 dB rejection. <b>Applications:</b> roof antenna modules, telematics units with Wi-Fi hotspot."},
      {label: "GNSS L1 with an LTE / 5G transmitter", values: {mode: "blocker", f: 1.575, pw: -130, pb: -30, rej: 40, nf: 2, bw: 2, snr: -24, ia: -10, ib: 10, pt: "lna"},
        note: "<b>Conditions:</b> the car's own LTE/5G uplink (+23 dBm) about 50 dB away from the GNSS antenna (est); a SAW/BAW pre-filter gives about 40 dB at the uplink offset (typical). GNSS works below the noise thanks to correlation gain, so the SNR target is negative: tracking at C/N<sub>0</sub> ≈ 35–40 dB-Hz is about −20 to −28 dB in 2 MHz (typical, est). <b>Applications:</b> shark-fin GNSS, telematics, lane-level ADAS."},
      {label: "Base station: neighbour-cell blocker", values: {mode: "blocker", f: 1.9, pw: -100, pb: -43, rej: 0, nf: 2, bw: 5, snr: 0, ia: 0, ib: 20, pt: "lna"},
        note: "<b>Conditions:</b> an in-band blocker from a nearby cell; 3GPP base-station blocking tests use about −43 dBm in-band for wide-area base stations (typical, check the spec edition). No filter can remove an in-band blocker, so the LNA linearity decides. <b>Applications:</b> macro and small-cell receivers, repeaters."},
      {label: "Phone: own uplink into Wi-Fi 2.4 GHz", values: {mode: "blocker", f: 2.44, pw: -80, pb: -15, rej: 30, nf: 3, bw: 20, snr: 10, ia: -5, ib: 10, pt: "switch"},
        note: "<b>Conditions:</b> the phone's own LTE B40/B7 uplink next to 2.4 GHz Wi-Fi; antennas only about 10–15 dB apart (typical, est), coexistence filter about 30 dB. The antenna switch sees the blocker first, so its IIP3 matters as much as the LNA's. <b>Applications:</b> phones, hotspots, IoT gateways."},
    ],
    controls: [
      {k: "mode", label: "View", type: "select", options: [["ladder", "Power ladder"], ["blocker", "Strong blocker next to the band"]], value: "ladder"},
      {k: "p", label: "Power", min: -140, max: 70, step: 1, value: 20, unit: "dBm", when: LADDER},
      {k: "f", label: "Frequency", min: 0.05, max: 40, value: 2.4, unit: "GHz", log: true, when: BLOCKER},
      {k: "pw", label: "Wanted signal", min: -140, max: -20, step: 1, value: -80, unit: "dBm", when: BLOCKER},
      {k: "pb", label: "Blocker at the antenna (per tone)", min: -80, max: 20, step: 1, value: -20, unit: "dBm", when: BLOCKER},
      {k: "rej", label: "Filter rejection at the blocker", min: 0, max: 70, step: 1, value: 20, unit: "dB", when: BLOCKER},
      {k: "nf", label: "Receiver noise figure", min: 0.5, max: 15, step: 0.1, value: 3, unit: "dB", when: BLOCKER},
      {k: "bw", label: "Channel bandwidth", min: 0.01, max: 400, value: 20, unit: "MHz", log: true, when: BLOCKER},
      {k: "snr", label: "SNR the demodulator needs", min: -30, max: 30, step: 0.5, value: 10, unit: "dB", when: BLOCKER},
      {k: "ia", label: "Standard part: input IP3", min: -30, max: 40, step: 0.5, value: -5, unit: "dBm", when: BLOCKER},
      {k: "ib", label: "High-linearity part: input IP3", min: -30, max: 50, step: 0.5, value: 15, unit: "dBm", when: BLOCKER},
      {k: "pt", label: "Part to look for", type: "select", options: [["lna", "LNA"], ["switch", "Switch"]], value: "lna", when: BLOCKER},
    ],
    parts: true,
    compute(v) {
      if (v.mode !== "blocker") {
        const w = 1e-3 * undb(v.p), vr = Math.sqrt(w * 50);
        const refs = [[-130, "GNSS at antenna"], [-95, "BLE sensitivity"], [0, "1 mW"], [20, "Wi-Fi client"], [24, "Phone PA"], [30, "1 W"], [46, "Macro cell 40 W"], [60, "Radar 1 kW"]];
        return {
          outputs: [["Power", si(w, "W")], ["dBW", `${num(v.p - 30)} dBW`], ["Voltage into 50 Ω", si(vr, "V") + " rms"]],
          eq: `P<sub>dBm</sub> = 10 · log<sub>10</sub>( P / 1 mW )`,
          eqn: `${num(v.p)} dBm = 10 · log<sub>10</sub>( ${si(w, "W")} / 1 mW )`,
          chart: {x: {min: -140, max: 70, label: "Power (dBm)"}, y: {min: 1e-18, max: 1e5, log: true, label: "Power (W)", fmt: x => si(x, "W")},
            series: [{pts: range(-140, 70, 60).map(p => [p, 1e-3 * undb(p)])}],
            vlines: refs.map(([p, l], i) => ({x: p, label: l, row: i % 4, color: C.grey})), marks: [{x: v.p, y: w, label: `${num(v.p)} dBm = ${si(w, "W")}`}]},
          note: "Every 10 dB is a factor of 10 in power, every 3 dB a factor of 2. A receiver handles signals 20 orders of magnitude below what the transmitter next to it sends: that is why filters, isolation and linearity matter. Switch the view to see a blocker scenario.",
        };
      }
      // two blockers placed so that their 3rd-order product falls on the wanted channel; levels input-referred
      const pin = v.pb - v.rej, N = -174 + v.nf + db(v.bw * 1e6), im3 = iip3 => 3 * pin - 2 * iip3;
      const sinr = iip3 => v.pw - db(undb(N) + undb(im3(iip3)));
      const room = v.pw - v.snr, allow = room > N ? db(undb(room) - undb(N)) : -Infinity, need = (3 * pin - allow) / 2;
      const ok = iip3 => sinr(iip3) >= v.snr, comp = iip3 => pin > iip3 - 9.6;
      const tone = iip3 => (ok(iip3) && !comp(iip3) ? "ok" : comp(iip3) ? "bad" : "warn");
      const xs = range(-90, 20, 60);
      const stages = v.pt === "switch" ? ["switch"] : ["lna"];
      const sg = isFinite(need) ? suggest(stages, v.f, p => p.iip3 != null && p.iip3 >= need, p => (p.iip3 ?? -99) >= need ? (p.nf ?? p.il ?? 0) : 100 - (p.iip3 ?? -99)) : {meet: false, list: []};
      return {
        outputs: [["Blocker after the filter", `${num(pin)} dBm`], ["Noise floor", `${num(N)} dBm`],
          [`IM3 with IIP3 ${num(v.ia)} dBm`, `${num(im3(v.ia))} dBm → SINR ${num(sinr(v.ia))} dB${comp(v.ia) ? ", compressed" : ""}`, tone(v.ia)],
          [`IM3 with IIP3 ${num(v.ib)} dBm`, `${num(im3(v.ib))} dBm → SINR ${num(sinr(v.ib))} dB${comp(v.ib) ? ", compressed" : ""}`, tone(v.ib)],
          ["Input IP3 needed", isFinite(need) ? `≥ ${num(need)} dBm` : "wanted signal is below the noise: raise it or lower the NF", isFinite(need) ? "" : "bad"]],
        eq: `IM3<sub>in</sub> = 3·P<sub>blk</sub> − 2·IIP3 &nbsp;·&nbsp; SINR = P<sub>wanted</sub> − 10 log(10<sup>N/10</sup> + 10<sup>IM3/10</sup>) &nbsp;·&nbsp; IIP3<sub>min</sub> = (3·P<sub>blk</sub> − I<sub>allowed</sub>) / 2`,
        eqn: `IM3 = 3·(${num(pin)}) − 2·(${num(v.ia)}) = ${num(im3(v.ia))} dBm (standard) &nbsp;·&nbsp; ${num(im3(v.ib))} dBm (high linearity) &nbsp;·&nbsp; noise floor ${num(N)} dBm`,
        chart: {x: {min: -90, max: 20, label: "Blocker at the receiver input, per tone (dBm)"}, y: {min: -180, max: 10, label: "Level at the input (dBm)"},
          series: [{pts: xs.map(x => [x, 3 * x - 2 * v.ia]), color: C.orange, label: `IM3, IIP3 ${num(v.ia)}`}, {pts: xs.map(x => [x, 3 * x - 2 * v.ib]), color: C.green, label: `IM3, IIP3 ${num(v.ib)}`}],
          hlines: [{y: N, label: `noise floor ${num(N)}`, color: C.grey}, {y: v.pw, label: `wanted ${num(v.pw)}`, color: C.blue, dash: ""}, ...(isFinite(allow) ? [{y: allow, label: "max interference for the SNR", color: C.red}] : [])],
          vlines: [{x: pin, label: "blocker after filter", color: C.purple, row: 1}],
          marks: [{x: pin, y: im3(v.ia), color: C.orange, label: `${num(im3(v.ia))} dBm`}, {x: pin, y: im3(v.ib), color: C.green, label: `${num(im3(v.ib))} dBm`}]},
        html: `<div class="vz-sugg"><b>Our ${v.pt === "switch" ? "switches" : "LNAs"} at ${num(v.f)} GHz with input IP3 ≥ ${isFinite(need) ? num(need) + " dBm" : "–"}</b>${suggestionHtml(sg, "no part of ours covers this frequency with a stated IP3")}<p class="small muted">From catalogue key specs; IIP3 is taken from the data sheet or as OIP3 − gain. Check the full data sheet.</p></div>`,
        note: "Each 1 dB more blocker raises the IM3 product by 3 dB; each 1 dB more IIP3 lowers it by 2 dB. Filtering helps three times over (1 dB more rejection = 3 dB less IM3), but an in-band blocker can only be handled by linearity. If the blocker reaches the input 1 dB compression point (about IIP3 − 10 dB) the receiver is blocked outright.",
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
    explains: [["UWB", "/knowledge#p-uwb"], ["Broadcast radio tuners", "/knowledge#p-tuners"]],
    physics: [["Antennas and wavelength", "phys_antennas_wavelength"]],
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

  // receiver chain for the cascaded noise figure: loss stages (filter, switch) set gain = −loss and NF = loss
  const NF_TYPES = {filter: ["Filter", true, C.grey, ["filter"]], switch: ["Switch", true, C.teal, ["switch"]], lna: ["LNA", false, C.blue, ["lna"]],
    gain: ["Gain block", false, C.green, ["gain"]], mixer: ["Mixer", false, C.orange, ["mixer"]], if: ["ADC / IF", false, C.purple, []]};
  const NF_DEFAULT = () => [{t: "filter", g: -1, nf: 1}, {t: "lna", g: 18, nf: 0.8}, {t: "mixer", g: 8, nf: 9}, {t: "if", g: 0, nf: 20}];
  let chain = NF_DEFAULT();
  V.push({
    id: "nf", group: "Receivers", title: "Cascaded noise figure and sensitivity",
    explains: [["Front-end modules and LNAs", "/knowledge#p-front_ends"], ["Broadcast radio tuners", "/knowledge#p-tuners"]],
    physics: [["Gain and noise", "phys_noise_gain"]],
    lead: "Why the first stage decides the receiver. Build the chain below: drag blocks to reorder them, add or remove stages, and move each block's gain and noise figure. Our parts that meet each block's numbers at the chosen frequency are suggested underneath.",
    controls: [
      {k: "f", label: "Frequency (for part suggestions)", min: 0.05, max: 40, value: 2.4, unit: "GHz", log: true},
      {k: "bw", label: "Channel bandwidth", min: 0.01, max: 400, value: 20, unit: "MHz", log: true},
      {k: "snr", label: "SNR the demodulator needs", min: -5, max: 30, step: 0.5, value: 10, unit: "dB"},
    ],
    parts: true,
    setup(el, rerender) {
      chain = NF_DEFAULT();
      let drag = null;
      const slider = (i, key, label, min, max, step, val) => `<label class="vz-bs"><span>${label} <output>${num(val)} dB</output></span><input type="range" data-i="${i}" data-f="${key}" min="${min}" max="${max}" step="${step}" value="${val}" aria-valuetext="${num(val)} dB"></label>`;
      const draw = () => {
        el.innerHTML = `<div class="vz-chain" role="list" aria-label="Receiver chain">${chain.map((s, i) => {
          const [name, loss, color] = NF_TYPES[s.t];
          return `${i ? '<span class="vz-arrow" aria-hidden="true">→</span>' : ""}<div class="vz-blk" role="listitem" draggable="false" data-i="${i}" style="border-top-color:${color}">
            <div class="vz-blk-h"><span class="vz-grip" title="Drag to reorder" aria-hidden="true">⠿</span><b>${i + 1}. ${esc(name)}</b>
              <span class="vz-blk-b"><button type="button" data-mv="-1" data-i="${i}" title="Move earlier" aria-label="Move ${esc(name)} earlier"${i ? "" : " disabled"}>←</button><button type="button" data-mv="1" data-i="${i}" title="Move later" aria-label="Move ${esc(name)} later"${i < chain.length - 1 ? "" : " disabled"}>→</button><button type="button" data-rm="${i}" title="Remove" aria-label="Remove ${esc(name)}"${chain.length > 1 ? "" : " disabled"}>×</button></span></div>
            ${loss ? slider(i, "loss", "Loss", 0, 6, 0.1, s.nf) : slider(i, "g", "Gain", -10, 35, 0.5, s.g) + slider(i, "nf", "NF", 0.2, 30, 0.05, s.nf)}</div>`;
        }).join("")}</div>
        <div class="vz-add"><select aria-label="Stage to add">${Object.entries(NF_TYPES).map(([k, [n]]) => `<option value="${k}">${esc(n)}</option>`).join("")}</select><button type="button" class="small-btn outline">+ Add stage</button></div>`;
        el.querySelectorAll("input[data-f]").forEach(inp => inp.addEventListener("input", () => {
          const s = chain[+inp.dataset.i], x = +inp.value;
          if (inp.dataset.f === "loss") { s.g = -x; s.nf = x; } else s[inp.dataset.f] = x;
          inp.previousElementSibling.querySelector("output").textContent = `${num(x)} dB`;
          inp.setAttribute("aria-valuetext", `${num(x)} dB`);
          rerender();
        }));
        el.querySelectorAll("[data-mv]").forEach(btn => btn.addEventListener("click", () => {
          const i = +btn.dataset.i, j = i + +btn.dataset.mv;
          [chain[i], chain[j]] = [chain[j], chain[i]]; draw(); rerender();
        }));
        el.querySelectorAll("[data-rm]").forEach(btn => btn.addEventListener("click", () => { chain.splice(+btn.dataset.rm, 1); draw(); rerender(); }));
        el.querySelector(".vz-add button").addEventListener("click", () => {
          if (chain.length >= 8) return;
          const t = el.querySelector(".vz-add select").value, loss = NF_TYPES[t][1];
          chain.push(loss ? {t, g: -1.5, nf: 1.5} : t === "lna" ? {t, g: 16, nf: 1} : t === "mixer" ? {t, g: 8, nf: 9} : t === "if" ? {t, g: 0, nf: 20} : {t, g: 15, nf: 3});
          draw(); rerender();
        });
        el.querySelectorAll(".vz-blk").forEach(b => {
          // only the header drags the block, so the sliders inside stay usable
          const h = b.querySelector(".vz-blk-h");
          h.addEventListener("pointerdown", e => { if (!e.target.closest("button")) b.draggable = true; });
          b.addEventListener("pointerup", () => { b.draggable = false; });
          b.addEventListener("dragstart", e => { drag = +b.dataset.i; b.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(drag)); });
          b.addEventListener("dragend", () => { b.classList.remove("dragging"); b.draggable = false; });
          b.addEventListener("dragover", e => { e.preventDefault(); b.classList.add("over"); });
          b.addEventListener("dragleave", () => b.classList.remove("over"));
          b.addEventListener("drop", e => {
            e.preventDefault();
            const to = +b.dataset.i;
            if (drag === null || drag === to) return;
            const [m] = chain.splice(drag, 1); chain.splice(to, 0, m); drag = null; draw(); rerender();
          });
        });
      };
      draw();
    },
    compute(v) {
      let G = 1, F = 0;
      const terms = chain.map((s, i) => { const t = i === 0 ? undb(s.nf) : (undb(s.nf) - 1) / G; G *= undb(s.g); F += t; return t; });
      const nf = db(F), sens = -174 + nf + db(v.bw * 1e6) + v.snr, gain = db(G);
      const extra = terms.map((t, i) => (i === 0 ? t - 1 : t)), tot = extra.reduce((a, b) => a + b, 0) || 1;
      const rows = chain.map((s, i) => {
        const [name, loss, , stages] = NF_TYPES[s.t];
        if (!stages.length) return `<tr><td>${i + 1}. ${esc(name)}</td><td class="muted small">Not an RF catalogue part (ADC, IF stage or your own design)</td></tr>`;
        const sg = loss
          ? suggest(stages, v.f, p => p.il != null && p.il <= s.nf + 0.05, p => p.il ?? 99)
          : suggest(stages, v.f, p => (p.nf == null || p.nf <= s.nf + 0.05) && (p.gain == null || p.gain >= s.g - 0.5) && (p.nf != null || p.gain != null),
            p => (p.nf ?? 9) + Math.abs((p.gain ?? s.g) - s.g) / 4);
        const target = loss ? `loss ≤ ${num(s.nf)} dB` : `gain ≥ ${num(s.g)} dB, NF ≤ ${num(s.nf)} dB`;
        return `<tr><td>${i + 1}. ${esc(name)}<br><small class="muted">${target}</small></td><td>${suggestionHtml(sg, `no ${name.toLowerCase()} of ours covers ${num(v.f)} GHz in the catalogue`)}</td></tr>`;
      });
      return {
        outputs: [["System noise figure", `${num(nf)} dB`], ["Total gain", `${num(gain)} dB`], ["Noise floor", `${num(-174 + db(v.bw * 1e6) + nf)} dBm`], ["Sensitivity", `${num(sens)} dBm`]],
        eq: `F = F<sub>1</sub> + (F<sub>2</sub> − 1)/G<sub>1</sub> + (F<sub>3</sub> − 1)/(G<sub>1</sub>G<sub>2</sub>) + … &nbsp;·&nbsp; S = −174 dBm/Hz + NF + 10 log<sub>10</sub>(BW) + SNR`,
        eqn: `S = −174 + ${num(nf)} + ${num(db(v.bw * 1e6))} + ${v.snr} = ${num(sens)} dBm`,
        bars: chain.map((s, i) => ({label: `${i + 1}. ${NF_TYPES[s.t][0]}`, value: Math.max(extra[i], 0), color: NF_TYPES[s.t][2], text: `${num((100 * extra[i]) / tot, 2)} % of the noise`})),
        html: `<div class="vz-sugg"><b>Our parts for each block at ${num(v.f)} GHz</b><table class="vz-sugg-t small"><tbody>${rows.join("")}</tbody></table><p class="small muted">From catalogue key specs (typical values at the test frequency; active parts only). Check the full data sheet before choosing.</p></div>`,
        note: "Drag the filter behind the LNA and watch the noise figure drop: its loss now counts only divided by the LNA gain, but the LNA then sees every blocker unfiltered (see the dBm visual's blocker view). Every 0.1 dB of loss in front of the LNA is 0.1 dB of sensitivity, which is why low-loss BAW filters and LNAs with integrated filters sell.",
      };
    },
    related: [["Blocker scenario (dBm visual)", "#dbm"], ["LNAs on the RF coverage page", "/business/rf-coverage"]],
  });

  V.push({
    id: "ip3", group: "Receivers", title: "IP3 and intermodulation",
    explains: [["Front-end modules and PAs", "/knowledge#p-front_ends"], ["RF switches", "/knowledge#p-rf_switches"]],
    physics: [["Linearity", "phys_linearity"]],
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
    explains: [["RF switches and antenna tuning", "/knowledge#p-rf_switches"], ["Front-end modules", "/knowledge#p-front_ends"]],
    physics: [["Impedance matching and VSWR", "phys_matching_vswr"]],
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
    explains: [["RF filters", "/knowledge#p-filters"], ["Clocks and oscillators", "/knowledge#p-timing"]],
    physics: [["Resonance and Q", "phys_resonance_q"]],
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

  const EDGE = v => v.src === "edge", GATE = v => v.src === "gate", COSS = v => v.src === "coss";
  V.push({
    id: "cmti", group: "Isolation and power", title: "CMTI against the switching edge",
    explains: [["Digital isolators", "/knowledge#p-digital_isolators"], ["Isolated gate drivers", "/knowledge#p-gate_drivers"]],
    physics: [["Crossing an isolation barrier", "phys_isolation_coupling"]],
    lead: "The isolator must ride through the voltage slew of the power stage it sits across. Pick an application to load its typical conditions, then choose what sets the edge: the edge time, the gate drive, or the load current charging the switch capacitance.",
    presetLabel: "Applications",
    presets: [
      {label: "EV traction inverter, SiC 800 V", values: {v: 800, t: 20, rg: 10, vdrv: 18, vpl: 9, cgd: 20, il: 150, coss: 3000},
        note: "<b>Applications:</b> 800 V EV traction inverters, high-power DC fast chargers. <b>Sets the edge:</b> SiC MOSFET module switching 800 V in about 15–30 ns; the gate resistor (≈ 5–15 Ω) through the Miller capacitance, and at high current the load charging the module's output capacitance (typical, est). Engineers slow the edge with Rg to limit EMI and motor-winding stress, at the cost of switching loss."},
      {label: "On-board charger / PFC, GaN 400 V", values: {v: 400, t: 5, rg: 2, vdrv: 6, vpl: 3, cgd: 20, il: 15, coss: 150},
        note: "<b>Applications:</b> on-board chargers, totem-pole PFC, server and telecom power supplies. <b>Sets the edge:</b> GaN HEMTs switch 400 V in 2–10 ns; at these speeds the load current charging C<sub>oss</sub> usually limits dV/dt more than the gate (typical, est). 100+ kV/µs is common, so CMTI of 150–200 kV/µs is a selection criterion."},
      {label: "Motor drive, Si IGBT 600 V", values: {v: 600, t: 100, rg: 15, vdrv: 15, vpl: 10, cgd: 50, il: 50, coss: 8000},
        note: "<b>Applications:</b> industrial motor drives, pumps, HVAC compressors, 400 V-class EV auxiliaries. <b>Sets the edge:</b> IGBT turn-on/off of 50–200 ns, usually limited on purpose by the gate resistor to protect motor insulation (typical, est). Older 35–50 kV/µs isolators are enough here."},
      {label: "Solar string inverter, SiC 1500 V", values: {v: 1500, t: 50, rg: 10, vdrv: 18, vpl: 9, cgd: 30, il: 80, coss: 2700},
        note: "<b>Applications:</b> 1500 V utility-scale PV string inverters, battery storage converters. <b>Sets the edge:</b> high bus voltage with moderate edges (30–80 ns, typical, est); the voltage, not the speed, drives the dV/dt and the reinforced-insulation and creepage need."},
      {label: "48 V mild hybrid / telecom, Si MOSFET", values: {v: 48, t: 10, rg: 3, vdrv: 10, vpl: 5, cgd: 300, il: 100, coss: 20000},
        note: "<b>Applications:</b> 48 V belt starter-generators, DC/DC converters, telecom rectifiers. <b>Sets the edge:</b> low voltage but fast, high-current MOSFETs; dV/dt stays a few kV/µs, so CMTI is rarely the limit (typical, est)."},
      {label: "Industrial 24 V I/O", values: {v: 24, t: 50, rg: 20, vdrv: 5, vpl: 3, cgd: 200, il: 1, coss: 2000},
        note: "<b>Applications:</b> PLC digital I/O, fieldbus interfaces, sensor isolation. <b>Sets the edge:</b> logic-level switching and ground shifts; dV/dt below 1 kV/µs, but ground bounce and surge (IEC 61000-4-5) matter more than CMTI here (typical, est)."},
    ],
    controls: [
      {k: "src", label: "What sets the edge", type: "select", options: [["edge", "Edge time (bus voltage / rise time)"], ["gate", "Gate drive: Rg and Miller capacitance"], ["coss", "Load current charging the switch capacitance"]], value: "edge"},
      {k: "v", label: "Switched voltage (bus)", min: 12, max: 2000, value: 800, unit: "V", log: true},
      {k: "t", label: "Edge time (10–90 %)", min: 1, max: 1000, value: 20, unit: "ns", log: true, when: EDGE},
      {k: "rg", label: "Gate resistance (total)", min: 0.5, max: 50, value: 10, unit: "Ω", log: true, when: GATE},
      {k: "vdrv", label: "Gate drive voltage", min: 5, max: 25, step: 0.5, value: 18, unit: "V", when: GATE},
      {k: "vpl", label: "Miller plateau voltage", min: 2, max: 15, step: 0.5, value: 9, unit: "V", when: GATE},
      {k: "cgd", label: "Miller capacitance Cgd (at high voltage)", min: 0.5, max: 1000, value: 20, unit: "pF", log: true, when: GATE},
      {k: "il", label: "Load current", min: 0.5, max: 600, value: 150, unit: "A", log: true, when: COSS},
      {k: "coss", label: "Switch output capacitance Coss", min: 20, max: 50000, value: 3000, unit: "pF", log: true, when: COSS},
      {k: "k", label: "Design margin", min: 1, max: 4, step: 0.5, value: 2, unit: "×"},
      {k: "ciso", label: "Isolator barrier capacitance", min: 0.2, max: 5, step: 0.1, value: 1, unit: "pF"},
    ],
    compute(v) {
      const ig = Math.max(v.vdrv - v.vpl, 0) / v.rg;  // gate current during the Miller plateau (A)
      const dvdt = v.src === "gate" ? (ig / (v.cgd * 1e-12)) / 1e9 : v.src === "coss" ? (v.il / (v.coss * 1e-12)) / 1e9 : v.v / v.t;  // kV/µs
      const tedge = v.v / dvdt, need = dvdt * v.k, icm = v.ciso * 1e-12 * dvdt * 1e9, ts = range(1, 1000, 60, true);
      const refs = DATA.cmti, pass = refs.filter(r => r.kvus >= need).map(r => r.name);
      const how = {edge: [`dV/dt = ΔV / t<sub>edge</sub>`, `${num(dvdt)} kV/µs = ${num(v.v)} V / ${num(v.t)} ns`],
        gate: [`dV/dt ≈ I<sub>G</sub> / C<sub>gd</sub>, I<sub>G</sub> = (V<sub>drive</sub> − V<sub>plateau</sub>) / R<sub>G</sub>`, `I<sub>G</sub> = (${num(v.vdrv)} − ${num(v.vpl)}) V / ${num(v.rg)} Ω = ${num(ig)} A → ${num(dvdt)} kV/µs with ${num(v.cgd)} pF`],
        coss: [`dV/dt ≈ I<sub>load</sub> / C<sub>oss</sub>`, `${num(dvdt)} kV/µs = ${num(v.il)} A / ${num(v.coss)} pF`]}[v.src];
      return {
        outputs: [["Edge slew dV/dt", `${num(dvdt)} kV/µs`], ["Implied edge time", si(tedge * 1e-9, "s")], ["CMTI needed with margin", `${num(need)} kV/µs`],
          ["Common-mode current through the barrier", si(icm, "A")], ["Isolators that pass", pass.length ? pass.join(", ") : "none of the listed", pass.length ? "ok" : "bad"]],
        eq: `${how[0]} &nbsp;·&nbsp; CMTI<sub>min</sub> ≥ k · dV/dt &nbsp;·&nbsp; I<sub>CM</sub> = C<sub>iso</sub> · dV/dt`,
        eqn: `${how[1]} &nbsp;·&nbsp; × ${v.k} = ${num(need)} kV/µs &nbsp;·&nbsp; ${num(v.ciso)} pF × ${num(dvdt)} kV/µs = ${si(icm, "A")}`,
        chart: {x: {min: 1, max: 1000, log: true, label: "Edge time (ns)"}, y: {min: 0.1, max: 3000, log: true, label: "dV/dt (kV/µs)"},
          bands: [{x0: 1, x1: 10, label: "GaN", color: C.purple}, {x0: 10, x1: 50, label: "SiC", color: C.teal}, {x0: 50, x1: 300, label: "Si IGBT / MOSFET", color: C.grey}],
          series: [{pts: ts.map(t => [t, v.v / t]), width: 3, label: `${num(v.v)} V edge`}, {pts: ts.map(t => [t, (v.v / t) * v.k]), color: C.orange, dash: "6 4", label: `× ${v.k} margin`}],
          hlines: refs.map(r => ({y: r.kvus, label: `${r.name} ${r.kvus}`, color: r.ours ? C.blue : C.grey, dash: r.ours ? "" : "4 4", width: r.ours ? 2 : 1.2})),
          marks: [{x: clamp(tedge, 1, 1000), y: need, label: `needs ${num(need)} kV/µs`}]},
        html: `<div class="vz-sugg small"><b>What around the isolator sets the edge</b><ul><li><b>Switch technology:</b> GaN (2–10 ns) and SiC (10–50 ns) switch far faster than Si IGBTs (50–300 ns).</li><li><b>Gate resistor:</b> a larger R<sub>G</sub> slows the Miller plateau and the edge, trading switching loss for lower dV/dt and EMI.</li><li><b>Bus voltage:</b> dV/dt scales with it: 800 V platforms double the slew of 400 V ones at the same edge time.</li><li><b>Parasitic capacitance:</b> the switch's C<sub>gd</sub> and C<sub>oss</sub> set the edge; the isolator's own barrier capacitance turns dV/dt into common-mode current that the receiver must reject.</li></ul><p class="muted">Gate-drive and C<sub>oss</sub> formulas are first-order: C<sub>gd</sub> and C<sub>oss</sub> are strongly voltage dependent. Preset values are typical, estimated.</p></div>`,
        note: "800 V switched in 20 ns is 40 kV/µs: the older Si86xx (35 kV/µs minimum) is already short, the Si86S (100) and Si82Ex (200) have room. CMTI values are data-sheet minimums from the cross lists; check the test method (static vs dynamic) when comparing.",
      };
    },
    related: [["Gate-drive visual", "#gate"], ["Skyworks + Qorvo: isolation", "/portfolio#pick"], ["Search isolators", "/parts?cat=isolation"]],
  });

  // IEC 60664-1 creepage table (Table F.4 in TI SLUP419/SLUP421, F.5 in the 2020 edition), basic insulation (mm):
  // voltage → [MG I, MG II, MG III], pollution degree 2. Cross-checked with MINMAX's reproduction (Oct 2026).
  const CREEP = [[50, .6, .85, 1.2], [63, .63, .9, 1.25], [80, .67, .95, 1.3], [100, .71, 1, 1.4], [125, .75, 1.05, 1.5], [160, .8, 1.1, 1.6], [200, 1, 1.4, 2], [250, 1.25, 1.8, 2.5], [320, 1.6, 2.2, 3.2], [400, 2, 2.8, 4], [500, 2.5, 3.6, 5], [630, 3.2, 4.5, 6.3], [800, 4, 5.6, 8], [1000, 5, 7.1, 10]];
  // pollution degree 1 (all groups) and 3 ([MG I, MG II, MG III])
  const CREEP1 = [[50, .18], [63, .2], [80, .22], [100, .25], [125, .28], [160, .32], [200, .42], [250, .56], [320, .75], [400, 1], [500, 1.3], [630, 1.8], [800, 2.4], [1000, 3.2]];
  const CREEP3 = [[50, 1.5, 1.7, 1.9], [63, 1.6, 1.8, 2], [80, 1.7, 1.9, 2.1], [100, 1.8, 2, 2.2], [125, 2, 2.2, 2.4], [160, 2.1, 2.3, 2.5], [200, 2.5, 2.8, 3.2], [250, 3.2, 3.6, 4], [320, 4, 4.5, 5], [400, 5, 5.6, 6.3], [500, 6.3, 7.1, 8], [630, 8, 9, 10], [800, 10, 11, 12.5], [1000, 12.5, 14, 16]];
  const creep = (u, g, pd = 2) => {
    const T = pd === 1 ? CREEP1 : pd === 3 ? CREEP3 : CREEP, c = pd === 1 ? 1 : g;
    if (u <= T[0][0]) return T[0][c];
    for (let i = 1; i < T.length; i++) if (u <= T[i][0]) { const [a, b] = [T[i - 1], T[i]]; return a[c] + ((b[c] - a[c]) * (u - a[0])) / (b[0] - a[0]); }
    return T[T.length - 1][c];
  };
  V.push({
    id: "creep", group: "Isolation and power", title: "Creepage against working voltage",
    explains: [["Digital isolators", "/knowledge#p-digital_isolators"], ["Isolated gate drivers", "/knowledge#p-gate_drivers"]],
    physics: [["Creepage and clearance", "phys_creepage_clearance"]],
    lead: "The distance along the package surface between the two sides must grow with the working voltage, the pollution and the insulating material.",
    controls: [
      {k: "u", label: "Working voltage", min: 50, max: 1000, step: 10, value: 400, unit: "V rms"},
      {k: "g", label: "Mold compound (material group)", type: "select", options: [["1", "I (CTI ≥ 600)"], ["2", "II (CTI 400–600)"], ["3", "III (CTI 175–400)"]], value: "1"},
      {k: "ins", label: "Insulation", type: "select", options: [["1", "Basic"], ["2", "Reinforced (2×)"]], value: "2"},
      {k: "pd", label: "Pollution degree", type: "select", options: [["1", "PD1 (sealed, coated or potted)"], ["2", "PD2 (closed housing, occasional condensation)"], ["3", "PD3 (condensation or conductive dust expected)"]], value: "2"},
    ],
    compute(v) {
      const g = +v.g, k = +v.ins, pd = +(v.pd || 2), need = creep(v.u, g, pd) * k, us = range(50, 1000, 60);
      const pk = DATA.creepage, fit = pk.filter(p => p.mm >= need).map(p => `${p.code} (${p.mm} mm)`);
      return {
        outputs: [["Creepage required", `${num(need)} mm`], ["Packages that reach it", fit.length ? fit.slice(0, 4).join(", ") : "none of the listed", fit.length ? "ok" : "bad"]],
        eq: `creepage ≥ table value (U<sub>rms</sub>, pollution degree, material group) × 2 for reinforced`,
        eqn: `${num(v.u)} V rms, PD${pd}, group ${pd === 1 ? "any" : ["", "I", "II", "III"][g]} → ${num(creep(v.u, g, pd))} mm${k === 2 ? ` × 2 = ${num(need)} mm` : ""}`,
        chart: {x: {min: 50, max: 1000, label: "Working voltage (V rms or DC)"}, y: {min: 0, max: pd === 3 ? 34 : 22, label: "Creepage (mm)"},
          series: [1, 2, 3].map(gr => ({pts: us.map(u => [u, creep(u, gr, pd) * k]), color: [C.blue, C.orange, C.purple][gr - 1], width: gr === g ? 3 : 1.5, dash: gr === g ? "" : "5 4", label: `group ${["", "I", "II", "III"][gr]}`})),
          hlines: pk.map(p => ({y: p.mm, label: `${p.code} ${p.mm} mm`, color: C.grey})), marks: [{x: v.u, y: need, label: `${num(need)} mm`}]},
        note: "Values from IEC 60664-1's creepage table as reproduced by TI (SLUP419/SLUP421) and MINMAX, linearly interpolated; DC working voltage is used like rms. Indicative only: the end-product standard (IEC 62368-1, 61800-5-1, 62109-1) decides. Package creepage is what the data sheets in our cross lists state; wide bodies (8 mm) and extra-wide (14.5 mm) exist for 800 V+ systems. At 800 V, PD2, group I, reinforced needs 8 mm; at PD3 no single package is enough. See the creepage guide for the full table.",
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

  // ---- physics visuals (22 Oct 2026): each names the product families it explains and its physics topic
  const cmul = (a, b) => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
  const cdiv = (a, b) => { const d = b[0] * b[0] + b[1] * b[1]; return [(a[0] * b[0] + a[1] * b[1]) / d, (a[1] * b[0] - a[0] * b[1]) / d]; };
  const cabs = a => Math.hypot(a[0], a[1]);
  V.push({
    id: "bvd", group: "Matching and filters", title: "Acoustic resonator (SAW / BAW)",
    lead: "A piezoelectric resonator has a series resonance (impedance dips) and, just above it, a parallel resonance (impedance peaks). The coupling k² sets their spacing and so the widest filter it can build; Q sets how sharp they are.",
    explains: [["RF filters, duplexers and multiplexers", "/knowledge#p-filters"], ["Clocks and oscillators (BAW references)", "/knowledge#p-timing"]],
    physics: [["Piezoelectricity and acoustic resonators", "phys_piezo_acoustic"], ["Resonance and Q", "phys_resonance_q"]],
    controls: [
      {k: "fs", label: "Series resonance fs", min: 0.5, max: 8, value: 2.5, unit: "GHz", log: true},
      {k: "k2", label: "Coupling k²eff", min: 1, max: 14, step: 0.1, value: 6.5, unit: "%"},
      {k: "q", label: "Resonator Q", min: 50, max: 4000, value: 2000, unit: "", log: true},
      {k: "c0", label: "Static capacitance C0", min: 0.2, max: 5, value: 1, unit: "pF", log: true},
    ],
    presets: [
      {label: "BAW 2.5 GHz (AlN)", values: {fs: 2.5, k2: 6.5, q: 2000, c0: 1.2}, note: "Typical aluminium-nitride BAW: about 6–7 % coupling, Q in the low thousands."},
      {label: "SAW 900 MHz", values: {fs: 0.9, k2: 7.5, q: 900, c0: 3.5}, note: "Lithium-tantalate SAW at a low band: good coupling, lower Q than BAW."},
      {label: "Wide band 3.7 GHz (ScAlN)", values: {fs: 3.7, k2: 11, q: 1200, c0: 0.9}, note: "Scandium-doped AlN raises the coupling for wide 5G bands such as n77, at some cost in Q."},
    ],
    compute(v) {
      const fs = v.fs * 1e9, k2 = v.k2 / 100, C0 = v.c0 * 1e-12, fp = fs / (1 - (4 * k2) / (Math.PI * Math.PI));
      const C1 = C0 * ((fp / fs) ** 2 - 1), L1 = 1 / ((2 * Math.PI * fs) ** 2 * C1), R1 = (2 * Math.PI * fs * L1) / v.q;
      const z = f => { const w = 2 * Math.PI * f, zm = [R1, w * L1 - 1 / (w * C1)], z0 = [0, -1 / (w * C0)]; return cabs(cdiv(cmul(zm, z0), [zm[0] + z0[0], zm[1] + z0[1]])); };
      const a = fs - (fp - fs) * 1.5, b = fp + (fp - fs) * 1.5, fsx = range(a, b, 500);
      const zs = fsx.map(z), lo = 10 ** Math.floor(log10(Math.min(...zs))), hi = 10 ** Math.ceil(log10(Math.max(...zs)));
      const t = 11000 / (2 * fs);
      return {
        outputs: [["Parallel resonance fp", si(fp, "Hz")], ["Spacing fp − fs", si(fp - fs, "Hz")], ["Rough ladder-filter bandwidth ≈ 2 (fp − fs)", si(2 * (fp - fs), "Hz")],
          ["|Z| at fs / at fp", `${si(z(fs), "Ω")} / ${si(z(fp), "Ω")}`], ["C0 reactance at fs (aim ≈ 50 Ω)", si(1 / (2 * Math.PI * fs * C0), "Ω")], ["AlN film thickness for a BAW ≈ v / 2fs", si(t, "m")]],
        eq: `f<sub>p</sub> = f<sub>s</sub> / (1 − 4k²/π²) &nbsp;·&nbsp; C<sub>1</sub> = C<sub>0</sub> ((f<sub>p</sub>/f<sub>s</sub>)² − 1) &nbsp;·&nbsp; BAW: f ≈ v / (2t)`,
        eqn: `f<sub>p</sub> = ${si(fs, "Hz")} / (1 − 4 · ${num(k2)} / π²) = ${si(fp, "Hz")} &nbsp;·&nbsp; t ≈ 11,000 m/s / (2 · ${si(fs, "Hz")}) = ${si(t, "m")}`,
        chart: {x: {min: a, max: b, label: "Frequency", fmt: x => si(x, "Hz")}, y: {min: lo, max: hi, log: true, label: "Impedance |Z|", fmt: x => si(x, "Ω")},
          series: [{pts: fsx.map((f, i) => [f, zs[i]]), width: 3}], hlines: [{y: 50, label: "50 Ω"}],
          vlines: [{x: fs, label: "fs", color: C.green}, {x: fp, label: "fp", color: C.orange}]},
        note: "Model: Butterworth-Van Dyke (a series R-L-C branch for the moving crystal, in parallel with the plate capacitance C0). In a ladder filter, series resonators sit at the band centre at fs and shunt resonators are tuned lower so their fp lands there; the pass band can only be about as wide as the fs–fp gap, which is why wide 5G bands need high-coupling materials. Higher Q gives a deeper dip, a taller peak, lower loss and steeper band edges.",
      };
    },
    related: [["LC resonance and Q", "#lc"], ["Band-pass filter", "#filter"]],
  });

  const besselJ = (n, x) => { let s = 0; const N = Math.max(400, Math.ceil(4 * Math.abs(x)) + 200); for (let i = 0; i <= N; i++) { const t = (Math.PI * i) / N; s += (i === 0 || i === N ? 0.5 : 1) * Math.cos(n * t - x * Math.sin(t)); } return s / N; };
  V.push({
    id: "mod", group: "Broadcast radio", title: "AM vs FM modulation",
    lead: "The same audio tone carried two ways: AM changes the carrier's strength, FM changes its frequency. Compare the waveforms, then the spectra and the bandwidth each needs.",
    explains: [["Broadcast radio tuners", "/knowledge#p-tuners"]],
    physics: [["AM and FM modulation", "phys_am_fm"], ["Mixing and the superheterodyne", "phys_mixing_superhet"]],
    animate: true,
    controls: [
      {k: "view", label: "Show", type: "select", options: [["wave", "Waveforms (time)"], ["spec", "Spectrum (frequency)"]], value: "wave"},
      {k: "fm", label: "Audio tone fm", min: 0.1, max: 15, value: 1, unit: "kHz", log: true},
      {k: "m", label: "AM depth m", min: 0, max: 1, step: 0.01, value: 0.6, unit: ""},
      {k: "df", label: "FM deviation Δf", min: 0.5, max: 100, value: 3, unit: "kHz", log: true},
    ],
    presets: [
      {label: "AM broadcast", values: {fm: 4.5, m: 0.8, df: 3}, note: "AM stations are spaced 9 or 10 kHz apart, so the audio is limited to about 4.5–5 kHz."},
      {label: "FM broadcast", values: {fm: 15, m: 0.6, df: 75}, note: "Broadcast FM: ±75 kHz deviation and 15 kHz audio – Carson's rule gives 180 kHz, inside the 200 kHz channel."},
      {label: "Narrow-band FM (voice)", values: {fm: 3, m: 0.6, df: 2.5}, note: "Two-way radio uses ±2.5 or ±5 kHz deviation for 12.5 or 25 kHz channels."},
    ],
    compute(v, phase = 0) {
      const beta = v.df / v.fm, carson = 2 * (v.df + v.fm), amBw = 2 * v.fm, sbPct = (100 * v.m * v.m) / (2 + v.m * v.m);
      const j0 = besselJ(0, beta), outputs = [["AM bandwidth 2 fm", `${num(amBw)} kHz`], ["FM index β = Δf / fm", num(beta)],
        ["FM bandwidth (Carson) 2 (Δf + fm)", `${num(carson)} kHz`], ["FM needs × the AM bandwidth", num(carson / amBw)],
        ["AM power in the sidebands (the audio)", `${num(sbPct)} %`], ["FM power left in the carrier J0(β)²", `${num(100 * j0 * j0)} %`]];
      const eq = `AM: s = [1 + m cos(2π f<sub>m</sub>t)] cos(2π f<sub>c</sub>t) &nbsp;·&nbsp; FM: s = cos(2π f<sub>c</sub>t + β sin(2π f<sub>m</sub>t)), β = Δf / f<sub>m</sub> &nbsp;·&nbsp; B<sub>FM</sub> ≈ 2(Δf + f<sub>m</sub>)`;
      const eqn = `β = ${num(v.df)} / ${num(v.fm)} = ${num(beta)} &nbsp;·&nbsp; B<sub>FM</sub> ≈ 2 (${num(v.df)} + ${num(v.fm)}) = ${num(carson)} kHz &nbsp;·&nbsp; B<sub>AM</sub> = ${num(amBw)} kHz`;
      let chart;
      if (v.view === "spec") {
        const span = Math.max(1.25 * carson / 2, 3 * v.fm), nmax = Math.min(400, Math.ceil(span / v.fm) + 1), series = [];
        for (let n = -nmax; n <= nmax; n++) {
          const lvl = 20 * log10(Math.abs(besselJ(Math.abs(n), beta)) + 1e-9);
          if (lvl > -60) series.push({pts: [[n * v.fm, -60], [n * v.fm, lvl]], color: C.blue, width: 2});
        }
        const am = [[0, 0], [-v.fm, 20 * log10(v.m / 2 + 1e-9)], [v.fm, 20 * log10(v.m / 2 + 1e-9)]];
        am.forEach(([x, y]) => series.push({pts: [[x, -60], [x, y]], color: C.orange, width: 5, opacity: 0.55}));
        series.push({pts: [[0, -99], [0, -99]], color: C.orange, label: "AM"}, {pts: [[0, -99], [0, -99]], color: C.blue, label: "FM"});
        chart = {x: {min: -span, max: span, label: "Offset from the carrier (kHz)"}, y: {min: -60, max: 3, label: "Level (dB, carrier = 0)"}, series,
          bands: [{x0: -carson / 2, x1: carson / 2, color: C.blue, opacity: 0.07, label: "FM (Carson)"}, {x0: -v.fm, x1: v.fm, color: C.orange, opacity: 0.12}]};
      } else {
        const fc = 12, ts = range(0, 2, 900), sh = phase / (2 * Math.PI), bd = Math.min(beta, 6);
        chart = {x: {min: 0, max: 2, label: "Time (periods of the audio tone)"}, y: {min: -3.2, max: 3.2, label: "Amplitude"},
          series: [
            {pts: ts.map(t => [t, 1.6 + 0.75 * (1 + v.m * Math.cos(2 * Math.PI * (t + sh))) * Math.cos(2 * Math.PI * fc * t) / (1 + v.m) * 1.5]), color: C.orange, width: 1.6, label: "AM"},
            {pts: ts.map(t => [t, -1.6 + 1.1 * Math.cos(2 * Math.PI * fc * t + bd * Math.sin(2 * Math.PI * (t + sh)))]), color: C.blue, width: 1.6, label: "FM"},
            {pts: ts.map(t => [t, 1.6 + 1.125 * (1 + v.m * Math.cos(2 * Math.PI * (t + sh))) / (1 + v.m)]), color: C.grey, width: 1.2, dash: "4 3"},
          ]};
      }
      return {outputs, eq, eqn, chart,
        note: "Waveforms: the carrier is drawn only 12 times faster than the tone so you can see it (a real FM station's carrier is about 100 MHz) and the FM swing is capped for drawing. AM's envelope is the audio itself, so any noise that changes the amplitude is heard; FM ignores amplitude, which is why it sounds cleaner and the stronger station 'captures' the receiver. The price is bandwidth: broadcast FM needs about 20 times more than AM."};
    },
    related: [["Wavelength and antenna size", "#wave"], ["Cascaded noise figure and sensitivity", "#nf"]],
  });

  const IB = {a: [12e3, 20e6, "12 kHz – 20 MHz (SerDes, SONET)"], b: [1e3, 100e6, "1 kHz – 100 MHz (wide)"], c: [10e3, 1e6, "10 kHz – 1 MHz (close-in)"]};
  V.push({
    id: "jitter", group: "Timing", title: "Phase noise to jitter",
    lead: "A clock's phase noise, measured in dBc/Hz at each offset from the carrier, adds up to its timing jitter. Move the PLL's in-band noise, loop bandwidth and noise floor and see the jitter, and what it does to an ADC or a radio.",
    explains: [["Clocks, oscillators and network timing", "/knowledge#p-timing"], ["Front ends (LO quality)", "/knowledge#p-front_ends"]],
    physics: [["Phase noise and jitter", "phys_phase_noise_jitter"], ["Phase-locked loops", "phys_pll"]],
    controls: [
      {k: "l0", label: "In-band phase noise", min: -150, max: -80, step: 1, value: -135, unit: "dBc/Hz"},
      {k: "bw", label: "PLL loop bandwidth", min: 1, max: 10000, value: 200, unit: "kHz", log: true},
      {k: "fl", label: "Noise floor", min: -175, max: -135, step: 1, value: -160, unit: "dBc/Hz"},
      {k: "f0", label: "Clock frequency", min: 10, max: 3000, value: 156.25, unit: "MHz", log: true},
      {k: "fin", label: "ADC input frequency", min: 1, max: 6000, value: 1000, unit: "MHz", log: true},
      {k: "ib", label: "Integration band", type: "select", options: Object.entries(IB).map(([k, x]) => [k, x[2]]), value: "a"},
    ],
    compute(v) {
      const L = f => 10 * log10(10 ** (v.l0 / 10) / (1 + (f / (v.bw * 1e3)) ** 2) + 10 ** (v.fl / 10));
      const [f1, f2] = IB[v.ib], fx = range(f1, f2, 600, true);
      let s = 0;
      for (let i = 1; i < fx.length; i++) s += 0.5 * (10 ** (L(fx[i]) / 10) + 10 ** (L(fx[i - 1]) / 10)) * (fx[i] - fx[i - 1]);
      const phi = Math.sqrt(2 * s), tj = phi / (2 * Math.PI * v.f0 * 1e6), snr = -20 * log10(2 * Math.PI * v.fin * 1e6 * tj);
      const fp = range(100, 1e8, 300, true);
      return {
        outputs: [["RMS jitter", si(tj, "s"), tj < 100e-15 ? "ok" : tj > 1e-12 ? "bad" : ""], ["RMS phase error", `${num(phi * 180 / Math.PI)}°`],
          ["ADC SNR limit at the input frequency", `${num(snr)} dB`], ["≈ effective bits (ENOB) limit", num((snr - 1.76) / 6.02)], ["EVM floor ≈ phase error", `${num(100 * phi)} %`]],
        eq: `σ<sub>φ</sub> = √(2 ∫ 10<sup>L(f)/10</sup> df) &nbsp;·&nbsp; σ<sub>t</sub> = σ<sub>φ</sub> / (2π f<sub>0</sub>) &nbsp;·&nbsp; SNR = −20 log<sub>10</sub>(2π f<sub>in</sub> σ<sub>t</sub>)`,
        eqn: `σ<sub>t</sub> = ${num(phi)} rad / (2π · ${si(v.f0 * 1e6, "Hz")}) = ${si(tj, "s")} &nbsp;·&nbsp; SNR = −20 log(2π · ${si(v.fin * 1e6, "Hz")} · ${si(tj, "s")}) = ${num(snr)} dB`,
        chart: {x: {min: 100, max: 1e8, log: true, label: "Offset from the carrier", fmt: x => si(x, "Hz")}, y: {min: -180, max: -60, label: "Phase noise L(f) (dBc/Hz)"},
          series: [{pts: fp.map(f => [f, L(f)]), width: 3}], bands: [{x0: f1, x1: f2, color: C.blue, opacity: 0.08, label: "integrated"}],
          vlines: [{x: v.bw * 1e3, label: "loop bandwidth", color: C.orange}], hlines: [{y: v.fl, label: "floor"}]},
        note: "Simplified PLL: flat in-band noise up to the loop bandwidth, falling 20 dB per decade beyond it, down to the output noise floor. Real plots also rise close to the carrier and may have spurs. Jitter numbers only compare over the same band. Modern clock generators and jitter attenuators reach roughly 50–150 fs rms over 12 kHz–20 MHz; at 1 GHz ADC input, 100 fs limits the SNR to about 64 dB.",
      };
    },
  });

  V.push({
    id: "swloss", group: "Isolation and power", title: "Switching loss vs frequency",
    lead: "Conduction loss stays the same at any switching frequency; switching loss grows with every edge. Faster edges (SiC, GaN, a strong gate driver) move the crossover up, so the converter can switch faster with smaller magnetics.",
    explains: [["Isolated gate drivers", "/knowledge#p-gate_drivers"], ["Power management and motor control", "/knowledge#p-power_motor"]],
    physics: [["Switching and conduction losses", "phys_switching_losses"], ["Energy in inductors and capacitors", "phys_lc_energy"]],
    controls: [
      {k: "v", label: "Bus voltage", min: 12, max: 1000, value: 400, unit: "V", log: true},
      {k: "i", label: "Load current", min: 1, max: 300, value: 30, unit: "A", log: true},
      {k: "t", label: "Edge time tr + tf", min: 2, max: 500, value: 40, unit: "ns", log: true},
      {k: "coss", label: "Output capacitance Coss", min: 10, max: 2000, value: 150, unit: "pF", log: true},
      {k: "ron", label: "On-resistance", min: 1, max: 200, value: 25, unit: "mΩ", log: true},
      {k: "fs", label: "Switching frequency", min: 5, max: 2000, value: 50, unit: "kHz", log: true},
    ],
    presets: [
      {label: "Si IGBT, 400 V", values: {v: 400, i: 30, t: 300, coss: 200, ron: 50, fs: 16}, note: "Slow edges keep IGBT inverters at a few to about 20 kHz."},
      {label: "SiC MOSFET, 800 V", values: {v: 800, i: 30, t: 30, coss: 120, ron: 25, fs: 50}, note: "SiC edges of tens of ns allow 50–100 kHz – and 50–100 V/ns dV/dt, hence the CMTI rating of the gate driver."},
      {label: "GaN HEMT, 48 V", values: {v: 48, i: 20, t: 4, coss: 300, ron: 5, fs: 500}, note: "GaN at 48 V switches in a few ns, so 0.5–2 MHz converters with tiny inductors are possible."},
    ],
    compute(v) {
      const kSw = 0.5 * v.v * v.i * v.t * 1e-9 + 0.5 * v.coss * 1e-12 * v.v * v.v, pc = v.i * v.i * v.ron * 1e-3 * 0.5;
      const f = v.fs * 1e3, ps = kSw * f, fx = range(5e3, 2e6, 200, true), cross = pc / kSw;
      const Lh = (v.v / 2) * 0.5 / (0.3 * v.i * f), E = 0.5 * Lh * v.i * v.i;
      const all = fx.map(x => pc + kSw * x), hi = 10 ** Math.ceil(log10(Math.max(...all, pc * 2))), lo = Math.max(1e-3, 10 ** Math.floor(log10(Math.min(pc, kSw * 5e3))));
      return {
        outputs: [["Conduction loss (50 % duty)", si(pc, "W")], ["Switching loss", si(ps, "W"), ps > pc ? "bad" : ""], ["Total per switch", si(pc + ps, "W")],
          ["Crossover frequency", si(cross, "Hz")], ["Buck inductor for 30 % ripple", si(Lh, "H")], ["Energy it stores ½ L I²", si(E, "J")]],
        eq: `P<sub>cond</sub> = I² R<sub>on</sub> D &nbsp;·&nbsp; P<sub>sw</sub> ≈ (½ V I (t<sub>r</sub>+t<sub>f</sub>) + ½ C<sub>oss</sub> V²) f<sub>sw</sub> &nbsp;·&nbsp; L = V<sub>out</sub>(1 − D) / (ΔI f<sub>sw</sub>)`,
        eqn: `P<sub>sw</sub> ≈ (½ · ${num(v.v)} V · ${num(v.i)} A · ${num(v.t)} ns + ½ · ${num(v.coss)} pF · (${num(v.v)} V)²) · ${num(v.fs)} kHz = ${si(ps, "W")}`,
        chart: {x: {min: 5e3, max: 2e6, log: true, label: "Switching frequency", fmt: x => si(x, "Hz")}, y: {min: lo, max: hi, log: true, label: "Loss per switch", fmt: x => si(x, "W")},
          series: [{pts: fx.map(x => [x, pc]), color: C.green, width: 2, dash: "6 4", label: "conduction"}, {pts: fx.map(x => [x, kSw * x]), color: C.orange, width: 2, label: "switching"},
            {pts: fx.map((x, i) => [x, all[i]]), color: C.blue, width: 3, label: "total"}],
          marks: [{x: f, y: pc + ps, label: si(pc + ps, "W")}], vlines: [{x: cross, label: "crossover", color: C.grey}]},
        note: "A first estimate for one hard-switched transistor (no diode reverse recovery, no soft switching). Halving the edge time halves the overlap loss, which needs about twice the gate-drive peak current and gives twice the dV/dt – so the gate driver's peak current and CMTI decide how far the customer can push the frequency. Higher frequency then shrinks the inductor: the stored energy ½ L I² falls in proportion.",
      };
    },
    related: [["Gate-drive current and power", "#gate"], ["CMTI against the switching edge", "#cmti"], ["Junction temperature", "#thermal"]],
  });

  // EFT burst (IEC 61000-4-4) and CISPR 25/32 what-if for an isolated design with an Si88x2x (digital isolator +
  // DC-DC controller + external transformer). Data-sheet numbers (Si88x2x, Tables 6 and 8): CMTI 40 kV/µs min,
  // 100 typ; input-output capacitance 1.4 pF. Everything else is a relative capacitive-divider estimate (est) for
  // comparing setups, not a pass/fail prediction. Note: /engineering/emc_eft_cispr.
  const SI88 = {cmtiMin: 40, cmtiTyp: 100, cio: 1.4};
  const EFT = v => v.mode === "eft", CIS = v => v.mode === "cispr";
  const ser = (a, b) => (a * b) / (a + b);
  const EMC_DEF = {mode: "eft", inj: "all", tie: "a", cdn: "33", y: "0", dcdc: "on", sec: "float", std: "c25", kv: "1", cinj: 1000, cra: 20, crb: 20, cww: 20};
  // charge one 5/50 ns pulse (50 Ω source) pushes through the coupling capacitor into a low-impedance input (est)
  const pulseCharge = (() => {
    const shape = t => Math.exp(-t / 72) - Math.exp(-t / 1.9);  // ns; about 5 ns rise, 50 ns half width
    let pk = 0;
    for (let t = 0; t < 60; t += 0.05) pk = Math.max(pk, shape(t));
    const run = cNf => {
      let vc = 0, q = 0;
      for (let t = 0; t < 600; t += 0.05) { const i = (shape(t) / pk - vc) / 50; vc += (i * 0.05) / cNf; q += Math.max(i, 0) * 0.05; }
      return q;
    };
    const q33 = run(33);
    return {"33": 1, "3.3": run(3.3) / q33};
  })();
  function emcModel(v) {
    const kv = +v.kv, cy = +v.y * 1000, ccdn = v.cdn === "33" ? 33000 : 3300;  // pF
    const cww = v.cww, cx = SI88.cio + cww + cy;  // the transformer is fitted whether or not it switches
    const bonded = v.sec === "bond", crb = bonded ? 1e7 : v.crb;
    const gen = (kv * 1000) / 5;  // kV/µs: V_burst / 5 ns rise
    const gndb = v.inj === "n" && v.tie === "b";
    let share, chit;
    if (gndb) { share = 1; chit = cx + crb; }  // the hit line drives the secondary; L and PE hold the primary
    else {
      share = (v.cinj * crb) / ((v.cinj + v.cra) * (cx + crb) + cx * crb);
      if (v.inj === "n") share *= 0.5;  // one of two lines driven, the CDN holds the other (est)
      chit = ser(v.cinj, v.cra + ser(cx, crb));
    }
    const tau = 0.05 * ser(ccdn, chit);  // ns: 50 Ω × pF
    const fEdge = 1 - Math.exp(-5 / tau);  // a big capacitance slows the edge the 50 Ω generator can make
    const slope = gen * share * fEdge;
    // CISPR: share of the converter's common-mode current that returns locally through the Y capacitor (est)
    const local = cy ? (bonded ? 0.5 : cy / (cy + v.crb)) : 0;
    return {kv, cy, cww, cx, bonded, gen, share, tau, fEdge, slope, gndb, local,
      iIso: SI88.cio * slope * 1e-3, iT: cww * slope * 1e-3, iY: cy * slope * 1e-3};  // A: pF × kV/µs = mA
  }
  const amp = a => (a >= 1 ? `${num(a)} A` : `${num(a * 1000)} mA`);
  const leak = cy => 2 * Math.PI * 50 * cy * 1e-12 * 230;  // A at 230 V 50 Hz across the barrier

  function emcSvg(v, m) {
    const eft = EFT(v), c25 = v.std === "c25", on = v.dcdc === "on", sub = (a, b) => `${a}<tspan class="emc-sb" dy="3">${b}</tspan><tspan dy="-3"> </tspan>`;
    const box = (x, y, w, h, t, s, cls = "") => `<rect class="emc-blk ${cls}" x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/><text class="emc-t" x="${x + w / 2}" y="${y + (s ? h / 2 - 2 : h / 2 + 4)}" text-anchor="middle">${t}</text>${s ? `<text class="emc-s" x="${x + w / 2}" y="${y + h / 2 + 13}" text-anchor="middle">${s}</text>` : ""}`;
    const w = pts => `<polyline class="emc-w" points="${pts}"/>`;
    const hot = (pts, frac, cls) => (frac > 0.004 ? `<polyline class="${cls}" points="${pts}" stroke-width="${(2.5 + 9 * Math.min(1, frac)).toFixed(1)}"/>` : "");
    const capH = (x, y, lab, dim) => `<g class="${dim ? "emc-dim" : ""}"><line class="emc-cp" x1="${x - 11}" x2="${x + 11}" y1="${y}" y2="${y}"/><line class="emc-cp" x1="${x - 11}" x2="${x + 11}" y1="${y + 8}" y2="${y + 8}"/>${lab}</g>`;
    const o = [];
    // ground plane and the generator's ground
    o.push(`<rect class="emc-plane" x="4" y="506" width="372" height="12" rx="2"/><text class="emc-s" x="190" y="536" text-anchor="middle">Reference ground plane</text>`);
    o.push(w("12,34 6,34 6,506"));
    // the isolation barrier
    o.push(`<line class="emc-barrier" x1="190" x2="190" y1="208" y2="470"/><text class="emc-s emc-bl" x="196" y="214">isolation barrier</text>`);
    // wires
    o.push(w("92,56 92,76"), w("92,200 92,222"), w("140,274 140,300"), w("240,274 240,300"), w("288,184 288,222"), w("150,352 150,374"), w("270,396 330,396 330,274"));
    const lines = eft || !c25 ? [[52, "L"], [92, "N"], [132, "PE"]] : [[62, "+"], [122, "−"]];
    for (const [x, l] of lines) o.push(w(`${x},120 ${x},160`), `<text class="emc-s" x="${x + 5}" y="145">${l}</text>`);
    // Y capacitor across the barrier, stray capacitances to the plane (or the bond)
    o.push(w("60,274 60,446 186,446"), w("194,446 350,446 350,274"));
    o.push(`<g class="${m.cy ? "" : "emc-dim"}"><line class="emc-cp" x1="186" x2="186" y1="435" y2="457"/><line class="emc-cp" x1="194" x2="194" y1="435" y2="457"/></g><text class="emc-s" x="190" y="474" text-anchor="middle">${m.cy ? `Y ${m.cy >= 3000 ? "3.3 nF (3 × 10 nF)" : "1 nF"}` : "Y: none"}</text>`);
    o.push(w("24,274 24,480"), w("24,488 24,506"), capH(24, 480, `<text class="emc-s" x="38" y="490">${sub("C", "ret,A")}</text>`));
    if (m.bonded) o.push(`<polyline class="emc-w emc-bond" points="362,274 362,506"/><text class="emc-s" x="356" y="490" text-anchor="end">bonded</text>`);
    else o.push(w("362,274 362,480"), w("362,488 362,506"), capH(362, 480, `<text class="emc-s" x="348" y="490" text-anchor="end">${sub("C", "ret,B")}</text>`));
    if (eft && m.gndb) o.push(`<polyline class="emc-w emc-dash" points="92,140 176,140 176,290 240,290"/><text class="emc-s" x="178" y="136">N → GNDB</text>`);
    // current paths (drawn under the blocks)
    if (eft) {
      const cls = "emc-hot", tot = m.cx || 1;
      const fi = SI88.cio / tot, ft = m.cww / tot, fy = m.cy / tot, k = Math.min(1, m.slope / SI88.cmtiMin);
      if (m.gndb) o.push(hot("92,56 92,76", 1, cls), hot("92,120 92,140 176,140 176,290 240,290 240,274", 1, cls));
      else {
        o.push(hot("92,56 92,76", 1, cls));
        for (const [x] of v.inj === "n" ? [[92]] : lines) o.push(hot(`${x},120 ${x},160`, 1, cls));
        o.push(hot("92,200 92,222", 1, cls), hot("24,274 24,506", 0.3, cls));
      }
      o.push(hot("140,274 140,326 240,326 240,274", fi * k + 0.15, cls));
      o.push(hot("150,352 150,396 330,396 330,274", ft * k + (m.cww ? 0.1 : 0), cls));
      if (m.cy) o.push(hot("60,274 60,446 186,446", fy * k + 0.1, cls), hot("194,446 350,446 350,274", fy * k + 0.1, cls));
      o.push(hot("362,274 362,512 6,512 6,34 12,34", m.bonded ? 1 : 0.35, cls));
    } else if (on) {
      const loc = m.local, cab = 1 - loc;
      o.push(hot("150,396 330,396 330,274", 1, "emc-cm"));
      if (m.cy) o.push(hot("350,274 350,446 194,446", loc, "emc-loc"), hot("186,446 60,446 60,274", loc, "emc-loc"));
      o.push(hot("362,274 362,512 6,512 6,34 12,34", cab, "emc-cm"), hot("92,56 92,76", cab, "emc-cm"), hot("92,120 92,160", cab, "emc-cm"), hot("92,200 92,222", cab, "emc-cm"), hot("140,274 140,300", Math.max(loc, cab), "emc-cm"));
    }
    // blocks
    o.push(box(12, 12, 160, 44, eft ? "Burst generator" : c25 ? "Artificial network" : "LISN", eft ? `5/50 ns · ${v.kv} kV · 50 Ω` : c25 ? "5 µH / 50 Ω (CISPR 25)" : "50 µH / 50 Ω (CISPR 32)"));
    o.push(box(12, 76, 160, 44, eft ? "Coupling network" : c25 ? "Supply harness" : "Mains cable", eft ? (v.cdn === "33" ? "33 nF per line" : "3 × 10 nF = 3.3 nF (not std)") : c25 ? "probe at 50 / 750 mm" : "Class A / B limits", eft && v.cdn !== "33" ? "emc-warn" : ""));
    o.push(box(12, 160, 160, 40, "Input filter", "X / Y caps, CM choke"));
    o.push(box(12, 222, 160, 52, "Primary side", "VDDA / GNDA"));
    o.push(box(208, 222, 160, 52, "Secondary side", "VDDB / GNDB"));
    o.push(box(208, 140, 160, 44, "Load and cable", `part of C ret,B`));
    o.push(box(110, 300, 160, 52, "Si88 isolator + DC-DC", "1.4 pF · CMTI 40 kV/µs min", "emc-chip"));
    o.push(box(110, 374, 160, 44, "Transformer", on ? `${sub("C", "ww")} ${num(m.cww)} pF (est)${CIS(v) ? " · 250 kHz" : ""}` : `${sub("C", "ww")} ${num(m.cww)} pF · not switching`, on ? "" : "emc-off"));
    // legend
    const lg = (y, cls, t) => `<line class="${cls}" x1="212" x2="236" y1="${y}" y2="${y}" stroke-width="6"/><text class="emc-s" x="242" y="${y + 4}">${t}</text>`;
    o.push(`<text class="emc-t" x="212" y="26">${eft ? "EFT burst" : c25 ? "CISPR 25" : "CISPR 32"}</text>`);
    if (eft) o.push(lg(46, "emc-hot", "common-mode current"), `<text class="emc-s" x="212" y="70">thicker = more current</text><text class="emc-s" x="212" y="86">estimate (est)</text>`);
    else o.push(lg(46, "emc-cm", "through cables (measured)"), lg(66, "emc-loc", "local, via Y (not measured)"), `<text class="emc-s" x="212" y="90">${on ? "source: DC-DC switching" : "DC-DC off: no source"}</text>`);
    return `<svg class="emc-svg" viewBox="0 0 380 548" role="img" aria-label="Block diagram: ${eft ? "EFT burst" : "CISPR emissions"} test setup with the common-mode current path">${o.join("")}</svg>`;
  }

  function emcChanges(v, m) {
    const out = [], eft = EFT(v), slopeIf = (k) => emcModel({...v, [k]: EMC_DEF[k]}).slope;
    const move = k => ` Barrier slope ${num(slopeIf(k))} → ${num(m.slope)} kV/µs (est).`;
    if (eft) {
      if (v.inj === "n") out.push(`<b>N only:</b> adds a line-to-line part, so the input filter, rectifier and regulator see the burst too, not only the barrier.${v.tie === "b" ? "" : " In the model about half the common-mode part reaches the primary side (est)." + move("inj")}`);
      if (v.inj === "n" && v.tie === "b") out.push(`<b>N tied to the secondary ground (GNDB):</b> the burst drives the secondary side directly while L and PE hold the primary, so nearly all the slope lands across the isolator (est). Only capacitance across the barrier slows it, because the 50 Ω generator has to charge it.${m.bonded ? " With the secondary also bonded, the burst goes straight into the plane: not a meaningful setup." : ""}`);
      if (v.cdn !== "33") out.push(`<b>3 × 10 nF in series (3.3 nF) in the generator path:</b> τ ≈ 50 Ω × 3.3 nF ≈ 165 ns against a 50 ns pulse. The peak drops only a little, but a low-impedance input gets about ${Math.round(pulseCharge["3.3"] * 100)} % of the charge per pulse it gets with 33 nF (est). A milder test and <b>not a valid IEC 61000-4-4 test</b>.${move("cdn")}`);
      if (v.y !== "0") out.push(`<b>Y capacitor ${v.y === "1" ? "1 nF" : "3.3 nF (3 × 10 nF in series)"} across the barrier:</b> a local return path; the primary and secondary move together, so less slope is left across the isolator.${move("y")} Cost: about ${num(leak(m.cy) * 1e6)} µA leakage at 230 V 50 Hz (if the barrier sees mains), and a Y-rated part.`);
      if (v.dcdc === "off") out.push("<b>DC-DC off:</b> the transformer is still fitted, so the capacitive paths here stay the same, but the converter is not running: a secondary-rail droop or reset cannot show up, and the converter's own emissions are gone. <b>Not representative.</b>");
      if (v.sec === "bond") out.push(`<b>Secondary bonded to the plane:</b> the secondary can no longer move with the primary, so the burst current has to cross the barrier capacitances.${move("sec")} Bond only if the real installation does.`);
      if (v.kv !== "1") out.push(`<b>${v.kv} kV burst:</b> the edge at the generator scales with the level: ${v.kv} kV / 5 ns = ${num(m.gen)} kV/µs.${move("kv")}`);
    } else {
      out.push("<b>CISPR mode:</b> the noise source is the DC-DC converter itself (about 250 kHz plus harmonics), charging the transformer's interwinding capacitance every cycle. Where that common-mode current returns decides what the receiver sees.");
      if (v.y !== "0") out.push(`<b>Y capacitor ${v.y === "1" ? "1 nF" : "3.3 nF"}:</b> the current returns locally instead of through the cables and the network. AN1131 example: a single 1000 pF Y capacitor let a 2-layer Si88241 board pass CISPR 25 class 1 and 2 conducted limits.${v.y === "3.3" ? " 3.3 nF lowers it further at low frequencies; above some tens of MHz the capacitor's own inductance limits it (AN1131)." : ""} Cost: leakage current (about ${num(leak(m.cy) * 1e6)} µA at 230 V 50 Hz) and a Y-rated part.`);
      if (v.dcdc === "off") out.push("<b>DC-DC off:</b> the main source is switched off, so emissions drop, but the result says nothing about the product. <b>Not representative.</b>");
      if (v.sec === "bond") out.push(`<b>Secondary bonded to the plane:</b> the current through the transformer capacitance has a low-impedance way back through the plane and the network, which is what the receiver measures (est).${m.cy ? " With the Y capacitor, part of it still stays local." : ""} Bond only if the real installation does.`);
      if (v.std === "c32") out.push("<b>CISPR 32:</b> mains measured through a 50 µH / 50 Ω LISN, Class A or the stricter Class B (residential). A different network impedance, so CISPR 25 results do not carry over.");
    }
    const strays = ["cinj", "cra", "crb", "cww"].filter(k => v[k] !== EMC_DEF[k]);
    if (strays.length) out.push("<b>Stray capacitances changed:</b> they decide the result as much as any part does, and must be measured or simulated for a real board.");
    if (!out.length || (out.length === 1 && !eft && v.y === "0" && v.dcdc === "on" && v.sec === "float" && v.std === "c25" && !strays.length))
      out.push(eft ? "<b>Baseline:</b> all lines together, standard 33 nF coupling, no Y capacitor, DC-DC on, secondary floating. Change a toggle to see what moves and why." : "<b>Baseline:</b> no Y capacitor, secondary floating, DC-DC on and loaded. Change a toggle to compare.");
    return out;
  }

  V.push({
    id: "emc", group: "Isolation and power", title: "EFT and CISPR: setup and design what-if",
    explains: [["Digital isolators with integrated DC-DC (Si88xx)", "/knowledge#p-isolators_dcdc"]],
    physics: [["Crossing an isolation barrier", "phys_isolation_coupling"]],
    lead: "Both the EFT burst test and CISPR emissions are about common-mode current and the path it takes back to the ground plane. Flip the test setup and the design choices and watch where the current flows across an isolated design with an Si88 isolator, its DC-DC controller and the external transformer. All results are relative estimates (est), not pass/fail predictions.",
    controls: [
      {k: "mode", label: "Test", type: "select", options: [["eft", "EFT burst (IEC 61000-4-4)"], ["cispr", "CISPR emissions"]], value: "eft"},
      {k: "inj", label: "Injection", type: "select", options: [["all", "All lines (L + N + PE)"], ["n", "N only"]], value: "all", when: EFT},
      {k: "tie", label: "N connects to", type: "select", options: [["a", "Primary circuit (usual)"], ["b", "Secondary ground GNDB"]], value: "a", when: v => EFT(v) && v.inj === "n"},
      {k: "cdn", label: "Coupling capacitor", type: "select", options: [["33", "33 nF (standard)"], ["3.3", "3 × 10 nF in series = 3.3 nF (not standard)"]], value: "33", when: EFT},
      {k: "kv", label: "Burst level", type: "select", options: [["0.5", "0.5 kV"], ["1", "1 kV"], ["2", "2 kV"], ["4", "4 kV"]], value: "1", when: EFT},
      {k: "std", label: "Standard", type: "select", options: [["c25", "CISPR 25 (vehicle, 5 µH AN)"], ["c32", "CISPR 32 (multimedia, 50 µH LISN)"]], value: "c25", when: CIS},
      {k: "y", label: "Y capacitor across the barrier", type: "select", options: [["0", "None"], ["1", "1 nF"], ["3.3", "3.3 nF (3 × 10 nF)"]], value: "0"},
      {k: "dcdc", label: "DC-DC converter", type: "select", options: [["on", "On (running, loaded)"], ["off", "Off"]], value: "on"},
      {k: "sec", label: "Secondary ground", type: "select", options: [["float", "Floating"], ["bond", "Bonded to the plane"]], value: "float"},
      {k: "cinj", label: "Burst coupling into the primary, C inj (est)", min: 10, max: 10000, value: 1000, unit: "pF", log: true, when: EFT},
      {k: "cra", label: "Primary side to plane, C ret,A (est)", min: 2, max: 200, value: 20, unit: "pF", log: true, when: EFT},
      {k: "crb", label: "Secondary + load + cable to plane, C ret,B (est)", min: 2, max: 200, value: 20, unit: "pF", log: true, when: v => v.sec !== "bond"},
      {k: "cww", label: "Transformer interwinding, C ww (est)", min: 2, max: 100, value: 20, unit: "pF", log: true},
    ],
    compute(v) {
      const m = emcModel(v), eft = EFT(v), changes = emcChanges(v, m);
      const svg = emcSvg(v, m);
      const why = `<div class="emc-why"><b>What changed and why</b><ul>${changes.map(c => `<li>${c}</li>`).join("")}</ul></div>`;
      if (eft) {
        const marg = SI88.cmtiMin / m.slope, tone = marg >= 2 ? "ok" : marg >= 1 ? "warn" : "bad";
        const max = Math.max(m.slope, SI88.cmtiTyp) * 1.2, pct = x => `${Math.min(100, (x / max) * 100).toFixed(1)}%`;
        const label = marg >= 1 ? `${num(marg)}× margin below the 40 kV/µs CMTI minimum (est)` : `${num(1 / marg)}× above the 40 kV/µs CMTI minimum (est)`;
        const bar = `<div class="emc-barbox"><b>Estimated barrier slope against the Si88x2x CMTI</b>
          <div class="emc-bar" role="img" aria-label="Barrier slope ${num(m.slope)} kV/µs; CMTI 40 kV/µs minimum, 100 typical"><div class="emc-fill t-${tone}" style="width:${pct(m.slope)}"></div>
          <span class="emc-mk" style="left:${pct(SI88.cmtiMin)}"><i>40 min</i></span><span class="emc-mk typ" style="left:${pct(SI88.cmtiTyp)}"><i>100 typ</i></span></div>
          <p class="emc-margin t-${tone}">${num(m.slope)} kV/µs · ${label}</p></div>`;
        return {
          outputs: [["Edge at the generator", `${num(m.gen)} kV/µs`], ["Barrier slope (est)", `${num(m.slope)} kV/µs`, tone],
            ["Against CMTI 40 kV/µs min", marg >= 1 ? `${num(marg)}× margin` : `${num(1 / marg)}× over`, tone],
            ["Peak current across the barrier (est)", `isolator ${amp(m.iIso)} · transformer ${amp(m.iT)} · Y ${m.cy ? amp(m.iY) : "–"}`],
            ["Line-to-line stress", v.inj === "n" ? "yes: filter, rectifier, regulator" : "none (common mode)", v.inj === "n" ? "warn" : ""],
            ["Charge per pulse vs 33 nF", `${Math.round(pulseCharge[v.cdn] * 100)} %${v.cdn === "33" ? "" : " (not std)"}`, v.cdn === "33" ? "" : "warn"],
            ["Secondary rail", v.dcdc === "on" ? (m.iT > 0.05 ? "may droop or reset (est)" : "small disturbance (est)") : "not exercised (converter off)", v.dcdc === "on" ? "" : "warn"]],
          eq: "dV/dt<sub>barrier</sub> ≈ share × V<sub>burst</sub> / t<sub>rise</sub> · (1 − e<sup>−t<sub>rise</sub>/τ</sup>), share = C<sub>inj</sub>C<sub>ret,B</sub> / [(C<sub>inj</sub> + C<sub>ret,A</sub>)(C<sub>across</sub> + C<sub>ret,B</sub>) + C<sub>across</sub>C<sub>ret,B</sub>], C<sub>across</sub> = 1.4 pF + C<sub>ww</sub> + C<sub>Y</sub>",
          eqn: `${num(m.gen)} kV/µs × share ${num(m.share)} × edge ${num(m.fEdge)} (τ ${si(m.tau * 1e-9, "s")}) = ${num(m.slope)} kV/µs; C<sub>across</sub> = ${num(m.cx)} pF; I = C × dV/dt`,
          html: `<div class="emc-wrap"><div class="emc-dia">${svg}</div><div class="emc-side">${bar}${why}</div></div>`,
          note: "Relative estimate (est) from a capacitive divider: wiring and choke inductance, which slow the real edge, are ignored. Use it to compare setups, not to predict pass or fail; the stray capacitances must be measured or simulated. Data sheet: Si88x2x CMTI 40 kV/µs min, 100 typ; isolator input-output capacitance 1.4 pF.",
          nochart: true,
        };
      }
      let score = v.y === "1" ? -1 : v.y === "3.3" ? -2 : 0;
      if (v.sec === "bond") score += 1;
      const off = v.dcdc === "off";
      const tend = off ? "Lower, but not representative" : score < 0 ? "Lower than the baseline" : score > 0 ? "Higher than the baseline" : "Similar to the baseline";
      const reason = off ? "The converter, the main source, is switched off." : score < 0 ? "More of the converter's common-mode current returns locally through the Y capacitor, not through the cables." : score > 0 ? "The bond gives the common-mode current a low-impedance way back through the plane and the measured network." : v.sec === "bond" ? "The Y capacitor's local path roughly offsets the bond (est)." : "No local return path: the current goes back through the cables and the network.";
      const tone = off ? "warn" : score < 0 ? "ok" : score > 0 ? "bad" : "";
      const card = `<div class="emc-barbox"><b>Emissions tendency (qualitative)</b><p class="emc-tend t-${tone}">${tend}</p><p class="small">${reason}</p>${v.y === "1" ? '<p class="small muted">Example, not a prediction: in AN1131 a 1000 pF Y capacitor let a 2-layer Si88241 board pass CISPR 25 class 1 and 2 conducted limits.</p>' : ""}</div>`;
      return {
        outputs: [["Emissions tendency", tend, tone],
          ["Common-mode current returns", off ? "– (no source)" : m.cy ? (v.sec === "bond" ? "partly local, partly via the plane (est)" : `about ${Math.round(m.local * 100)} % locally via Y (est)`) : "through cables and the network"],
          ["Network", v.std === "c25" ? "5 µH / 50 Ω AN, classes 1–5" : "50 µH / 50 Ω LISN, Class A / B"],
          ["Leakage through Y at 230 V 50 Hz", m.cy ? `${num(leak(m.cy) * 1e6)} µA (est)` : "none added"]],
        eq: "I<sub>CM</sub> ≈ C<sub>ww</sub> · dV<sub>sw</sub>/dt, returning through C<sub>Y</sub> (local) or C<sub>ret,B</sub> / bond → plane → network (measured)",
        eqn: off ? "Converter off: no switching, no I<sub>CM</sub> from it." : m.cy && v.sec !== "bond" ? `local share ≈ C<sub>Y</sub> / (C<sub>Y</sub> + C<sub>ret,B</sub>) = ${num(m.cy)} / (${num(m.cy)} + ${num(v.crb)}) pF = ${Math.round(m.local * 100)} % (capacitive divider, ignores the Y capacitor's inductance)` : "No dB numbers here: the level depends on the board, the transformer and the setup.",
        html: `<div class="emc-wrap"><div class="emc-dia">${svg}</div><div class="emc-side">${card}${why}</div></div>`,
        note: "Qualitative only: the tendency compares with the baseline (no Y capacitor, secondary floating, DC-DC on and loaded). Si88x2x switches at about 250 kHz (225–275 kHz) with dithering for low EMI (data sheet); its harmonics fall inside the 150 kHz-and-up range both standards measure.",
        nochart: true,
      };
    },
    related: [["Engineering note: EFT burst and CISPR emissions on isolated designs", "/engineering/emc_eft_cispr"], ["CMTI against the switching edge", "#cmti"], ["CMTI guide", "/engineering/cmti_kv_us"]],
  });

  // visuals kept in their own files: each templates/engineering/visuals/_<id>.html include loads a static/vz/<id>.js
  // that pushes a function onto window.VZ_ADD before this file runs; it receives the helpers and adds its definitions
  for (const add of window.VZ_ADD || []) add({V, DATA, C, num, si, db, undb, log10, clamp, esc, range});

  // ------------------------------------------------------------------ page
  const groups = [...new Set(V.map(v => v.group))];
  const nav = $("#vz-nav"), panel = $("#vz-panel");
  nav.innerHTML = groups.map(g => `<div class="vz-g"><b>${esc(g)}</b>${V.filter(v => v.group === g).map(v => `<a href="#${v.id}" data-id="${v.id}">${esc(v.title)}</a>`).join("")}</div>`).join("")
    + '<div class="vz-g"><b>Spectrum</b><a href="/rf-bands">RF bands chart</a></div>';  // its own page, same section
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
      ${cur.explains ? `<p class="small vz-explains">Explains: ${cur.explains.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ")}${cur.physics ? ` · Physics: ${cur.physics.map(([l, id]) => `<a href="/rf-notes#${id}">${esc(l)}</a>`).join(" · ")}` : ""}</p>` : ""}
      ${cur.presets ? `<div class="vz-presets"><span class="small muted">${esc(cur.presetLabel || "Typical conditions")}:</span> ${cur.presets.map((p, i) => `<button type="button" class="vz-pre" data-p="${i}">${esc(p.label)}</button>`).join("")}<p class="vz-pre-note small" hidden></p></div>` : ""}
      ${cur.setup ? '<div class="vz-extra"></div>' : ""}
      <div class="vz-body"><div class="vz-ctl">${cur.controls.map(c => c.type === "select"
        ? `<label class="vz-c" data-c="${c.k}"><span>${esc(c.label)}</span><select data-k="${c.k}">${c.options.map(([k, l]) => `<option value="${k}"${k === c.value ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`
        : `<label class="vz-c" data-c="${c.k}"><span>${esc(c.label)} <output data-o="${c.k}">${show(c, c.value)}</output></span><input type="range" data-k="${c.k}" min="${c.log ? 0 : c.min}" max="${c.log ? 1000 : c.max}" step="${c.log ? 1 : c.step || (c.max - c.min) / 200}" value="${toPos(c, c.value)}" aria-valuetext="${esc(show(c, c.value))}"></label>`).join("")}
        <div class="vz-btns">${cur.animate ? '<button type="button" class="small-btn vz-play">▶ Play</button>' : ""}<button type="button" class="outline secondary small-btn vz-reset">Reset</button></div></div>
        <div class="vz-out"><div class="vz-kpis"></div></div></div>
      <div class="vz-chartwrap"><svg class="vz-chart" role="img" aria-label="${esc(cur.title)}"></svg></div>
      <div class="vz-eq"><div class="vz-eq-sym"></div><div class="vz-eq-num"></div></div>
      <div class="vz-more"></div>
      <p class="vz-note"></p>${cur.related ? `<p class="small">Related: ${cur.related.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ")}</p>` : ""}`;
    panel.querySelectorAll("[data-k]").forEach(el => el.addEventListener("input", () => {
      const c = cur.controls.find(x => x.k === el.dataset.k);
      vals[c.k] = c.type === "select" ? el.value : fromPos(c, el.value);
      const o = panel.querySelector(`[data-o="${c.k}"]`);
      if (o) o.textContent = show(c, vals[c.k]);
      if (c.type !== "select") el.setAttribute("aria-valuetext", show(c, vals[c.k]));  // read as "1.5 dB", not "1.5"
      render();
    }));
    panel.querySelectorAll(".vz-pre").forEach(b => b.addEventListener("click", () => {
      const p = cur.presets[+b.dataset.p];
      Object.assign(vals, p.values);
      for (const c of cur.controls) {  // move the sliders and selects to the preset values
        const el = panel.querySelector(`[data-k="${c.k}"]`);
        if (!el || !(c.k in p.values)) continue;
        el.value = c.type === "select" ? vals[c.k] : toPos(c, vals[c.k]);
        const o = panel.querySelector(`[data-o="${c.k}"]`);
        if (o) o.textContent = show(c, vals[c.k]);
        if (c.type !== "select") el.setAttribute("aria-valuetext", show(c, vals[c.k]));
      }
      panel.querySelectorAll(".vz-pre").forEach(x => x.classList.toggle("on", x === b));
      const note = panel.querySelector(".vz-pre-note");
      note.innerHTML = p.note; note.hidden = !p.note;
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
    if (cur.setup) cur.setup(panel.querySelector(".vz-extra"), render);
    if (cur.parts) loadParts();
    render();
  }
  function render() {
    const r = cur.compute(vals, phase);
    panel.querySelector(".vz-kpis").innerHTML = r.outputs.map(([l, val, tone]) => `<div class="vz-kpi${tone ? " t-" + tone : ""}${String(val).length > 22 ? " wide" : ""}"><span>${esc(l)}</span><b>${esc(val)}</b></div>`).join("");
    panel.querySelector(".vz-eq-sym").innerHTML = r.eq;
    panel.querySelector(".vz-eq-num").innerHTML = r.eqn;
    panel.querySelector(".vz-note").textContent = r.note;
    panel.querySelector(".vz-more").innerHTML = r.html || "";
    for (const c of cur.controls) {  // controls that only apply in some modes
      const lab = panel.querySelector(`[data-c="${c.k}"]`);
      if (lab) lab.hidden = c.when ? !c.when(vals) : false;
    }
    const svg = panel.querySelector(".vz-chart");
    svg.parentElement.hidden = !!r.nochart;  // visuals that draw their own diagram in .vz-more
    if (r.nochart) return;
    if (r.bars) bars(svg, r.bars); else plot(svg, r.chart);
  }
  const route = () => open((location.hash || "").slice(1) || V[0].id);
  window.addEventListener("hashchange", route);
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 120); });
  route();
})();
