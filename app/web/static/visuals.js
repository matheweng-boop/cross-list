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

  const EDGE = v => v.src === "edge", GATE = v => v.src === "gate", COSS = v => v.src === "coss";
  V.push({
    id: "cmti", group: "Isolation and power", title: "CMTI against the switching edge",
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
    if (r.bars) bars(svg, r.bars); else plot(svg, r.chart);
  }
  const route = () => open((location.hash || "").slice(1) || V[0].id);
  window.addEventListener("hashchange", route);
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 120); });
  route();
})();
