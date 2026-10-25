// Interactive visual "UWB: power limit, range, time of flight, relay attacks and the first path" (owner, 23 Oct 2026:
// "equations and calculations related to UWB ... safety requirements, range ... keyless entry, path and measurement").
// Registers with the visuals engine in visuals.js (window.VZ_ADD); textbook equations, limits from ETSI EN 302 065-3-1
// as summarised in the Systems library topic auto_uwb. Our own simplifications are marked est on the page.
(window.VZ_ADD = window.VZ_ADD || []).push(({V, C, num, si, log10, esc, range, bandText}) => {
  const c0 = 299792458, BW = 499.2;  // m/s; HRP UWB channel 5 and 9 bandwidth in MHz
  const FC = {"5": 6489.6, "9": 7987.2};  // channel centre frequencies (MHz)
  const PSD = -41.3, PEAK_PSD = 0 - 10 * log10(50);  // mean dBm/MHz; 0 dBm peak in 50 MHz as dBm/MHz
  const ETSI_SENS = -111.3;  // dBm/MHz receiver baseline sensitivity (auto_uwb d4)
  const RATES = [["110e3", "110 kb/s (long range)"], ["850e3", "850 kb/s"], ["6.8e6", "6.8 Mb/s (car keys, typical)"], ["27.2e6", "27.2 Mb/s"]];
  const mode = k => v => v.mode === k;
  const est = '<span class="kn-est" title="BizDev\'s own reasoning, not from a source">est</span>';
  const PARTS = [["QPF5100Q", "automotive UWB SoC"], ["DW3300Q", "automotive UWB SoC"], ["QM35825", "UWB SoC with radar"],
    ["QM14068", "bypass switch + LNA, 6.2–8.3 GHz"], ["QM14070", "PA with bypass, 6–9 GHz"], ["SKY5A2108", "SPDT switch to 8.3 GHz, AEC-Q100"]];
  const partsHtml = `<div class="vz-sugg small"><b>Our UWB parts</b> (catalogue search): ${PARTS.map(([p, d]) => `<a href="/find?q=${p}">${p}</a> <span class="muted">${esc(d)}</span>`).join(" · ")}
    <br>Design rules and sources: <a href="/library/auto_uwb">Systems library: Automotive UWB</a> · front end: <a href="/engineering/uwb_signal_path">UWB signal path: pulse fidelity, group delay ripple and linearity</a></div>`;

  // deterministic noise so the picture does not flicker while a slider moves
  const rnd = seed => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  // raised-cosine pulse (roll-off 0.6), unit peak, t in ns, B in MHz
  const pulse = (t, B) => {
    const x = t * B * 1e-3, b = 0.6, s = x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x), d = 1 - (2 * b * x) ** 2;
    return s * (Math.abs(d) < 1e-6 ? Math.PI / 4 : Math.cos(Math.PI * b * x) / d);
  };

  function rangeMode(v) {
    const fc = FC[v.ch], meanEirp = PSD + 10 * log10(BW);
    const boost = Math.max(0, Math.min(10 * log10(1000 / v.pkt), PEAK_PSD - PSD));
    const eirp = meanEirp + boost, rate = +v.rate;
    const sens = -174 + 10 * log10(rate) + v.nf + v.ebn0;
    const fspl1 = 20 * log10((4 * Math.PI * fc * 1e6) / c0);
    const lmax = eirp + v.gr - v.extra - sens, d = 10 ** ((lmax - fspl1) / (10 * v.n));
    const etsi = ETSI_SENS + 10 * log10(BW);
    const prx = x => eirp + v.gr - v.extra - fspl1 - 10 * v.n * log10(x), ds = range(0.3, 1000, 90, true);
    return {
      outputs: [["Mean e.i.r.p. limit (whole channel)", `${num(meanEirp)} dBm = ${si(10 ** (meanEirp / 10) * 1e-3, "W")}`],
        ["e.i.r.p. during a short packet (est)", `${num(eirp)} dBm (+${num(boost)} dB)`, boost > 0 ? "ok" : ""],
        ["Receiver sensitivity (est)", `${num(sens)} dBm`], ["ETSI baseline in 499.2 MHz", `${num(etsi)} dBm`, sens <= etsi ? "ok" : "bad"],
        ["Path loss allowed", `${num(lmax)} dB`], ["Range (est)", `${num(d)} m`, d >= 10 ? "ok" : d >= 3 ? "warn" : "bad"]],
      eq: "e.i.r.p.<sub>mean</sub> = −41.3 dBm/MHz + 10·log<sub>10</sub>(B / 1 MHz) &nbsp;·&nbsp; P<sub>rx</sub>(d) = e.i.r.p. + G<sub>rx</sub> − L<sub>body</sub> − FSPL(1 m) − 10·n·log<sub>10</sub>(d) &nbsp;·&nbsp; Sens = −174 dBm/Hz + 10·log<sub>10</sub>(R) + NF + E<sub>b</sub>/N<sub>0</sub>",
      eqn: `−41.3 + 10·log(${BW}) = ${num(meanEirp)} dBm · FSPL(1 m) at ${num(fc)} MHz = ${num(fspl1)} dB · Sens = −174 + ${num(10 * log10(rate))} + ${num(v.nf)} + ${num(v.ebn0)} = ${num(sens)} dBm · d = 10<sup>(${num(lmax)} − ${num(fspl1)}) / (10·${num(v.n)})</sup> = ${num(d)} m`,
      chart: {x: {min: 0.3, max: 1000, log: true, label: "Distance (m)"}, y: {min: -130, max: -20, label: "Received power (dBm, whole channel)"},
        series: [{pts: ds.map(x => [x, prx(x)]), width: 3, label: `with ${num(v.extra)} dB body / car loss`},
          {pts: ds.map(x => [x, prx(x) + v.extra]), color: C.grey, dash: "6 4", width: 2, label: "line of sight"}],
        hlines: [{y: sens, label: `sensitivity ${num(sens)} dBm`, color: C.orange}, {y: etsi, label: `ETSI baseline ${num(etsi)} dBm`, color: C.purple}],
        marks: [{x: d, y: sens, label: `range ≈ ${num(d)} m`}]},
      html: `<p class="small">Range comes from the receiver, the antennas and the number of anchors, not from transmit power: the limit is on the radiated density (−41.3 dBm/MHz mean, measured over 1 ms; 0 dBm peak in 50 MHz). A packet shorter than 1 ms may be sent proportionally louder until the peak limit stops it ${est}. Every dB of loss in front of the LNA (switch, filter, cable) adds to NF and costs range.</p>${partsHtml}`,
      note: "Rough planning numbers (est): the required Eb/N0 includes implementation loss and is not a data-sheet value; real ranges also depend on the antenna pattern, the phone in a pocket and the car body. ETSI baseline: −111.3 dBm/MHz at the receiver, 70 dB below the emission limit.",
    };
  }

  function tofMode(v) {
    const tof = v.dist / c0, B = v.bw * 1e6, snr = 10 ** (v.snr / 10), beta = B / Math.sqrt(12);
    const crlb = d => c0 / (2 * Math.PI * (d / Math.sqrt(12)) * Math.sqrt(2 * snr));
    const ss = (v.treply * 1e-6 * v.ppm * 1e-6) / 2 * c0, ds = v.dist * v.ppm * 1e-6;
    const bws = range(1, 2000, 80, true).map(x => x * 1e6);
    const sigma = c0 / (2 * Math.PI * beta * Math.sqrt(2 * snr)), res = c0 / B;
    return {
      outputs: [["Time of flight", si(tof, "s")], ["Rule of thumb", "1 ns ↔ 30 cm"],
        ["Single-sided TWR clock error", `${num(ss * 100)} cm`, ss > 0.3 ? "bad" : ss > 0.1 ? "warn" : "ok"],
        ["Double-sided TWR clock error (est)", `${num(ds * 1000)} mm`, "ok"],
        ["Best accuracy at this SNR (CRLB)", `${num(sigma * 100)} cm`], ["Paths closer than this merge", `${num(res * 100)} cm`]],
      eq: "d = c · ToF &nbsp;·&nbsp; SS-TWR: ToF = (T<sub>round</sub> − T<sub>reply</sub>) / 2, error ≈ T<sub>reply</sub> · Δppm / 2 &nbsp;·&nbsp; DS-TWR: ToF = (T<sub>r1</sub>T<sub>r2</sub> − T<sub>d1</sub>T<sub>d2</sub>) / (T<sub>r1</sub> + T<sub>r2</sub> + T<sub>d1</sub> + T<sub>d2</sub>) &nbsp;·&nbsp; σ<sub>d</sub> ≥ c / (2π β √(2·SNR)), β = B/√12",
      eqn: `ToF = ${num(v.dist)} m / c = ${si(tof, "s")} · SS-TWR error = ${num(v.treply)} µs × ${num(v.ppm)} ppm / 2 × c = ${num(ss * 100)} cm · σ<sub>d</sub> = c / (2π · ${si(beta, "Hz")} · √(2 · ${num(snr)})) = ${num(sigma * 100)} cm`,
      chart: {x: {min: 1, max: 2000, log: true, label: "Signal bandwidth (MHz)"}, y: {min: 0.001, max: 1000, log: true, label: "Distance (m)"},
        series: [{pts: bws.map(b => [b / 1e6, crlb(b)]), width: 3, label: "best accuracy (CRLB)"}, {pts: bws.map(b => [b / 1e6, c0 / b]), color: C.orange, dash: "6 4", width: 2, label: "multipath resolution c/B"}],
        vlines: [{x: 2, label: "BLE 2 MHz"}, {x: 160, label: "Wi-Fi 160 MHz", row: 1}, {x: 499.2, label: "UWB 499.2 MHz", color: C.blue, row: 2}],
        marks: [{x: v.bw, y: sigma, label: `${num(sigma * 100)} cm`}]},
      html: `<p class="small">Two-way ranging: the car sends a poll, the key answers after a known reply time, and the car halves the rest of the round trip. Each side's crystal is a few ppm off, so a single exchange with a long reply time is off by tens of centimetres; double-sided ranging (three messages) cancels the clock error to first order. Wide bandwidth gives sharp pulses: that is why UWB measures to about 10 cm where signal-strength methods (BLE, LF) are off by metres.</p>${partsHtml}`,
      note: "The CRLB is the best case for one clean path; multipath and a weak first path make real errors larger (see the First path mode). Flat spectrum assumed for the RMS bandwidth β (est). Clock offsets: up to ±20 ppm crystals are common; the SoC measures and corrects part of it.",
    };
  }

  function relayMode(v) {
    const apparent = v.dkey + v.detour + (c0 * v.rdelay * 1e-9);
    const advance = Math.max(0, (apparent - v.unlock) / c0);
    const uwbOpen = apparent <= v.unlock;
    return {
      outputs: [["Key's real distance", `${num(v.dkey)} m`], ["Signal-strength key, relayed", "looks ≈ 1 m: unlocks", "bad"],
        ["UWB distance seen through the relay", `${num(apparent)} m`, uwbOpen ? "bad" : "ok"], ["UWB decision", uwbOpen ? "unlocks" : "stays locked", uwbOpen ? "bad" : "ok"],
        ["Time an attacker would have to gain", si(advance, "s")], ["Guessing the STS (FiRa high security)", "1 in 2⁴⁸ per try"]],
      eq: "d<sub>measured</sub> = c · (T<sub>round</sub> − T<sub>reply</sub>) / 2 = d<sub>path</sub> + c · t<sub>relay</sub> ≥ d<sub>real</sub> &nbsp;·&nbsp; unlock only if d<sub>measured</sub> ≤ d<sub>unlock</sub>",
      eqn: `${num(v.dkey)} m + ${num(v.detour)} m detour + c × ${num(v.rdelay)} ns = ${num(apparent)} m ${uwbOpen ? "≤" : ">"} ${num(v.unlock)} m`,
      bars: [{label: "Real distance", value: v.dkey, color: C.grey, text: `${num(v.dkey)} m`},
        {label: "Signal-strength key", value: 1, color: C.red, text: "≈ 1 m (relay restores the level)"},
        {label: "UWB time of flight", value: apparent, color: uwbOpen ? C.red : C.green, text: `${num(apparent)} m`},
        {label: "Unlock distance", value: v.unlock, color: C.orange, text: `${num(v.unlock)} m`}],
      html: `<p class="small"><b>Why UWB keys resist relay attacks.</b> A passive-entry key that is judged by signal strength can be relayed: one box near the car, one near the key at home, and the car hears a strong signal and opens. With UWB the car measures time; nothing travels faster than light, and every relay adds cable, air path and processing delay, so a relay can only make the key look <i>further</i> away. This is distance bounding. The remaining attack is to fake an <i>early</i> first path; the scrambled timestamp sequence (STS, 802.15.4z) is a secret random pulse pattern, so the attacker would have to guess it, and the receiver must check the first-path candidate against it (library rule d11). ${est} for the 1 m figure of a relayed signal-strength key.</p>${partsHtml}`,
      note: "Distance bounding gives an upper bound on how close the key can be. It holds only if the receiver does not accept a fake early peak: front-end pre-echo from group-delay ripple, or a simple threshold detector, can create one (see First path in multipath).",
    };
  }

  function pathMode(v) {
    const t0 = 20, B = v.bw, fc = 8e9;
    const paths = [{t: t0, a: 10 ** (-v.att / 20)}, {t: t0 + v.dly, a: 1}, {t: t0 + v.dly + 5, a: 0.5}, {t: t0 + v.dly + 11, a: 0.3}];
    const b = v.gd * (v.gdp / 1000), T = 1000 / v.gdp;  // phase ripple amplitude (rad) and echo spacing (ns)
    const taps = [];
    for (const p of paths) {
      const ph = -2 * Math.PI * fc * p.t * 1e-9;
      taps.push({t: p.t, re: p.a * Math.cos(ph), im: p.a * Math.sin(ph)});
      if (b > 0) for (const [s, k] of [[-1, -1], [1, 1]]) taps.push({t: p.t + s * T, re: (k * b / 2) * p.a * Math.cos(ph), im: (k * b / 2) * p.a * Math.sin(ph)});
    }
    const ts = range(0, 60, 601), r = rnd(7), nl = 10 ** (-v.snr / 20);
    const noise = ts.map(() => { const u = Math.max(1e-9, r()), w = r(); const m = nl * Math.sqrt(-Math.log(u)); return [m * Math.cos(2 * Math.PI * w), m * Math.sin(2 * Math.PI * w)]; });
    const mag = ts.map((t, i) => { let re = noise[i][0], im = noise[i][1]; for (const q of taps) { const p = pulse(t - q.t, B); re += q.re * p; im += q.im * p; } return Math.hypot(re, im); });
    const peak = Math.max(...mag), dbv = mag.map(m => 20 * log10(m / peak));
    const thr = Math.max(-v.thr, -v.snr + 8);
    let i = dbv.findIndex(x => x >= thr), det = NaN;
    if (i >= 0) { const w = Math.ceil(1000 / B / 0.1); let j = i; for (let k = i; k < Math.min(ts.length, i + w); k++) if (mag[k] > mag[j]) j = k; det = ts[j]; }
    const err = (det - t0) * 1e-9 * c0;
    const tone = !isFinite(err) ? "bad" : err < -0.3 ? "bad" : err > 0.3 ? "warn" : "ok";
    const verdict = !isFinite(err) ? "nothing above the threshold" : err < -0.3 ? "too early: shorter distance, a security risk" : err > 0.3 ? "too late: first path missed, range too long" : "first path found";
    const echoDb = b > 0 ? 20 * log10(b / 2) : -Infinity;
    return {
      outputs: [["Detected first path", isFinite(det) ? `${num(det)} ns` : "–"], ["True first path", `${t0} ns (6 m)`],
        ["Ranging error", isFinite(err) ? `${err >= 0 ? "+" : ""}${num(err * 100)} cm` : "–", tone], ["Result", verdict, tone],
        ["Pulse width ≈ 1/B", `${num(1000 / B)} ns = ${num(c0 / (B * 1e6) * 100)} cm`],
        ["Pre-echo from group-delay ripple", b > 0 ? `${num(echoDb)} dB, ${num(T)} ns early` : "none"]],
      eq: "first path = first peak above the threshold, searched from the start of the window &nbsp;·&nbsp; group-delay ripple ΔGD (peak) with period f<sub>p</sub> across frequency → phase ripple b = ΔGD·f<sub>p</sub> → echoes of size b/2 at ±1/f<sub>p</sub>",
      eqn: `b = ${num(v.gd)} ns × ${num(v.gdp)} MHz = ${num(b)} rad → echo ${b > 0 ? num(echoDb) + " dB" : "none"} at ±${num(T)} ns · threshold ${num(thr)} dB below the peak · error = (${isFinite(det) ? num(det) : "–"} − ${t0}) ns × c`,
      chart: {x: {min: 0, max: 60, label: "Time (ns); 1 ns = 30 cm"}, y: {min: -50, max: 2, label: "Channel impulse response (dB below peak)"},
        series: [{pts: ts.map((t, k) => [t, dbv[k]]), width: 2}],
        hlines: [{y: thr, label: `threshold ${num(thr)} dB`, color: C.orange}, {y: -v.snr, label: "noise", color: C.grey}],
        vlines: [{x: t0, label: "true first path", color: C.green}, ...(isFinite(det) ? [{x: det, label: "detected", color: tone === "ok" ? C.blue : C.red, row: 1}] : [])]},
      html: `<p class="small">In a car the direct path to the key often goes through a body or a seat and arrives weaker than a reflection off the roof or a door. The receiver must find the <i>first</i> path, not the strongest. Narrow bandwidth smears the pulses together, so the first path is lost and the distance comes out long. Ripple in the front end's group delay (switch, filter, LNA) adds small copies of every path before and after it; a pre-echo of the strong reflection that rises above the threshold makes the key look closer than it is. The owner's point: keep the TX/RX chain phase-linear and uncompressed so the weak first tap is not buried ${est}.</p>${partsHtml}`,
      note: "Illustration with a raised-cosine pulse, four paths and fixed noise (est). Real receivers validate the first path against the STS and use adaptive thresholds; the point is the trend: bandwidth, first-path strength and front-end ripple decide whether the first path is found.",
    };
  }

  V.push({
    id: "uwb", group: "UWB", title: "UWB: power limit, range, time of flight, relay and first path",
    explains: [["UWB and low-power wireless", "/knowledge#p-uwb"], ["Systems library: Automotive UWB", "/library/auto_uwb"], ["UWB signal path note", "/engineering/uwb_signal_path"]],
    physics: [["Antennas and wavelength", "phys_antennas_wavelength"], ["Gain and noise", "phys_noise_gain"]],
    lead: "UWB car keys in four steps: how much power the rules allow and what range it gives, how time of flight becomes distance, why a relay attack fails, and how the receiver finds the first path among reflections.",
    controls: [
      {k: "mode", label: "Topic", type: "select", options: [["range", "Power limit, link budget and range"], ["tof", "Time of flight and two-way ranging"], ["relay", "Relay attack and distance bounding"], ["path", "First path in multipath"]], value: "range"},
      {k: "ch", label: "UWB channel", type: "select", options: [["9", `Channel 9: ${bandText("uwb9") || "7738–8237 MHz"} (centre 7987.2, global)`], ["5", `Channel 5: ${bandText("uwb5") || "6240–6739 MHz"} (centre 6489.6)`]], value: "9", when: mode("range")},
      {k: "pkt", label: "Packet length", min: 50, max: 2000, value: 200, unit: "µs", log: true, when: mode("range")},
      {k: "rate", label: "Data rate", type: "select", options: RATES, value: "6.8e6", when: mode("range")},
      {k: "nf", label: "Receiver noise figure (incl. front-end loss)", min: 2, max: 14, step: 0.5, value: 7, unit: "dB", when: mode("range")},
      {k: "ebn0", label: "Required Eb/N0 incl. losses (est)", min: 4, max: 20, step: 0.5, value: 12, unit: "dB", when: mode("range")},
      {k: "gr", label: "RX antenna gain", min: -10, max: 6, step: 0.5, value: 0, unit: "dBi", when: mode("range")},
      {k: "extra", label: "Body, pocket or car loss", min: 0, max: 35, step: 1, value: 6, unit: "dB", when: mode("range")},
      {k: "n", label: "Path-loss exponent (2 = free space)", min: 1.6, max: 3.5, step: 0.1, value: 2, when: mode("range")},
      {k: "dist", label: "Distance key to anchor", min: 0.1, max: 100, value: 5, unit: "m", log: true, when: mode("tof")},
      {k: "treply", label: "Reply time", min: 50, max: 5000, value: 300, unit: "µs", log: true, when: mode("tof")},
      {k: "ppm", label: "Clock offset between the two ends", min: 0, max: 40, step: 0.5, value: 10, unit: "ppm", when: mode("tof")},
      {k: "snr", label: "First-path SNR", min: 0, max: 40, step: 1, value: 20, unit: "dB", when: mode("tof")},
      {k: "bw", label: "Signal bandwidth", min: 1, max: 2000, value: 499.2, unit: "MHz", log: true, when: mode("tof")},
      {k: "dkey", label: "Key's real distance (at home)", min: 3, max: 200, value: 30, unit: "m", log: true, when: mode("relay")},
      {k: "detour", label: "Relay detour (extra path)", min: 0, max: 50, step: 1, value: 5, unit: "m", when: mode("relay")},
      {k: "rdelay", label: "Relay processing delay", min: 0, max: 500, step: 5, value: 50, unit: "ns", when: mode("relay")},
      {k: "unlock", label: "Unlock distance", min: 0.5, max: 5, step: 0.1, value: 2, unit: "m", when: mode("relay")},
    ],
    compute(v) {
      if (v.mode === "tof") return tofMode(v);
      if (v.mode === "relay") return relayMode(v);
      if (v.mode === "path") return pathMode({...v, bw: v.bwp, snr: v.psnr});
      return rangeMode(v);
    },
    related: [["Link budget and range", "#link"], ["Cascaded noise figure", "#nf"], ["RF bands chart (UWB channels)", "/rf-bands"]],
  });
  // first-path controls (own keys so the modes keep separate defaults)
  const u = V[V.length - 1];
  u.controls.push(
    {k: "bwp", label: "Signal bandwidth", min: 50, max: 1500, value: 499.2, unit: "MHz", log: true, when: mode("path")},
    {k: "att", label: "First path below the strongest", min: 0, max: 25, step: 0.5, value: 10, unit: "dB", when: mode("path")},
    {k: "dly", label: "Strongest reflection after the first path", min: 0.5, max: 20, step: 0.1, value: 3, unit: "ns", when: mode("path")},
    {k: "psnr", label: "Peak SNR (noise below the strongest path)", min: 10, max: 50, step: 1, value: 35, unit: "dB", when: mode("path")},
    {k: "thr", label: "Detection threshold below the peak", min: 6, max: 40, step: 1, value: 20, unit: "dB", when: mode("path")},
    {k: "gd", label: "Front-end group-delay ripple (peak)", min: 0, max: 2, step: 0.05, value: 0, unit: "ns", when: mode("path")},
    {k: "gdp", label: "Ripple period across frequency", min: 50, max: 500, step: 10, value: 100, unit: "MHz", when: mode("path")},
  );
});
