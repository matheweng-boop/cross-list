// Interactive visual "Three-step turn-on: overshoot, ringing, EMI and the filter" (owner, 23 Oct 2026, isolation and
// power: "model a multi-phase turn-on that can be shaped in 3 steps, allowing through different currents at the dv/dt
// stages, and estimate the overshoot and ring, the expected EMI emissions and the filter required"). Registers with the
// visuals engine in visuals.js (window.VZ_ADD). A teaching model, all results est: gate charge in three current steps,
// a series RLC for the power loop, the trapezoid spectrum envelope and a common-mode coupling path to the network.
(window.VZ_ADD = window.VZ_ADD || []).push(({V, C, num, si, log10, range}) => {
  const est = '<span class="kn-est" title="BizDev\'s own reasoning, not from a source">est</span>';
  const dBuV = v => 20 * log10(Math.max(v, 1e-12) / 1e-6);
  // CISPR 25 conducted-voltage limit bands (MHz, dBµV), class 5 peak, approximate reference (est); classes step ~6 dB
  const C25 = [[0.15, 0.3, 70, "LW"], [0.53, 1.8, 54, "MW"], [5.9, 6.2, 53, "SW"], [26, 28, 44, "CB"], [30, 54, 44, "VHF"], [68, 87, 39, "VHF"], [76, 108, 38, "FM"]];
  const VIEW = k => v => v.view === k;

  function model(v) {
    const t1 = (v.ciss * 1e-9 * (v.vth - v.voff)) / v.i1, t2 = (v.ciss * 1e-9 * (v.vpl - v.vth)) / v.i2, t3 = (v.qgd * 1e-9) / v.i3;
    const t4 = (v.ciss * 1e-9 * (v.von - v.vpl)) / v.i3;  // after the plateau the third step finishes the gate
    const L = v.lloop * 1e-9, Co = v.coss * 1e-12, R = v.rloop;
    const w0 = 1 / Math.sqrt(L * Co), f0 = w0 / (2 * Math.PI), zeta = (R / 2) * Math.sqrt(Co / L);
    const didt = (v.iload / t2), dvdt = v.vbus / t3, dip = L * didt;
    // simulate: the switch forces the node from 0 to Vbus during t3; the loop L, R rings with the opposite device's Coss
    const tEnd = t1 + t2 + t3 + Math.max(8 / f0, 3 * t3), dt = Math.max(tEnd / 2e5, Math.min(1 / (f0 * 300), t3 / 200, 0.05e-9));
    let i = 0, vc = 0, maxV = 0, maxI = 0;
    const pts = {vds: [], vop: [], id: [], ig: []}, every = Math.max(1, Math.round(tEnd / dt / 500));
    for (let k = 0, t = 0; t <= tEnd; k++, t += dt) {
      const ts = t - t1 - t2, vs = ts <= 0 ? 0 : ts >= t3 ? v.vbus : (v.vbus * ts) / t3;
      const di = (vs - vc - R * i) / L;
      i += di * dt; vc += (i / Co) * dt;
      maxV = Math.max(maxV, vc); maxI = Math.max(maxI, i);
      if (k % every) continue;
      const iload = t < t1 ? 0 : t < t1 + t2 ? (v.iload * (t - t1)) / t2 : v.iload;
      const vds = t < t1 ? v.vbus : t < t1 + t2 ? v.vbus - dip : Math.max(0, v.vbus - vs);
      const ig = t < t1 ? v.i1 : t < t1 + t2 ? v.i2 : t < t1 + t2 + t3 + t4 ? v.i3 : 0;
      const tn = t * 1e9;
      pts.vds.push([tn, (100 * vds) / v.vbus]); pts.vop.push([tn, (100 * vc) / v.vbus]);
      pts.id.push([tn, (100 * (iload + (ts > 0 ? i : 0))) / v.iload]); pts.ig.push([tn, (100 * ig) / Math.max(v.i1, v.i2, v.i3)]);
    }
    const over = Math.max(0, maxV - v.vbus);
    const eon = 0.5 * v.vbus * v.iload * (t2 + t3);
    return {t1, t2, t3, t4, f0, zeta, didt, dvdt, dip, over, maxI, eon, pts, tEnd};
  }

  function spectrum(v, m) {
    const T = 1 / (v.fsw * 1e3), D = 0.5, A = v.vbus;
    const f1 = 1 / (Math.PI * D * T), f2 = 1 / (Math.PI * m.t3);
    const ringC = m.over > 0 ? (m.over * v.fsw * 1e3) / (m.zeta * 2 * Math.PI * m.f0) : 0;  // est line level of the ring
    const fs = range(0.15e6, 200e6, 160, true);
    const sw = f => {
      const env = 2 * A * D * Math.min(1, f1 / f) * Math.min(1, f2 / f);
      const ring = ringC / Math.sqrt(1 + ((f - m.f0) / (m.zeta * m.f0)) ** 2);
      return Math.hypot(env, ring);
    };
    const couple = f => Math.min(1, 2 * Math.PI * f * v.cp * 1e-12 * 25);  // common-mode current into 2 x 50 Ω networks
    const at = f => dBuV(sw(f) * couple(f));
    const off = (5 - +v.cls) * 6;
    const lim = f => { const b = C25.find(([a, z]) => f / 1e6 >= a && f / 1e6 <= z); return b ? b[2] + off : null; };
    // the main LC filter is sized below 30 MHz; above it, parasitics limit any filter and the ring is fixed at the source
    let need = 0, worst = null, hf = 0, hfAt = null;
    for (const f of fs) {
      const l = lim(f); if (l == null) continue;
      const r = at(f) - l + v.margin;
      if (f <= 30e6 && r > need) { need = r; worst = f; }
      if (f > 30e6 && r > hf) { hf = r; hfAt = f; }
    }
    // smallest corner frequency an LC (-40 dB/dec) or two-stage (-80 dB/dec) filter needs to meet every band
    let fc1 = Infinity, fc2 = Infinity;
    for (const f of fs) { const l = lim(f); if (l == null || f > 30e6) continue; const r = at(f) - l + v.margin; if (r <= 0) continue; fc1 = Math.min(fc1, f / 10 ** (r / 40)); fc2 = Math.min(fc2, f / 10 ** (r / 80)); }
    const Lfor = fc => 1 / ((2 * Math.PI * fc) ** 2 * v.cy * 1e-9);
    return {fs, sw, at, lim, off, need, worst, hf, hfAt, fc1, fc2, Lfor, f1, f2};
  }

  V.push({
    id: "turnon", group: "Isolation and power", title: "Three-step turn-on: overshoot, ringing, EMI and the filter",
    explains: [["Isolated gate drivers", "/knowledge#p-gate_drivers"], ["Si829x programmable current drive", "/find?q=Si829"], ["EMC note", "/engineering/emc_eft_cispr"]],
    physics: [["Switching losses", "phys_switching_losses"], ["Inductors, capacitors and stored energy", "phys_lc_energy"]],
    lead: "Shape the turn-on of a SiC or IGBT switch in three steps with three gate currents: a fast step to the threshold, a softer one while the current rises (di/dt) and another while the voltage falls (dv/dt). See the overshoot and ringing of the power loop, the emissions spectrum it causes and the filter needed to meet a CISPR 25 class. All numbers are estimates (est).",
    presets: [
      {label: "One fixed current (like a gate resistor)", values: {i1: 2, i2: 2, i3: 2}, note: "Same current in all three steps: slow to the threshold, fast edges after it. This is what a fixed gate resistor roughly does."},
      {label: "Fast delay, soft di/dt, medium dv/dt", values: {i1: 10, i2: 1.5, i3: 2.5}, note: "A strong first step cuts the delay; a gentle di/dt step limits the voltage dip and the diode's recovery; the dv/dt step sets the edge that drives EMI."},
      {label: "Low EMI (soft dv/dt)", values: {i1: 10, i2: 2, i3: 0.8}, note: "A slow voltage edge pushes the second spectrum corner down and shrinks the ring, at the cost of more turn-on loss."},
    ],
    presetLabel: "Drive profiles",
    controls: [
      {k: "view", label: "Show", type: "select", options: [["wave", "Turn-on waveforms"], ["emi", "Emissions spectrum and filter"]], value: "wave"},
      {k: "i1", label: "Step 1 gate current (to threshold)", min: 0.2, max: 15, step: 0.1, value: 10, unit: "A"},
      {k: "i2", label: "Step 2 gate current (current rise, di/dt)", min: 0.2, max: 15, step: 0.1, value: 2, unit: "A"},
      {k: "i3", label: "Step 3 gate current (voltage fall, dv/dt)", min: 0.2, max: 15, step: 0.1, value: 1.5, unit: "A"},
      {k: "vbus", label: "DC bus voltage", min: 50, max: 1000, step: 10, value: 800, unit: "V"},
      {k: "iload", label: "Load current", min: 5, max: 600, step: 5, value: 100, unit: "A"},
      {k: "ciss", label: "Input capacitance Ciss", min: 0.5, max: 60, value: 5, unit: "nF", log: true},
      {k: "qgd", label: "Miller charge Qgd", min: 5, max: 500, value: 40, unit: "nC", log: true},
      {k: "lloop", label: "Power-loop inductance", min: 2, max: 100, value: 20, unit: "nH", log: true},
      {k: "coss", label: "Opposite switch Coss", min: 50, max: 3000, value: 300, unit: "pF", log: true},
      {k: "rloop", label: "Loop resistance (damping)", min: 0.05, max: 5, value: 0.5, unit: "Ω", log: true},
      {k: "fsw", label: "Switching frequency", min: 5, max: 500, value: 100, unit: "kHz", log: true, when: VIEW("emi")},
      {k: "cp", label: "Switch node to chassis (heatsink)", min: 10, max: 1000, value: 100, unit: "pF", log: true, when: VIEW("emi")},
      {k: "cls", label: "CISPR 25 class (reference)", type: "select", options: [["5", "Class 5 (strictest)"], ["4", "Class 4"], ["3", "Class 3"], ["2", "Class 2"], ["1", "Class 1"]], value: "5", when: VIEW("emi")},
      {k: "margin", label: "Design margin", min: 0, max: 12, step: 1, value: 6, unit: "dB", when: VIEW("emi")},
      {k: "cy", label: "Y capacitor per line (filter)", min: 1, max: 100, value: 4.7, unit: "nF", log: true, when: VIEW("emi")},
    ],
    compute(v) {
      const m = model({...v, voff: -4, vth: 3.5, vpl: 9, von: 18});
      const ovTone = m.over > 0.2 * v.vbus ? "bad" : m.over > 0.1 * v.vbus ? "warn" : "ok";
      const common = [["Delay to threshold", si(m.t1, "s")], ["di/dt (step 2)", `${num(m.didt / 1e9)} A/ns`], ["dv/dt (step 3)", `${num(m.dvdt / 1e9)} V/ns`],
        ["Overshoot on the opposite switch", `${num(m.over)} V (${num((100 * m.over) / v.vbus)} %)`, ovTone], ["Ringing", `${si(m.f0, "Hz")}, ζ = ${num(m.zeta)}`], ["Turn-on energy", si(m.eon, "J")]];
      const parts = `<div class="vz-sugg small"><b>Our drivers:</b> <a href="/find?q=Si829">Si829x</a> sets the gate current in steps (programmable current drive, 0–15 A, three phases of turn-on and turn-off, 125 kV/µs CMTI) instead of a fixed gate resistor; <a href="/find?q=Si828">Si828x</a> and <a href="/find?q=Si8239">Si8239x</a> have separate source and sink paths or outputs, so turn-on and turn-off can be set apart with resistors. Background: <a href="/engineering/emc_eft_cispr">EFT and CISPR on isolated designs</a> · <a href="/engineering/peak_source_a">Peak drive current</a> · <a href="/engineering/cmti_kv_us">CMTI</a>.</div>`;
      if (v.view === "emi") {
        const s = spectrum(v, m), clsOff = s.off, ok = s.need <= 0;
        const bands = C25.map(([a, z, l], i) => ({pts: [[a, l + clsOff], [z, l + clsOff]], color: C.red, width: 3, label: i === 0 ? `CISPR 25 cl. ${v.cls}` : ""}));
        const fl = f => (isFinite(s.fc1) ? Math.max(0, 40 * log10(f / s.fc1)) : 0);
        return {
          outputs: [["Spectrum corners", `${si(s.f1, "Hz")} and ${si(s.f2, "Hz")}`], ["Ring peak", si(m.f0, "Hz")],
            ["Excess below 30 MHz (incl. margin)", ok ? "none: meets it" : `${num(s.need)} dB at ${si(s.worst, "Hz")}`, ok ? "ok" : "bad"],
            ["Excess above 30 MHz", s.hf > 0 ? `${num(s.hf)} dB at ${si(s.hfAt, "Hz")}: fix at the source` : "none", s.hf > 0 ? "warn" : "ok"],
            ["LC filter (−40 dB/dec) corner", ok ? "no filter needed" : `≤ ${si(s.fc1, "Hz")}: L ≈ ${si(s.Lfor(s.fc1), "H")} with ${num(v.cy)} nF`],
            ["Two-stage filter (−80 dB/dec) corner", ok ? "–" : `≤ ${si(s.fc2, "Hz")}: L ≈ ${si(s.Lfor(s.fc2), "H")} per stage`]],
          eq: "f<sub>1</sub> = 1 / (π·D·T), f<sub>2</sub> = 1 / (π·t<sub>r</sub>); envelope = 2·V·D, −20 dB/dec above f<sub>1</sub>, −40 dB/dec above f<sub>2</sub> &nbsp;·&nbsp; V<sub>AN</sub> ≈ V<sub>sw</sub>(f) · 2πf·C<sub>p</sub>·25 Ω &nbsp;·&nbsp; filter: 40·log<sub>10</sub>(f / f<sub>c</sub>) ≥ excess + margin, f<sub>c</sub> = 1 / (2π√(LC))",
          eqn: `f<sub>1</sub> = 1 / (π · 0.5 · ${si(1 / (v.fsw * 1e3), "s")}) = ${si(s.f1, "Hz")} · f<sub>2</sub> = 1 / (π · ${si(m.t3, "s")}) = ${si(s.f2, "Hz")} · ${ok ? "meets the reference line" : `f<sub>c</sub> = ${si(s.worst, "Hz")} / 10<sup>${num(s.need)}/40</sup> → ${si(s.fc1, "Hz")}`}`,
          chart: {x: {min: 0.15, max: 200, log: true, label: "Frequency (MHz)"}, y: {min: 0, max: 160, label: "Conducted voltage at the network (dBµV)"},
            series: [{pts: s.fs.map(f => [f / 1e6, s.at(f)]), width: 2.5, label: "emission"},
              ...(ok ? [] : [{pts: s.fs.map(f => [f / 1e6, s.at(f) - fl(f)]), color: C.green, width: 2, dash: "6 4", label: "filtered"}]), ...bands],
            vlines: [{x: s.f2 / 1e6, label: "f₂ (edge)", color: C.grey}, {x: m.f0 / 1e6, label: "ring", color: C.orange, row: 1}]},
          html: `<p class="small">A slower voltage edge (lower step-3 current) moves f₂ down, so everything above it falls 40 dB per decade; less loop inductance or more damping moves and lowers the ring peak. The LC filter is sized from the bands below 30 MHz; above that its own parasitics limit it, so a ring peak there is fixed at the source: smaller loop, a snubber, softer step 3, ferrites ${est}. The filter has to make up whatever the edge shaping leaves. Common-mode current through the heatsink capacitance is the usual main path; the limit line is an approximate CISPR 25 conducted-voltage reference (class 5 peak, other classes about 6 dB per class) ${est}; check the standard and the test plan.</p>${parts}`,
          note: "Rough estimate (est): trapezoid envelope at 50 % duty, ringing as a damped resonance, common-mode coupling only, a single 50 Ω/5 µH network per line seen as 25 Ω. Real spectra need measurement; use it to compare drive profiles and to size a first filter.",
        };
      }
      const pts = m.pts;
      return {
        outputs: common,
        eq: "t<sub>1</sub> = C<sub>iss</sub>·(V<sub>th</sub> − V<sub>off</sub>) / I<sub>1</sub> &nbsp;·&nbsp; di/dt = I<sub>load</sub> / t<sub>2</sub>, t<sub>2</sub> = C<sub>iss</sub>·(V<sub>pl</sub> − V<sub>th</sub>) / I<sub>2</sub> &nbsp;·&nbsp; dv/dt = V<sub>bus</sub>·I<sub>3</sub> / Q<sub>gd</sub> &nbsp;·&nbsp; f<sub>ring</sub> = 1 / (2π√(L·C<sub>oss</sub>)), ζ = (R/2)·√(C<sub>oss</sub>/L)",
        eqn: `t<sub>1</sub> = ${num(v.ciss)} nF × 7.5 V / ${num(v.i1)} A = ${si(m.t1, "s")} · di/dt = ${num(v.iload)} A / ${si(m.t2, "s")} = ${num(m.didt / 1e9)} A/ns → L·di/dt = ${num(m.dip)} V dip · dv/dt = ${num(v.vbus)} V × ${num(v.i3)} A / ${num(v.qgd)} nC = ${num(m.dvdt / 1e9)} V/ns · f = ${si(m.f0, "Hz")}`,
        chart: {x: {min: 0, max: m.tEnd * 1e9, label: "Time (ns)"}, y: {min: -20, max: 180, label: "% of bus voltage / load current"},
          series: [{pts: pts.vds, color: C.blue, width: 2.5, label: "V sw"}, {pts: pts.vop, color: C.red, width: 2, label: "V opp"},
            {pts: pts.id, color: C.green, width: 2.5, label: "I d"}, {pts: pts.ig, color: C.grey, width: 1.5, dash: "4 3", label: "I gate"}],
          hlines: [{y: 100, color: C.grey}],
          vlines: [{x: m.t1 * 1e9, label: "1→2", color: C.purple}, {x: (m.t1 + m.t2) * 1e9, label: "2→3", color: C.purple, row: 1}]},
        html: `<p class="small">Step 1 charges the gate to the threshold: nothing happens in the power stage, so a high current here only shortens the delay. Step 2 sets how fast the load current moves over (di/dt): the loop inductance turns it into a voltage dip now and a recovery spike on the other switch. Step 3 runs through the Miller plateau and sets dv/dt: the edge that charges the opposite switch's Coss (the current hump), excites the L–Coss ringing and drives common-mode current into the heatsink, which is what CISPR measures. CMTI of the driver must exceed this dv/dt with margin.</p>${parts}`,
        note: "Teaching model (est): gate thresholds fixed at −4 V off, 3.5 V threshold, 9 V plateau, +18 V on; Ciss and Qgd taken as constants; no diode reverse recovery. Use it to compare profiles, then confirm with a double-pulse test.",
      };
    },
    related: [["Gate-drive current and power", "#gate"], ["CMTI against the switching edge", "#cmti"], ["Switching loss vs frequency", "#swloss"], ["EFT and CISPR what-if", "#emc"]],
  });
});
