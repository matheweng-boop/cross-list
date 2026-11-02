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
      if (b.x1 < X.min || b.x0 > X.max) continue;
      o.push(`<rect x="${a}" y="${T}" width="${Math.max(b.minw || 0, z - a)}" height="${H - T - B}" fill="${b.color || C.grey}" opacity="${b.opacity || 0.1}"/>`);
      if (b.label) o.push(`<text class="vz-bl" x="${clamp((a + z) / 2, L + b.label.length * 3.3, W - R - b.label.length * 3.3)}" y="${H - B - 8 - (b.row || 0) * 13}" text-anchor="middle">${esc(b.label)}</text>`);
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

  // application bands (owner 24 Oct 2026: "add ranges into the graph to accurately show the application. FM is not
  // only at 100 MHz"): data/engineering_rf_bands.yaml, the source of the RF bands chart, in MHz. Charts draw them as
  // ranges; a visual that calculates at one frequency keeps that centre value and shows the band strip around it.
  const BANDS = DATA.bands || {};
  const mhzR = (a, b) => (b >= 10000 ? `${+(a / 1000).toPrecision(4)}–${+(b / 1000).toPrecision(4)} GHz` : `${+a.toPrecision(5)}–${+b.toPrecision(5)} MHz`);
  const bandText = id => (BANDS[id] ? BANDS[id].ranges.map(([a, b, l]) => (BANDS[id].ranges.length > 1 ? `${l} ` : "") + mhzR(a, b)).join(", ") : "");
  // bands whose ranges hold f (MHz), narrowest first
  const bandsAt = f => Object.entries(BANDS).filter(([, b]) => b.ranges.some(([a, z]) => f >= a && f <= z))
    .sort((p, q) => Math.min(...p[1].ranges.map(r => r[1] - r[0])) - Math.min(...q[1].ranges.map(r => r[1] - r[0]))).map(([id]) => id);
  const bandOut = (fMHz, n = 2) => { const ids = bandsAt(fMHz).slice(0, n); return ["Band at this frequency", ids.length ? ids.map(id => `${BANDS[id].name}: ${bandText(id)}`).join(" · ") : "none in the RF bands chart"]; };
  // chart bands: [[id, label, row, color]] -> plot() bands in the chart's unit (k: MHz -> unit)
  const appBands = (list, k = 1, sub = false) => list.flatMap(([id, label, row = 0, color = C.teal]) => {
    const b = BANDS[id];
    if (!b) return [];
    const rs = sub && b.sub.length ? b.sub : b.ranges;
    return rs.map(([a, z, l], i) => ({x0: a * k, x1: z * k, color, opacity: 0.16, minw: 3, row: sub ? i : row, label: sub ? l : i ? "" : label}));
  });
  // a strip of the frequency axis around f (MHz): the bands there as ranges (one row each, bars on a log scale) and f
  // as a line; HTML, not SVG, so the text keeps its size on a phone
  function bandStrip(f, opts = {}) {
    const lo = opts.lo || f / 1.6, hi = opts.hi || f * 1.6;
    const pc = v => (100 * (log10(Math.min(Math.max(v, lo), hi)) - log10(lo))) / (log10(hi) - log10(lo));
    const mid = b => Math.min(...b.ranges.map(r => Math.abs(log10(Math.sqrt(r[0] * r[1]) / f))));
    const ids = Object.entries(BANDS).filter(([, b]) => b.ranges.some(([a, z]) => z >= lo && a <= hi))
      .map(([id, b]) => [id, b, b.ranges.some(([a, z]) => f >= a && f <= z)])
      .sort((p, q) => q[2] - p[2] || mid(p[1]) - mid(q[1])).slice(0, opts.n || 6);
    const rows = ids.map(([id, b, on]) => `<div class="vz-sr">${b.ranges.filter(([a, z]) => z >= lo && a <= hi)
      .map(([a, z]) => `<i class="vz-sbar${on ? " on" : ""}" style="left:${pc(a).toFixed(2)}%;width:${Math.max(0.8, pc(z) - pc(a)).toFixed(2)}%"></i>`).join("")}<span>${esc(b.name)}: ${esc(bandText(id))}</span></div>`).join("");
    return `<figure class="vz-strip"><figcaption class="small muted">${esc(opts.caption || "Where this frequency sits: the bands around it as ranges (from the RF bands chart)")}</figcaption>
      <div class="vz-sb" role="img" aria-label="Bands around ${esc(si(f * 1e6, "Hz"))}">${rows || '<div class="vz-sr"><span class="muted">no band of the RF bands chart here</span></div>'}<b class="vz-sf" style="left:${pc(f).toFixed(2)}%"></b>
      <div class="vz-sax"><span>${esc(si(lo * 1e6, "Hz"))}</span><span class="vz-sfl" style="left:${pc(f).toFixed(2)}%">${esc(si(f * 1e6, "Hz"))}</span><span>${esc(si(hi * 1e6, "Hz"))}</span></div></div></figure>`;
  }

  // Skyworks / Qorvo RF parts (gain, NF, IP3, loss, band) for part suggestions; fetched once, when a visual needs them
  let PARTS = null, partsLoading = false, redraw = null;
  function loadParts() {
    if (PARTS || partsLoading) return;
    partsLoading = true;
    fetch("/api/visuals/rf-parts").then(r => r.json()).then(d => { PARTS = d.parts || []; if (cur && cur.parts) { if (redraw) redraw(); render(); } })
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

  // the dBm ladder's rungs in plain words (owner 23 Oct 2026: "What does BLE sensitivity mean? Or GNSS antenna? Or
  // 1 mW? What happens if it is violated? What am I actually blocking?"). Rungs with a range in DBM_RANGES are drawn
  // as bands; the others (fixed definitions) stay lines at p.
  const NOTE = id => `/rf-notes#${id}`;
  const DBM_RUNGS = [
    {p: -160, name: "GNSS receiver sensitivity",
      what: "The weakest satellite signal a navigation receiver can still follow, or find from a cold start. It lies far below the noise: the receiver finds it by correlating with the known code for a long time.",
      bad: "Weaker than this: no position indoors, a slow first fix (minutes instead of seconds), positions that jump. Every 1 dB of loss or noise figure in front of the GNSS LNA costs 1 dB here.",
      parts: [["GNSS LNA SKY65723-11", "/find?q=SKY65723-11"], ["L5 LNA SKY65728-11", "/find?q=SKY65728-11"]],
      read: [["Sensitivity and noise floor", NOTE("sensitivity_noise_floor")], ["Cascaded NF visual", "#nf"]]},
    {p: -128.5, name: "GNSS signal at the antenna",
      what: "A navigation satellite 20,000 km away arrives this weak: below the receiver's own noise. The receiver still finds it by correlating with the known code for a long time.",
      bad: "Weaker than this, or more noise from the receiver: slow or no position fix, position jumps. Every 1 dB of loss or noise figure in front of the GNSS LNA costs 1 dB here.",
      parts: [["GNSS LNA SKY65723-11", "/find?q=SKY65723-11"], ["L5 LNA SKY65728-11", "/find?q=SKY65728-11"]],
      read: [["Sensitivity and noise floor", NOTE("sensitivity_noise_floor")], ["GNSS L1 band", "/rf-bands?band=gnss_l1"], ["Cascaded NF visual", "#nf"]]},
    {p: -114, name: "Thermal noise in 1 MHz",
      what: "The noise every resistor and antenna makes at room temperature: −174 dBm in each hertz of bandwidth, so −114 dBm in 1 MHz and −101 dBm in 20 MHz. No receiver can go below it; it can only add to it (its noise figure).",
      typ: "−174 dBm/Hz + 10·log10(bandwidth in Hz): a fixed value for a given bandwidth, so it stays a line.",
      ifLabel: "Why it matters", bad: "A signal must stand above this floor plus the receiver's noise figure by the SNR the modulation needs; otherwise it cannot be decoded.",
      read: [["Sensitivity and noise floor", NOTE("sensitivity_noise_floor")], ["Cascaded noise figure", NOTE("cascaded_noise_figure")]]},
    {p: -112, name: "FM tuner sensitivity",
      what: "The weakest FM station a broadcast tuner still turns into clean mono audio (26 dB signal-to-noise). Tuner data sheets give it in µV EMF; into 50 Ω, dBm = dBµV − 113.",
      bad: "Weaker: hiss, then the radio blends to mono or mutes. RDS text (station name, traffic) stops first, because it needs a stronger signal.",
      parts: [["Si47xx AM / FM / DAB tuners", "/find?q=Si47"]],
      read: [["FM band", "/rf-bands?band=fm"], ["FM intermodulation visual", "#fmim"]]},
    {p: -97, name: "LTE / 5G phone sensitivity",
      what: "The weakest cellular downlink a phone must still receive at a stated data rate (3GPP calls it reference sensitivity), here in a 10 MHz channel.",
      bad: "Below it the phone drops to a lower data rate, then loses the cell at the edge of coverage. A strong signal in a neighbouring band (a blocker) raises the effective floor: the phone is 'desensitised'.",
      parts: [["LNA SKY67151-396LF", "/find?q=SKY67151-396LF"], ["Switch SKY13489-001", "/find?q=SKY13489-001"]],
      read: [["Sensitivity and noise floor", NOTE("sensitivity_noise_floor")], ["Cascaded NF visual", "#nf"]]},
    {p: -97, name: "BLE sensitivity",
      what: "The weakest Bluetooth Low Energy packet a receiver still decodes with few bit errors (0.1 % in the Bluetooth test).",
      bad: "Below it packets are lost and resent, range shrinks, the connection drops. Wi-Fi or an LTE uplink next to 2.4 GHz can block it: their strong signal overloads the receiver, which then misses the weak BLE packet.",
      parts: [["2.4 GHz LNA SKY65405-21", "/find?q=SKY65405-21"], ["2.4 GHz front end SKY85203-11", "/find?q=SKY85203-11"]],
      read: [["Sensitivity and noise floor", NOTE("sensitivity_noise_floor")], ["2.4 GHz band", "/rf-bands?band=ism24"]]},
    {p: -74.5, name: "Wi-Fi sensitivity (by data rate)",
      what: "The weakest Wi-Fi signal a receiver still decodes. It depends on the data rate: slow, robust rates are heard far weaker than fast ones. A good signal in the next room is about −70 dBm (est).",
      bad: "Below it the link falls back to slower rates, the throughput drops, then the connection is lost.",
      parts: [["5 GHz LNA SKY65404-31", "/find?q=SKY65404-31"], ["5 GHz filter SKY85922-11", "/find?q=SKY85922-11"]],
      read: [["Wi-Fi front ends", NOTE("wifi_fem_and_triband_ap")], ["Link budget visual", "#link"]]},
    {p: -30, name: "Strong blocker at a receiver",
      what: "A strong unwanted signal next to the band, for example the phone's own transmitter or a nearby base station, as it arrives at the receiver input after the antenna isolation.",
      ifLabel: "What you are blocking", bad: "Nothing is switched off: the weak wanted signal is drowned. The blocker compresses the LNA (its gain drops) or mixes with a second signal into an intermodulation product on the wanted channel. Fix it with filter rejection (BAW / SAW), or with higher linearity (IIP3).",
      parts: [["High-IIP3 switch SKY13414-485LF", "/find?q=SKY13414-485LF"], ["Filters (SKY85922-11)", "/find?q=SKY85922-11"]],
      read: [["Blocking and dynamic range", NOTE("dynamic_range_sfdr_blocking")], ["Blocker view (this visual)", "#dbm"]]},
    {p: 0, name: "1 mW: the reference",
      what: "The zero of the dBm scale: one milliwatt, by definition, so it stays a line. Many BLE transmitters send about this; it is also a typical drive level for a mixer's local oscillator.",
      typ: "0 dBm = 1 mW = 0.22 V rms into 50 Ω.",
      ifLabel: "If a receiver sees it", bad: "At an LNA input 0 dBm is huge: most LNAs compress between −20 and 0 dBm, and +10 to +20 dBm can damage them. Receivers next to transmitters use limiters or switches to protect the LNA.",
      read: [["dBm and decibels", NOTE("dbm_basics")], ["P1dB and compression", NOTE("p1db_dynamic_range")], ["Limiters", NOTE("limiters_receiver_protection")]]},
    {p: 5, name: "BLE transmitter",
      what: "What a Bluetooth Low Energy device sends: from a coin-cell sensor that whispers to a long-range module with a front-end module.",
      ifLabel: "If it is exceeded", bad: "Above +20 dBm the product leaves the Bluetooth specification and the radio rules; more power also empties the battery faster.",
      parts: [["BLE front-end module SKY66111-11", "/find?q=SKY66111-11"], ["2.4 GHz FEM SKY66112-11", "/find?q=SKY66112-11"]],
      read: [["Link budget visual", "#link"], ["2.4 GHz band", "/rf-bands?band=ism24"]]},
    {p: 10.9, name: "IIP3 of a good LNA",
      what: "Not a real power: the input level at which the intermodulation products of two signals would, extrapolated, be as strong as the signals. It measures linearity.",
      ifLabel: "If the signals approach it", bad: "Long before it: each 1 dB more of two blockers makes their third-order product 3 dB stronger, until it lands on the wanted channel above the noise. The part also compresses about 10 dB below IIP3.",
      parts: [["LNA SKY67021-396LF (IIP3 +22.5 dBm)", "/find?q=SKY67021-396LF"], ["Mixer SKY73090-21", "/find?q=SKY73090-21"]],
      read: [["IIP3 in plain words", NOTE("iip3_basics")], ["IP3 visual", "#ip3"], ["FM intermodulation visual", "#fmim"]]},
    {p: 17, name: "Wi-Fi client transmitter",
      what: "A laptop or phone sending Wi-Fi: about 50 mW.",
      ifLabel: "If it is exceeded", bad: "Above the legal limit the product fails certification; pushed close to the PA's limit it distorts and spills into neighbouring channels (EVM and spectral mask fail).",
      parts: [["Wi-Fi front ends (SKY85…)", "/find?q=SKY85"]],
      read: [["Wi-Fi front ends", NOTE("wifi_fem_and_triband_ap")]]},
    {p: 23, name: "Phone transmitter (LTE / 5G)",
      what: "What a phone sends on the cellular uplink. Power control turns it down next to the base station and up at the edge of the cell; +23 dBm (200 mW) is the usual maximum.",
      ifLabel: "If it is exceeded", bad: "Not allowed by the standard; in practice the PA's linearity limits it, because distortion breaks the adjacent-channel limits (ACLR). Next to the phone's own GNSS or Wi-Fi receivers this is the blocker.",
      parts: [["PA modules (SKY78…)", "/find?q=SKY78"]],
      read: [["PA linearisation", NOTE("pa_linearization_dpd_doherty")]]},
    {p: 30, name: "1 W",
      what: "One watt, by definition +30 dBm, so it stays a line: small-cell and repeater outputs, handheld two-way radios (about 1–5 W).",
      typ: "+30 dBm = 1 W = 7.1 V rms into 50 Ω.", ifLabel: "Why it matters",
      bad: "At this level heat and voltage stress matter: switches need high power handling (P0.1dB), and 1 dB of loss is 200 mW of heat.",
      read: [["RF switches", NOTE("rf_switches")]]},
    {p: 46, name: "Macro base station, 40 W",
      what: "One carrier of a macro cell site.",
      ifLabel: "Why it matters",
      bad: "Efficiency and linearity of the PA decide the site's power bill; Doherty PAs and predistortion are used.",
      parts: [["Qorvo PAs (QPA…)", "/find?q=QPA"]],
      read: [["PA linearisation", NOTE("pa_linearization_dpd_doherty")]]},
    {p: 66, name: "Radar transmitter (peak)",
      what: "Peak pulse power of a marine or weather radar; the average power is much lower because it sends short pulses.",
      ifLabel: "Why it matters", bad: "The receiver next to it must survive its own transmitter: limiters and switches protect the LNA.",
      read: [["Radar fundamentals", NOTE("radar_fundamentals")], ["Limiters", NOTE("limiters_receiver_protection")]]},
    {p: 70, name: "FM broadcast transmitter",
      what: "The effective radiated power (ERP) of an FM station: transmitter power times antenna gain.",
      ifLabel: "Why it matters", bad: "Near such a transmitter a car radio sees a very strong station: it can overload the tuner and mix with a second station into the one you listen to.",
      read: [["FM intermodulation visual", "#fmim"], ["FM band", "/rf-bands?band=fm"]]},
  ];

  // owner, 2 Nov 2026 ("BLE sensitivity is a range, not a dotted line at one value"): every rung that is really a range,
  // as label (= the rung's name), low end, typical and high end in dBm, what moves the value within the band, points
  // inside it and the sources [text, url]. est: no source for the band, or for the part the text marks "est".
  const SRC = {
    bt: "https://www.bluetooth.com/learn-about-bluetooth/key-attributes/range/",
    cc2652: "https://www.ti.com/lit/ds/symlink/cc2652r.pdf", cc3235: "https://www.ti.com/lit/ds/symlink/cc3235s.pdf",
    an1451: "https://www.skyworksinc.com/-/media/SkyWorks/Documents/Products/Application-Notes/AN1451_Enabling_High_Performance_Bluetooth_207463A.pdf",
    lte: "https://www.etsi.org/deliver/etsi_ts/136100_136199/136101/08.09.00_60/ts_136101v080900p.pdf",
    nr: "https://www.etsi.org/deliver/etsi_ts/138100_138199/13810101/15.02.00_60/ts_13810101v150200p.pdf",
    si4734: "https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-shorts/Si4734-35-short.pdf",
    si4730: "https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-shorts/Si4730-31-short.pdf",
  };
  const DBM_RANGES = [
    {label: "GNSS receiver sensitivity", lo: -167, typ: -160, hi: -145, est: true,
      moves: "Following a satellite already found (tracking) works 10–20 dB weaker than finding it from a cold start (acquisition). Help from the network (A-GNSS), longer integration, a low-noise LNA right at the antenna and the receiver's own noise figure move it.",
      pts: [["tracking, high-sensitivity receiver (est)", -167], ["tracking, typical (est)", -160], ["cold-start acquisition (est)", -145]], src: []},
    {label: "GNSS signal at the antenna", lo: -155, typ: -128.5, hi: -123,
      moves: "The satellite's elevation (low satellites are weaker), the antenna and its gain pattern, and what is in the way: trees, buildings, a car roof or metal-coated glass take 10–30 dB (est).",
      pts: [["indoors or in a car with metal-coated glass (est)", -155], ["minimum in open sky (GPS L1 C/A, specification)", -128.5], ["strongest in open sky (est)", -123]],
      src: [["IS-GPS-200, the GPS interface specification: minimum received L1 C/A power −158.5 dBW (= −128.5 dBm) in open sky", ""]]},
    {label: "FM tuner sensitivity", lo: -112, typ: -112, hi: -95,
      moves: "What you ask for: clean mono audio needs 1.1 µV EMF (−112 dBm), RDS data about 8 µV (−95 dBm), stereo much more; and the antenna: a headphone wire instead of a matched 50 Ω antenna costs about 6 dB (2.2 µV).",
      pts: [["mono audio, 26 dB S/N, 50 Ω antenna (1.1 µV EMF)", -112.2], ["the same with a headphone-wire antenna (2.2 µV EMF)", -106.2], ["RDS data (8 µV EMF)", -94.9]],
      src: [["Si4734/35 data sheet: 1.1 µV EMF (50 Ω), 2.2 µV EMF (headphone antenna)", SRC.si4734], ["Si4730/31 data sheet: RDS sensitivity 8 µV EMF", SRC.si4730]]},
    {label: "LTE / 5G phone sensitivity", lo: -101, typ: -97, hi: -94,
      moves: "The band (the specification allows −94 dBm in LTE bands 3, 8 and 20, but asks −97 dBm in band 1), the channel width (each doubling costs 3 dB: −94 dBm in 20 MHz in band 1), four receive antennas instead of two (2–3 dB better), and the phone's own front end: switch and filter losses and the LNA's noise figure. A good phone beats the specification by a few dB (est).",
      pts: [["a good phone, 10 MHz (est)", -101], ["5G n78, 10 MHz, four antennas (specification)", -98], ["LTE band 1, 10 MHz (specification)", -97], ["5G n1, 10 MHz, two antennas (specification)", -96.8], ["LTE bands 3, 8, 20, 10 MHz (specification)", -94]],
      src: [["3GPP TS 36.101 (ETSI TS 136 101 V8.9.0), Table 7.3.1-1: LTE reference sensitivity", SRC.lte], ["3GPP TS 38.101-1 (ETSI TS 138 101-1 V15.2.0), Tables 7.3.2-1 and 7.3.2-2: 5G NR reference sensitivity", SRC.nr]]},
    {label: "BLE sensitivity", lo: -105, typ: -97, hi: -70,
      moves: "The data rate (PHY): LE Coded at 125 kb/s hears about 8 dB weaker signals than LE 1M, LE 2M about 6 dB less weak. Then the chip, its temperature and supply voltage (a few dB from −40 to +85 °C, est), and the board: the matching network, filter and antenna switch losses (typically 1–1.5 dB) come straight off.",
      pts: [["specification minimum, LE 1M", -70], ["specification minimum, LE Coded", -82], ["typical chip, LE 2M (CC2652R)", -91], ["typical chip, LE 1M (CC2652R)", -97], ["average LE Coded chip (Bluetooth SIG)", -103], ["LE Coded 125 kb/s (CC2652R)", -105]],
      src: [["Bluetooth SIG: the specification asks −70 to −82 dBm depending on the PHY; average LE Coded chips reach −103 dBm", SRC.bt], ["TI CC2652R data sheet (typical, 25 °C, conducted)", SRC.cc2652], ["Skyworks AN1451: matching and switches cost 1–1.5 dB", SRC.an1451]]},
    {label: "Wi-Fi sensitivity (by data rate)", lo: -96, typ: -74.5, hi: -64,
      moves: "The data rate above all: 1 Mb/s is heard about 20 dB weaker than 54 Mb/s. Then the channel width (40 MHz costs 3 dB), the band, the chip and the losses in front of it (front-end module, filter, switch); one data sheet adds 1 dB on channel 13.",
      pts: [["1 Mb/s, typical chip (CC3235S)", -96], ["6 Mb/s, typical chip", -90.5], ["6 Mb/s, IEEE 802.11 minimum", -82], ["54 Mb/s, typical chip", -74.5], ["MCS7, typical chip", -71.5], ["54 Mb/s, IEEE 802.11 minimum", -65], ["MCS7, IEEE 802.11 minimum", -64]],
      src: [["TI CC3235S data sheet, 2.4 GHz (typical, 25 °C)", SRC.cc3235], ["IEEE 802.11, minimum input sensitivity for OFDM in 20 MHz (standard, not public)", ""]]},
    {label: "Strong blocker at a receiver", lo: -56, typ: -30, hi: -15,
      moves: "How close the other transmitter is and how much antenna isolation and filtering sit in between. The 3GPP tests put a blocker at −56 or −44 dBm inside the phone's band and at −44, −30 or −15 dBm the further it is outside; the phone's own transmitter or a radio in the same box can be stronger still (est).",
      pts: [["in-band blocking, close (LTE test)", -56], ["in-band blocking, further away (LTE test)", -44], ["out of band, 15–60 MHz away (LTE test)", -44], ["out of band, 60–85 MHz away (LTE test)", -30], ["out of band, further away (LTE test)", -15]],
      src: [["3GPP TS 36.101 (ETSI TS 136 101 V8.9.0), Tables 7.6.1.1-2 and 7.6.2.1-2: blocking", SRC.lte]]},
    {label: "BLE transmitter", lo: -20, typ: 5, hi: 20,
      moves: "The power setting (range against battery life), the power class the product is built for, and an external front-end module: Bluetooth chips alone typically send +4 to +10 dBm, a front-end module adds up to 12 dB.",
      pts: [["lowest in the specification", -20], ["typical chip (CC2652R maximum)", 5], ["typical chips, top end (AN1451)", 10], ["highest in the specification", 20]],
      src: [["Bluetooth SIG: −20 dBm to +20 dBm", SRC.bt], ["Skyworks AN1451: chips 4–10 dBm, front-end modules up to +22 dBm", SRC.an1451], ["TI CC2652R data sheet: +5 dBm", SRC.cc2652]]},
    {label: "IIP3 of a good LNA", lo: -4, typ: 10.9, hi: 21.5,
      moves: "The design and its supply current (more current buys linearity), the gain (more gain usually means a lower input IP3), the frequency, and the bias mode many LNAs offer (high linearity or low current). RF switches sit far higher (median +56 dBm in our catalogue).",
      pts: [["10 % of our LNAs are below", -4], ["median of our LNAs", 10.9], ["90 % of our LNAs are below", 21.5]],
      src: [["BizDev catalogue, 2 Nov 2026: 89 Skyworks and Qorvo LNAs with an IIP3 from the data sheet or OIP3 − gain (10th to 90th percentile)", "/business/rf-coverage"]]},
    {label: "Wi-Fi client transmitter", lo: 13, typ: 17, hi: 20,
      moves: "The data rate: fast rates need a cleaner signal, so the transmitter backs off (+18 dBm at 1 Mb/s, +13 dBm at MCS7 on one chip); edge channels are turned down to meet emission limits; the supply (1.5 dB less below 2.8 V on that chip); and the legal limit (20 dBm EIRP at 2.4 GHz in Europe, est).",
      pts: [["MCS7, 2.4 GHz (CC3235S)", 13], ["54 Mb/s", 14.5], ["6 Mb/s", 17.3], ["1 Mb/s", 18], ["legal limit at 2.4 GHz in Europe, EIRP (est)", 20]],
      src: [["TI CC3235S data sheet, 2.4 GHz (typical, 25 °C)", SRC.cc3235]]},
    {label: "Phone transmitter (LTE / 5G)", lo: -40, typ: 23, hi: 26,
      moves: "The distance to the cell: power control turns the phone down by up to 60 dB next to the base station. Then the power class (class 3: +23 dBm ± 2 dB; class 2: +26 dBm in the 5G bands n41, n77, n78 and n79) and the signal: wide, high-order signals need back-off to stay clean.",
      pts: [["lowest setting (specification)", -40], ["power class 3 (specification)", 23], ["power class 2, some 5G bands (specification)", 26]],
      src: [["3GPP TS 36.101 (ETSI TS 136 101 V8.9.0), Tables 6.2.2-1 and 6.3.2.1-1: power class and minimum output power", SRC.lte], ["3GPP TS 38.101-1 (ETSI TS 138 101-1 V15.2.0), Table 6.2.1-1: power classes", SRC.nr]]},
    {label: "Macro base station, 40 W", lo: 43, typ: 46, hi: 49, est: true,
      moves: "The cell's size and the number of carriers and antennas: 20–80 W per carrier for a macro cell (est); small cells send far less.",
      pts: [["20 W carrier (est)", 43], ["40 W carrier (est)", 46], ["80 W carrier (est)", 49]], src: []},
    {label: "Radar transmitter (peak)", lo: 44, typ: 66, hi: 90, est: true,
      moves: "The radar type: a solid-state marine radar sends about 25 W peak with long coded pulses, a magnetron boat radar 4 kW, a weather or air-traffic radar up to 1 MW (est).",
      pts: [["solid-state marine radar (est)", 44], ["4 kW boat radar (est)", 66], ["weather and air-traffic radar (est)", 90]], src: []},
    {label: "FM broadcast transmitter", lo: 50, typ: 70, hi: 80, est: true,
      moves: "The station's coverage: a local station sends 100 W to 1 kW ERP, a regional one 10–100 kW (est).",
      pts: [["local station, 100 W (est)", 50], ["regional station, 10 kW (est)", 70], ["large regional station, 100 kW (est)", 80]], src: []},
  ];
  const dlRange = name => DBM_RANGES.find(g => g.label === name);
  const DL0 = -170, DL1 = 90, dlPc = x => (100 * (clamp(x, DL0, DL1) - DL0)) / (DL1 - DL0);
  const dbmTxt = x => `${x > 0 ? "+" : x < 0 ? "−" : ""}${+Math.abs(x).toFixed(1)} dBm`;
  const dlLink = ([l, h]) => `<a href="${h}">${esc(l)}</a>`;
  const dlSrc = ([t, u]) => (!u ? esc(t) : /^https?:/.test(u) ? `<a href="${u}" target="_blank" rel="noopener noreferrer">${esc(t)} ↗</a>` : `<a href="${u}">${esc(t)}</a>`);
  // distance from a power to a rung: 0 inside its band (then the nearest typical value wins), else to the band or line
  const dlDist = (r, p) => { const g = dlRange(r.name); return g ? Math.max(0, g.lo - p, p - g.hi) + Math.abs(p - g.typ) / 100 : Math.abs(p - r.p); };
  // the plain-words card of one rung: what it is, its range and what moves it, the points in it, our parts, sources
  function dlBody(r) {
    const g = dlRange(r.name);
    return `<dl><dt>What it is</dt><dd>${r.what}</dd>${g ? `<dt>Range</dt><dd>${dbmTxt(g.lo)} to ${dbmTxt(g.hi)}, typical ${dbmTxt(g.typ)}${g.est ? ' <span class="dl-est">est</span>' : ""}</dd>
      <dt>What moves it</dt><dd>${g.moves}</dd><dt>In the band</dt><dd><ul class="dl-pts">${g.pts.map(([l, x]) => `<li><b>${dbmTxt(x)}</b> ${esc(l)}</li>`).join("")}</ul></dd>` : `<dt>Value</dt><dd>${r.typ}</dd>`}
      <dt>${esc(r.ifLabel || "If it is violated")}</dt><dd>${r.bad}</dd>${r.parts ? `<dt>Our parts</dt><dd>${r.parts.map(dlLink).join(" · ")}</dd>` : ""}
      ${g ? `<dt>Source</dt><dd>${g.src.map(dlSrc).join("<br>")}${g.est ? `${g.src.length ? "<br>" : ""}BizDev estimate (est): no public source for this band yet.` : ""}</dd>` : ""}<dt>Read more</dt><dd>${r.read.map(dlLink).join(" · ")}</dd></dl>`;
  }
  const dlInfo = r => `<h4>${esc(r.name)}</h4>${dlBody(r)}`;
  // the ladder: one row per range (a band from low to high, a dark tick at the typical value), the fixed definitions as
  // lines across all rows, your power as an orange line. HTML, not SVG, so the text keeps its size on a phone.
  function dlLadder(p, pick) {
    const rows = DBM_RUNGS.filter(r => dlRange(r.name)).map(r => {
      const g = dlRange(r.name), a = dlPc(g.lo), b = dlPc(g.hi), right = a + b > 110, on = r.name === pick;
      const say = `${r.name}: ${dbmTxt(g.lo)} to ${dbmTxt(g.hi)}, typical ${dbmTxt(g.typ)}${g.est ? " (estimate)" : ""}. Show what moves it`;
      return `<div class="dl-row"><span class="dl-lab" style="${right ? `padding-right:${(100 - b).toFixed(1)}%;text-align:right` : `padding-left:${a.toFixed(1)}%`}">${esc(r.name)} <span class="dl-r">${dbmTxt(g.lo).replace(" dBm", "")} to ${dbmTxt(g.hi)}</span>${g.est ? ' <span class="dl-est">est</span>' : ""}</span>
        <span class="dl-tr"><button type="button" class="dl-b${g.est ? " est" : ""}${on ? " on" : ""}" data-dl="${esc(r.name)}" aria-pressed="${on}" aria-label="${esc(say)}" title="${esc(say)}" style="left:${a.toFixed(2)}%;width:${(b - a).toFixed(2)}%"><i style="left:${((100 * (g.typ - g.lo)) / Math.max(1e-9, g.hi - g.lo)).toFixed(1)}%"></i></button></span></div>`;
    }).join("");
    const lines = DBM_RUNGS.filter(r => !dlRange(r.name)), lab = {"Thermal noise in 1 MHz": "noise in 1 MHz", "1 mW: the reference": "1 mW", "1 W": "1 W"};
    const ticks = [];
    for (let x = -160; x <= 80; x += 20) ticks.push(`<span class="${x % 40 ? "mn" : ""}" style="left:${dlPc(x).toFixed(2)}%">${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x)}</span>`);
    return `<figure class="dl"><figcaption class="small muted">Each band runs from the realistic low end to the high end; the dark tick is the typical value. Dashed bands are estimates (est). Lines are fixed definitions. Tap or hover a band to see what moves the value.</figcaption>
      <div class="dl-plot">
        <div class="dl-head" aria-hidden="true">${lines.map(r => `<span style="left:${dlPc(r.p).toFixed(2)}%">${esc(lab[r.name] || r.name)}</span>`).join("")}</div>
        ${lines.map(r => `<i class="dl-ln" aria-hidden="true" style="left:${dlPc(r.p).toFixed(2)}%"></i>`).join("")}<i class="dl-ln you" aria-hidden="true" style="left:${dlPc(p).toFixed(2)}%"></i>
        ${rows}<div class="dl-ax" aria-hidden="true">${ticks.join("")}<span class="you" style="left:${dlPc(p).toFixed(2)}%">${esc(dbmTxt(p))}</span></div></div>
      <p class="small muted dl-axl">Power in dBm. Orange line: your slider.</p>
      <div class="dl-info" aria-live="polite">${dlInfo(DBM_RUNGS.find(r => r.name === pick) || DBM_RUNGS[0])}</div></figure>`;
  }
  let dlPick = null, dlLastP = null;  // the band picked by tap or hover; moving the slider shows the nearest again
  const BLOCKER = v => v.mode === "blocker", LADDER = v => v.mode !== "blocker";
  V.push({
    id: "dbm", group: "RF links", title: "dBm: the power ladder",
    lead: "Every RF power on one logarithmic scale, from a GNSS signal at the antenna to a radar transmitter. Most rungs are ranges, not one value: each band shows the realistic low and high end and the typical value, with its source. Switch to the blocker view to see what a strong signal next to the band does to a receiver, and what linearity fixes it.",
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
      {k: "p", label: "Power", min: -170, max: 90, step: 1, value: 20, unit: "dBm", when: LADDER},
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
    setup(el) {  // tap, hover or focus a band: the box under the ladder explains it (no re-render, so focus stays)
      el.hidden = true;
      const more = el.parentElement.querySelector(".vz-more");
      const pick = b => {
        if (!b) return;
        dlPick = b.dataset.dl;
        more.querySelectorAll(".dl-b").forEach(x => { const on = x === b; x.classList.toggle("on", on); x.setAttribute("aria-pressed", String(on)); });
        const box = more.querySelector(".dl-info"), r = DBM_RUNGS.find(x => x.name === dlPick);
        if (box && r) box.innerHTML = dlInfo(r);
      };
      more.addEventListener("click", e => pick(e.target.closest(".dl-b")));
      more.addEventListener("focusin", e => pick(e.target.closest(".dl-b")));
      more.addEventListener("pointerover", e => { if (e.pointerType === "mouse") pick(e.target.closest(".dl-b")); });
    },
    compute(v) {
      if (v.mode !== "blocker") {
        const w = 1e-3 * undb(v.p), vr = Math.sqrt(w * 50);
        if (v.p !== dlLastP) { dlPick = null; dlLastP = v.p; }
        const near = DBM_RUNGS.reduce((a, r) => (dlDist(r, v.p) < dlDist(a, v.p) ? r : a)), pick = dlPick || near.name;
        const inside = DBM_RANGES.filter(g => v.p >= g.lo && v.p <= g.hi).map(g => g.label);
        const rung = r => { const g = dlRange(r.name); return `<details class="vz-rung${r === near ? " near" : ""}"><summary><b class="lv">${g ? `${dbmTxt(g.lo).replace(" dBm", "")} to ${dbmTxt(g.hi)}` : dbmTxt(r.p)}</b><b>${esc(r.name)}</b><span class="muted">${g ? `typical ${esc(dbmTxt(g.typ))}${g.est ? " (est)" : ""}` : esc(si(1e-3 * undb(r.p), "W"))}</span></summary>${dlBody(r)}</details>`; };
        return {
          outputs: [["Power", si(w, "W")], ["dBW", `${num(v.p - 30)} dBW`], ["Voltage into 50 Ω", si(vr, "V") + " rms"],
            ["Inside these bands", inside.length ? inside.join(" · ") : `none: nearest is ${near.name}`]],
          eq: `P<sub>dBm</sub> = 10 · log<sub>10</sub>( P / 1 mW )`,
          eqn: `${num(v.p)} dBm = 10 · log<sub>10</sub>( ${si(w, "W")} / 1 mW )`,
          nochart: true,
          html: `${dlLadder(v.p, pick)}<div class="vz-terms small"><span><b>dBm</b>: power compared with 1 milliwatt, in decibels. 0 dBm = 1 mW, +10 dBm = 10 mW, +30 dBm = 1 W, −30 dBm = 1 µW. +3 dB doubles the power, +10 dB is ten times.</span>
            <span><b>dB</b>: a ratio (gain, loss, isolation), no unit. <b>dBc</b>: below the carrier. <b>dBi</b>: antenna gain.</span>
            <span><b>Sensitivity</b>: the weakest signal a receiver still decodes. <b>Blocker</b>: a strong unwanted signal near the band that overloads the receiver so it loses the weak wanted one.</span>
            <span><b>IIP3</b>: how strong two unwanted signals may be before the receiver makes its own interference; higher is better (<a href="/rf-notes#iip3_basics">IIP3 in plain words</a>, <a href="#ip3">IP3 visual</a>).</span>
            <span>Basics: <a href="/rf-notes#dbm_basics">dBm and decibels</a> · <a href="/rf-notes#sensitivity_noise_floor">Sensitivity and noise floor</a> · <a href="/rf-notes#dynamic_range_sfdr_blocking">Blocking</a> · <a href="https://www.minicircuits.com/appdoc/AN60-038.html" target="_blank" rel="noopener noreferrer">Mini-Circuits: amplifier terms defined ↗</a></span></div>
            <p class="small"><b>All rungs as text</b> <span class="muted">(open one for its range, what moves it and the source)</span></p><div class="vz-rungs">${DBM_RUNGS.map(rung).join("")}</div>`,
          note: "Every 10 dB is a factor of 10 in power, every 3 dB a factor of 2. A receiver handles signals 20 orders of magnitude below what the transmitter next to it sends: that is why filters, isolation and linearity matter. Each band names its source (standards and data sheets); bands marked est are BizDev estimates. Check the specification edition for a design.",
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
          ["Input IP3 needed", isFinite(need) ? `≥ ${num(need)} dBm` : "wanted signal is below the noise: raise it or lower the NF", isFinite(need) ? "" : "bad"], bandOut(v.f * 1000)],
        eq: `IM3<sub>in</sub> = 3·P<sub>blk</sub> − 2·IIP3 &nbsp;·&nbsp; SINR = P<sub>wanted</sub> − 10 log(10<sup>N/10</sup> + 10<sup>IM3/10</sup>) &nbsp;·&nbsp; IIP3<sub>min</sub> = (3·P<sub>blk</sub> − I<sub>allowed</sub>) / 2`,
        eqn: `IM3 = 3·(${num(pin)}) − 2·(${num(v.ia)}) = ${num(im3(v.ia))} dBm (standard) &nbsp;·&nbsp; ${num(im3(v.ib))} dBm (high linearity) &nbsp;·&nbsp; noise floor ${num(N)} dBm`,
        chart: {x: {min: -90, max: 20, label: "Blocker at the receiver input, per tone (dBm)"}, y: {min: -180, max: 10, label: "Level at the input (dBm)"},
          series: [{pts: xs.map(x => [x, 3 * x - 2 * v.ia]), color: C.orange, label: `IM3, IIP3 ${num(v.ia)}`}, {pts: xs.map(x => [x, 3 * x - 2 * v.ib]), color: C.green, label: `IM3, IIP3 ${num(v.ib)}`}],
          hlines: [{y: N, label: `noise floor ${num(N)}`, color: C.grey}, {y: v.pw, label: `wanted ${num(v.pw)}`, color: C.blue, dash: ""}, ...(isFinite(allow) ? [{y: allow, label: "max interference for the SNR", color: C.red}] : [])],
          vlines: [{x: pin, label: "blocker after filter", color: C.purple, row: 1}],
          marks: [{x: pin, y: im3(v.ia), color: C.orange, label: `${num(im3(v.ia))} dBm`}, {x: pin, y: im3(v.ib), color: C.green, label: `${num(im3(v.ib))} dBm`}]},
        html: `${bandStrip(v.f * 1000)}<div class="vz-sugg"><b>Our ${v.pt === "switch" ? "switches" : "LNAs"} at ${num(v.f)} GHz with input IP3 ≥ ${isFinite(need) ? num(need) + " dBm" : "–"}</b>${suggestionHtml(sg, "no part of ours covers this frequency with a stated IP3")}<p class="small muted">From catalogue key specs; IIP3 is taken from the data sheet or as OIP3 − gain. Check the full data sheet.</p></div>`,
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
        outputs: [["Path loss", `${num(L)} dB`], ["Received", `${num(pr(v.d))} dBm`], ["Margin", `${num(margin)} dB`, margin < 0 ? "bad" : margin < 10 ? "warn" : "ok"], ["Free-space range", si(dmax * 1000, "m")], bandOut(v.f * 1000)],
        eq: `FSPL = 20 log<sub>10</sub>(d<sub>km</sub>) + 20 log<sub>10</sub>(f<sub>MHz</sub>) + 32.44 &nbsp;·&nbsp; P<sub>rx</sub> = P<sub>tx</sub> + G − FSPL`,
        eqn: `${num(L)} dB = 20 log(${num(v.d)}) + 20 log(${num(v.f * 1000)}) + 32.44 &nbsp;·&nbsp; ${num(pr(v.d))} dBm = ${v.pt} + ${v.g} − ${num(L)}`,
        chart: {x: {min: 0.001, max: 100, log: true, label: "Distance (km)", fmt: x => si(x * 1000, "m")}, y: {min: -160, max: 40, label: "Received power (dBm)"},
          series: [[0.9, C.grey], [5.8, C.purple], [28, C.teal]].filter(([f]) => Math.abs(f - v.f) > 0.05).map(([f, c]) => ({pts: ds.map(d => [d, v.pt + v.g - fspl(d, f)]), color: c, width: 1.5, dash: "4 3", label: `${f} GHz`}))
            .concat([{pts: ds.map(d => [d, pr(d)]), color: C.blue, width: 3, label: `${num(v.f)} GHz`}]),
          hlines: [{y: v.s, label: `sensitivity ${v.s} dBm`, color: C.red}], marks: [{x: v.d, y: pr(v.d), label: `${num(pr(v.d))} dBm at ${si(v.d * 1000, "m")}`}]},
        html: `${bandStrip(v.f * 1000, {caption: "The path loss is worked out at one frequency; across a band it changes by 20·log(high / low) dB. The bands around it, as ranges:"})}`,
        note: "Each doubling of distance or frequency costs 6 dB. Higher bands lose more with fixed antenna gains, but an antenna of the same size has more gain at a higher frequency, which is how mmWave links close. Real paths add walls, rain and fading on top of this free-space line.",
      };
    },
    related: [["RF bands", "/rf-bands"]],
  });

  // the application bands on the wavelength chart: [band id, label, label row]; ranges come from the RF bands data
  const WAVE_BANDS = [["am", "AM", 0], ["fm", "FM", 1], ["dab", "DAB", 2], ["b8", "LTE 900", 0], ["gnss_l5", ""], ["gnss_l2", ""], ["gnss_l1", "GNSS", 1],
    ["ism24", "2.4 GHz", 2], ["wifi5", "Wi-Fi 5/6", 3], ["wifi6", ""], ["uwb5", ""], ["uwb9", "UWB", 4], ["n257", "n257", 0], ["radar_77", "radar", 1]];
  V.push({
    id: "wave", group: "RF links", title: "Wavelength and antenna size",
    explains: [["UWB", "/knowledge#p-uwb"], ["Broadcast radio tuners", "/knowledge#p-tuners"]],
    physics: [["Antennas and wavelength", "phys_antennas_wavelength"]],
    lead: "Wavelength sets antenna size and tells you when a PCB trace starts behaving like a transmission line.",
    controls: [{k: "f", label: "Frequency", min: 0.0001, max: 100, value: 2.4, unit: "GHz", log: true}],
    compute(v) {
      const lam = 0.299792458 / v.f, pcb = lam / Math.sqrt(3.3), id = bandsAt(v.f * 1000)[0];
      const span = id ? [Math.min(...BANDS[id].ranges.map(r => r[0])), Math.max(...BANDS[id].ranges.map(r => r[1]))] : null;  // MHz
      return {
        outputs: [["Wavelength λ", si(lam, "m")], ["λ/4 monopole", si(lam / 4, "m")], ["λ/2 dipole", si(lam / 2, "m")], ["λ on FR-4 microstrip", si(pcb, "m")], ["Trace is a line above ≈ λ/10", si(pcb / 10, "m")],
          bandOut(v.f * 1000, 1), ...(span ? [[`λ/4 across ${BANDS[id].name}`, `${si(299.792458 / span[1] / 4, "m")} to ${si(299.792458 / span[0] / 4, "m")}`]] : [])],
        eq: `λ = c / f &nbsp;·&nbsp; λ<sub>PCB</sub> ≈ λ / √ε<sub>r,eff</sub> (FR-4 microstrip ε<sub>r,eff</sub> ≈ 3.3)`,
        eqn: `${si(lam, "m")} = 3·10<sup>8</sup> m/s / ${si(v.f * 1e9, "Hz")}`,
        chart: {x: {min: 0.0001, max: 100, log: true, label: "Frequency (bands as ranges, from the RF bands chart)", fmt: x => si(x * 1e9, "Hz")}, y: {min: 1e-3, max: 3000, log: true, label: "Length", fmt: x => si(x, "m")},
          series: [{pts: range(0.0001, 100, 50, true).map(f => [f, 0.299792458 / f]), label: "λ in air"}, {pts: range(0.0001, 100, 50, true).map(f => [f, 0.299792458 / f / 4]), color: C.orange, dash: "6 4", label: "λ/4 antenna"}],
          bands: appBands(WAVE_BANDS, 1e-3), marks: [{x: v.f, y: lam, label: `λ = ${si(lam, "m")}`}]},
        html: `<p class="small">The shaded ranges are the real bands, not one frequency: FM is ${bandText("fm")} (${BANDS.fm ? BANDS.fm.sub.map(([a, b, l]) => `${l} ${mhzR(a, b)}`).join(", ") : ""}), AM ${bandText("am")}, DAB ${bandText("dab")}. An antenna for a whole band is a compromise across it; the <a href="/rf-bands">RF bands chart</a> lists every band.</p>`,
        note: "At 2.4 GHz a quarter-wave antenna is 31 mm; at 28 GHz it is under 3 mm, small enough to put arrays of them in a package (antenna-in-package). Above λ/10 a trace needs controlled impedance.",
      };
    },
  });

  // receiver chain for the cascaded noise figure: loss stages (filter, switch) set gain = −loss and NF = loss.
  // A block can take a real part's numbers (owner 23 Oct 2026: "allow a selection of 1 or 2 Skyworks parts as an
  // example; graph how the signal behaves through each block"); a number the catalogue does not state stays the
  // slider's assumed value and is marked "Not Enough Data".
  const NF_TYPES = {filter: ["Filter", true, C.grey, ["filter"], "Filt"], switch: ["Switch", true, C.teal, ["switch"], "Sw"], lna: ["LNA", false, C.blue, ["lna"], "LNA"],
    gain: ["Gain block", false, C.green, ["gain"], "Gain"], mixer: ["Mixer", false, C.orange, ["mixer"], "Mix"], if: ["ADC / IF", false, C.purple, [], "ADC"]};
  const NF_DEFAULT = () => [{t: "filter", g: -1, nf: 1}, {t: "lna", g: 18, nf: 0.8}, {t: "mixer", g: 8, nf: 9}, {t: "if", g: 0, nf: 20}];
  // worked examples with real Skyworks parts (numbers from the catalogue key specs)
  const NF_EXAMPLES = [
    {label: "Cellular 1.9 GHz: SKY13489-001 switch + SKY67151-396LF LNA", f: 1.9, bw: 10, chain: [{t: "switch", part: "SKY13489-001"}, {t: "lna", part: "SKY67151-396LF"}, {t: "mixer", part: "SKY73090-21"}, {t: "if", g: 0, nf: 20}]},
    {label: "GNSS L1: SKY65723-11 LNA", f: 1.575, bw: 2, chain: [{t: "filter", g: -1.5, nf: 1.5}, {t: "lna", part: "SKY65723-11"}, {t: "if", g: 0, nf: 12}]},
    {label: "Wi-Fi 5.2 GHz: SKY85922-11 filter + SKY65404-31 LNA", f: 5.2, bw: 20, chain: [{t: "filter", part: "SKY85922-11"}, {t: "lna", part: "SKY65404-31"}, {t: "if", g: 0, nf: 15}]},
  ];
  const partBy = mpn => (PARTS || []).find(p => p.mpn === mpn);
  // copy a part's numbers into a block; returns the block with ned = the numbers the catalogue does not give
  function usePart(s, mpn) {
    s.part = mpn || "";
    s.ned = [];
    const p = partBy(s.part), loss = NF_TYPES[s.t][1];
    if (!p) { s.part = ""; return s; }
    if (loss) { if (p.il != null) { s.g = -p.il; s.nf = p.il; } else s.ned.push("loss"); }
    else {
      if (p.gain != null) s.g = p.gain; else s.ned.push("gain");
      if (p.nf != null) s.nf = p.nf; else s.ned.push("NF");
    }
    return s;
  }
  let chain = NF_DEFAULT();
  V.push({
    id: "nf", group: "Receivers", title: "Cascaded noise figure and sensitivity",
    explains: [["Front-end modules and LNAs", "/knowledge#p-front_ends"], ["Broadcast radio tuners", "/knowledge#p-tuners"]],
    physics: [["Gain and noise", "phys_noise_gain"]],
    lead: "Why the first stage decides the receiver. Build the chain below or start from an example with real Skyworks parts: pick a part for any block and its catalogue gain, noise figure or loss is used. The graph follows the signal and the noise through each block; the gap between them is the signal-to-noise ratio, and it can only shrink.",
    controls: [
      {k: "f", label: "Frequency", min: 0.05, max: 40, value: 2.4, unit: "GHz", log: true},
      {k: "bw", label: "Channel bandwidth", min: 0.01, max: 400, value: 20, unit: "MHz", log: true},
      {k: "pin", label: "Signal at the antenna", min: -130, max: -30, step: 1, value: -90, unit: "dBm"},
      {k: "snr", label: "SNR the demodulator needs", min: -5, max: 30, step: 0.5, value: 10, unit: "dB"},
    ],
    parts: true,
    setup(el, rerender, setVals) {
      chain = NF_DEFAULT();
      let drag = null;
      const slider = (i, key, label, min, max, step, val, off) => `<label class="vz-bs"><span>${label} <output>${num(val)} dB</output></span><input type="range" data-i="${i}" data-f="${key}" min="${min}" max="${max}" step="${step}" value="${val}" aria-valuetext="${num(val)} dB"${off ? " disabled" : ""}></label>`;
      const picker = (i, s) => {
        const stages = NF_TYPES[s.t][3];
        if (!stages.length) return "";
        if (!PARTS) return '<span class="muted small">loading parts…</span>';
        const opts = mfr => PARTS.filter(p => p.mfr === mfr && stages.includes(p.stage)).sort((a, b) => a.mpn.localeCompare(b.mpn))
          .map(p => `<option value="${esc(p.mpn)}"${p.mpn === s.part ? " selected" : ""}>${esc(p.mpn)} (${num(p.fmin)}–${num(p.fmax)} GHz)</option>`).join("");
        return `<select class="vz-part" data-pi="${i}" aria-label="Part for block ${i + 1}"><option value="">Your numbers</option><optgroup label="Skyworks">${opts("Skyworks")}</optgroup><optgroup label="Qorvo (Skyworks)">${opts("Qorvo")}</optgroup></select>`;
      };
      const ned = (s, k) => (s.ned || []).includes(k) ? ' <span class="vz-ned">Not Enough Data: assumed</span>' : "";
      const draw = () => {
        el.innerHTML = `<div class="vz-ex small"><span class="muted">Examples with Skyworks parts:</span>${NF_EXAMPLES.map((x, i) => `<button type="button" class="outline secondary" data-ex="${i}">${esc(x.label)}</button>`).join("")}</div>
        <div class="vz-chain" role="list" aria-label="Receiver chain">${chain.map((s, i) => {
          const [name, loss, color] = NF_TYPES[s.t], fixed = !!s.part;
          return `${i ? '<span class="vz-arrow" aria-hidden="true">→</span>' : ""}<div class="vz-blk" role="listitem" draggable="false" data-i="${i}" style="border-top-color:${color}">
            <div class="vz-blk-h"><span class="vz-grip" title="Drag to reorder" aria-hidden="true">⠿</span><b>${i + 1}. ${esc(name)}</b>
              <span class="vz-blk-b"><button type="button" data-mv="-1" data-i="${i}" title="Move earlier" aria-label="Move ${esc(name)} earlier"${i ? "" : " disabled"}>←</button><button type="button" data-mv="1" data-i="${i}" title="Move later" aria-label="Move ${esc(name)} later"${i < chain.length - 1 ? "" : " disabled"}>→</button><button type="button" data-rm="${i}" title="Remove" aria-label="Remove ${esc(name)}"${chain.length > 1 ? "" : " disabled"}>×</button></span></div>
            ${picker(i, s)}
            ${loss ? slider(i, "loss", "Loss" + ned(s, "loss"), 0, 6, 0.05, s.nf, fixed && !ned(s, "loss")) : slider(i, "g", "Gain" + ned(s, "gain"), -10, 35, 0.5, s.g, fixed && !ned(s, "gain")) + slider(i, "nf", "NF" + ned(s, "NF"), 0.2, 30, 0.05, s.nf, fixed && !ned(s, "NF"))}</div>`;
        }).join("")}</div>
        <div class="vz-add"><select aria-label="Stage to add">${Object.entries(NF_TYPES).map(([k, [n]]) => `<option value="${k}">${esc(n)}</option>`).join("")}</select><button type="button" class="small-btn outline">+ Add stage</button></div>`;
        el.querySelectorAll("input[data-f]").forEach(inp => inp.addEventListener("input", () => {
          const s = chain[+inp.dataset.i], x = +inp.value;
          if (inp.dataset.f === "loss") { s.g = -x; s.nf = x; } else s[inp.dataset.f] = x;
          inp.previousElementSibling.querySelector("output").textContent = `${num(x)} dB`;
          inp.setAttribute("aria-valuetext", `${num(x)} dB`);
          rerender();
        }));
        el.querySelectorAll("select[data-pi]").forEach(sel => sel.addEventListener("change", () => { usePart(chain[+sel.dataset.pi], sel.value); draw(); rerender(); }));
        el.querySelectorAll("[data-ex]").forEach(btn => btn.addEventListener("click", () => {
          const x = NF_EXAMPLES[+btn.dataset.ex];
          chain = x.chain.map(s => (s.part ? usePart({t: s.t, g: 10, nf: 2}, s.part) : {...s}));
          setVals({f: x.f, bw: x.bw});
          draw(); rerender();
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
      return draw;  // redrawn when the parts list arrives
    },
    compute(v) {
      // stage by stage: cumulative gain and noise factor, signal and noise at each block's output
      const kTB = -174 + db(v.bw * 1e6);
      let G = 1, F = 0;
      const st = chain.map((s, i) => {
        const t = i === 0 ? undb(s.nf) : (undb(s.nf) - 1) / G;
        G *= undb(s.g); F += t;
        return {s, t, gc: db(G), nfc: db(F), sig: v.pin + db(G), noise: kTB + db(F) + db(G), snr: v.pin - kTB - db(F)};
      });
      const nf = db(F), sens = kTB + nf + v.snr, gain = db(G);
      const extra = st.map(({t}, i) => (i === 0 ? t - 1 : t)), tot = extra.reduce((a, b) => a + b, 0) || 1;
      const snr0 = v.pin - kTB, snrEnd = st.length ? st[st.length - 1].snr : snr0;
      const anyNed = chain.some(s => (s.ned || []).length);
      const cell = (s, k, val) => ((s.ned || []).includes(k) ? `<span class="vz-ned" title="The catalogue does not state it; the slider value is assumed">Not Enough Data</span> <small class="muted">(${val} assumed)</small>` : val);
      const tbl = `<div class="vz-cas"><table><thead><tr><th>Block</th><th>Part</th><th class="n">Gain</th><th class="n">NF / loss</th><th class="n">Signal out</th><th class="n">Noise out</th><th class="n">SNR</th><th class="n">NF so far</th><th class="n">Share of noise</th></tr></thead><tbody>
        <tr><td>Antenna</td><td class="muted">–</td><td></td><td></td><td class="n">${num(v.pin)} dBm</td><td class="n">${num(kTB)} dBm</td><td class="n">${num(snr0)} dB</td><td class="n">0 dB</td><td></td></tr>
        ${st.map((x, i) => {
          const [name, loss] = NF_TYPES[x.s.t], p = partBy(x.s.part), cov = p ? covers(p, v.f) : true;
          return `<tr><td>${i + 1}. ${esc(name)}</td><td>${p ? `<a href="/find?q=${encodeURIComponent(p.mpn)}">${esc(p.mpn)}</a>${cov ? "" : ` <small class="vz-ned">not at ${num(v.f)} GHz</small>`}` : '<span class="muted">your numbers</span>'}</td>
            <td class="n">${loss ? cell(x.s, "loss", `${num(x.s.g)} dB`) : cell(x.s, "gain", `${num(x.s.g)} dB`)}</td><td class="n">${loss ? cell(x.s, "loss", `${num(x.s.nf)} dB`) : cell(x.s, "NF", `${num(x.s.nf)} dB`)}</td>
            <td class="n">${num(x.sig)} dBm</td><td class="n">${num(x.noise)} dBm</td><td class="n">${num(x.snr)} dB</td><td class="n">${num(x.nfc)} dB</td><td class="n">${num((100 * extra[i]) / tot, 2)} %</td></tr>`;
        }).join("")}</tbody></table></div>`;
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
      const xs = [0, ...st.map((_, i) => i + 1)], lab = i => (i === 0 ? "Ant" : `${i} ${NF_TYPES[chain[i - 1].t][4]}`);
      const ys = [v.pin, kTB, ...st.flatMap(x => [x.sig, x.noise])], ymin = Math.floor((Math.min(...ys) - 10) / 10) * 10, ymax = Math.ceil((Math.max(...ys) + 10) / 10) * 10;
      return {
        outputs: [["System noise figure", `${num(nf)} dB`], ["Total gain", `${num(gain)} dB`], ["SNR at the antenna → output", `${num(snr0)} → ${num(snrEnd)} dB`, snrEnd < v.snr ? "bad" : ""],
          ["Noise floor (input)", `${num(kTB + nf)} dBm`], ["Sensitivity", `${num(sens)} dBm`], bandOut(v.f * 1000), ...(anyNed ? [["Catalogue data", "Not Enough Data for some blocks: assumed values used", "warn"]] : [])],
        eq: `F = F<sub>1</sub> + (F<sub>2</sub> − 1)/G<sub>1</sub> + (F<sub>3</sub> − 1)/(G<sub>1</sub>G<sub>2</sub>) + … &nbsp;·&nbsp; SNR<sub>k</sub> = P<sub>in</sub> − (−174 + 10 log BW + NF<sub>k</sub>) &nbsp;·&nbsp; S = −174 dBm/Hz + NF + 10 log<sub>10</sub>(BW) + SNR`,
        eqn: `SNR = ${num(v.pin)} − (${num(kTB)} + ${num(nf)}) = ${num(snrEnd)} dB &nbsp;·&nbsp; S = −174 + ${num(nf)} + ${num(db(v.bw * 1e6))} + ${v.snr} = ${num(sens)} dBm`,
        chart: {x: {min: 0, max: Math.max(1, st.length), label: "Block (Ant = antenna, then the output of each block)", fmt: t => (Number.isInteger(t) && t <= st.length ? lab(t) : "")},
          y: {min: ymin, max: ymax, label: "Level (dBm)"},
          series: [{pts: xs.map((x, i) => [x, i ? st[i - 1].sig : v.pin]), color: C.blue, label: "Signal"}, {pts: xs.map((x, i) => [x, i ? st[i - 1].noise : kTB]), color: C.red, label: "Noise in the channel"}],
          marks: xs.map((x, i) => ({x, y: i ? st[i - 1].sig : v.pin, r: 4, color: C.blue, label: i === xs.length - 1 || i === 0 ? `SNR ${num(i ? st[i - 1].snr : snr0)} dB` : ""}))},
        html: `${tbl}${bandStrip(v.f * 1000, {caption: "The parts are chosen at one frequency; the band around it is a range (from the RF bands chart)"})}<div class="vz-sugg"><b>Our parts for each block at ${num(v.f)} GHz</b><table class="vz-sugg-t small"><tbody>${rows.join("")}</tbody></table><p class="small muted">Part numbers from catalogue key specs (typical values at the test frequency; active parts only). "Not Enough Data": the catalogue does not state that number, so the block keeps the slider's assumed value. Check the full data sheet before choosing.</p></div>`,
        note: "The blue line is the wanted signal, the red line the noise in the channel. Both rise with gain, but each block adds its own noise, so the gap (SNR) only shrinks: most of it is lost in the first blocks. Put a lossy filter or switch first and the SNR drops by its loss straight away; behind a high-gain LNA, the mixer and ADC hardly matter. That is why low-loss switches, BAW filters and low-NF LNAs sell.",
      };
    },
    related: [["Blocker scenario (dBm visual)", "#dbm"], ["IIP3 in plain words", "/rf-notes#iip3_basics"], ["Cascaded noise figure (note)", "/rf-notes#cascaded_noise_figure"], ["LNAs on the RF coverage page", "/business/rf-coverage"]],
  });

  // ---- intermodulation maths for the IP3 and FM visuals (owner, 2 Nov 2026). Pure: nothing from the page or the
  // helpers above, so tests/test_rf_visuals_1102.py runs this block in node. Levels in dBm at the receiver input, MHz.
  const IMX = (() => {
    const dB = x => 10 * Math.log10(x), lin = x => 10 ** (x / 10);
    const sum = (...ps) => dB(ps.reduce((s, p) => s + lin(p), 0));  // power sum of levels in dBm
    // third-order products of tones A and B: at 2A − B the tone A counts twice, so 2·P_A + P_B − 2·IIP3 (equal tones:
    // 3·P − 2·IIP3): 1 dB more of both tones makes them 3 dB stronger, 1 dB more IIP3 2 dB weaker
    const im3 = (fa, pa, fb, pb, iip3) => [
      {k: "2A − B", f: 2 * fa - fb, p: 2 * pa + pb - 2 * iip3},
      {k: "2B − A", f: 2 * fb - fa, p: 2 * pb + pa - 2 * iip3},
    ];
    const noise = (nf, bwHz) => -174 + nf + dB(bwHz);  // thermal noise in the channel plus the noise figure
    const friis = (nf1, g1, nf2) => dB(lin(nf1) + (lin(nf2) - 1) / lin(g1));  // noise figure of two stages in a row
    const tracking = (df, bw) => (bw ? dB(1 + ((2 * df) / bw) ** 2) : 0);  // single-tuned filter of 3 dB bandwidth bw
    const current = (ip3, ip30 = 20, i0 = 10) => i0 * 2 ** ((ip3 - ip30) / 10);  // est: about 2x per +10 dB of IP3
    // where a product falls against the tuned channel: on it (±25 kHz), inside it (±100 kHz), next channel (±200 kHz)
    const near = (f, ft) => { const d = Math.abs(f - ft) - 1e-9; return d <= 0.025 ? "on" : d <= 0.1 ? "near" : d <= 0.2 ? "adjacent" : ""; };
    // FM: tuned station ft at pt, strong stations A (fa, pa) and B (fb, pb), receiver IIP3, and the fixes in dB:
    // lin = more IIP3; att = an attenuator or AGC in front (every signal falls by att); bw = tracking filter (MHz)
    const fm = (s, fx = {}) => {
      const ra = tracking(s.fa - s.ft, fx.bw), rb = tracking(s.fb - s.ft, fx.bw), att = fx.att || 0;
      const pa = s.pa - att - ra, pb = s.pb - att - rb, pt = s.pt - att, iip3 = s.iip3 + (fx.lin || 0);
      return {pa, pb, pt, iip3, ra, rb, ghosts: im3(s.fa, pa, s.fb, pb, iip3).map(g => ({...g, d: g.f - s.ft, at: near(g.f, s.ft), over: g.p - pt}))};
    };
    // the one-line verdict with the arithmetic; sel: what the channel filter takes off one channel away (dB), sens: the
    // tuner's sensitivity (dBm). tone: ok, warn or bad
    const mhz = f => f.toFixed(1), n0 = x => String(Math.round(Math.abs(x)));
    function verdict(s, m, sel = 50, sens = -112) {
      const own = ["A", "B"].find((k, i) => Math.abs((i ? s.fb : s.fa) - s.ft) < 0.05);
      if (own) return {tone: "warn", text: `You are tuned to station ${own} itself: move your station or the strong stations.`};
      const g = m.ghosts.filter(x => x.at).sort((a, b) => Math.abs(a.d) - Math.abs(b.d))[0];
      const weak = m.pt < sens ? ` Your station is now at ${Math.round(m.pt)} dBm, below the tuner's sensitivity (${sens} dBm): too weak to hear.` : "";
      const [f1, f2] = m.ghosts.map(x => x.f).sort((a, b) => a - b);
      if (!g) return {tone: weak ? "warn" : "ok", text: `No: the products land on ${mhz(f1)} and ${mhz(f2)} MHz; your ${mhz(s.ft)} MHz is clear.${weak}`};
      const [a, b] = g.k === "2A − B" ? [s.fa, s.fb] : [s.fb, s.fa], sumTxt = `2 × ${mhz(a)} − ${mhz(b)} = ${mhz(g.f)} MHz`;
      const kHz = Math.round(Math.abs(g.d) * 1000), eff = g.at === "adjacent" ? g.over - sel : g.over;  // the filter's share
      const head = g.at === "on" ? `Yes, this is an intermod product: ${sumTxt}, exactly your station.`
        : g.at === "near" ? `Yes, close: ${sumTxt}, ${kHz} kHz from your ${mhz(s.ft)} MHz, inside its channel.`
          : `Next door: ${sumTxt}, on the adjacent channel ${kHz} kHz from your ${mhz(s.ft)} MHz; the channel filter takes about ${sel} dB off it.`;
      const what = eff >= 0 ? (g.at === "on" ? "you'll hear stations A and B mixed in, or a whistle" : "you'll hear a whistle or distortion")
        : eff > -30 ? "still audible as noise or distortion (about 30 dB is needed for clean mono, est)" : "harmless with this receiver";
      const tone = eff >= 0 ? "bad" : eff > -30 || weak ? "warn" : "ok";
      return {tone, g, text: `${head} The ghost is ${g.over >= 0 ? `${n0(g.over)} dB louder than` : `${n0(g.over)} dB below`} your station → ${what}.${weak}`};
    }
    // the IP3 visual: a wanted signal pw and two neighbours of pn each, placed so that 2f1 − f2 falls on the wanted one,
    // into an amplifier (gain g, output IP3 oip3, noise figure nf1) with the rest of the receiver behind it (nf2)
    function rx(s) {
      const iip3 = s.oip3 - s.g, nf = friis(s.nf1, s.g, s.nf2), n = noise(nf, s.bw * 1e6), im = 3 * s.pn - 2 * iip3;
      const sinr = s.pw - sum(n, im);
      return {iip3, nf, n, im, sinr, mNoise: s.pw - n - s.snr, mIm: s.pw - im - s.snr, lost: sinr < s.snr, comp: s.pn > iip3 - 9.6, ma: current(s.oip3)};
    }
    return {dB, lin, sum, im3, noise, friis, tracking, current, near, fm, verdict, rx};
  })();
  // ---- end of the intermodulation maths

  const dbTxt = x => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${+Math.abs(x).toFixed(1)} dB`;
  // fold the engine's chart under a summary (the redesigned visuals draw their own main picture above the controls)
  function foldChart(el, text, rerender) {
    const cw = el.parentElement.querySelector(".vz-chartwrap");
    if (!cw) return;
    const d = document.createElement("details");
    d.className = "vz-fold";
    d.innerHTML = `<summary>${esc(text)}</summary>`;
    cw.before(d);
    d.append(cw);
    d.addEventListener("toggle", () => rerender());  // draw it at its real width once open
  }
  // repaint a box of our own and give the focus back to the control that had it (keyboard users keep their place)
  function keepFocus(root, paint) {
    const a = document.activeElement, k = a && root.contains(a) ? a.dataset.fk : null;
    paint();
    if (k) { const el = root.querySelector(`[data-fk="${k}"]`); if (el) el.focus({preventScroll: true}); }
  }
  // SVG labels that do not overlap: move a label up by one line while it hits one already placed
  function placeLabels(labels, top, left, right) {
    const out = [], placed = [];
    for (const lb of labels.sort((a, b) => a.x - b.x)) {
      const w = lb.t.length * 6.2 + 6, x = clamp(lb.x, left + w / 2, right - w / 2);
      let y = Math.max(top + 10, lb.y);
      while (placed.some(p => Math.abs(p.x - x) < (p.w + w) / 2 && Math.abs(p.y - y) < 12) && y > top + 10) y -= 12;
      placed.push({x, y, w});
      out.push(`<text class="${lb.c || "fm-lb"}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle">${esc(lb.t)}</text>`);
    }
    return out.join("");
  }

  // ---- IP3 (owner, 2 Nov 2026: "I can move a lot, but it doesn't bring any value: what am I actually trading off with
  // linearity?"): a weak signal, two strong neighbours and their false tones growing until one covers it, and a meter
  // of the trade-off: too weak to hear (noise: gain, noise figure) against drowned by distortion (IP3, neighbours).
  // Scenario values are BizDev estimates (est) unless the preset note names a source.
  const IP3_CASES = {
    gen: {label: "A receiver at 1 GHz", f0: 1000, df: 1, pw: -90, bw: 1, snr: 10, nf1: 2, nf2: 15},
    ble: {label: "BLE next to Wi-Fi", f0: 2402, df: 3, pw: -90, bw: 1, snr: 12, nf1: 2, nf2: 10},
    fm: {label: "Car FM next to a strong local station", f0: 98, df: 0.4, pw: -80, bw: 0.2, snr: 26, nf1: 3, nf2: 10},
    nr: {label: "5G phone near a base station", f0: 3500, df: 20, pw: -95, bw: 10, snr: -1, nf1: 1.5, nf2: 10},
  };
  const IPP = {L: 36, R: 10, T: 22, B: 34, H: 236, Y0: -140, Y1: 0};
  let ipUI = null;
  function ipSvg(c, s, r, W) {
    const {L, R, T, B, H, Y0, Y1} = IPP, w = W - L - R, h = H - T - B, base = T + h;
    const x = k => L + ((k + 1.5) / 5) * w, y = p => T + ((Y1 - clamp(p, Y0, Y1)) / (Y1 - Y0)) * h;
    const bar = (k, p, cls, bw) => `<rect class="${cls}" x="${(x(k) - bw / 2).toFixed(1)}" y="${y(p).toFixed(1)}" width="${bw}" height="${Math.max(2, base - y(p)).toFixed(1)}"/>`;
    const fq = k => `${+(c.f0 + k * c.df).toPrecision(6)}`, o = [`<rect class="ip-plot" x="${L}" y="${T}" width="${w}" height="${h}"/>`];
    for (let p = -120; p <= 0; p += 30) o.push(`<line class="fm-grid" x1="${L}" x2="${L + w}" y1="${y(p)}" y2="${y(p)}"/><text class="fm-tk" x="${L - 4}" y="${y(p) + 4}" text-anchor="end">${p < 0 ? "−" + -p : p}</text>`);
    for (const k of [-1, 0, 1, 2, 3]) o.push(`<text class="fm-tk" x="${x(k)}" y="${base + 14}" text-anchor="middle">${fq(k)}</text>`);
    o.push(`<text class="fm-ax" x="${L + w / 2}" y="${H - 4}" text-anchor="middle">Frequency (MHz) · level at the input (dBm)</text>`);
    o.push(`<rect class="ip-noise" x="${L}" y="${y(r.n)}" width="${w}" height="${Math.max(0, base - y(r.n))}"/>`);
    o.push(bar(0, r.im, "ip-im", 26), bar(0, s.pw, `ip-w${r.lost ? " lost" : ""}`, 12), bar(1, s.pn, "ip-n", 12), bar(2, s.pn, "ip-n", 12), bar(3, r.im, "ip-im", 12));
    o.push(`<line class="ip-lim" x1="${x(-0.45)}" x2="${x(0.45)}" y1="${y(s.pw - s.snr)}" y2="${y(s.pw - s.snr)}"/>`);
    const lab = [{x: x(0), y: y(s.pw) - 5, t: r.lost ? "your signal is lost" : `your signal ${Math.round(s.pw)}`, c: r.lost ? "ip-lost" : "fm-lb"},
      {x: x(1.5), y: y(s.pn) - 5, t: `neighbours ${Math.round(s.pn)}`}, {x: x(3), y: y(r.im) - 5, t: r.im < Y0 ? "IM3 below −140" : `IM3 ${Math.round(r.im)}`, c: "fm-lg"},
      {x: x(-1), y: y(r.n) - 5, t: `noise ${Math.round(r.n)}`, c: "fm-tk"}, {x: x(0.45) + 22, y: y(s.pw - s.snr) + 4, t: "limit", c: "fm-lg"}];
    if (r.im >= Y0 && Math.abs(r.im - s.pw) > 8) lab.push({x: x(-0.55), y: y(r.im) - 5, t: `IM3 ${Math.round(r.im)}`, c: "fm-lg"});
    o.push(placeLabels(lab, T, L, L + w));
    return o.join("");
  }
  function ipPaint(c, s, r) {
    const W = Math.max(280, ipUI.pic.clientWidth || 300);
    ipUI.svg.setAttribute("viewBox", `0 0 ${W} ${IPP.H}`);
    ipUI.svg.setAttribute("width", W);
    ipUI.svg.setAttribute("height", IPP.H);
    ipUI.svg.innerHTML = ipSvg(c, s, r, W);
    ipUI.cap.textContent = `${c.label}: your signal ${dbmTxt(s.pw)} in ${si(s.bw * 1e6, "Hz")}, needing ${dbTxt(s.snr).replace("+", "")} signal-to-noise; two neighbours ${si(c.df * 1e6, "Hz")} and ${si(2 * c.df * 1e6, "Hz")} away.`;
    ipUI.vals.textContent = `Your signal ${+c.f0.toPrecision(6)} MHz at ${dbmTxt(s.pw)} · neighbours at ${+(c.f0 + c.df).toPrecision(6)} and ${+(c.f0 + 2 * c.df).toPrecision(6)} MHz, ${dbmTxt(s.pn)} each · false tones (IM3) at ${+c.f0.toPrecision(6)} and ${+(c.f0 + 3 * c.df).toPrecision(6)} MHz, ${dbmTxt(Math.round(r.im * 10) / 10)} · noise floor ${dbmTxt(Math.round(r.n * 10) / 10)}.`;
    const both = `${Math.round(r.mNoise)} dB to spare against noise, ${Math.round(r.mIm)} dB against distortion`;
    const v = !r.lost ? {tone: r.mNoise < 3 || r.mIm < 3 ? "warn" : "ok", t: `Your signal is heard: ${both}.`}
      : r.mIm < 0 && r.mNoise >= 0 ? {tone: "bad", t: `Your signal is lost: drowned by distortion. The false tone on your channel (${dbmTxt(Math.round(r.im))}) is ${Math.round(-r.mIm)} dB too strong for the ${Math.round(s.snr)} dB your signal needs above it.`}
        : r.mNoise < 0 && r.mIm >= 0 ? {tone: "bad", t: `Your signal is lost: too weak to hear. It needs ${Math.round(s.snr)} dB above the noise (${dbmTxt(Math.round(r.n))}) and is ${Math.round(-r.mNoise)} dB short.`}
          : {tone: "bad", t: `Your signal is lost: noise and distortion together (${both}).`};
    ipUI.verdict.className = `ip-verdict t-${v.tone}`;
    ipUI.verdict.textContent = v.t + (r.comp ? " The neighbours also push the amplifier into compression (input P1dB ≈ IIP3 − 10 dB): its gain drops." : "");
    const pc = m => clamp(((m + 30) / 70) * 100, 0, 100), z = pc(0);
    const row = (l, sub, m, txt) => `<div class="tm-row t-${m < 0 ? "bad" : m < 3 ? "warn" : "ok"}"><span class="tm-l">${l}<small>${sub}</small></span><span class="tm-tr" aria-hidden="true"><i class="tm-z" style="left:${z.toFixed(1)}%"></i><b style="left:${Math.min(z, pc(m)).toFixed(1)}%;width:${Math.abs(pc(m) - z).toFixed(1)}%"></b></span><span class="tm-v">${txt}</span></div>`;
    const room = m => (m >= 0 ? `${dbTxt(m)} to spare` : `${+(-m).toFixed(1)} dB short`);
    ipUI.meter.innerHTML = row("Too weak to hear", "noise: gain and noise figure", r.mNoise, `${room(r.mNoise)}: noise floor ${dbmTxt(Math.round(r.n * 10) / 10)} with a noise figure of ${num(r.nf)} dB at this gain`)
      + row("Drowned by distortion", "intermodulation: IP3 and the neighbours", r.mIm, `${room(r.mIm)}: false tone ${dbmTxt(Math.round(r.im * 10) / 10)}, input IP3 ${dbmTxt(r.iip3)}`)
      + `<div class="tm-row t-cur"><span class="tm-l">What it costs<small>amplifier current (est)</small></span><span class="tm-tr" aria-hidden="true"><b style="left:0;width:${clamp(r.ma, 0.5, 100).toFixed(1)}%"></b></span><span class="tm-v">about ${num(r.ma)} mA (est: about twice per +10 dB of IP3; bar to 100 mA)</span></div>`;
  }
  V.push({
    id: "ip3", group: "Receivers", title: "IP3 and intermodulation",
    explains: [["Front-end modules and PAs", "/knowledge#p-front_ends"], ["RF switches", "/knowledge#p-rf_switches"]],
    physics: [["Linearity", "phys_linearity"]],
    lead: "IP3 is like a loudspeaker turned up too far: it adds tones that weren't in the music. IP3 tells you how loud the input can get before those false tones matter. Here a weak signal sits next to two strong neighbours, and their false tones grow until one covers it.",
    presetLabel: "Ready-made scenarios",
    presets: [
      {label: "BLE next to Wi-Fi", values: {sc: "ble", g: 12, oip3: 5, pn: -40},
        note: "<b>Conditions:</b> a BLE receiver at 2402 MHz, its signal at −90 dBm, with two strong 2.4 GHz signals (Wi-Fi from a device nearby) 3 and 6 MHz away at −40 dBm each (est); an external LNA in front (gain 12 dB, output IP3 +5 dBm, est). The Bluetooth intermodulation test uses the same spacing (<a href=\"https://www.ti.com/lit/ds/symlink/cc2652r.pdf\" target=\"_blank\" rel=\"noopener noreferrer\">TI CC2652R data sheet ↗</a>: wanted signal at −64 dBm, interferers at 2405 and 2408 MHz). About 12 dB SNR needed (est)."},
      {label: "Car FM next to a strong local station", values: {sc: "fm", g: 10, oip3: 2, pn: -25},
        note: "<b>Conditions:</b> two strong local FM stations 400 and 800 kHz from yours (the spacing the <a href=\"https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-shorts/Si4706-short.pdf\" target=\"_blank\" rel=\"noopener noreferrer\">Si4706 data sheet ↗</a> uses for its input IP3), −25 dBm each a few km from a big transmitter (est); your station at −80 dBm. Input IP3 −8 dBm, as a tuner with 105 dBµV EMF (<a href=\"https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-shorts/Si4734-35-short.pdf\" target=\"_blank\" rel=\"noopener noreferrer\">Si4734/35 data sheet ↗</a>); clean mono FM needs 26 dB signal-to-noise (the data sheets' sensitivity test)."},
      {label: "5G phone near a base station", values: {sc: "nr", g: 18, oip3: 20, pn: -35},
        note: "<b>Conditions:</b> a phone at the edge of its own cell in band n78 (−95 dBm in 10 MHz; the 3GPP reference sensitivity is about −96 dBm, <a href=\"https://www.etsi.org/deliver/etsi_ts/138100_138199/13810101/15.02.00_60/ts_13810101v150200p.pdf\" target=\"_blank\" rel=\"noopener noreferrer\">TS 38.101-1 ↗</a>) next to another operator's base station whose two carriers 20 and 40 MHz away arrive at −35 dBm each (est; the 3GPP blocking tests use −56 to −44 dBm in band). QPSK at reference sensitivity works at about −1 dB SNR (est)."},
    ],
    controls: [
      {k: "sc", label: "Scenario", type: "select", options: Object.entries(IP3_CASES).map(([k, c]) => [k, c.label]), value: "gen", when: () => false},
      {k: "g", label: "Gain of the amplifier", min: 0, max: 40, step: 0.5, value: 15, unit: "dB"},
      {k: "oip3", label: "IP3 of the amplifier (output IP3, as data sheets give it)", min: -10, max: 45, step: 0.5, value: 20, unit: "dBm"},
      {k: "pn", label: "Level of each strong neighbour", min: -80, max: -5, step: 1, value: -40, unit: "dBm"},
    ],
    setup(el, rerender) {
      el.classList.add("ip-ui");
      el.innerHTML = `<figure class="ip-fig"><figcaption class="small ip-cap"></figcaption><div class="ip-pic"><svg class="ip-svg" role="img" aria-label="Spectrum: your signal, the two neighbours, their false tones and the noise floor"></svg></div><p class="fm-vals small ip-vals"></p></figure>
        <p class="ip-verdict" aria-live="polite"></p><div class="tm"></div>
        <p class="ip-try small"><b>What to try:</b> raise the gain until the red appears, then raise IP3 and see what it costs.</p>`;
      const q = s => el.querySelector(s);
      ipUI = {root: el, pic: q(".ip-pic"), svg: q(".ip-svg"), cap: q(".ip-cap"), vals: q(".ip-vals"), verdict: q(".ip-verdict"), meter: q(".tm")};
      foldChart(el, "Show the textbook IP3 chart", rerender);
    },
    compute(v) {
      const c = IP3_CASES[v.sc] || IP3_CASES.gen, s = {...c, g: v.g, oip3: v.oip3, pn: v.pn}, r = IMX.rx(s);
      if (ipUI && ipUI.root.isConnected) ipPaint(c, s, r);
      const iip3 = r.iip3, pf = v.pn + v.g, pim = r.im + v.g, xs = range(-80, Math.max(iip3 + 8, 0), 40);
      return {
        outputs: [["Input IP3 = output IP3 − gain", dbmTxt(iip3)], ["False tone (IM3) on your channel", dbmTxt(Math.round(r.im * 10) / 10), r.mIm < 0 ? "bad" : ""],
          ["Noise floor", `${dbmTxt(Math.round(r.n * 10) / 10)} (NF ${num(r.nf)} dB)`, r.mNoise < 0 ? "bad" : ""],
          ["Signal to noise + distortion", `${num(r.sinr)} dB (needs ${num(s.snr)})`, r.lost ? "bad" : "ok"], ["Current (est)", `${num(r.ma)} mA`]],
        eq: `P<sub>IM3</sub> = 3·P<sub>n</sub> − 2·IIP3 &nbsp;·&nbsp; IIP3 = OIP3 − G &nbsp;·&nbsp; NF = 10·log(F<sub>1</sub> + (F<sub>2</sub> − 1) / G) &nbsp;·&nbsp; SINR = P<sub>w</sub> − 10·log(10<sup>N/10</sup> + 10<sup>IM3/10</sup>)`,
        eqn: `IM3 = 3·(${num(v.pn)}) − 2·(${num(iip3)}) = ${num(r.im)} dBm &nbsp;·&nbsp; IIP3 = ${num(v.oip3)} − ${num(v.g)} = ${num(iip3)} dBm &nbsp;·&nbsp; N = −174 + ${num(r.nf)} + 10·log(${si(s.bw * 1e6, "Hz")}) = ${num(r.n)} dBm`,
        chart: {x: {min: -80, max: Math.max(iip3 + 8, 0), label: "Input power per tone (dBm)"}, y: {min: -160, max: v.oip3 + 10, label: "Output power (dBm)"},
          series: [{pts: xs.map(p => [p, p + v.g]), label: "Fundamental (slope 1)"}, {pts: xs.map(p => [p, 3 * p + v.g - 2 * iip3]), color: C.orange, label: "IM3 (slope 3)"}],
          vlines: [{x: iip3 - 9, label: "≈ 1 dB compression", color: C.red}, {x: iip3, label: `IIP3 ${num(iip3)} dBm`, color: C.grey, row: 1}],
          marks: [{x: v.pn, y: pf, label: `tones ${num(pf)} dBm`, color: C.blue}, {x: v.pn, y: pim, label: `IM3 ${num(pim)} dBm`}, {x: iip3, y: v.oip3, label: `IP3 (${num(iip3)}, ${num(v.oip3)})`, color: C.grey}]},
        html: `<div class="small ip-words"><p><b>In plain words.</b> Two strong neighbours at f<sub>1</sub> and f<sub>2</sub> make false tones at 2·f<sub>1</sub> − f<sub>2</sub> and 2·f<sub>2</sub> − f<sub>1</sub>; with this spacing one lands exactly on your weak signal, where no filter can take it out again. Each 1 dB more of the neighbours makes the false tones 3 dB louder; each 1 dB more IP3 makes them 2 dB quieter.</p>
          <p><b>What you trade.</b> More gain in front lowers the noise of everything behind it, so a weak signal is heard better (the first bar grows). But the same amplifier then reaches its IP3 with a smaller input (input IP3 = output IP3 − gain), so the false tones grow (the second bar shrinks). A part with a higher IP3 gives you both, and costs current: about twice per +10 dB (est). The usual answer is a high-IP3 LNA with just enough gain, a filter in front against neighbours far away, and AGC that turns the gain down when the neighbours are strong.</p>
          <p>Our parts: <a href="/find?q=SKY67021-396LF">LNA SKY67021-396LF (IIP3 +22.5 dBm)</a> · <a href="/business/rf-coverage">LNAs on the RF coverage page</a> · Read more: <a href="/rf-notes#iip3_basics">IIP3 in plain words</a> · <a href="/rf-notes#ip3_intermodulation">IP3 and two-tone intermodulation</a></p></div>`,
        note: "Levels are referred to the amplifier input. The rest of the receiver behind the amplifier is taken as noise only (its noise figure per scenario, est); its own linearity is left out. IP3 is an extrapolation: the real amplifier compresses about 10 dB below it. The current is a rule of thumb (est), not a data sheet value.",
      };
    },
    related: [["IIP3 in plain words", "/rf-notes#iip3_basics"], ["FM intermodulation", "#fmim"], ["Blocker view of the dBm ladder", "#dbm"]],
  });

  // FM intermodulation (owner 23 Oct 2026: "when a particular FM frequency is tuned, at which other frequencies could
  // intermod occur?"; 2 Nov 2026: "here's the tuned station, here's strong station A and strong station B; is this an
  // intermod product of that?"): the FM band with A and B as bars to drag, their ghosts at 2A − B and 2B − A, a one-line
  // verdict with the arithmetic, three ways to fix it with their cost, and the pairs from a list of local stations.
  let fmList = "88.1, 89.5, 91.0, 94.3, 96.7, 99.9, 102.4, 105.8";
  const fmParse = s => [...new Set(String(s).split(/[\s,;]+/).map(Number).filter(f => f >= 60 && f <= 120).map(f => +f.toFixed(2)))].sort((a, b) => a - b);
  const FM_SENS = -112, FM_SEL = 50;  // Si4734/35 data sheet: 1.1 µV EMF (about −112 dBm); 50 dB at ±200 kHz
  const FM_FILTER = 4;  // tracking filter in front, 3 dB bandwidth in MHz (est: a tuned circuit with Q about 25)
  const FMP = {L: 36, R: 10, T: 24, B: 34, H: 240, F0: 87.5, F1: 108, Y0: -125, Y1: 0};
  let fmFix = {lin: false, att: false, filt: false}, fmUI = null, fmV = null;
  const fmFixes = f => ({lin: f.lin ? 10 : 0, att: f.att ? 10 : 0, bw: f.filt ? FM_FILTER : 0});
  function fmSvg(s, m, W) {
    const {L, R, T, B, H, F0, F1, Y0, Y1} = FMP, w = W - L - R, h = H - T - B, base = T + h;
    const x = f => L + ((clamp(f, F0, F1) - F0) / (F1 - F0)) * w, y = p => T + ((Y1 - clamp(p, Y0, Y1)) / (Y1 - Y0)) * h;
    const o = [`<rect class="fm-plot" x="${L}" y="${T}" width="${w}" height="${h}"/>`], lab = [];
    for (let p = -120; p <= 0; p += 30) o.push(`<line class="fm-grid" x1="${L}" x2="${L + w}" y1="${y(p)}" y2="${y(p)}"/><text class="fm-tk" x="${L - 4}" y="${y(p) + 4}" text-anchor="end">${p < 0 ? "−" + -p : p}</text>`);
    for (let f = 88; f <= 108; f += W < 520 ? 4 : 2) o.push(`<line class="fm-grid" x1="${x(f)}" x2="${x(f)}" y1="${T}" y2="${base}"/><text class="fm-tk" x="${x(f)}" y="${base + 14}" text-anchor="middle">${f}</text>`);
    o.push(`<text class="fm-ax" x="${L + w / 2}" y="${H - 4}" text-anchor="middle">FM band (MHz) · level at the receiver input (dBm)</text>`);
    o.push(`<rect class="fm-ch" x="${(x(s.ft - 0.1) - 2).toFixed(1)}" y="${T}" width="${Math.max(6, x(s.ft + 0.1) - x(s.ft - 0.1) + 4).toFixed(1)}" height="${h}"/>`);
    o.push(`<line class="fm-sens" x1="${L}" x2="${L + w}" y1="${y(FM_SENS)}" y2="${y(FM_SENS)}"/><text class="fm-sl" x="${L + 4}" y="${y(FM_SENS) - 4}">tuner sensitivity</text>`);
    for (const g of m.ghosts) {
      if (g.f < F0 || g.f > F1) {  // outside the band: an arrow at the edge
        const left = g.f < F0;
        o.push(`<text class="fm-lg" x="${left ? L + 3 : L + w - 3}" y="${base - 6}" text-anchor="${left ? "start" : "end"}">${left ? "◂ " : ""}${g.k} ${g.f.toFixed(1)}${left ? "" : " ▸"}</text>`);
        continue;
      }
      o.push(`<rect class="fm-gh${g.at === "on" || g.at === "near" ? " hit" : g.at ? " adj" : ""}" x="${(x(g.f) - 5).toFixed(1)}" y="${y(g.p).toFixed(1)}" width="10" height="${Math.max(2, base - y(g.p)).toFixed(1)}"/>`);
      lab.push({x: x(g.f), y: y(g.p) - 5, t: g.p < Y0 ? `${g.k}: below −125` : `${g.k} ${g.f.toFixed(1)}`, c: "fm-lg"});
    }
    const drag = (k, name, f, p, inner) => `<g class="fm-drag" data-fk="${k}" tabindex="0" role="slider" aria-label="${esc(name)}: drag, or use the arrow keys" aria-valuemin="87.5" aria-valuemax="108" aria-valuenow="${f}" aria-valuetext="${f.toFixed(1)} MHz, ${Math.round(p)} dBm"><rect class="fm-hit" x="${(x(f) - 14).toFixed(1)}" y="${T}" width="28" height="${h}"/>${inner}</g>`;
    for (const [k, n, f, p] of [["f1", "A", s.fa, m.pa], ["f2", "B", s.fb, m.pb]]) {
      o.push(drag(k, `Strong station ${n}`, f, p, `<rect class="fm-st" x="${(x(f) - 5).toFixed(1)}" y="${y(p).toFixed(1)}" width="10" height="${Math.max(2, base - y(p)).toFixed(1)}" rx="2"/>`));
      lab.push({x: x(f), y: y(p) - 5, t: `${n} ${f.toFixed(1)}`});
    }
    const yt = y(m.pt);
    o.push(drag("ft", "Your station", s.ft, m.pt, `<line class="fm-yl" x1="${x(s.ft)}" x2="${x(s.ft)}" y1="${yt}" y2="${base}"/><path class="fm-yt" d="M${(x(s.ft) - 7).toFixed(1)} ${(yt - 10).toFixed(1)} h14 l-7 9 z"/>`));
    lab.push({x: x(s.ft), y: yt - 13, t: `you ${s.ft.toFixed(1)}`, c: "fm-ly"});
    o.push(placeLabels(lab, T, L, L + w));
    return o.join("");
  }
  function fmPaint(s, m, vd, fx) {
    keepFocus(fmUI.root, () => {
      const W = Math.max(280, fmUI.pic.clientWidth || 300);
      fmUI.svg.setAttribute("viewBox", `0 0 ${W} ${FMP.H}`);
      fmUI.svg.setAttribute("width", W);
      fmUI.svg.setAttribute("height", FMP.H);
      fmUI.svg.innerHTML = fmSvg(s, m, W);
      const tried = [fmFix.lin && "better linearity", fmFix.att && "input 10 dB down", fmFix.filt && "tracking filter"].filter(Boolean);
      fmUI.vals.textContent = `Your station ${s.ft.toFixed(1)} MHz at ${dbmTxt(Math.round(m.pt))} · A ${s.fa.toFixed(1)} MHz at ${dbmTxt(Math.round(m.pa))} · B ${s.fb.toFixed(1)} MHz at ${dbmTxt(Math.round(m.pb))} · ghosts ${m.ghosts.map(g => `${g.k} at ${g.f.toFixed(1)} MHz, ${dbmTxt(Math.round(g.p))}`).join("; ")}${tried.length ? ` (with ${tried.join(" and ")})` : ""}.`;
      fmUI.verdict.className = `fm-verdict t-${vd.tone}`;
      fmUI.verdict.textContent = vd.text;
      fmUI.fix.innerHTML = fx;
    });
  }
  // the three fixes, each on its own against no fix: what it does to the ghost on your channel and to your station
  function fmFixHtml(s, base) {
    const gi = Math.max(0, base.ghosts.findIndex(g => g.at)), g0 = base.ghosts[gi], one = fx => IMX.fm(s, fx).ghosts[gi].p - g0.p;
    const dl = one({lin: 10}), da = one({att: 10}), F = IMX.fm(s, {bw: FM_FILTER}), df = F.ghosts[gi].p - g0.p, pt = s.pt - 10;
    const card = (k, title, does, cost) => `<div class="fx-card${fmFix[k] ? " on" : ""}"><b>${title}</b><p>${does}</p><p class="fx-cost"><b>Costs:</b> ${cost}</p>
      <button type="button" class="fx-try${fmFix[k] ? "" : " outline"}" data-fix="${k}" data-fk="fix-${k}" aria-pressed="${fmFix[k]}">${fmFix[k] ? "Applied ✓ (tap to undo)" : "Try it"}</button></div>`;
    const ghost = d => `ghost (${g0.k}) ${dbTxt(d)}, from ${dbmTxt(Math.round(g0.p))} to ${dbmTxt(Math.round(g0.p + d))}`;
    return `<h3>How to fix it</h3><div class="fx-cards">
      ${card("lin", "Better linearity: +10 dB IIP3", `The ${ghost(dl)}: each 1 dB more IIP3 takes 2 dB off it. Your station stays where it is.`, "current: about twice the front-end current (est), so more battery drain and heat.")}
      ${card("att", "Turn the input down: AGC or a 10 dB attenuator", `The ${ghost(da)}, because both stations fall 10 dB and the ghost three times as fast. But your station falls 10 dB too, to ${dbmTxt(pt)}: ${pt < FM_SENS ? `<b>below the tuner's sensitivity (${dbmTxt(FM_SENS)}): too weak to hear</b>` : `still ${Math.round(pt - FM_SENS)} dB above the tuner's sensitivity (${dbmTxt(FM_SENS)})`}.`, "nothing in current, but every weak station gets weaker: hiss, or lost altogether.")}
      ${card("filt", "Filter before the amplifier", `A tuned (tracking) filter ${FM_FILTER} MHz wide (est) takes A, ${Math.abs(s.fa - s.ft).toFixed(1)} MHz away, down ${num(F.ra)} dB and B, ${Math.abs(s.fb - s.ft).toFixed(1)} MHz away, ${num(F.rb)} dB: the ${ghost(df)}. A fixed FM band filter takes nothing here: both stations are inside 87.5–108 MHz.`, "a filter removes far-away stations, not close neighbours, which is the usual FM case; a tuned filter also needs tuning and loses about 1 dB (est).")}</div>`;
  }
  V.push({
    id: "fmim", group: "Broadcast radio", title: "FM intermodulation: where interference can come from",
    lead: "Here is your station, here are strong stations A and B: is there an intermodulation product of A and B on your station? Drag A and B on the band (or use the sliders and arrow keys); their ghosts at 2A − B and 2B − A follow, and the line under the picture answers yes or no with the arithmetic. Below: three ways to fix it and what each costs.",
    explains: [["Broadcast radio tuners (Si47xx)", "/knowledge#p-tuners"], ["Front-end LNAs and filters", "/knowledge#p-front_ends"]],
    physics: [["Linearity", "phys_linearity"], ["Mixing and the superheterodyne", "phys_mixing_superhet"]],
    presetLabel: "Examples",
    presets: [
      {label: "A ghost on your station", values: {ft: 92.5, f1: 91, f2: 89.5, pa: -30, pb: -30, pw: -80}, note: "2 × 91.0 − 89.5 = 92.5 MHz: two strong stations 1.5 MHz apart put a product another 1.5 MHz further out, on your station."},
      {label: "Your station is clear", values: {ft: 94.3, f1: 91, f2: 89.5, pa: -30, pb: -30, pw: -80}, note: "The same two stations; the products land on 88.0 and 92.5 MHz, not on 94.3 MHz."},
      {label: "Next channel, 200 kHz away", values: {ft: 92.5, f1: 91.1, f2: 89.5, pa: -25, pb: -30, pw: -80}, note: "2 × 91.1 − 89.5 = 92.7 MHz: the ghost sits on the adjacent channel; the tuner's channel filter takes about 50 dB off it (Si4734/35 data sheet: adjacent-channel selectivity at ±200 kHz)."},
    ],
    controls: [
      {k: "ft", label: "Your station (tuned)", min: 87.5, max: 108, step: 0.1, value: 92.5, unit: "MHz"},
      {k: "f1", label: "Strong station A", min: 87.5, max: 108, step: 0.1, value: 91, unit: "MHz"},
      {k: "f2", label: "Strong station B", min: 87.5, max: 108, step: 0.1, value: 89.5, unit: "MHz"},
      {k: "pa", label: "Level of A at the input", min: -60, max: 0, step: 1, value: -30, unit: "dBm"},
      {k: "pb", label: "Level of B at the input", min: -60, max: 0, step: 1, value: -30, unit: "dBm"},
      {k: "pw", label: "Level of your station", min: -110, max: -30, step: 1, value: -80, unit: "dBm"},
      {k: "iip3", label: "Receiver input IP3", min: -30, max: 30, step: 0.5, value: -8, unit: "dBm"},
      {k: "if", label: "Intermediate frequency (IF)", type: "select", options: [["10.7", "10.7 MHz (classic superhet)"], ["0.2", "low IF, about 0.2 MHz (est, Si47xx-type)"]], value: "10.7"},
    ],
    setup(el, rerender, setVals) {
      fmFix = {lin: false, att: false, filt: false};
      el.classList.add("fm-ui");
      el.innerHTML = `<figure class="fm-fig"><figcaption class="small" id="fm-cap">The FM band, 87.5–108 MHz. Drag the tall bars A and B (or your green station) along the band; with the keyboard, tab to one and use the arrow keys (Page Up / Down: 1 MHz).</figcaption>
        <div class="fm-pic"><svg class="fm-svg" aria-labelledby="fm-cap"></svg></div><p class="fm-vals small"></p></figure>
        <p class="fm-verdict" aria-live="polite"></p><div class="fm-fix"></div>
        <div class="fm-list"><h3>My local stations</h3><label class="small">Strong stations where you are (MHz, separated by commas) <input type="text" class="vz-fmlist" value="${esc(fmList)}" inputmode="decimal" aria-label="Strong FM stations in MHz"></label><div class="fm-pairs small" aria-live="polite"></div></div>`;
      const q = s => el.querySelector(s), svg = q(".fm-svg");
      fmUI = {root: el, pic: q(".fm-pic"), svg, vals: q(".fm-vals"), verdict: q(".fm-verdict"), fix: q(".fm-fix"), pairs: q(".fm-pairs")};
      q(".vz-fmlist").addEventListener("input", e => { fmList = e.target.value; rerender(); });
      el.addEventListener("click", e => {
        const b = e.target.closest("[data-fix]");
        if (b) { fmFix[b.dataset.fix] = !fmFix[b.dataset.fix]; rerender(); }
      });
      const put = (k, f) => {
        f = clamp(Math.round(f * 10) / 10, FMP.F0, FMP.F1);
        if (!fmV || Math.abs(f - fmV[k]) > 1e-9) { setVals({[k]: f}); rerender(); }
      };
      const at = e => {  // the pointer's frequency on the band
        const r = svg.getBoundingClientRect(), W = +svg.getAttribute("width") || r.width, px = ((e.clientX - r.left) * W) / r.width;
        return FMP.F0 + ((px - FMP.L) / (W - FMP.L - FMP.R)) * (FMP.F1 - FMP.F0);
      };
      let drag = null;
      svg.addEventListener("pointerdown", e => {
        const g = e.target.closest("[data-fk]");
        if (!g) return;
        drag = g.dataset.fk;
        svg.setPointerCapture(e.pointerId);
        e.preventDefault();
        g.focus({preventScroll: true});
        put(drag, at(e));
      });
      svg.addEventListener("pointermove", e => { if (drag) put(drag, at(e)); });
      const stop = e => { drag = null; if (svg.hasPointerCapture(e.pointerId)) svg.releasePointerCapture(e.pointerId); };
      svg.addEventListener("pointerup", stop);
      svg.addEventListener("pointercancel", stop);
      svg.addEventListener("keydown", e => {
        const g = e.target.closest("[data-fk]"), k = g && g.dataset.fk;
        const d = {ArrowLeft: -0.1, ArrowDown: -0.1, ArrowRight: 0.1, ArrowUp: 0.1, PageDown: -1, PageUp: 1}[e.key];
        if (!k || !fmV) return;
        if (d !== undefined) put(k, fmV[k] + d); else if (e.key === "Home") put(k, FMP.F0); else if (e.key === "End") put(k, FMP.F1); else return;
        e.preventDefault();
      });
      foldChart(el, "Show the whole picture: every product, the image and the FM band by region", rerender);
    },
    compute(v) {
      fmV = v;
      const IF = +v.if, ch = 0.1, f1 = v.f1, f2 = v.f2, ft = v.ft;  // ±100 kHz: half an FM channel
      const s = {ft, pt: v.pw, fa: f1, pa: v.pa, fb: f2, pb: v.pb, iip3: v.iip3}, base = IMX.fm(s), m = IMX.fm(s, fmFixes(fmFix));
      const vd = IMX.verdict(s, m, FM_SEL, FM_SENS);
      const iip2 = m.iip3 + 20;  // IIP2 ≈ IIP3 + 20 dB (est)
      const prods = [
        ...m.ghosts.map(g => ({l: g.k, f: g.f, o: 3, lvl: g.p})), ["A + B", f1 + f2, m.pa + m.pb - iip2], ["|A − B|", Math.abs(f1 - f2), m.pa + m.pb - iip2],
        ["2A", 2 * f1, 2 * m.pa - iip2], ["2B", 2 * f2, 2 * m.pb - iip2], ["2A + B", 2 * f1 + f2, 2 * m.pa + m.pb - 2 * m.iip3], ["2B + A", 2 * f2 + f1, 2 * m.pb + m.pa - 2 * m.iip3],
      ].map(p => (Array.isArray(p) ? {l: p[0], f: p[1], o: /^(A \+ B|\|A − B\||2A|2B)$/.test(p[0]) ? 2 : 3, lvl: p[2]} : p)).map(p => ({...p, hit: Math.abs(p.f - ft) <= ch}));
      const img = ft + 2 * IF, half = ft + IF / 2, lo = ft + IF;  // high-side LO
      const stations = fmParse(`${fmList}, ${f1}, ${f2}`).filter(f => Math.abs(f - ft) > ch);
      const pairs = [];
      for (const a of stations) for (const b of stations) if (a !== b && Math.abs(2 * a - b - ft) <= ch) pairs.push([a, b, 2 * a - b]);
      const imgSt = stations.filter(f => Math.abs(f - img) <= ch), halfSt = stations.filter(f => Math.abs(f - half) <= ch);
      const fmt = f => `${num(f, 4)} MHz`;
      if (fmUI && fmUI.root.isConnected) {
        fmPaint(s, m, vd, fmFixHtml(s, base));
        fmUI.pairs.innerHTML = `<p><b>Pairs from your list that land on ${ft.toFixed(1)} MHz</b> (2 × one station − another, within ±100 kHz): ${pairs.length ? `</p><ul>${pairs.map(([a, b, f]) => `<li>2 × ${a.toFixed(1)} − ${b.toFixed(1)} = ${f.toFixed(1)} MHz</li>`).join("")}</ul>` : "none.</p>"}`;
      }
      const inR = (id, f) => (BANDS[id] ? BANDS[id].ranges : [[76, 108]]).some(([a, z]) => f >= a && f <= z), inBand = f => inR("fm", f);  // the RF bands data
      const oirt = f => !!BANDS.fm && BANDS.fm.sub.some(([a, z, l]) => /OIRT/.test(l) && f >= a && f <= z);
      const series = [{pts: [[ft, -130], [ft, m.pt]], color: C.green, width: 5, label: "Tuned"}, {pts: [[f1, -130], [f1, m.pa]], color: C.blue, width: 4, label: "A, B"}, {pts: [[f2, -130], [f2, m.pb]], color: C.blue, width: 4}];
      prods.filter(p => p.f >= 60 && p.f <= 120).forEach((p, i) => series.push({pts: [[p.f, -130], [p.f, p.lvl]], color: p.hit ? C.red : C.orange, width: 3, ...(i ? {} : {label: "Products"})}));
      const rowsP = prods.map(p => `<tr class="${p.hit ? "hit" : ""}"><td>${esc(p.l)}</td><td class="n">${fmt(p.f)}</td><td>${p.o === 3 ? "3rd" : "2nd"}</td><td class="n">${num(p.lvl)} dBm</td><td>${p.hit ? "<b>on your channel</b>" : inBand(p.f) ? "inside the FM band" : oirt(p.f) ? "in the old OIRT band" : inR("dab", p.f) ? "in DAB Band III" : "outside the FM band"}</td></tr>`).join("");
      const g = vd.g || m.ghosts[0], gsum = `2·${num(g.k === "2A − B" ? f1 : f2, 4)} − ${num(g.k === "2A − B" ? f2 : f1, 4)}`;
      return {
        outputs: [["2A − B / 2B − A", `${fmt(m.ghosts[0].f)} / ${fmt(m.ghosts[1].f)}`, vd.g ? "bad" : ""], [vd.g ? "Ghost on your channel" : "Ghosts", vd.g ? dbmTxt(Math.round(vd.g.p)) : m.ghosts.map(x => dbmTxt(Math.round(x.p))).join(" / ")],
          ["Your station against the ghost", vd.g ? `${dbTxt(Math.round(-vd.g.over))}` : "no ghost on it", vd.g ? vd.tone : "ok"],
          ["Image frequency", `${fmt(img)}${imgSt.length ? " · a station is there" : ""}`, imgSt.length && IF > 1 ? "warn" : ""], ["Pairs from your list on your channel", String(pairs.length), pairs.length ? "warn" : "ok"]],
        eq: `ghosts at 2·f<sub>A</sub> − f<sub>B</sub> and 2·f<sub>B</sub> − f<sub>A</sub> &nbsp;·&nbsp; P<sub>2A−B</sub> = 2·P<sub>A</sub> + P<sub>B</sub> − 2·IIP3 (equal levels: 3·P − 2·IIP3) &nbsp;·&nbsp; image = f<sub>tuned</sub> + 2·IF (LO above)`,
        eqn: `${gsum} = ${fmt(g.f)} &nbsp;·&nbsp; P = 2·(${num(g.k === "2A − B" ? m.pa : m.pb)}) + (${num(g.k === "2A − B" ? m.pb : m.pa)}) − 2·(${num(m.iip3)}) = ${num(g.p)} dBm &nbsp;·&nbsp; image = ${num(ft, 4)} + 2·${IF} = ${fmt(img)}`,
        chart: {x: {min: 64, max: IF > 1 ? Math.min(135, Math.max(112, img + 2)) : 112, label: "Frequency (MHz); FM band by region as ranges"}, y: {min: -130, max: 5, label: "Level at the input (dBm)"}, series,
          bands: [...appBands([["fm"]], 1, true), {x0: ft - ch, x1: ft + ch, color: C.green, opacity: 0.15}, {x0: 108, x1: 112, color: C.grey, opacity: 0.08, label: "above FM"}],
          vlines: [...(IF > 1 ? [{x: img, label: "image", color: C.purple, row: 0}, {x: half, label: "½ IF", color: C.purple, row: 1}] : []), {x: lo, label: "LO", color: C.grey, row: 2}],
          hlines: [{y: m.pt - 30, label: "30 dB below tuned (est. limit)", color: C.red}]},
        html: `<div class="vz-im small"><p><b>Every product, the image and the half-IF spur</b> <span class="muted">(levels with the fixes you tried; IIP2 ≈ IIP3 + 20 dB, est)</span></p><div class="vz-imwrap"><table><thead><tr><th>Product of A and B</th><th class="n">Frequency</th><th>Order</th><th class="n">Level (est)</th><th>Where</th></tr></thead><tbody>${rowsP}
          <tr class="${imgSt.length ? "hit" : ""}"><td>Image (LO + IF)</td><td class="n">${fmt(img)}</td><td>mixer</td><td></td><td>${IF > 1 ? (imgSt.length ? `<b>station at ${imgSt.map(fmt).join(", ")}</b>: needs image rejection` : "an RF filter or image-reject mixer must suppress it") : "next to the channel: removed by I/Q image rejection, not a filter"}</td></tr>
          ${IF > 1 ? `<tr class="${halfSt.length ? "hit" : ""}"><td>Half-IF spur</td><td class="n">${fmt(half)}</td><td>2nd</td><td></td><td>${halfSt.length ? `<b>station at ${halfSt.map(fmt).join(", ")}</b>` : "a strong station here also leaks in"}</td></tr>` : ""}</tbody></table></div>
          <p><b>In plain words.</b> Two strong stations 1.5 MHz apart create products another 1.5 MHz further out on each side (2A − B and 2B − A). These third-order products stay inside the FM band, so no band filter can remove them; only a more linear front end (higher IIP3) or less input level (an attenuator, AGC) helps. Each 1 dB stronger stations make them 3 dB stronger; each 1 dB more IIP3 makes them 2 dB weaker. Second-order products (A + B, A − B) fall outside the FM band (A + B lands in DAB Band III, 174–216 MHz), so a car radio with DAB has to care about them too. The image is the other frequency the mixer converts to the same IF; a classic 10.7 MHz radio has it 21.4 MHz away, where aviation and other services sit.</p>
          <p><b>The FM band is a range, by region</b> (shaded in the whole picture): ${BANDS.fm ? BANDS.fm.sub.map(([a, b, l]) => `${esc(l)} ${mhzR(a, b)}`).join(" · ") : ""}. A car radio sold worldwide tunes ${bandText("fm")}; DAB Band III is ${bandText("dab")}.</p>
          <p>Our tuners: <a href="/find?q=Si47">Si47xx AM / FM / DAB receivers</a> (low-IF digital architecture: the image is removed by I/Q processing) · Read more: <a href="/rf-notes#iip3_basics">IIP3 in plain words</a> · <a href="/rf-notes#ip3_intermodulation">IP3 and two-tone intermodulation</a> · <a href="/rf-notes#frequency_planning_pitfalls">Frequency planning pitfalls</a> · <a href="/rf-bands?band=fm">FM band</a></p></div>`,
        note: "Levels are estimates for a single front end: P(2A − B) = 2·P(A) + P(B) − 2·IIP3, IM2 with IIP2 ≈ IIP3 + 20 dB (est). The 30 dB margin for clean mono FM is an estimate (stereo needs more). The FM capture effect helps when your station is clearly stronger than the ghost, and hurts when it is not. Tuner sensitivity and selectivity: Si4734/35 data sheet.",
      };
    },
    related: [["IP3 and intermodulation", "#ip3"], ["AM vs FM modulation", "#mod"], ["dBm ladder", "#dbm"]],
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
        note: `Waveforms: the carrier is drawn only 12 times faster than the tone so you can see it (a real FM station's carrier is anywhere in ${bandText("fm")}, not one frequency) and the FM swing is capped for drawing. AM's envelope is the audio itself, so any noise that changes the amplitude is heard; FM ignores amplitude, which is why it sounds cleaner and the stronger station 'captures' the receiver. The price is bandwidth: broadcast FM needs about 20 times more than AM.`};
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
  for (const add of window.VZ_ADD || []) add({V, DATA, C, num, si, db, undb, log10, clamp, esc, range, BANDS, bandText, bandStrip, appBands, mhzR});

  // ------------------------------------------------------------------ page: tabs, drop-downs and search
  // Owner, 2 Nov 2026: three tabs (RF & wireless · Power & isolation · Basics); under the chosen tab each sub-group is
  // one closed drop-down line with its count, listing only titles; a title shows only that visual; the search box finds
  // a visual by its title or a word; #id deep links open the right tab, sub-group and visual. The tab and sub-group
  // mapping is the #vz-tabs block in templates/engineering/visuals.html; the visuals themselves are not touched here.
  const TABS = JSON.parse($("#vz-tabs").textContent), WORDS = JSON.parse($("#vz-words").textContent);
  const byId = Object.fromEntries(V.map(v => [v.id, v]));
  const SUBS = TABS.flatMap((t, ti) => t.subs.map((s, si) => Object.assign(s, {ti, key: `${t.key}-${si}`, v: []})));
  const taken = new Set();
  for (const s of SUBS) for (const id of s.ids || []) if (byId[id] && !taken.has(id)) { s.v.push(byId[id]); taken.add(id); }
  for (const v of V) {
    const s = taken.has(v.id) ? null : SUBS.find(x => (x.groups || []).includes(v.group));
    if (s) { s.v.push(v); taken.add(v.id); }
  }
  const rest = V.filter(v => !taken.has(v.id));  // a visual no line names: kept under More, never lost
  if (rest.length) SUBS.push(Object.assign({label: "More", ti: TABS.length - 1, key: "more", v: rest}));
  const subOf = Object.fromEntries(SUBS.flatMap(s => s.v.map(v => [v.id, s])));
  const nav = $("#vz-nav"), panel = $("#vz-panel"), tabbar = $("#vz-tabbar"), q = $("#vz-q"), hits = $("#vz-hits");
  const count = ti => SUBS.filter(s => s.ti === ti).reduce((n, s) => n + s.v.length, 0);
  tabbar.innerHTML = TABS.map((t, ti) => `<button type="button" role="tab" id="vz-tab-${t.key}" aria-controls="vz-tp-${t.key}" data-tab="${ti}">${esc(t.label)} <small>${count(ti)}</small></button>`).join("");
  nav.innerHTML = TABS.map((t, ti) => `<div class="vz-tp" role="tabpanel" id="vz-tp-${t.key}" aria-labelledby="vz-tab-${t.key}" data-tab="${ti}" hidden>${
    SUBS.filter(s => s.ti === ti && s.v.length).map(s => `<details class="vz-sub" data-sub="${s.key}"><summary>${esc(s.label)} <small>· ${s.v.length}</small></summary><div class="vz-titles">${
      s.v.map(v => `<a href="#${v.id}" data-id="${v.id}">${esc(v.title)}</a>`).join("")}</div></details>`).join("")}${
    (t.links || []).map(([l, h, d]) => `<p class="vz-also"><a href="${h}">${esc(l)}</a>${d ? ` <span class="muted">· ${esc(d)}</span>` : ""}</p>`).join("")}</div>`).join("");
  let tab = 0;
  function showTab(ti) {
    tab = ti;
    tabbar.querySelectorAll("[role=tab]").forEach(b => {
      const on = +b.dataset.tab === ti;
      b.setAttribute("aria-selected", on); b.classList.toggle("on", on); b.tabIndex = on ? 0 : -1;
    });
    nav.querySelectorAll(".vz-tp").forEach(p => { p.hidden = +p.dataset.tab !== ti; });
  }
  tabbar.addEventListener("click", e => { const b = e.target.closest("[role=tab]"); if (b) showTab(+b.dataset.tab); });
  tabbar.addEventListener("keydown", e => {  // arrow keys move between the tabs
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const ti = (tab + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
    showTab(ti); tabbar.querySelector(`[data-tab="${ti}"]`).focus();
  });
  // search: title, lead, group, the words in library.VISUALS and the "How to read this visual" box
  const norm = s => String(s).toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
  const text = v => norm([v.title, v.lead, v.group, subOf[v.id].label, ...(WORDS[v.id] || []), ...(v.explains || []).map(x => x[0]),
    (document.querySelector(`#vz-explain-src [data-for="${v.id}"]`) || {}).textContent].filter(Boolean).join(" "));
  const INDEX = V.map(v => [v, text(v), norm(v.title + " " + (WORDS[v.id] || []).join(" "))]);
  function find() {
    const words = norm(q.value).split(/\s+/).filter(Boolean);
    hits.hidden = !words.length;
    if (!words.length) { hits.innerHTML = ""; return; }
    const found = INDEX.filter(([, t]) => words.every(w => t.includes(w)))
      .sort((a, b) => words.filter(w => b[2].includes(w)).length - words.filter(w => a[2].includes(w)).length);
    hits.innerHTML = found.length
      ? `<p class="muted">${found.length} visual${found.length === 1 ? "" : "s"}:</p><ul>${found.slice(0, 12).map(([v]) => `<li><a href="#${v.id}" data-hit="${v.id}">${esc(v.title)}</a> <span class="muted">${esc(TABS[subOf[v.id].ti].label)} › ${esc(subOf[v.id].label)}</span></li>`).join("")}</ul>`
      : '<p class="muted">No visual matches. Try one word, e.g. noise, filter, gate.</p>';
  }
  q.addEventListener("input", find);
  q.addEventListener("keydown", e => {
    const first = hits.querySelector("a[data-hit]");
    if (e.key === "Enter" && first) { e.preventDefault(); first.click(); }
  });
  document.addEventListener("click", e => {  // a title or a search hit: show the visual (also when it is shown already)
    const a = e.target.closest("#vz-nav a[data-id], #vz-hits a[data-hit]");
    if (!a) return;
    const id = a.dataset.id || a.dataset.hit;
    if (location.hash.slice(1) === id) { e.preventDefault(); reveal(id); }
    setTimeout(() => {  // bring the visual into view when the list pushed it away (always on a phone)
      const top = panel.getBoundingClientRect().top;
      if (window.matchMedia("(max-width: 900px)").matches || top < 0 || top > window.innerHeight * 0.6) panel.scrollIntoView({block: "start"});
    }, 0);
  });
  function reveal(id) {
    const s = subOf[id];
    if (!s) return;
    showTab(s.ti);
    const d = nav.querySelector(`details[data-sub="${s.key}"]`);
    if (d) d.open = true;
  }
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
      <div class="vz-explain-slot"></div>
      <p class="vz-note"></p>${cur.related ? `<p class="small">Related: ${cur.related.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ")}</p>` : ""}`;
    // plain-language "How to read this visual" box below the graph (owner, 26 Oct 2026), rendered by the page
    const ex = document.querySelector(`#vz-explain-src [data-for="${cur.id}"]`);
    if (ex) panel.querySelector(".vz-explain-slot").replaceWith(ex.cloneNode(true));
    panel.querySelectorAll("[data-k]").forEach(el => el.addEventListener("input", () => {
      const c = cur.controls.find(x => x.k === el.dataset.k);
      vals[c.k] = c.type === "select" ? el.value : fromPos(c, el.value);
      const o = panel.querySelector(`[data-o="${c.k}"]`);
      if (o) o.textContent = show(c, vals[c.k]);
      if (c.type !== "select") el.setAttribute("aria-valuetext", show(c, vals[c.k]));  // read as "1.5 dB", not "1.5"
      render();
    }));
    const setVals = values => {
      Object.assign(vals, values);
      for (const c of cur.controls) {  // move the sliders and selects to the new values
        const el = panel.querySelector(`[data-k="${c.k}"]`);
        if (!el || !(c.k in values)) continue;
        el.value = c.type === "select" ? vals[c.k] : toPos(c, vals[c.k]);
        const o = panel.querySelector(`[data-o="${c.k}"]`);
        if (o) o.textContent = show(c, vals[c.k]);
        if (c.type !== "select") el.setAttribute("aria-valuetext", show(c, vals[c.k]));
      }
    };
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
    redraw = cur.setup ? cur.setup(panel.querySelector(".vz-extra"), render, setVals) || null : null;
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
  // #id opens the visual in its tab and sub-group; no (or an unknown) hash: the first tab, every line closed
  const route = () => {
    const id = (location.hash || "").slice(1);
    if (byId[id]) { reveal(id); open(id); } else if (!cur) showTab(tab);
  };
  window.addEventListener("hashchange", route);
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => cur && render(), 120); });
  route();
  if (cur && window.matchMedia("(max-width: 900px)").matches) panel.scrollIntoView({block: "start"});  // a link from another page, on a phone: the visual first
})();
