// Animated circuit visuals (owner, 28 Oct 2026: "diagrams that move like in a circuit diagram the way current flows";
// "Build the six examples you mentioned ... Put it in the engineering knowledge"). Six visuals that register with the
// visuals engine in visuals.js (window.VZ_ADD), group "Circuits in motion":
//   bootstrap  gate driver and half-bridge with the bootstrap supply, dead time and the Miller plateau
//   bldc       BLDC motor: 6-step commutation, with a toggle to FOC (sine currents); back-EMF per phase, the floating
//              phase's zero crossing and the 30° commutation delay, and a speed slider (back-EMF against the bus)
//   buck       buck converter: on loop, freewheel loop, inductor-current triangle; duty-cycle slider
//   efuse      hot-swap / eFuse: inrush in the linear region, then a short, the fast trip and latch-off or retry
//   isosense   isolated current sensing: shunt, RC filter, isolated amplifier, error tags (AN1270 numbers)
//   ook        capacitive isolator: on-off keyed carrier on a differential pair, common-mode transient rejected
// Each is an inline SVG schematic redrawn every animation frame. Current is a row of dots moving along the wires
// (stroke-dashoffset): speed means magnitude, direction means the direction of flow; each loop or phase has its own
// colour (CSS tokens in circuit.css, light and dark). Controls: Play / Pause, Step (next phase) and the engine's
// sliders. With prefers-reduced-motion the animation starts paused and Step still works. Simplified and labelled so.
(() => {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  const EST = '<span class="kn-est" title="BizDev\'s own reasoning or simplification, not from a source">est</span>';
  const clamp01 = x => Math.max(0, Math.min(1, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const f1 = x => (Math.abs(x) < 0.05 ? "0" : x.toFixed(1));
  const W = 720;

  // ------------------------------------------------------------------ schematic symbols (all strings of SVG)
  const wire = (d, cls = "") => `<path d="${d}" class="cf-w ${cls}"/>`;
  const dot = (x, y) => `<circle cx="${x}" cy="${y}" r="3.2" class="cf-dot"/>`;
  const txt = (x, y, s, a = "start", cls = "cf-t") => `<text x="${x}" y="${y}" text-anchor="${a}" class="${cls}">${s}</text>`;
  function resH(x1, y, x2) {
    const n = 6, w = (x2 - x1 - 12) / n;
    let d = `M${x1} ${y}H${x1 + 6}`;
    for (let i = 0; i < n; i++) d += `L${x1 + 6 + w * (i + 0.5)} ${y + (i % 2 ? 6 : -6)}`;
    return `<path d="${d}L${x2 - 6} ${y}H${x2}" class="cf-part"/>`;
  }
  function resV(x, y1, y2) {
    const n = 6, h = (y2 - y1 - 12) / n;
    let d = `M${x} ${y1}V${y1 + 6}`;
    for (let i = 0; i < n; i++) d += `L${x + (i % 2 ? 6 : -6)} ${y1 + 6 + h * (i + 0.5)}`;
    return `<path d="${d}L${x} ${y2 - 6}V${y2}" class="cf-part"/>`;
  }
  const capV = (x, yT, yB) => `<path d="M${x - 13} ${yT}H${x + 13}M${x - 13} ${yB}H${x + 13}" class="cf-cap"/>`;
  const capH = (xL, xR, y) => `<path d="M${xL} ${y - 12}V${y + 12}M${xR} ${y - 12}V${y + 12}" class="cf-cap"/>`;
  function ind(x1, y, x2) {
    const n = 4, r = (x2 - x1) / (2 * n);
    let d = `M${x1} ${y}`;
    for (let i = 0; i < n; i++) d += `a${r} ${r} 0 0 1 ${2 * r} 0`;
    return `<path d="${d}" class="cf-part"/>`;
  }
  function diode(x, y, dir, s = 9) {  // anode -> cathode points along dir
    const P = {r: [[x - s, y - s], [x - s, y + s], [x + s, y], [x + s, y - s, x + s, y + s]],
      u: [[x - s, y + s], [x + s, y + s], [x, y - s], [x - s, y - s, x + s, y - s]]}[dir];
    return `<polygon points="${P[0]} ${P[1]} ${P[2]}" class="cf-diode"/><path d="M${P[3][0]} ${P[3][1]}L${P[3][2]} ${P[3][3]}" class="cf-cap"/>`;
  }
  // a transistor as a labelled switch box: state off / lin (linear region, partly on) / on / pwm
  const STATE = {off: "off", lin: "linear", on: "on", pwm: "PWM"};
  const fet = (x, y, w, h, state, label, sub = "") => `<g class="cf-fet ${state}" data-state="${state}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6"/>`
    + `<text x="${x + w / 2}" y="${y + h / 2 - (sub ? 2 : -4)}" text-anchor="middle" class="cf-t cf-b">${label}</text>`
    + (sub ? `<text x="${x + w / 2}" y="${y + h / 2 + 12}" text-anchor="middle" class="cf-ts">${sub} · ${STATE[state]}</text>` : "") + "</g>";
  const box = (x, y, w, h, cls = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" class="cf-box ${cls}"/>`;
  const src = (cx, cy, r = 18) => `<circle cx="${cx}" cy="${cy}" r="${r}" class="cf-src"/><text x="${cx}" y="${cy - 3}" text-anchor="middle" class="cf-t cf-b">+</text><text x="${cx}" y="${cy + 12}" text-anchor="middle" class="cf-t cf-b">−</text>`;
  const gnd = (x, y) => `<path d="M${x - 11} ${y}H${x + 11}M${x - 7} ${y + 4}H${x + 7}M${x - 3} ${y + 8}H${x + 3}" class="cf-cap"/>`;
  const arrowR = (x, y) => `<path d="M${x - 8} ${y - 5}L${x} ${y}L${x - 8} ${y + 5}" class="cf-cap"/>`;
  // a callout: lines of text in a rounded box; c = colour index of the border
  function tag(x, y, lines, c = 2, cls = "") {
    const w = Math.max(...lines.map(l => l.length)) * 6 + 14, h = lines.length * 14 + 8;
    return `<g class="cf-tag cf-tc${c} ${cls}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6"/>${lines.map((l, i) => `<text x="${x + 7}" y="${y + 17 + i * 14}" class="cf-ts cf-tt">${esc(l)}</text>`).join("")}</g>`;
  }

  // ------------------------------------------------------------------ small waveform panel below a schematic
  // rows: [{label, lo, hi, h, series: [{pts: [[x 0..1, y]], c, dash}], zero, marks, vlines: [{x, cls}]}], o: {cursor, shades: [{x0, x1, label}], foot}
  function waveSvg(rows, o) {
    const L = 122, R = 10, rh0 = o.rowH || 40, gap = 10, T = o.top || 6;
    const tops = rows.reduce((a, r) => [...a, a[a.length - 1] + (r.h || rh0) + gap], [T]);  // a row may set its own height h
    const H = tops[rows.length] + (o.foot ? 18 : 4);
    const X = x => L + clamp01(x) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" class="cf-wsvg" role="img" aria-label="${esc(o.label)}" font-size="11">`;
    for (const sh of o.shades || []) {
      s += `<rect x="${X(sh.x0)}" y="${T - 4}" width="${Math.max(1, X(sh.x1) - X(sh.x0))}" height="${H - T - (o.foot ? 18 : 4) + 2}" class="cf-shade ${sh.cls || ""}"/>`;
      if (sh.label) s += `<text x="${(X(sh.x0) + X(sh.x1)) / 2}" y="${T + 6}" text-anchor="middle" class="cf-ts">${esc(sh.label)}</text>`;
    }
    rows.forEach((r, i) => {
      const rh = r.h || rh0, y0 = tops[i], Y = v => y0 + rh - ((v - r.lo) / (r.hi - r.lo)) * rh;
      s += `<line x1="${L}" x2="${W - R}" y1="${Y(r.zero ?? r.lo)}" y2="${Y(r.zero ?? r.lo)}" class="cf-axis"/>`;
      s += `<text x="${L - 8}" y="${y0 + rh / 2 + 4}" text-anchor="end" class="cf-ts">${esc(r.label)}</text>`;
      for (const se of r.series) {
        if (!se.pts.length) continue;
        s += `<path d="${se.pts.map(([x, y], k) => `${k ? "L" : "M"}${X(x).toFixed(1)} ${Y(Math.max(r.lo, Math.min(r.hi, y))).toFixed(1)}`).join("")}" class="cf-trace cf-c${se.c}${se.dash ? " cf-dash" : ""}"/>`;
      }
      for (const vl of r.vlines || []) s += `<line x1="${X(vl.x).toFixed(1)}" x2="${X(vl.x).toFixed(1)}" y1="${y0}" y2="${y0 + rh}" class="${vl.cls || "cf-zc"}"/>`;
      for (const m of r.marks || []) s += `<text x="${X(m.x)}" y="${Y(m.y) - 4}" text-anchor="${m.a || "middle"}" class="cf-ts">${esc(m.t)}</text>`;
    });
    if (o.cursor != null) s += `<line x1="${X(o.cursor)}" x2="${X(o.cursor)}" y1="${T - 4}" y2="${H - (o.foot ? 18 : 4)}" class="cf-cur"/>`;
    if (o.foot) s += `<text x="${W - R}" y="${H - 4}" text-anchor="end" class="cf-ts">${esc(o.foot)}</text>`;
    return s + "</svg>";
  }
  // sample a piecewise timeline: segs [{w (relative width), f(p) -> {key: value}}] -> {key: [[x, value]]}
  function sampleSegs(segs, keys, n = 30) {
    const tot = segs.reduce((a, s) => a + s.w, 0), out = Object.fromEntries(keys.map(k => [k, []]));
    let x0 = 0;
    for (const sg of segs) {
      for (let j = 0; j <= n; j++) {
        const p = j / n, v = sg.f(p);
        for (const k of keys) out[k].push([(x0 + p * sg.w) / tot, v[k]]);
      }
      x0 += sg.w;
    }
    return out;
  }

  // ------------------------------------------------------------------ the animation engine shared by the six
  // def: {id, label, phases(st, v) -> [{label, cap, dur, hold, next}], draw(st, F, v) -> {svg, h, legend, wave},
  //       buttons: [{k, label(st), click(st, v, go)}], tick(st, dt, v) (optional), step(st, v, go) (optional), init(st)}
  function mount(el, def, S, rerender) {
    const reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const st = {i: 0, tp: 0, t: 0, pos: {}, dtNow: 0, flags: {...(def.flags || {})}, playing: !reduce, reduce};
    S.st = st;
    if (def.init) def.init(st);
    el.innerHTML = `<div class="cf" data-cf="${def.id}">
      <div class="cf-bar" role="toolbar" aria-label="Animation controls">
        <button type="button" class="small-btn cf-play"></button>
        <button type="button" class="small-btn outline secondary cf-step">Step ▸ next phase</button>
        ${(def.buttons || []).map(b => `<button type="button" class="small-btn outline cf-x" data-b="${b.k}"></button>`).join("")}
      </div>
      <p class="cf-ph" aria-live="polite"></p>
      <div class="cf-fig"></div>
      <div class="cf-legend small"></div>
      <p class="cf-cap small"></p>
      <div class="cf-wave"></div>
    </div>`;
    const q = s => el.querySelector(s), fig = q(".cf-fig"), ph = q(".cf-ph"), cap = q(".cf-cap"), leg = q(".cf-legend"), wave = q(".cf-wave"), play = q(".cf-play");
    const F = (key, d, speed, c, cls = "") => {
      if (!speed || !isFinite(speed)) return "";
      st.pos[key] = ((st.pos[key] || 0) + speed * 60 * st.dtNow) % 1400;  // 14 px dot pitch: wrap on a whole number of dots
      return `<path d="${d}" class="cf-flow cf-c${c} ${cls}" style="stroke-dashoffset:${(-st.pos[key]).toFixed(1)}px" data-k="${key}"/>`;
    };
    const phases = () => def.phases(st, S.v);
    const go = i => { st.i = i; st.tp = 0; };
    let lastLeg = "";
    function paint(dt) {
      st.dtNow = dt;
      const P = phases(), cur = P[st.i] || P[0], r = def.draw(st, F, S.v);
      fig.innerHTML = `<svg viewBox="0 0 ${W} ${r.h || 360}" class="cf-svg" role="img" aria-label="${esc(def.label)}" font-size="12">${r.svg}<text x="${W - 6}" y="14" text-anchor="end" class="cf-ts cf-simp">simplified</text></svg>`;
      const label = r.phase || `Phase ${st.i + 1} of ${P.length}: ${cur.label}`;
      if (ph.textContent !== label) ph.textContent = label;
      const c = r.cap || cur.cap || "";
      if (cap.textContent !== c) cap.textContent = c;
      const lg = (r.legend || []).map(([n, l]) => `<span><i class="cf-sw cf-b${n}"></i>${esc(l)}</span>`).join("");
      if (lg !== lastLeg) { leg.innerHTML = lg; lastLeg = lg; }
      wave.innerHTML = r.wave || "";
      play.textContent = st.playing ? "❚❚ Pause" : "▶ Play";
      play.setAttribute("aria-pressed", String(st.playing));
      el.querySelectorAll(".cf-x").forEach(b => {
        const d = def.buttons.find(x => x.k === b.dataset.b);
        b.textContent = d.label(st);
        if (d.pressed) b.setAttribute("aria-pressed", String(!!d.pressed(st)));
      });
    }
    function advance(dt) {
      st.t += dt;
      if (def.tick) return def.tick(st, dt, S.v, go);
      const P = phases(), cur = P[st.i];
      st.tp += dt / cur.dur;
      if (st.tp >= 1) { if (cur.hold) st.tp = 1; else go(cur.next != null ? cur.next : (st.i + 1) % P.length); }
    }
    let raf = 0, last = 0;
    function loop(now) {
      raf = 0;
      if (!el.isConnected || !st.playing) return;  // the visual was closed or paused
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
      last = now;
      advance(dt);
      paint(dt);
      raf = requestAnimationFrame(loop);
    }
    const start = () => { if (!raf && st.playing) { last = 0; raf = requestAnimationFrame(loop); } };
    play.addEventListener("click", () => { st.playing = !st.playing; paint(0); start(); });
    q(".cf-step").addEventListener("click", () => {
      if (def.step) def.step(st, S.v, go);
      else { const P = phases(), cur = P[st.i]; go(cur.stepNext != null ? cur.stepNext : cur.next != null ? cur.next : (st.i + 1) % P.length); }
      paint(0.12);  // a small nudge so the dots visibly move on each step, also when paused
    });
    el.querySelectorAll(".cf-x").forEach(b => b.addEventListener("click", () => {
      def.buttons.find(x => x.k === b.dataset.b).click(st, S.v, go);
      paint(0);
      if (rerender) rerender();
    }));
    S.redraw = () => { if (el.isConnected && !st.playing) paint(0); };
    paint(0);
    start();
  }

  // each visual keeps its slider values (S.v, set by compute) and its animation state (S.st)
  const state = () => ({v: null, st: null, redraw: null});
  const defaults = controls => Object.fromEntries(controls.map(c => [c.k, c.value]));
  const visual = (V, base, def) => {
    const S = state();
    S.v = defaults(base.controls);
    V.push({
      ...base,
      setup(el, rerender) { mount(el, def, S, rerender); },
      compute(v) {
        S.v = {...v};
        if (S.redraw) S.redraw();
        return {nochart: true, ...base.result(v, S.st || {flags: {...(def.flags || {})}})};
      },
    });
  };

  (window.VZ_ADD = window.VZ_ADD || []).push(({V}) => {
    const PK = {motor: ["Part knowledge: motor drivers and controllers", "/reviews/how/motor"], gd: ["Part knowledge: isolated gate drivers", "/reviews/how/gatedriver"],
      iso: ["Part knowledge: capacitive digital isolators", "/reviews/how/isolator"], cs: ["Part knowledge: isolated current sensing", "/reviews/how/currentsense"],
      hs: ["Research: hot-swap and eFuses, cars and data centers", "/business/reports/auto-hv-hot-swap#applications-in-depth"]};
    const more = (...ls) => `<p class="small">More: ${ls.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ")}</p>`;
    const simp = s => `<p class="small"><b>Simplified</b> ${EST}: ${s}</p>`;

    // ================================================================ 1 · gate driver, half-bridge, bootstrap
    const bootPhases = v => [
      {label: "Low side on: the bootstrap capacitor charges", dur: 2.6,
        cap: "Q2 is on, so the switch node sits at ground. VDD charges Cboot through the bootstrap diode and Q2 (green). The load current comes up through Q2 (blue)."},
      {label: "Dead time: both switches off", dur: 0.5 + v.dead / 200,
        cap: "Both gates are low so the two switches never conduct together (shoot-through). The load current keeps flowing through the body diode of Q2, which costs a diode drop."},
      {label: "High-side turn-on: gate charge, Miller plateau, switch node rises", dur: 3.4,
        cap: "Cboot is the floating supply: its charge flows through HB and HO into the gate of Q1 (orange) and back through the switch node. On the Miller plateau the gate voltage stays flat while the switch node rises to VBUS."},
      {label: "High side on: Cboot powers the high-side gate", dur: 2.4,
        cap: "Q1 carries the load current from VBUS (blue). The high-side driver floats on the switch node and lives on Cboot, which slowly droops; it is refilled in the next low-side phase."},
      {label: "High-side turn-off, then dead time again", dur: 0.9 + v.dead / 200,
        cap: "The driver pulls the gate of Q1 down (orange), the switch node falls and the load current moves back to the body diode of Q2 until the low side turns on."},
    ];
    function bootVals(i, p) {
      let vgs = 0, vsw = -0.1, vb = 11.4, q1 = "off", q2 = "off", main = 0, low = 0, ig = 0, chg = 0;
      if (i === 0) { q2 = "on"; vb = 11.0 + (0.4 * (1 - Math.exp(-4 * p))) / (1 - Math.exp(-4)); low = 1; chg = 1.6 * Math.exp(-3 * p) + 0.15; }
      else if (i === 1) { vsw = -0.7; low = 1; }
      else if (i === 2) {
        vb = 11.4 - 0.25 * Math.min(1, p / 0.9);
        if (p < 0.35) { vgs = 4.5 * (p / 0.35) ** 0.8; vsw = -0.7; const k = clamp01((p - 0.2) / 0.15); main = k; low = 1 - k; q1 = p < 0.2 ? "off" : "lin"; ig = 1.4; }
        else if (p < 0.7) { vgs = 4.5; vsw = lerp(-0.7, 48, (p - 0.35) / 0.35); main = 1; q1 = "lin"; ig = 1.0; }
        else { vgs = 4.5 + (vb - 4.5) * (1 - Math.exp((-6 * (p - 0.7)) / 0.3)); vsw = 48; main = 1; q1 = "on"; ig = Math.exp((-5 * (p - 0.7)) / 0.3) + 0.1; }
      } else if (i === 3) { q1 = "on"; vb = 11.15 - 0.15 * p; vgs = vb; vsw = 48; main = 1; ig = 0.15; }
      else {
        vb = 11.0;
        if (p < 0.3) { const k = p / 0.3; q1 = "lin"; vgs = lerp(11, 0, k); vsw = lerp(48, -0.7, k); main = 1 - k; low = k; ig = -1.2; }
        else { vsw = -0.7; low = 1; }
      }
      return {vgs, vsw, vb, q1, q2, main, low, ig, chg};
    }
    visual(V, {
      id: "bootstrap", group: "Circuits in motion", title: "Gate driver and half-bridge: bootstrap, dead time, Miller plateau",
      explains: [PK.gd, PK.motor],
      lead: "Watch the current in a half-bridge: while the low side is on, the bootstrap capacitor charges; after a dead time, its charge turns on the high-side gate, the gate voltage pauses on the Miller plateau and the switch node climbs to the bus voltage.",
      controls: [{k: "dead", label: "Dead time", min: 20, max: 500, step: 10, value: 100, unit: "ns"}],
      result(v) {
        const loss = 2 * v.dead * 1e-9 * 10 * 0.8 * 100e3;
        return {
          outputs: [["Dead time", `${v.dead} ns`, v.dead < 50 ? "bad" : v.dead > 300 ? "warn" : "ok"], ["Body diode conducts per cycle", `${2 * v.dead} ns`],
            ["Body-diode loss at 10 A, 0.8 V, 100 kHz", `${loss.toFixed(2)} W`], ["Shoot-through risk", v.dead < 50 ? "high: edges may overlap" : "low"]],
          eq: "P<sub>diode</sub> ≈ 2 × t<sub>dead</sub> × I<sub>load</sub> × V<sub>F</sub> × f<sub>sw</sub> &nbsp;·&nbsp; C<sub>boot</sub> ≥ 10 × Q<sub>g</sub> / V<sub>GS</sub>",
          eqn: `2 × ${v.dead} ns × 10 A × 0.8 V × 100 kHz = ${loss.toFixed(2)} W · e.g. Q<sub>g</sub> = 50 nC at 12 V: C<sub>boot</sub> ≥ 42 nF, use 100 nF or more`,
          html: simp("one switching cycle slowed down by about a million; the voltages are typical round numbers (VDD 12 V, VBUS 48 V, plateau 4.5 V), not a specific part. The load (an inductor or a motor winding) is not drawn; its current is shown leaving the switch node.")
            + more(PK.gd, PK.motor, ["Gate-drive current and power", "#gate"], ["Three-step turn-on", "#turnon"]),
          note: "Too short a dead time and both switches conduct for a moment (shoot-through); too long and the body diode conducts longer, which wastes power and adds reverse-recovery loss. The bootstrap rule (Cboot at least 10 × Qg / VGS) is from TI SLUA887A, as on the Part knowledge page.",
        };
      },
      related: [["BLDC 6-step and FOC", "#bldc"], ["Buck converter", "#buck"], ["Gate-drive current and power", "#gate"]],
    }, {
      id: "bootstrap", label: "Half-bridge with gate driver and bootstrap capacitor, current flow animated",
      phases: (st, v) => bootPhases(v),
      draw(st, F, v) {
        const P = bootPhases(v), x = bootVals(st.i, st.tp);
        let s = wire("M70 187V50H401") + wire("M419 50H450V106") + wire("M450 114V180") + wire("M340 90H450") + wire("M340 125H530") + wire("M340 180H560")
          + wire("M340 235H530") + wire("M240 50V75") + wire("M560 40V100") + wire("M560 150V210") + wire("M560 260V330") + wire("M560 40H690V237")
          + wire("M690 273V330") + wire("M70 223V330H690") + wire("M265 300V330") + wire("M560 180H640");
        s += arrowR(648, 180) + diode(410, 50, "r") + capV(450, 106, 114);
        s += box(190, 75, 150, 225) + `<rect x="232" y="100" width="82" height="76" rx="6" class="cf-box cf-float"/>`
          + txt(273, 124, "high-side", "middle", "cf-ts") + txt(273, 137, "driver", "middle", "cf-ts") + txt(273, 150, "(floats on HS)", "middle", "cf-ts")
          + txt(215, 215, "Gate driver", "start", "cf-t cf-b") + txt(215, 232, "(half-bridge)", "start", "cf-ts")
          + txt(212, 92, "VDD", "middle", "cf-ts") + txt(336, 94, "HB", "end", "cf-ts") + txt(336, 129, "HO", "end", "cf-ts") + txt(336, 184, "HS", "end", "cf-ts")
          + txt(336, 239, "LO", "end", "cf-ts") + txt(265, 294, "COM", "middle", "cf-ts");
        s += fet(530, 100, 60, 50, x.q1, "Q1", "high") + fet(530, 210, 60, 50, x.q2, "Q2", "low");
        s += src(70, 205) + txt(96, 202, "VDD", "start", "cf-t cf-b") + txt(96, 216, "12 V", "start", "cf-ts");
        s += src(690, 255) + txt(682, 300, "VBUS", "end", "cf-t cf-b") + txt(682, 314, "48 V", "end", "cf-ts");
        s += dot(450, 90) + dot(450, 180) + dot(560, 180) + dot(240, 50) + dot(560, 40) + gnd(380, 330) + dot(560, 330) + dot(265, 330);
        s += txt(410, 36, "Dboot", "middle", "cf-ts") + txt(436, 108, "Cboot", "end", "cf-ts") + txt(436, 120, `${x.vb.toFixed(2)} V`, "end", "cf-ts cf-b")
          + `<g class="cf-badge"><rect x="572" y="161" width="66" height="16" rx="4"/>${txt(605, 173, `SW ${f1(x.vsw)} V`, "middle", "cf-ts cf-b")}</g>`
          + txt(600, 198, "to the load", "middle", "cf-ts") + txt(530, 92, `VGS ${x.vgs.toFixed(1)} V`, "end", "cf-ts");
        if (st.i === 2 && st.tp >= 0.35 && st.tp < 0.7) s += tag(598, 102, ["Miller plateau:", "VGS flat at 4.5 V", "switch node rising"], 2, "cf-pop");
        if (st.i === 1 || (st.i === 4 && st.tp >= 0.3)) s += tag(596, 272, ["dead time:", "both gates low"], 4, "cf-pop");
        if (x.low && x.q2 !== "on") s += txt(598, 252, "body diode", "start", "cf-ts cf-b");
        if (x.chg) s += F("b1", "M70 187V50H401", x.chg, 3) + F("b2", "M419 50H450V106", x.chg, 3) + F("b3", "M450 114V180H554V330H70V223", x.chg, 3);
        if (x.low) s += F("lo", "M566 330V180H640", x.low * 1.5, 1);
        if (x.main) s += F("mn", "M690 237V40H566V180H640", x.main * 1.5, 1);
        if (x.ig > 0) s += F("g1", "M450 106V90H325V125H530", x.ig, 2) + F("g2", "M554 150V174H456V114", x.ig, 2);
        if (x.ig < 0) s += F("g3", "M530 125H325V184H554V150", -x.ig, 2);
        // waveform: one cycle, not to scale
        const durs = P.map(p => p.dur), segs = P.map((p, i) => ({w: p.dur, f: q => bootVals(i, q)}));
        const sm = sampleSegs(segs, ["vgs", "vsw", "vb"]), tot = durs.reduce((a, b) => a + b, 0);
        const at = (i, p) => (durs.slice(0, i).reduce((a, b) => a + b, 0) + p * durs[i]) / tot;
        const wave = waveSvg([
          {label: "Q1 gate (VGS)", lo: -1, hi: 13, zero: 0, series: [{pts: sm.vgs, c: 2}]},
          {label: "Switch node", lo: -5, hi: 52, zero: 0, series: [{pts: sm.vsw, c: 1}]},
          {label: "Cboot voltage", lo: 10.8, hi: 11.6, series: [{pts: sm.vb, c: 3}]},
        ], {label: "Gate voltage, switch node and bootstrap voltage over one cycle", cursor: at(st.i, st.tp), top: 16,
          shades: [{x0: at(2, 0.35), x1: at(2, 0.7), label: "Miller plateau", cls: "cf-sh1"}, {x0: at(1, 0), x1: at(2, 0), label: "dead time", cls: "cf-sh2"}, {x0: at(4, 0.3), x1: 1, label: "dead time", cls: "cf-sh2"}],
          foot: "one switching cycle, not to scale"});
        return {svg: s, h: 350, wave, legend: [[3, "Bootstrap charging: VDD → Dboot → Cboot → Q2"], [2, "Gate charge from Cboot into Q1"], [1, "Load current (from VBUS or up through Q2)"]]};
      },
    });

    // ================================================================ 2 · BLDC 6-step and FOC
    const AX = {A: 90, B: 210, C: 330}, LEG = {A: 130, B: 210, C: 290}, NY = {A: 130, B: 150, C: 170}, PC = {A: 1, B: 2, C: 3};
    const STEPS = [["A", "B"], ["A", "C"], ["B", "C"], ["B", "A"], ["C", "A"], ["C", "B"]];
    const MC = [590, 185];
    const TERM = Object.fromEntries(Object.entries(AX).map(([k, a]) => [k, [MC[0] + 100 * Math.cos((a * Math.PI) / 180), MC[1] - 100 * Math.sin((a * Math.PI) / 180)]]));
    const PPATH = {
      A: "M130 130H206a4 4 0 0 1 8 0H286a4 4 0 0 1 8 0H420V24H590V85",
      B: "M210 150H286a4 4 0 0 1 8 0H440V235H503.4",
      C: "M290 170H400V336H700V235H676.6",
    };
    function coil(k) {  // winding from the terminal to the star point, drawn as a zigzag
      const a = (AX[k] * Math.PI) / 180, u = [Math.cos(a), -Math.sin(a)], n = [-u[1], u[0]];
      let d = `M${TERM[k][0].toFixed(1)} ${TERM[k][1].toFixed(1)}`;
      for (let j = 0; j <= 8; j++) {
        const r = 92 - j * 5.5, o = j === 0 || j === 8 ? 0 : j % 2 ? 7 : -7;
        d += `L${(MC[0] + u[0] * r + n[0] * o).toFixed(1)} ${(MC[1] + u[1] * r + n[1] * o).toFixed(1)}`;
      }
      return d + `L${MC[0]} ${MC[1]}`;
    }
    const COIL = {A: coil("A"), B: coil("B"), C: coil("C")};
    const sixState = th => (Math.floor((((th % 360) + 360) % 360) / 60) + 1) % 6;
    const fieldAngle = k => { const [X, Y] = STEPS[k]; return vecAngle({[X]: 1, [Y]: -1}); };
    function vecAngle(i) {
      let x = 0, y = 0;
      for (const k of "ABC") { const a = (AX[k] * Math.PI) / 180; x += (i[k] || 0) * Math.cos(a); y += (i[k] || 0) * Math.sin(a); }
      return (Math.atan2(y, x) * 180) / Math.PI;
    }
    const focI = (th, k) => Math.cos(((th + 90 - AX[k]) * Math.PI) / 180);
    const sixI = (th, k) => { const [X, Y] = STEPS[sixState(th)]; return k === X ? 1 : k === Y ? -1 : 0; };
    // back-EMF (owner, 28 Oct 2026: "BLDC Motor Functionality - including Back EMF"): the voltage the turning magnet
    // induces in each winding, in phase with the FOC current for the most torque. A BLDC motor has a trapezoidal
    // back-EMF (flat for 120°, ramps between), a PMSM a sine. In 6-step the floating phase's back-EMF crosses zero in the
    // middle of each 60° step; the next commutation comes 30° later (TI SPRABQ7A section 4.5).
    const VBUS = 48;
    const wrap180 = a => ((((a + 180) % 360) + 360) % 360) - 180;
    const trap = a => { const p = Math.abs(wrap180(a)); return p <= 60 ? 1 : p >= 120 ? -1 : 1 - (p - 60) / 30; };
    const emfTrap = (th, k) => trap(th + 90 - AX[k]);
    const emfSine = (th, k) => Math.cos(((th + 90 - AX[k]) * Math.PI) / 180);
    const floating = k => "ABC".split("").find(L => !STEPS[k].includes(L));
    // the motor model behind the speed slider (est): back-EMF grows with speed; at full PWM duty the current the bus
    // can push is (VBUS - back-EMF) / R, here scaled so that it equals 200 % of the rated current at standstill
    function bemfDrive(v) {
      const s = clamp01(v.spd / 100), e = s * VBUS, avail = 200 * (1 - s), i = Math.min(v.amp, avail);
      return {s, e, head: VBUS - e, avail, i, limited: avail < v.amp};
    }
    visual(V, {
      id: "bldc", group: "Circuits in motion", title: "BLDC motor: 6-step commutation, FOC and back-EMF",
      explains: [PK.motor, PK.gd],
      lead: "A three-phase inverter drives a brushless motor. In 6-step drive two phases carry current at a time and the pattern steps every 60° as the rotor turns; the third phase floats, and the zero crossing of its back-EMF tells a sensorless controller when to switch next. Switch to FOC and all three phases carry smooth sine currents. Raise the speed: the back-EMF grows and leaves less voltage to push current.",
      controls: [{k: "amp", label: "Phase current command (torque)", min: 20, max: 100, step: 5, value: 70, unit: "%"},
        {k: "spd", label: "Motor speed (share of no-load speed)", min: 5, max: 100, step: 5, value: 40, unit: "%"},
        {k: "pp", label: "Motor pole pairs", min: 1, max: 8, step: 1, value: 4, unit: ""}],
      result(v, st) {
        const foc = st.flags && st.flags.foc, d = bemfDrive(v);
        return {
          outputs: [["Drive", foc ? "FOC (sine currents)" : "6-step (trapezoidal)"], ["Commutation steps per electrical turn", foc ? "continuous" : "6"],
            ["Steps per mechanical turn", foc ? "continuous" : `${6 * v.pp}`], ["Torque ripple from the current pattern (ideal motor)", foc ? "≈ 0 %" : "≈ 13 %", foc ? "ok" : "warn"],
            ["Back-EMF (line to line, peak)", `${d.e.toFixed(1)} V of the ${VBUS} V bus`], ["Voltage left to push current", `${d.head.toFixed(1)} V`, d.head < 10 ? "warn" : "ok"],
            ["Phase current", `${Math.round(d.i)} % of rated${d.limited ? " (limited by the back-EMF)" : " (as commanded)"}`, d.limited ? "warn" : "ok"],
            ["Sensorless position from", foc ? "an observer (currents and voltages)" : "back-EMF zero crossing of the floating phase, commutate 30° later"]],
          eq: "back-EMF e = k<sub>e</sub> × ω &nbsp;·&nbsp; at full duty I = (V<sub>bus</sub> − e) / R &nbsp;·&nbsp; 6-step: commutate 30° after the back-EMF zero crossing; torque ripple ≈ 1 − cos 30° ≈ 13 %",
          eqn: `${v.spd} % speed → e ≈ ${d.e.toFixed(1)} V · (48 − ${d.e.toFixed(1)}) V / R → up to ${Math.round(d.avail)} % current, command ${v.amp} % → ${Math.round(d.i)} % · ${v.pp} pole pairs → ${6 * v.pp} steps per turn in 6-step`,
          html: simp(`an ideal motor (trapezoidal back-EMF in 6-step, sine in FOC) on a ${VBUS} V bus, turning at constant speed; the current model is round numbers (stall current twice the rated current), not a specific motor. Real 6-step drives PWM the on switches; the floating terminal is compared with the star point (or half the bus) and a few samples after each commutation are ignored. FOC needs the rotor angle (sensor or observer) and current sensing.`)
            + more(PK.motor, PK.gd, PK.cs, ["Research: 48 V motor control in the car", "/business/reports/auto-48v-motor-control"]),
          note: "6-step is simple (Hall sensors or back-EMF zero crossings are enough) but gives torque ripple and noise; FOC needs current sensing and more computing, and gives smooth, quiet torque. At low speed the back-EMF is too small to detect, so sensorless drives start open loop. The ripple figures are for an idealised motor.",
        };
      },
      related: [["Gate driver and bootstrap", "#bootstrap"], ["Isolated current sensing", "#isosense"]],
    }, {
      id: "bldc", label: "Three-phase inverter and a brushless motor, current flow and back-EMF animated", flags: {foc: false},
      init(st) { st.theta = 15; },
      phases: st => (st.flags.foc ? [{label: "FOC", dur: 1}] : STEPS.map(([X, Y]) => ({label: `${X}+ → ${Y}−`, dur: 1}))),
      tick(st, dt, v) { st.theta = (st.theta + dt * (8 + 64 * bemfDrive(v).s)) % 360; st.i = st.flags.foc ? 0 : sixState(st.theta); },
      step(st) {
        st.theta = st.flags.foc ? (st.theta + 30) % 360 : ((Math.floor(st.theta / 60) + 1) * 60 + 2) % 360;
        st.i = st.flags.foc ? 0 : sixState(st.theta);
      },
      buttons: [{k: "foc", label: st => (st.flags.foc ? "Switch to 6-step" : "Switch to FOC"), pressed: st => st.flags.foc,
        click(st) { st.flags.foc = !st.flags.foc; st.i = st.flags.foc ? 0 : sixState(st.theta); }}],
      draw(st, F, v) {
        const foc = st.flags.foc, th = st.theta, k = sixState(th), [X, Y] = STEPS[k], d = bemfDrive(v), cur = (d.i / 100) * 1.8;
        let s = wire("M50 152V40H290") + wire("M50 188V270H290") + src(50, 170) + txt(74, 174, "DC bus", "start", "cf-ts") + txt(74, 188, `${VBUS} V`, "start", "cf-ts");
        for (const L of "ABC") {
          const x = LEG[L], hs = foc ? "pwm" : L === X ? "on" : "off", ls = foc ? "pwm" : L === Y ? "on" : "off";
          s += wire(`M${x} 40V60`) + wire(`M${x} 105V195`) + wire(`M${x} 240V270`) + fet(x - 24, 60, 48, 45, hs, `${L} hi`) + fet(x - 24, 195, 48, 45, ls, `${L} lo`)
            + dot(x, NY[L]) + dot(x, 40) + dot(x, 270) + wire(PPATH[L]) + wire(COIL[L]);
        }
        s += `<circle cx="${MC[0]}" cy="${MC[1]}" r="110" class="cf-stator"/>` + dot(MC[0], MC[1]);
        for (const L of "ABC") {
          const [tx, ty] = TERM[L], a = (AX[L] * Math.PI) / 180;
          s += txt(tx + 16 * Math.cos(a) + (L === "A" ? 14 : 0), ty - 16 * Math.sin(a) + 4, L, "middle", `cf-t cf-b cf-fc${PC[L]}`);
        }
        s += txt(MC[0], 318, "motor: 3 windings in star", "middle", "cf-ts") + txt(140, 300, "3-phase inverter", "middle", "cf-ts");
        // flows
        if (!foc) {
          const xs = LEG[X], ys = LEG[Y];
          s += F(`bus${X}`, `M50 152V40H${xs}`, cur, 4) + F(`hs${X}`, `M${xs} 40V${NY[X]}`, cur, PC[X]) + F(`ph${X}`, PPATH[X], cur, PC[X]) + F(`co${X}`, COIL[X], cur, PC[X])
            + F(`co${Y}`, COIL[Y], -cur, PC[Y]) + F(`ph${Y}`, PPATH[Y], -cur, PC[Y]) + F(`ls${Y}`, `M${ys} ${NY[Y]}V270`, cur, PC[Y]) + F(`rt${Y}`, `M${ys} 270H50V188`, cur, 4);
        } else {
          for (const L of "ABC") {
            const i = focI(th, L) * cur, x = LEG[L];
            s += F(`ph${L}`, PPATH[L], i, PC[L]) + F(`co${L}`, COIL[L], i, PC[L]);
            s += i > 0 ? F(`hs${L}`, `M${x} 40V${NY[L]}`, i, PC[L]) : F(`ls${L}`, `M${x} ${NY[L]}V270`, -i, PC[L]);
          }
        }
        const phi = foc ? th + 90 : fieldAngle(k);
        const fx = MC[0] + 78 * Math.cos((phi * Math.PI) / 180), fy = MC[1] - 78 * Math.sin((phi * Math.PI) / 180);
        s += `<line x1="${MC[0]}" y1="${MC[1]}" x2="${fx.toFixed(1)}" y2="${fy.toFixed(1)}" class="cf-field"/><circle cx="${fx.toFixed(1)}" cy="${fy.toFixed(1)}" r="4" class="cf-fieldend"/>`;
        s += `<g class="cf-rotor" data-angle="${th.toFixed(1)}" transform="rotate(${(-th).toFixed(2)} ${MC[0]} ${MC[1]})"><circle cx="${MC[0]}" cy="${MC[1]}" r="44" class="cf-rotorbg"/>`
          + `<path d="M${MC[0]} ${MC[1] - 9}H${MC[0] + 30}V${MC[1] - 15}L${MC[0] + 42} ${MC[1]}L${MC[0] + 30} ${MC[1] + 15}V${MC[1] + 9}H${MC[0]}Z" class="cf-north"/>`
          + `<rect x="${MC[0] - 36}" y="${MC[1] - 9}" width="36" height="18" class="cf-south"/>`
          + `<text x="${MC[0] + 16}" y="${MC[1] + 4}" text-anchor="middle" class="cf-ts cf-b cf-on">N</text><text x="${MC[0] - 18}" y="${MC[1] + 4}" text-anchor="middle" class="cf-ts cf-b cf-on">S</text></g>`;
        // back-EMF of the floating phase (6-step) and the zero-crossing timing, as a tag under the inverter
        const t360 = ((th % 360) + 360) % 360, start = Math.floor(t360 / 60) * 60, zc = start + 30;
        const emfV = L => (foc ? emfSine : emfTrap)(th, L) * d.e / 2;
        if (!foc) {
          const Fl = floating(k), when = t360 < zc ? `zero crossing in ${Math.round(zc - t360)}°` : `zero crossed: commutate in ${Math.round(start + 60 - t360)}°`;
          s += tag(20, 352, [`Phase ${Fl} floats: back-EMF ${emfV(Fl).toFixed(1)} V`, when, "commutation = zero crossing + 30°"], PC[Fl], "cf-bemf");
        } else {
          s += tag(20, 352, ["FOC: no phase floats", "a sensorless drive estimates the angle", "from currents and voltages (observer)"], 4, "cf-bemf");
        }
        s += tag(400, 352, [`Back-EMF ${d.e.toFixed(1)} V of ${VBUS} V`, `left to push current: ${d.head.toFixed(1)} V`, `current ${Math.round(d.i)} %${d.limited ? ", limited by back-EMF" : ""}`], d.limited ? 5 : 3, "cf-head");
        // waveform over one electrical turn
        const ths = Array.from({length: 361}, (_, j) => j);
        const fn = foc ? focI : sixI, emf = foc ? emfSine : emfTrap, ia = d.i / 100;
        const torque = t => ia * (foc ? 1 : Math.sin(((fieldAngle(sixState(t)) - t) * Math.PI) / 180));
        const zcs = [30, 90, 150, 210, 270, 330], cms = [0, 60, 120, 180, 240, 300, 360];
        const vlines = foc ? zcs.map(z => ({x: z / 360, cls: "cf-zc"})) : [...zcs.map(z => ({x: z / 360, cls: "cf-zc"})), ...cms.map(c => ({x: c / 360, cls: "cf-cm"}))];
        // the floating phase's back-EMF in each 60° step, drawn bold over the three thin traces
        const flo = foc ? [] : Array.from({length: 6}, (_, m) => ({pts: ths.filter(t => t >= m * 60 && t <= m * 60 + 60).map(t => [t / 360, emf(t, floating(sixState(Math.min(t, m * 60 + 59.9)))) * d.s]), c: 5}));
        const wave = waveSvg([
          ...["A", "B", "C"].map(L => ({label: `Phase ${L} current`, lo: -1.3, hi: 1.3, zero: 0, series: [{pts: ths.map(t => [t / 360, fn(t, L) * ia]), c: PC[L]}]})),
          {label: "Back-EMF A, B, C", lo: -1.15, hi: 1.15, zero: 0, h: 76, vlines,
            series: [...["A", "B", "C"].map(L => ({pts: ths.map(t => [t / 360, emf(t, L) * d.s]), c: PC[L], dash: true})), ...flo],
            marks: foc ? [{x: 30 / 360, y: 0.05, t: "zero crossings", a: "start"}] : [{x: 30 / 360, y: -1.1, t: "zero crossing", a: "middle"}, {x: 61 / 360, y: 0.9, t: "+30° → commutate", a: "start"}]},
          {label: "Torque (relative)", lo: 0, hi: 1.1, series: [{pts: ths.map(t => [t / 360, torque(t)]), c: 4}]},
        ], {label: "Phase currents, back-EMF with its zero crossings, and torque over one electrical turn", cursor: t360 / 360, rowH: 30,
          foot: foc ? "one electrical turn (0° to 360°) · back-EMF scaled to the speed" : "one electrical turn · red solid: floating phase, red ticks: zero crossings, teal dashed: commutations"});
        const phase = foc ? `FOC: all three phases carry sine currents · rotor at ${Math.round(th)}°` : `Step ${k + 1} of 6: current into ${X}, out of ${Y} · rotor at ${Math.round(th)}°`;
        const cap = foc ? "Each phase current follows a sine wave, 120° apart and in step with that phase's back-EMF; the sum of the three is always zero. The stator field (dashed) turns smoothly, always 90° ahead of the rotor, which gives the most torque per amp."
          : `The high-side switch of ${X} and the low-side switch of ${Y} are on: current flows from the bus into winding ${X}, through the star point and out of winding ${Y}. Phase ${floating(k)} floats: its back-EMF ramps through zero in the middle of the step, and the controller switches to the next step 30° later. The stator field (dashed) jumps 60° at each step and pulls the rotor (N) round.`;
        return {svg: s, h: 410, wave, phase, cap, legend: [[1, "Phase A"], [2, "Phase B"], [3, "Phase C"], [4, "DC bus current"], [5, "Back-EMF of the floating phase"]]};
      },
    });

    // ================================================================ 3 · buck converter
    const BUCK = {vin: 12, L: 10e-6, f: 500e3};
    const ripple = d => (BUCK.vin * d * (1 - d)) / (BUCK.L * BUCK.f);
    const iL = (u, d, io) => { const r = ripple(d); return u < d ? io - r / 2 + (r * u) / d : io + r / 2 - (r * (u - d)) / (1 - d); };
    visual(V, {
      id: "buck", group: "Circuits in motion", title: "Buck converter: on loop, freewheel loop, inductor current",
      explains: [["Part knowledge: motor drivers (power stages)", "/reviews/how/motor"], PK.hs],
      lead: "A buck converter chops the input with a switch and smooths it with an inductor and a capacitor. While the high-side switch is on, current flows from the input; while it is off, the inductor keeps the current going through the low-side switch or diode.",
      controls: [{k: "d", label: "Duty cycle (on time ÷ period)", min: 0.1, max: 0.9, step: 0.01, value: 0.42, unit: ""},
        {k: "io", label: "Load current", min: 0.5, max: 3, step: 0.1, value: 2, unit: "A"}],
      result(v, st) {
        const r = ripple(v.d), diode = st.flags && st.flags.diode;
        const pd = 0.5 * v.io * (1 - v.d), pf = 0.01 * v.io ** 2 * (1 - v.d);
        return {
          outputs: [["Output voltage", `${(v.d * BUCK.vin).toFixed(2)} V`], ["Inductor ripple (peak to peak)", `${r.toFixed(2)} A`],
            ["Peak inductor current", `${(v.io + r / 2).toFixed(2)} A`], [diode ? "Low-side loss, diode (0.5 V)" : "Low-side loss, FET (10 mΩ)", `${(diode ? pd : pf).toFixed(3)} W`, diode ? "warn" : "ok"]],
          eq: "V<sub>out</sub> = D × V<sub>in</sub> &nbsp;·&nbsp; Δi<sub>L</sub> = (V<sub>in</sub> − V<sub>out</sub>) × D / (L × f<sub>sw</sub>)",
          eqn: `${v.d.toFixed(2)} × 12 V = ${(v.d * 12).toFixed(2)} V · Δi = (12 − ${(v.d * 12).toFixed(2)}) V × ${v.d.toFixed(2)} / (10 µH × 500 kHz) = ${r.toFixed(2)} A`,
          html: simp("ideal parts (no resistance, no switching loss), 12 V in, 10 µH, 500 kHz, slowed down so one period takes about three seconds; continuous conduction. The average inductor current equals the load current; the capacitor (purple) takes the ripple.")
            + more(PK.motor, PK.hs, ["Switching loss vs frequency", "#swloss"]),
          note: "Ripple is largest at 50 % duty and shrinks with a larger inductor or a higher switching frequency. A diode is simpler but loses about 0.5 V × the current while it conducts; a synchronous FET loses only I² × R.",
        };
      },
      related: [["Gate driver and bootstrap", "#bootstrap"], ["Hot-swap / eFuse", "#efuse"], ["Switching loss vs frequency", "#swloss"]],
    }, {
      id: "buck", label: "Buck converter with on and freewheel current loops animated", flags: {diode: false},
      init(st) { st.u2 = 0; },
      phases: () => [{label: "Switch on: current from the input through the inductor", dur: 1}, {label: "Switch off: the inductor freewheels through the low side", dur: 1}],
      tick(st, dt, v) { st.u2 = (st.u2 + dt / 3) % 2; st.i = st.u2 % 1 < v.d ? 0 : 1; },
      step(st, v) {
        const u = st.u2 % 1, base = st.u2 - u;
        st.u2 = u < v.d ? base + v.d + 0.001 : (base + 1.001) % 2;
        st.i = st.u2 % 1 < v.d ? 0 : 1;
      },
      buttons: [{k: "diode", label: st => (st.flags.diode ? "Low side: use a FET" : "Low side: use a diode"), pressed: st => st.flags.diode, click(st) { st.flags.diode = !st.flags.diode; }}],
      draw(st, F, v) {
        const u = st.u2 % 1, on = u < v.d, il = iL(u, v.d, v.io), ic = il - v.io, diode = st.flags.diode, k = 0.75;
        let s = wire("M70 172V70H200") + wire("M270 70H380") + wire("M500 70H660") + wire("M330 70V150") + wire("M330 210V300") + wire("M560 70V179")
          + wire("M560 189V300") + wire("M660 70V160") + wire("M660 230V300") + wire("M70 208V300H660") + wire("M235 90V106") + ind(380, 70, 500);
        s += fet(200, 50, 70, 40, on ? "on" : "off", "Q1") + txt(235, 120, "PWM", "middle", "cf-ts") + txt(235, 40, "high side", "middle", "cf-ts");
        if (diode) s += `<rect x="306" y="150" width="48" height="60" rx="6" class="cf-box cf-blank"/>` + wire("M330 150V168") + diode(330, 180, "u") + wire("M330 190V210") + txt(296, 184, "diode", "end", "cf-ts");
        else s += fet(306, 150, 48, 60, on ? "off" : "on", "Q2") + wire("M306 180H292") + txt(288, 176, "inverse", "end", "cf-ts") + txt(288, 189, "PWM", "end", "cf-ts");
        s += capV(560, 179, 189) + resV(660, 160, 230) + src(70, 190);
        s += dot(330, 70) + dot(560, 70) + dot(560, 300) + dot(330, 300);
        s += txt(96, 186, "Vin", "start", "cf-t cf-b") + txt(96, 200, "12 V", "start", "cf-ts") + txt(440, 52, "L 10 µH", "middle", "cf-ts")
          + txt(338, 60, `SW ${on ? "12" : diode ? "−0.5" : "0"} V`, "start", "cf-ts cf-b") + txt(576, 182, "Cout", "start", "cf-ts") + txt(672, 200, "load", "start", "cf-ts")
          + `<g class="cf-badge"><rect x="520" y="32" width="96" height="18" rx="4"/>${txt(568, 45, `Vout ${(v.d * 12).toFixed(1)} V`, "middle", "cf-ts cf-b")}</g>`
          + txt(440, 96, `iL ${il.toFixed(2)} A`, "middle", "cf-ts cf-b");
        const c = on ? 1 : 2;
        s += (on ? F("in", "M70 172V70H330", il * k, 1) + F("rt", "M560 300H70V208", il * k, 1) : F("fw", diode ? "M560 300H330V70" : "M560 300H330V70", il * k, 2))
          + F("L", "M330 70H560", il * k, c) + F("ld", "M560 70H660V300H560", v.io * k, c) + F("c1", "M560 70V179", ic * 1.6, 4) + F("c2", "M560 189V300", ic * 1.6, 4);
        // inductor-current triangle over two periods, synced
        const pts = [], sw = [];
        for (let j = 0; j <= 400; j++) { const x = (j / 400) * 2, uu = x % 1; pts.push([x / 2, iL(uu, v.d, v.io), uu < v.d]); sw.push([x / 2, uu < v.d ? 12 : 0]); }
        const seg = flag => { const out = []; let curr = []; for (const p of pts) { if (p[2] === flag) curr.push([p[0], p[1]]); else if (curr.length) { out.push(curr); curr = []; } } if (curr.length) out.push(curr); return out; };
        const hi = Math.max(3.6, v.io + ripple(v.d));
        const wave = waveSvg([
          {label: "Switch node (V)", lo: -1, hi: 14, zero: 0, series: [{pts: sw, c: 4}]},
          {label: "Inductor current", lo: Math.max(0, v.io - ripple(v.d) / 2 - 0.5), hi: v.io + ripple(v.d) / 2 + 0.5, series: [...seg(true).map(p => ({pts: p, c: 1})), ...seg(false).map(p => ({pts: p, c: 2})), {pts: [[0, v.io], [1, v.io]], c: 4, dash: true}],
            marks: [{x: 0.995, y: v.io, t: `average = load ${v.io.toFixed(1)} A`, a: "end"}, {x: v.d / 2, y: v.io + ripple(v.d) / 2 + 0.05, t: `Δi ${ripple(v.d).toFixed(2)} A`}]},
        ], {label: "Switch node voltage and inductor current over two periods", cursor: st.u2 / 2, rowH: 64, foot: "two switching periods (2 µs), slowed down"});
        return {svg: s, h: 330, wave, legend: [[1, "Switch on: input → Q1 → L → load"], [2, `Switch off: freewheel through ${diode ? "the diode" : "Q2"} → L → load`], [4, "Capacitor ripple current"]],
          cap: on ? "Q1 is on: the input drives current through the inductor, which ramps up; the inductor stores energy. The switch node is at the input voltage."
            : `Q1 is off: the inductor keeps the current flowing through ${diode ? "the diode" : "the low-side FET Q2"}, ramping down; the switch node sits at ${diode ? "about −0.5 V" : "about 0 V"}.`};
      },
    });

    // ================================================================ 4 · hot-swap / eFuse
    const EF = {vin: 12, c: 1e-3, r: 6, ilim: 5, trip: 20, soaLim: 60};
    const soaFrac = v => (EF.vin * Math.sqrt(EF.vin * v.dvdt)) / EF.soaLim;  // P × √t of the ramp against an illustrative limit
    const EF_CAP = ["The board is not plugged in: no current, the output is at 0 V.",
      "The controller holds the FET partly on so the output rises at the set slope: the current is the capacitor's charging current (Cout × dV/dt) plus the load. The FET drops the difference between input and output, so it heats up (meter).",
      "The output has reached the bus voltage; the FET is fully on and only the load current flows. Power good.",
      "A short at the output: the capacitor discharges into it and the current through the FET climbs very fast (red).",
      "The fast-trip comparator sees the current pass its threshold and pulls the gate down within about a microsecond: the current stops.",
      "Latch-off: the eFuse stays off until it is reset or the board is re-plugged, so a real fault is not stressed again.",
      "Auto-retry: after a cool-down time the eFuse starts again; if the short is still there it trips again (hiccup mode)."];
    const withCaps = P => P.map((p, i) => ({cap: EF_CAP[i], ...p}));
    const efPhases = st => withCaps([
      {label: "Unplugged", dur: 1.4, next: 1, stepNext: 1},
      st.flags.short ? {label: "Start into the short: current limit, the fault timer runs out", dur: 1.6,
        cap: "The output is still shorted: the controller holds the current at its limit with the FET in its linear region, which heats it, and the fault timer runs out.", next: 4, stepNext: 4}
        : {label: "Plug-in: inrush limited, FET in its linear region", dur: 3.6, next: 2, stepNext: 2},
      {label: "Fully on: the FET is a closed switch", dur: 3, hold: true, stepNext: 0},
      {label: "Short at the output: the current spikes", dur: 1.2, next: 4, stepNext: 4},
      {label: "Fast trip: the FET turns off within about a microsecond", dur: 1.2, next: st.flags.retry ? 6 : 5, stepNext: st.flags.retry ? 6 : 5},
      {label: "Latched off: waits for a reset or a new plug-in", dur: 2, hold: true, stepNext: 0},
      {label: "Auto-retry: cool down, then try again", dur: 2.6, next: 1, stepNext: 1},
    ]);
    function efVals(i, p, short, v) {
      const iin = EF.c * v.dvdt * 1e3, fr = soaFrac(v);
      let vout = 0, I = 0, q = "off", meter = 0, plugged = true, iload = 0, ic = 0, ish = 0;
      if (i === 0) plugged = false;
      else if (i === 1 && short) { q = "lin"; I = EF.ilim; ish = I; meter = p; }
      else if (i === 1) { q = "lin"; vout = EF.vin * p; iload = vout / EF.r; ic = iin; I = iin + iload; meter = Math.min(1, fr * Math.sqrt(p)); }
      else if (i === 2) { q = "on"; vout = EF.vin; iload = EF.vin / EF.r; I = iload; meter = Math.max(0, Math.min(1, fr) * (1 - 2 * p)); }
      else if (i === 3) { q = "on"; vout = EF.vin * (1 - p) ** 4; I = EF.vin / EF.r + (EF.trip - 2) * p; ish = I - vout / EF.r; iload = vout / EF.r; ic = -Math.min(ish, 4) * (1 - p); meter = 0.3 + 0.7 * p; }
      else if (i === 4) { q = p < 0.3 ? "lin" : "off"; I = EF.trip * (1 - Math.min(1, p / 0.3)) ** 2; ish = I; meter = 1; }
      else if (i === 5) { meter = 1; }
      else if (i === 6) { meter = 1 - p; }
      return {vout, I, q, meter, plugged, iload, ic, ish};
    }
    visual(V, {
      id: "efuse", group: "Circuits in motion", title: "Hot-swap / eFuse: inrush, short and trip",
      explains: [PK.hs, PK.gd],
      lead: "Plug a board into a live bus and the eFuse lets the power in gently: its FET runs in the linear region so the output rises at a set slope. Then press Short: the current spikes, the controller trips in microseconds and either stays off or retries.",
      controls: [{k: "dvdt", label: "Output slope during plug-in (dV/dt)", min: 0.2, max: 3, step: 0.1, value: 1, unit: "V/ms"}],
      result(v, st) {
        const iin = EF.c * v.dvdt * 1e3, fr = soaFrac(v), retry = st.flags && st.flags.retry;
        return {
          outputs: [["Inrush current into 1000 µF", `${iin.toFixed(1)} A`], ["Ramp time 0 → 12 V", `${(12 / v.dvdt).toFixed(1)} ms`],
            ["FET peak power at the start", `${(EF.vin * iin).toFixed(1)} W`], ["FET stress against its limit", `${Math.round(fr * 100)} %`, fr > 1 ? "bad" : fr > 0.8 ? "warn" : "ok"],
            ["After a fault", retry ? "auto-retry" : "latch off"]],
          eq: "I<sub>inrush</sub> = C<sub>out</sub> × dV/dt &nbsp;·&nbsp; P<sub>FET</sub> = (V<sub>in</sub> − V<sub>out</sub>) × I &nbsp;·&nbsp; stress ∝ P × √t (a simple SOA rule)",
          eqn: `1000 µF × ${v.dvdt.toFixed(1)} V/ms = ${iin.toFixed(1)} A · peak ${(EF.vin * iin).toFixed(1)} W for ${(12 / v.dvdt).toFixed(1)} ms → ${Math.round(fr * 100)} % of the illustrative limit${fr > 1 ? ": the timer trips during the plug-in" : ""}`,
          html: simp("12 V bus, 1000 µF output capacitor, 6 Ω load (2 A); the FET limit is an illustrative P × √t figure, not a specific part; the current limit, trip level and timing are typical shapes, not data-sheet values. Time is stretched: the plug-in takes milliseconds, the trip about a microsecond.")
            + more(PK.hs, ["Junction temperature", "#thermal"]),
          note: "A slower slope means less current and less heat in the FET at a time, but a longer start-up; too fast and the fault timer or the FET's safe operating area (SOA) is exceeded. Latch-off is the safe choice for a real short; auto-retry suits faults that clear themselves.",
        };
      },
      related: [["Buck converter", "#buck"], ["Junction temperature", "#thermal"], ["Three-step turn-on", "#turnon"]],
    }, {
      id: "efuse", label: "eFuse with pass FET, sense resistor and output capacitor, current flow animated", flags: {short: false, retry: false},
      phases: st => efPhases(st),
      tick(st, dt, v, go) {
        const P = efPhases(st), cur = P[st.i];
        st.tp += dt / cur.dur;
        const fr = soaFrac(v);
        if (st.i === 1 && !st.flags.short && fr > 1 && st.tp >= 1 / fr ** 2) { st.reason = "the FET stress limit (timer) was reached during the plug-in"; go(4); return; }
        if (st.tp >= 1) { if (cur.hold) st.tp = 1; else go(cur.next); }
      },
      step(st, v, go) { const cur = efPhases(st)[st.i]; if (cur.stepNext === 4 && st.i === 3) st.reason = ""; go(cur.stepNext); },
      buttons: [
        {k: "short", label: st => (st.flags.short ? "Remove the short" : "Short the output ⚡"), pressed: st => st.flags.short,
          click(st, v, go) { st.flags.short = !st.flags.short; if (st.flags.short && (st.i === 1 || st.i === 2)) { st.reason = ""; go(3); } }},
        {k: "retry", label: st => (st.flags.retry ? "Fault mode: auto-retry" : "Fault mode: latch-off"), pressed: st => st.flags.retry, click(st) { st.flags.retry = !st.flags.retry; }},
      ],
      draw(st, F, v) {
        const x = efVals(st.i, st.tp, st.flags.short, v), k = 0.42;
        let s = wire("M60 172V80H120") + wire("M150 80H190") + wire("M250 80H310") + wire("M390 80H640") + wire("M520 80V184") + wire("M520 192V300")
          + wire("M640 80V165") + wire("M640 235V300") + wire("M60 208V300H120") + wire("M150 300H640") + wire("M350 100V190") + wire("M350 260V300")
          + wire("M190 80V150H280V190", "cf-thin") + wire("M250 80V140H300V190", "cf-thin");
        s += x.plugged ? wire("M120 80H150") + wire("M120 300H150") : `<path d="M120 80H128M142 80H150M120 300H128M142 300H150" class="cf-w"/>` + txt(135, 66, "unplugged", "middle", "cf-ts cf-b");
        s += `<rect x="116" y="70" width="38" height="240" rx="6" class="cf-conn"/>` + txt(135, 326, "connector", "middle", "cf-ts");
        s += resH(190, 80, 250) + fet(310, 60, 80, 40, x.q, "pass FET") + capV(520, 184, 192) + resV(640, 165, 235) + src(60, 190);
        s += box(250, 190, 200, 70) + txt(350, 212, "eFuse controller", "middle", "cf-t cf-b") + txt(350, 228, "current sense · dV/dt", "middle", "cf-ts") + txt(350, 242, "fault timer · SOA", "middle", "cf-ts");
        s += dot(520, 80) + dot(520, 300) + dot(640, 300);
        if (st.flags.short) s += wire("M590 80V300", "cf-shortw") + dot(590, 80) + dot(590, 300) + txt(596, 196, "⚡ short", "start", "cf-t cf-b cf-fc5");
        s += txt(84, 186, "12 V", "start", "cf-t cf-b") + txt(84, 200, "bus", "start", "cf-ts") + txt(220, 102, "Rsense", "middle", "cf-ts") + txt(536, 190, "Cout", "start", "cf-ts")
          + txt(536, 204, "1000 µF", "start", "cf-ts") + txt(652, 204, "load", "start", "cf-ts") + txt(356, 180, "gate", "start", "cf-ts")
          + `<g class="cf-badge"><rect x="410" y="34" width="96" height="18" rx="4"/>${txt(458, 47, `Vout ${x.vout.toFixed(1)} V`, "middle", "cf-ts cf-b")}</g>`
          + `<g class="cf-badge"><rect x="170" y="34" width="96" height="18" rx="4"/>${txt(218, 47, `I ${x.I.toFixed(1)} A`, "middle", "cf-ts cf-b")}</g>`;
        // stress meter (timer / SOA)
        const mw = 380, fill = clamp01(x.meter);
        s += txt(252, 343, "FET stress / timer", "end", "cf-ts") + `<rect x="260" y="332" width="${mw}" height="14" rx="4" class="cf-meter"/>`
          + `<rect x="260" y="332" width="${(mw * fill).toFixed(1)}" height="14" rx="4" class="cf-meterfill${fill >= 0.999 ? " full" : fill > 0.8 ? " warn" : ""}"/>`
          + `<path d="M${260 + mw} 326V352" class="cf-trip"/>` + txt(260 + mw + 4, 343, "trip", "start", "cf-ts");
        const status = st.i === 5 ? "LATCHED OFF" : st.i === 6 ? "RETRY WAIT" : st.i === 4 ? "TRIPPED" : st.i === 3 ? "FAULT" : st.i === 2 ? "POWER GOOD" : st.i === 1 ? (st.flags.short ? "CURRENT LIMIT" : "SOFT START") : "OFF";
        s += `<g class="cf-badge cf-status s${st.i}"><rect x="532" y="150" width="100" height="18" rx="4"/>${txt(582, 163, status, "middle", "cf-ts cf-b")}</g>`;
        if (st.i === 4) s += tag(410, 112, ["comparator trips:", "gate pulled down in ≈ 1 µs"], 5, "cf-pop");
        if (st.i === 1 && !st.flags.short) s += tag(404, 112, ["FET in linear region:", "it drops Vin − Vout"], 2, "cf-pop");
        // flows
        const c = st.i === 1 && !st.flags.short ? 2 : st.i >= 3 || st.flags.short ? 5 : 1, sp = a => Math.min(6, a * k);
        if (x.I > 0.01) {
          s += F("in", "M60 172V80H310", sp(x.I), c) + F("fet", "M310 80H520", sp(x.I), c) + F("ret", "M520 300H60V208", sp(x.I), c);
          if (x.iload > 0.01) s += F("ld", "M520 80H640V300H520", sp(x.iload), c);
          if (Math.abs(x.ic) > 0.01) s += F("c1", "M520 80V184", sp(x.ic), 4) + F("c2", "M520 192V300", sp(x.ic), 4);
          if (x.ish > 0.01 && st.flags.short) s += F("sh", "M520 80H590V300H520", sp(x.ish), 5);
        }
        // storyline waveform
        const story = [[0, 0.07], [1, 0.3], [2, 0.18], [3, 0.1], [4, 0.1], [st.flags.retry ? 6 : 5, 0.25]];
        const segs = story.map(([i, w]) => ({w, f: p => efVals(i, p, false, v)}));
        segs[3].f = p => efVals(3, p, true, v);
        segs[4].f = p => efVals(4, p, true, v);
        const sm = sampleSegs(segs, ["vout", "I"]);
        let x0 = 0, cursor = 0;
        const shades = story.map(([i, w]) => { const sh = {x0, x1: x0 + w, label: ["unplugged", "plug-in", "on", "short", "trip", "latched", "", "retry"][i] || "", cls: i >= 3 ? "cf-sh5" : ""}; if (i === st.i || (st.i === 6 && i === 6) || (st.i === 5 && i === 5)) cursor = x0 + st.tp * w; x0 += w; return sh; });
        if (st.i === 1 && st.flags.short) cursor = 0.07 + st.tp * 0.3;
        const wave = waveSvg([
          {label: "Output voltage", lo: 0, hi: 13, series: [{pts: sm.vout, c: 3}]},
          {label: "Current", lo: 0, hi: 21, series: [{pts: sm.I, c: 5}], marks: [{x: 0.75, y: 19, t: `trip at ${EF.trip} A`}]},
        ], {label: "Output voltage and current through plug-in, short and trip", cursor: shades.length ? cursor : 0, top: 18, rowH: 44, shades,
          foot: "time not to scale: the plug-in takes milliseconds, the trip about a microsecond"});
        const cap = st.i === 4 && st.reason ? `Tripped because ${st.reason}. Slow the slope (dV/dt) to stay inside the FET's safe operating area.` : undefined;
        return {svg: s, h: 360, wave, cap, legend: [[1, "Normal load current"], [2, "Inrush (FET in its linear region)"], [5, "Fault current"], [4, "Capacitor current"]]};
      },
    });

    // ================================================================ 5 · isolated current sensing
    const AN = {off: [-0.218, 0.26], gain: [-0.44, 0.356], nl: [-0.2, 0.2], rss: [-0.53, 0.484], wc: [-0.858, 0.816]};
    const SENSE = [
      {label: "Load current through the shunt", tag: [300, 88, ["250 mV at full scale", "e.g. 50 A × 5 mΩ"], 1],
        cap: "The load current (blue) flows through a small shunt resistor on the high-voltage side. Ohm's law turns it into a few tens to 250 millivolts across the shunt."},
      {label: "RC input filter", tag: [10, 186, ["RC filter: 20 Ω + 10 nF", "corner ≈ 400 kHz (est)"], 3],
        cap: "The shunt voltage (green: a signal, almost no current flows) passes 20 Ω in each line and 10 nF across them, which keeps switching spikes out of the amplifier (AN1270 data-sheet circuit)."},
      {label: "Amplifier input: offset", tag: [326, 128, ["Offset −0.218 / +0.260 %", "of full scale, −40…125 °C"], 2],
        cap: "Offset is the reading at zero input. For the Si8922B it is ±0.35 mV at 25 °C, which with drift becomes −0.218 % to +0.260 % of the 250 mV full scale over −40 to 125 °C (AN1270)."},
      {label: "Gain error", tag: [110, 298, ["Gain error −0.440 / +0.356 %", "of the reading, −40…125 °C"], 2],
        cap: "Gain error is an error in the slope, so it grows with the reading: ±0.2 % at 25 °C becomes −0.440 % to +0.356 % over temperature (AN1270)."},
      {label: "Nonlinearity", tag: [492, 128, ["Nonlinearity ±0.200 %", "of full scale (AN1270)"], 2],
        cap: "Nonlinearity is the bend of the transfer curve away from a straight line: ±0.04 % at 25 °C, ±0.200 % over temperature. A two-point calibration cannot remove it (AN1270)."},
      {label: "Across the barrier: common-mode transients (CMTI)", tag: [492, 298, ["CMTI ≥ 50 kV/µs (Si8921 min)", "not a static error"], 5],
        cap: "The signal crosses the isolation barrier as a bit stream. When the switch node jumps, a common-mode current flows through the barrier capacitance (red); CMTI is the steepest edge the part rides out without a wrong output. Sample away from the edges."},
      {label: "Output to the controller: the total", tag: [452, 26, ["Total −40…125 °C: RSS −0.530 / +0.484 %", "worst case −0.858 / +0.816 % (AN1270)"], 4],
        cap: "The controller reads the output. Adding the errors straight gives the worst case; root-sum-of-squares (RSS) gives the realistic total when the errors are independent. The shunt tolerance and the ADC add on top."},
    ];
    visual(V, {
      id: "isosense", group: "Circuits in motion", title: "Isolated current sensing: shunt to controller, error by error",
      explains: [PK.cs, ["Engineering knowledge: error propagation and uncertainty bands", "/engineering/error_budget"]],
      lead: "Follow the load current through a shunt, the small voltage through the RC filter and the isolated amplifier across the barrier to the controller. At each stage an error tag pops up with the AN1270 numbers for the Si8922B, building up the error budget.",
      controls: [{k: "pct", label: "Load current, as % of full scale", min: 5, max: 100, step: 1, value: 60, unit: "%"}],
      result(v) {
        const f = v.pct / 100, hi = Math.hypot(AN.off[1] / f, AN.gain[1], AN.nl[1] / f), lo = Math.hypot(AN.off[0] / f, AN.gain[0], AN.nl[0] / f);
        return {
          outputs: [["Shunt voltage", `${(250 * f).toFixed(0)} mV`], ["Offset, as % of this reading", `−${(-AN.off[0] / f).toFixed(2)} / +${(AN.off[1] / f).toFixed(2)} %`],
            ["Total (RSS), as % of this reading", `−${lo.toFixed(2)} / +${hi.toFixed(2)} %`, hi > 1.5 ? "bad" : hi > 0.8 ? "warn" : "ok"], ["At full scale (AN1270, RSS)", "−0.530 / +0.484 %"]],
          eq: "error (% of reading) = √( (offset<sub>FS</sub> / x)² + gain² + (nonlinearity<sub>FS</sub> / x)² ), x = reading ÷ full scale",
          eqn: `x = ${f.toFixed(2)}: √((${AN.off[1]} / ${f.toFixed(2)})² + ${AN.gain[1]}² + (${AN.nl[1]} / ${f.toFixed(2)})²) = +${hi.toFixed(2)} % · at x = 1 this is AN1270's +0.484 %`,
          html: simp("the Si8922B (single-ended output, 250 mV full scale) with the numbers from Skyworks AN1270 over −40 to 125 °C; the 50 A / 5 mΩ shunt, the bit stream and the timing are illustrative. Offset and nonlinearity are % of full scale, so they grow as a share of small readings.")
            + `<p class="small">The full budget, with the four-line offset method: <a href="/engineering/error_budget">Engineering knowledge: error propagation and uncertainty bands</a> · <a href="/reviews/how/currentsense">Part knowledge: isolated current sensing</a> · <a href="https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/application-notes/an1270-si89xx-estimating-total-static-error.pdf" target="_blank" rel="noopener noreferrer">AN1270 ↗</a></p>`,
          note: "Sources: Skyworks AN1270 (Si89xx: estimating total static error), Tables 2–6 for the Si8922B; CMTI 50 kV/µs minimum from the Si8921 data sheet as listed on the Part knowledge page. Noise, bandwidth and the shunt's own tolerance are not in these numbers.",
        };
      },
      related: [["CMTI against the switching edge", "#cmti"], ["BLDC 6-step and FOC", "#bldc"]],
    }, {
      id: "isosense", label: "Shunt, RC filter and isolated amplifier across the barrier, with the error tags",
      phases: () => SENSE.map(p => ({label: p.label, cap: p.cap, dur: 2.6})),
      draw(st, F, v) {
        const f = v.pct / 100, i = st.i;
        let s = `<rect x="0" y="0" width="460" height="340" class="cf-zone hv"/><rect x="460" y="0" width="260" height="340" class="cf-zone lv"/>`
          + txt(10, 16, "high-voltage side (floats with the shunt)", "start", "cf-ts cf-b") + txt(470, 16, "low-voltage side (controller)", "start", "cf-ts cf-b");
        s += wire("M20 70H160") + resH(160, 70, 260) + wire("M260 70H440") + arrowR(448, 70) + txt(20, 58, "from the inverter / battery", "start", "cf-ts") + txt(440, 58, "to the motor", "end", "cf-ts")
          + txt(210, 54, "shunt", "middle", "cf-ts cf-b");
        s += wire("M160 70V140") + resV(160, 140, 180) + wire("M160 180V220H256a4 4 0 0 1 8 0H320") + wire("M260 70V140") + resV(260, 140, 180) + wire("M260 180V250H320")
          + wire("M290 220V231") + capV(290, 231, 239) + wire("M290 239V250") + dot(160, 70) + dot(260, 70) + dot(290, 220) + dot(290, 250)
          + txt(146, 164, "20 Ω", "end", "cf-ts") + txt(274, 164, "20 Ω", "start", "cf-ts") + txt(282, 274, "10 nF", "end", "cf-ts");
        s += box(320, 190, 280, 100) + `<path d="M460 150V318" class="cf-barrier"/>` + txt(460, 334, "isolation barrier", "middle", "cf-ts cf-b")
          + txt(390, 210, "isolated amplifier", "middle", "cf-ts cf-b") + txt(390, 223, "or ΔΣ modulator", "middle", "cf-ts") + txt(530, 210, "receiver", "middle", "cf-ts cf-b")
          + txt(530, 223, "and output", "middle", "cf-ts") + txt(326, 224, "IN+", "start", "cf-ts") + txt(326, 254, "IN−", "start", "cf-ts");
        s += wire("M600 240H650") + box(650, 214, 62, 52) + txt(681, 236, "MCU", "middle", "cf-t cf-b") + txt(681, 251, "ADC", "middle", "cf-ts");
        // the bit stream across the barrier: a first-order delta-sigma pattern whose density of ones follows the input
        const n0 = Math.floor(st.t * 5);
        for (let j = 0; j < 14; j++) {
          const n = n0 + j, bit = Math.floor((n + 1) * (0.1 + 0.8 * f)) - Math.floor(n * (0.1 + 0.8 * f));
          s += `<rect x="${404 + j * 8}" y="252" width="7" height="${bit ? 14 : 3}" class="cf-bit${bit ? " one" : ""}" transform="translate(0 ${bit ? 0 : 11})"/>`;
        }
        s += txt(460, 284, "bit stream", "middle", "cf-ts");
        s += `<g class="cf-badge"><rect x="170" y="78" width="80" height="18" rx="4"/>${txt(210, 91, `${(250 * f).toFixed(0)} mV`, "middle", "cf-ts cf-b")}</g>`;
        s += F("pw", "M20 70H440", 0.6 + 2.2 * f, 1);
        if (i >= 1) s += F("s1", "M160 70V220H256a4 4 0 0 1 8 0H320", 0.45, 3) + F("s2", "M260 70V250H320", 0.45, 3);
        if (i >= 2) s += F("s3", "M330 240H600", 0.5, 3);
        if (i >= 6) s += F("s4", "M600 240H650", 0.5, 3);
        if (i === 5) s += F("cm", "M460 312V156", 2.6, 5, "cf-wide") + tag(486, 166, ["edge current through the barrier"], 5, "cf-pop");
        for (let j = 0; j <= Math.min(i, SENSE.length - 1); j++) { const [x, y, lines, c] = SENSE[j].tag; s += tag(x, y, lines, c, j === i ? "cf-pop cf-now" : "cf-old"); }
        // error budget bars (AN1270, % of full scale at full scale)
        const rows = [["Offset", AN.off, 2, 2], ["Gain error", AN.gain, 3, 2], ["Nonlinearity", AN.nl, 4, 2], ["Total, RSS", AN.rss, 6, 4], ["Worst case", AN.wc, 6, 5]];
        const L = 122, R = 30, X = e => L + ((e + 1) / 2) * (W - L - R), H = 22 * rows.length + 48;
        let w = `<svg viewBox="0 0 ${W} ${H}" class="cf-wsvg" role="img" aria-label="Error budget building up, AN1270 numbers" font-size="11">`;
        for (const t of [-1, -0.5, 0, 0.5, 1]) w += `<line x1="${X(t)}" x2="${X(t)}" y1="4" y2="${H - 36}" class="cf-axis${t ? " cf-faint" : ""}"/><text x="${X(t)}" y="${H - 22}" text-anchor="middle" class="cf-ts">${t > 0 ? "+" : ""}${t} %</text>`;
        rows.forEach(([lab, [a, b], from, c], j) => {
          const y = 8 + j * 22, on = i >= from;
          w += `<text x="${L - 8}" y="${y + 12}" text-anchor="end" class="cf-ts${on ? "" : " cf-faint"}">${esc(lab)}</text>`;
          if (on) w += `<rect x="${X(a)}" y="${y}" width="${X(b) - X(a)}" height="14" rx="3" class="cf-ebar cf-b${c}"/><text x="${X(b) + 4}" y="${y + 11}" class="cf-ts">${a.toFixed(3)} / +${b.toFixed(3)} %</text>`;
        });
        w += `<text x="${W - 4}" y="${H - 4}" text-anchor="end" class="cf-ts">% of full scale, −40…125 °C</text></svg>`;
        return {svg: s, h: 340, wave: w, legend: [[1, "Load current"], [3, "Signal path (a voltage)"], [5, "Common-mode current at an edge"], [4, "Total error"]]};
      },
    });

    // ================================================================ 6 · capacitive isolator, on-off keying
    const BITS = [1, 0, 1, 1, 0, 0, 1, 0];
    const CMTI = {si86: 35, si86s: 100, si86sd: 150};
    const carrierOn = (bit, st, v) => st.flags.power && (v.def === "high" ? bit === 0 : bit === 1);
    const outLevel = (bit, st, v) => (st.flags.power ? bit : v.def === "high" ? 1 : 0);
    visual(V, {
      id: "ook", group: "Circuits in motion", title: "Capacitive isolator: on-off keying and common-mode rejection",
      explains: [PK.iso, PK.gd],
      lead: "A digital isolator sends each logic level as an RF carrier switched on or off, through two SiO2 capacitors in series on each line of a differential pair. Press the common-mode button: the ground of side 2 jumps, both lines see the same disturbance and the differential receiver cancels it.",
      controls: [
        {k: "slope", label: "Common-mode transient slope", min: 10, max: 200, step: 5, value: 50, unit: "kV/µs"},
        {k: "part", label: "Part family (CMTI rating)", type: "select", options: [["si86", "Si86xx (> 35 kV/µs)"], ["si86s", "Si86Sx (> 100 kV/µs)"], ["si86sd", "Si86Sx with deglitch (150 kV/µs)"]], value: "si86s"},
        {k: "def", label: "Default output (part option)", type: "select", options: [["low", "Default low"], ["high", "Default high"]], value: "low"},
      ],
      result(v, st) {
        const r = CMTI[v.part], ok = v.slope <= r, power = !st.flags || st.flags.power !== false;
        return {
          outputs: [["CMTI rating", `${r} kV/µs`], ["Transient", `${v.slope} kV/µs`], ["Output during the transient", ok ? "unchanged" : "may glitch", ok ? "ok" : "bad"],
            ["With side 1 unpowered", `output ${v.def === "high" ? "high" : "low"} (default)`, power ? "" : "warn"]],
          eq: "receiver sees V<sub>P</sub> − V<sub>N</sub>: a common-mode step adds the same to both and cancels &nbsp;·&nbsp; I<sub>CM</sub> ≈ C<sub>barrier</sub> × dV/dt",
          eqn: `about 1 pF × ${v.slope} kV/µs ≈ ${v.slope} mA per line (est) · rating ${r} kV/µs → ${ok ? "inside the rating" : "above the rating: a wrong output pulse is possible"}`,
          html: simp("the carrier, the burst shapes and the barrier capacitance are drawn for clarity, not to scale; the real carrier is an RF signal in the GHz range (the Si86SW options move it away from Wi-Fi and DECT, AN1359). Which input level sends the carrier is set by the default-output option, so 'no carrier' reads as the default.")
            + more(PK.iso, PK.gd, ["CMTI against the switching edge", "#cmti"], ["CMTI guide", "/engineering/cmti_kv_us"]),
          note: "CMTI ratings from the Part knowledge page (AN1359 p. 17): Si86xx above 35 kV/µs, Si86Sx above 100 kV/µs, 150 kV/µs with the deglitch option. A transient above the rating does not always cause an error, but it is no longer guaranteed.",
        };
      },
      related: [["CMTI against the switching edge", "#cmti"], ["Gate driver and bootstrap", "#bootstrap"], ["Isolated current sensing", "#isosense"]],
    }, {
      id: "ook", label: "Capacitive digital isolator with on-off keyed carrier on a differential pair", flags: {power: true},
      phases: (st, v) => BITS.map(b => ({label: `IN = ${b} → carrier ${carrierOn(b, st, v) ? "on" : "off"}`, dur: 1.4})),
      tick(st, dt, v, go) {
        st.tp += dt / 1.4;
        if (st.tp >= 1) go((st.i + 1) % BITS.length);
        if (st.cm) { st.cm.q += dt / 1.8; if (st.cm.q >= 1) st.cm = null; }
      },
      step(st, v, go) {
        if (st.cm) { st.cm.q += 0.34; if (st.cm.q >= 1) st.cm = null; return; }
        go((st.i + 1) % BITS.length);
        st.tp = 0.5;
      },
      buttons: [
        {k: "cm", label: () => "Common-mode transient ⚡", click(st) { st.cm = {q: st.playing ? 0 : 0.2, at: (st.i + st.tp) / BITS.length}; }},
        {k: "power", label: st => (st.flags.power ? "Side 1 power: on" : "Side 1 power: off"), pressed: st => !st.flags.power, click(st) { st.flags.power = !st.flags.power; }},
      ],
      draw(st, F, v) {
        const bit = BITS[st.i], on = carrierOn(bit, st, v), cm = st.cm, q = cm ? cm.q : 0, glitch = cm && v.slope > CMTI[v.part] && q > 0.1 && q < 0.35;
        const lvl = outLevel(bit, st, v), outShown = st.tp < 0.12 ? outLevel(BITS[(st.i + 7) % 8], st, v) : lvl, out = glitch ? 1 - outShown : outShown;
        const dy = cm ? -16 * Math.min(1, q / 0.25) : 0;
        let s = box(30, 60, 290, 230, "cf-die") + `<g transform="translate(0 ${dy.toFixed(1)})">${box(400, 60, 290, 230, `cf-die${cm ? " cf-jump" : ""}`)}</g>`;
        s += txt(40, 80, "Side 1 die (input)", "start", "cf-t cf-b") + txt(680, 80 + dy, "Side 2 die (output)", "end", "cf-t cf-b");
        s += wire("M14 180H90") + txt(14, 172, "IN", "start", "cf-ts cf-b") + box(90, 128, 120, 104) + txt(150, 170, "oscillator", "middle", "cf-ts cf-b") + txt(150, 184, "+ on-off", "middle", "cf-ts")
          + txt(150, 198, "switch", "middle", "cf-ts");
        for (const [y, n] of [[150, "P"], [210, "N"]]) {
          s += wire(`M210 ${y}H292`) + capH(292, 300, y) + wire(`M300 ${y}H320`) + `<path d="M320 ${y}C345 ${y - 22} 375 ${y - 22 + dy} 400 ${y + dy}" class="cf-w cf-bond"/>`
            + `<g transform="translate(0 ${dy.toFixed(1)})">${wire(`M400 ${y}H420`) + capH(420, 428, y) + wire(`M428 ${y}H490`)}</g>` + txt(232, y - 8, n, "middle", "cf-ts cf-b");
        }
        s += `<g transform="translate(0 ${dy.toFixed(1)})">${box(490, 128, 120, 104) + txt(550, 170, "detector", "middle", "cf-ts cf-b") + txt(550, 184, "P − N", "middle", "cf-ts")
          + txt(550, 198, "+ comparator", "middle", "cf-ts") + wire("M610 180H704") + txt(704, 172, "OUT", "end", "cf-ts cf-b")
          + `<g class="cf-badge${glitch ? " bad" : ""}"><rect x="622" y="194" width="60" height="18" rx="4"/>${txt(652, 207, `OUT ${out}`, "middle", "cf-ts cf-b")}</g>`
          + wire("M545 290V318") + gnd(545, 318) + txt(560, 312, cm ? "GND2 jumps" : "GND2", "start", "cf-ts")}</g>`;
        s += wire("M175 290V318") + gnd(175, 318) + txt(190, 312, "GND1", "start", "cf-ts") + txt(360, 112, "SiO2 barrier", "middle", "cf-ts cf-b") + txt(360, 254, "2 capacitors", "middle", "cf-ts")
          + txt(360, 267, "in series per line", "middle", "cf-ts") + `<path d="M360 120V240" class="cf-barrier"/>`;
        s += `<g class="cf-badge"><rect x="40" y="250" width="64" height="18" rx="4"/>${txt(72, 263, `IN ${bit}`, "middle", "cf-ts cf-b")}</g>`
          + txt(110, 282, st.flags.power ? "VDD1 on" : "VDD1 OFF: no carrier", "start", `cf-ts cf-b${st.flags.power ? "" : " cf-fc5"}`);
        // carrier: an RF burst on P and its mirror image on N, moving to the right
        if (on) {
          for (const [y, sg, c] of [[150, 1, 1], [210, -1, 2]]) {
            let d = "";
            for (let xx = 210; xx <= 490; xx += 3) { const yy = y + sg * 7 * Math.sin(xx / 6 - st.t * 9) + (xx > 400 ? dy : 0); d += `${xx === 210 ? "M" : "L"}${xx} ${yy.toFixed(1)}`; }
            s += `<path d="${d}" class="cf-carrier cf-c${c}" data-k="car${c}"/>`;
          }
        }
        if (cm && q < 0.7) {
          const sp = 2.5 * (1 - q / 0.7);
          s += F("cmP", `M428 ${150 + dy}H400M320 150H210`, sp, 5) + F("cmN", `M428 ${210 + dy}H400M320 210H210`, sp, 5)
            + tag(470, 244 + dy, glitch ? ["above the CMTI rating:", "a short wrong pulse"] : ["same on P and N:", "P − N cancels it"], 5, "cf-pop");
        }
        // waveform over the 8 bits
        const N = BITS.length, pts = {in: [], car: [], out: [], cmv: []};
        for (let j = 0; j <= N * 60; j++) {
          const x = j / (N * 60), b = BITS[Math.min(N - 1, Math.floor(x * N))], pb = BITS[(Math.floor(x * N) + N - 1) % N], fr = (x * N) % 1;
          pts.in.push([x, b]);
          pts.car.push([x, carrierOn(b, st, v) ? Math.sin(j * 1.1) * 0.9 : 0]);
          pts.out.push([x, fr < 0.12 ? outLevel(pb, st, v) : outLevel(b, st, v)]);
          pts.cmv.push([x, cm && x >= cm.at ? Math.min(1, (x - cm.at) * 40) : 0]);
        }
        const wave = waveSvg([
          {label: "IN (logic)", lo: -0.2, hi: 1.2, series: [{pts: pts.in, c: 4}]},
          {label: "Carrier on P", lo: -1.1, hi: 1.1, zero: 0, series: [{pts: pts.car, c: 1}]},
          {label: "OUT (logic)", lo: -0.2, hi: 1.2, series: [{pts: pts.out, c: 3}]},
          {label: "GND2 − GND1", lo: -0.1, hi: 1.2, series: [{pts: pts.cmv, c: 5}]},
        ], {label: "Input, carrier, output and the common-mode step over eight bits", cursor: (st.i + st.tp) / N, rowH: 26, foot: "eight bits; the output follows after a short delay"});
        const cap = cm ? (glitch ? "The common-mode edge is steeper than the part's CMTI rating: the two lines no longer cancel perfectly and the output can show a short wrong pulse."
          : "The ground of side 2 jumps. Current flows through the barrier capacitors (red), but equally on P and N, so the detector (P − N) does not see it and the output stays as it was.")
          : !st.flags.power ? `Side 1 has no power, so there is no carrier: the output goes to its default state (${v.def === "high" ? "high" : "low"}), set by the part number option.`
          : on ? "Carrier on: the RF burst crosses the two series capacitors on each line, in opposite phase on P and N. The detector senses the energy and sets the output."
          : "Carrier off: nothing crosses the barrier and the detector sees no energy, so the output takes the other logic level.";
        return {svg: s, h: 340, wave, cap, legend: [[1, "Carrier on line P"], [2, "Carrier on line N (mirror image)"], [5, "Common-mode current at the transient"]]};
      },
    });
  });
})();
