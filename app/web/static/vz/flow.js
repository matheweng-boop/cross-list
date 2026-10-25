// Interactive visual "Signal flow: from the antenna to the audio" (owner, 25 Oct 2026: "Can you add a Signal Flow…
// RF Signal comes in what does it look like, and how does it change in each step until you get audio. Do the same for
// AM/FM"). Nine steps each for DAB, FM and AM; every step shows a spectrum and a time sketch and one sentence on what
// changed. The sketches are illustrative (plausible axes, made-up levels). Chip notes only repeat what the Skyworks
// data shorts / product briefs and the configurator data in data/broadcast/ say. Uses window.VZ_SKETCH (sketch.js).
(window.VZ_ADD = window.VZ_ADD || []).push(({V, C}) => {
  const {esc, lin, rnd, gauss, sumDb, brick, bell, spec, plot} = window.VZ_SKETCH;
  const find = m => [m, `/find?q=${encodeURIComponent(m)}`];
  const CFG = ["Radio configurator", "/broadcast/configurations/new"], FEAT = ["Tuner feature table", "/broadcast"];
  const RDS = ["RDS visual", "#rds"], ENS = ["DAB ensemble visual", "#dab"];
  const BLUE = C.blue, ORANGE = C.orange, GREEN = C.green, GREY = C.grey, RED = C.red, PURPLE = C.purple;

  // ------------------------------------------------------------------ signal pieces (seeded: same picture every time)
  const noisy = (pts, seed, amp = 1.2) => { const r = rnd(seed); return pts.map(([f, d]) => [f, d + gauss(r) * amp]); };
  const smoothNoise = (n, seed, k = 7) => {  // band-limited noise: a few random sines
    const r = rnd(seed), parts = Array.from({length: k}, () => [0.5 + r() * 6, r() * 6.28, 0.4 + r()]);
    return i => parts.reduce((a, [f, p, a0]) => a + a0 * Math.sin((2 * Math.PI * f * i) / n + p), 0) / Math.sqrt(k);
  };
  const music = t => 0.42 * Math.sin(2 * Math.PI * 0.44 * t) + 0.25 * Math.sin(2 * Math.PI * 1.1 * t + 1) + 0.13 * Math.sin(2 * Math.PI * 2.7 * t + 2) + 0.07 * Math.sin(2 * Math.PI * 5.3 * t);  // t in ms
  const tracks = (t0, t1, fns, n = 300) => fns.map(fn => lin(t0, t1, n).map(t => [t, fn(t)]));
  const musicSpec = (hi, seed) => noisy(spec(0, 20, f => (f < 0.05 ? -60 : f <= hi ? -12 - 9 * Math.log2(1 + f) : -12 - 9 * Math.log2(1 + f) - 60 * (f - hi))), seed, 1.5);

  const dabRf = (fc, gain, nf) => f => sumDb(brick(f, fc, 0.768, -75 + gain), brick(f, fc - 1.712, 0.768, -86 + gain), brick(f, fc + 1.712, 0.768, -66 + gain), brick(f, fc + 3.424, 0.768, -92 + gain), -108 + gain + nf);
  const dabBb = (filt, adc) => f => sumDb(brick(f, 0, 0.768, -30), brick(f, -1.712, 0.768, -41) - (filt ? 55 : 0), brick(f, 1.712, 0.768, -21) - (filt ? 55 : 0), adc ? -78 : -88);
  const fmRf = (fc, gain) => f => sumDb(bell(f, fc, 0.11, -68 + gain), bell(f, fc - 0.4, 0.11, -76 + gain), bell(f, fc + 0.4, 0.11, -52 + gain), bell(f, fc - 1.3, 0.11, -61 + gain), bell(f, fc + 1.1, 0.11, -80 + gain), -110 + gain + (gain ? 4 : 0));
  const fmBb = filt => f => sumDb(bell(f, 0, 110, -28), bell(f, -400, 110, -36) - (filt ? 60 : 0), bell(f, 400, 110, -12) - (filt ? 60 : 0), -90);
  const amStation = (f, c, lev) => sumDb(bell(f, c, 0.25, lev), brick(f, c, 4.5, lev - 14, 14));
  const amRf = (fc, gain) => f => sumDb(amStation(f, fc, -60 + gain), amStation(f, fc - 9, -66 + gain), amStation(f, fc + 9, -50 + gain), amStation(f, fc + 18, -72 + gain), -104 + gain + (gain ? 5 : 0));
  const amBb = filt => f => sumDb(amStation(f, 0, -22), amStation(f, -9, -28) - (filt ? 55 : 0), amStation(f, 9, -12) - (filt ? 55 : 0), -86);
  const mpxSpec = (rds = true) => noisy(spec(0, 60, f => sumDb(f > 0.03 && f < 15 ? -14 - 0.6 * f : -95, bell(f, 19, 0.15, -22),
    f > 23 && f < 53 ? -28 - 0.6 * Math.abs(f - 38) + (Math.abs(f - 38) < 0.4 ? -40 : 0) : -95, rds ? brick(f, 57, 2.4, -40, 3) + (Math.abs(f - 57) < 0.3 ? -12 : 0) : -95, -85), 400), 41, 1);
  const MPX_BANDS = [[0.03, 15, "L+R (mono)", BLUE], [23, 53, "L−R (stereo)", PURPLE], [54.6, 59.4, "RDS", GREEN]];

  // ------------------------------------------------------------------ sketches
  const spectrum = (label, x, y, xt, yt, xlab, pts, extra = {}) => plot({label, x, y, xt, yt, xlab, ylab: extra.ylab || "dBm", series: [{pts, color: extra.color || BLUE, fill: true}], ...extra});
  const dBmTicks = (lo, hi, st = 20) => lin(lo, hi, Math.round((hi - lo) / st) + 1).map(v => [v, String(Math.round(v))]);
  const iqPlot = (label, n, seed, dots, xlab) => {
    const i = smoothNoise(n, seed), q = smoothNoise(n, seed + 7);
    const pts = (fn, o) => Array.from({length: n}, (_, k) => [k, o + fn(k) * 0.9]);
    return plot({label, x: [0, n - 1], y: [-3.2, 3.2], xt: [[0, "0"], [n - 1, xlab]], yt: [[1.4, "I"], [-1.6, "Q"]], xlab: dots ? "sample number" : "time",
      ylab: "volts (relative)", series: [{pts: pts(i, 1.4), color: BLUE, dots, r: 1.6}, {pts: pts(q, -1.6), color: ORANGE, dots, r: 1.6}]});
  };
  const timePlot = (label, t, y, fns, cols, xlab, ylab, xt, extra = {}) => plot({label, x: t, y, xlab, ylab, xt, yt: extra.yt || [[0, "0"]],
    series: tracks(t[0], t[1], fns, extra.n || 300).map((pts, k) => ({pts, color: cols[k], width: 1.3, label: extra.labels && extra.labels[k], at: extra.at && extra.at[k]})), ...extra.o});
  const rfTime = (label, amp, ghz, envFn, unit) => timePlot(label, [0, 40], [-1.25 * amp, 1.25 * amp], [t => amp * envFn(t) * Math.sin(2 * Math.PI * ghz * t)], [BLUE], "time (ns)", unit, [[0, "0"], [20, "20"], [40, "40 ns"]], {n: 500, yt: [[amp, `${amp}`], [0, "0"], [-amp, `−${amp}`]]});
  function constellation(snr) {
    const r = rnd(5), S = 120, c = S / 2, k = S / 5, ideal = [[1, 1], [-1, 1], [-1, -1], [1, -1]];
    const dots = Array.from({length: 220}, (_, i) => { const p = ideal[i % 4]; return [p[0] + gauss(r) * snr, p[1] + gauss(r) * snr]; })
      .map(([a, b]) => `<circle cx="${(c + a * k).toFixed(1)}" cy="${(c - b * k).toFixed(1)}" r="1.4" fill="${BLUE}" opacity=".55"/>`).join("");
    const lab = [["00", 1, 1], ["01", -1, 1], ["11", -1, -1], ["10", 1, -1]].map(([t, a, b]) => `<text x="${c + a * k * 1.75}" y="${c - b * k * 1.75 + 3}" text-anchor="middle" class="sk-t">${t}</text>`).join("");
    return `<svg viewBox="0 0 ${S} ${S + 14}" class="sk-svg sk-sq" role="img" aria-label="DQPSK constellation"><rect width="${S}" height="${S}" fill="#fcfcfd" stroke="#e3e6ea"/>
      <line x1="${c}" x2="${c}" y1="0" y2="${S}" stroke="#d5dae0"/><line x1="0" x2="${S}" y1="${c}" y2="${c}" stroke="#d5dae0"/>${dots}${lab}
      <text x="${c}" y="${S + 11}" text-anchor="middle" class="sk-t">phase change per carrier → 2 bits</text></svg>`;
  }
  function bitStrip(errBefore, errAfter) {
    const n = 48, r = rnd(17), bits = Array.from({length: n}, () => (r() > 0.5 ? 1 : 0));
    const row = (y, errs, lab) => `<text x="2" y="${y + 9}" class="sk-t">${lab}</text>` + bits.map((b, i) => {
      const bad = errs.includes(i);
      return `<rect x="${70 + i * 4.7}" y="${y}" width="4" height="12" fill="${bad ? RED : b ? BLUE : "#cfd8e3"}"/>`;
    }).join("");
    return `<svg viewBox="0 0 300 62" class="sk-svg" role="img" aria-label="Bits before and after error correction">${row(4, errBefore, "after demapping")}${row(24, errAfter, "after Viterbi")}
      <text x="70" y="56" class="sk-t"><tspan fill="${RED}">■</tspan> wrong bit (illustrative) · <tspan fill="${BLUE}">■</tspan> 1 · <tspan fill="#9aa8b8">■</tspan> 0</text></svg>`;
  }
  function cuBar() {
    const subs = [[96, "City Pop"], [48, "News 24"], [80, "Classics"], [64, "Sport Live"], [64, "Jazz"], [80, "Rock"], [64, ""], [48, ""], [48, ""], [48, ""], [32, ""], [16, ""]];
    const cols = [BLUE, ORANGE, GREEN, PURPLE, C.teal, RED, "#a16207", "#be185d", "#4d7c0f", "#0369a1", GREY, "#6b7280"];
    let at = 0;
    const segs = subs.map(([kb, n], i) => { const cu = kb * 0.75, x = 6 + (at / 864) * 288, w = (cu / 864) * 288; at += cu;
      return `<rect x="${x.toFixed(1)}" y="8" width="${(w - 0.6).toFixed(1)}" height="22" fill="${cols[i]}" opacity="${i === 0 ? 1 : 0.3}"${i === 0 ? ' stroke="#1d2228" stroke-width="1.5"' : ""}/>${i === 0 ? `<text x="${(x + w / 2).toFixed(1)}" y="23" text-anchor="middle" class="sk-t" fill="#fff">${esc(n)}</text>` : ""}`; }).join("");
    return `<svg viewBox="0 0 300 66" class="sk-svg" role="img" aria-label="Only the selected sub-channel is decoded">${segs}<rect x="${(6 + (at / 864) * 288).toFixed(1)}" y="8" width="${(288 - (at / 864) * 288).toFixed(1)}" height="22" fill="#eef1f4"/>
      <text x="6" y="44" class="sk-t">one 24 ms CIF = 864 capacity units; the receiver keeps only the 72 CU of "City Pop"</text>
      <text x="6" y="58" class="sk-t">→ Reed-Solomon check → HE-AAC v2 decoder → 48 000 audio samples per second</text></svg>`;
  }
  function carrierComb() {
    const r = rnd(9), pts = [];
    for (let k = -768; k <= 768; k += 16) if (k !== 0) pts.push([k, 0.75 + 0.25 * r()]);
    return plot({label: "1536 carriers after the FFT", x: [-900, 900], y: [0, 1.15], xt: [[-768, "−768"], [0, "0"], [768, "+768"]], yt: [[1, "1"], [0, "0"]],
      xlab: "carrier (1 kHz apart); every 16th drawn, centre carrier unused", ylab: "amplitude", series: [{pts, color: BLUE, stems: true, width: 1.4}]});
  }

  // ------------------------------------------------------------------ the three chains
  // step: [short name, title, where ("rf" analogue in the tuner, "dig" digital in the tuner, "demod" coprocessor / decoder,
  //        "out" audio out), what changed (one sentence), sketches(v) -> [svg, svg], chip note, links]
  const kHz = (lo, hi, st) => lin(lo, hi, Math.round((hi - lo) / st) + 1).map(v => [v, String(+v.toFixed(1))]);
  const DAB = [
    ["Antenna", "RF at the antenna", "rf", "Everything in Band III arrives at once; our block 12C (227.36 MHz) is one 1.536 MHz slot among its neighbours, only microvolts strong.",
      () => [spectrum("Band III around 12C", [221, 234], [-112, -50], kHz(222, 232, 2), dBmTicks(-110, -50), "frequency (MHz)", noisy(spec(221, 234, dabRf(227.36, 0, 0)), 1), {bands: [[226.592, 228.128, "12C", BLUE]]}),
        rfTime("RF voltage", 5, 0.22736, t => 1 + 0.35 * Math.sin(t / 3.1) * Math.cos(t / 1.7), "µV")],
      "The tuner's Band III RF input (B3A / B3B in the configurator) takes this signal.", [CFG, FEAT]],
    ["LNA + AGC", "Low-noise amplifier and gain control", "rf", "The signal is about 30 dB stronger; the noise floor rises too (the amplifier's noise figure), and the AGC keeps the strongest neighbour from overloading the mixer.",
      () => [spectrum("After the LNA", [221, 234], [-82, -20], kHz(222, 232, 2), dBmTicks(-80, -20), "frequency (MHz)", noisy(spec(221, 234, dabRf(227.36, 30, 3)), 2), {bands: [[226.592, 228.128, "12C", BLUE]]}),
        rfTime("RF voltage after the LNA", 160, 0.22736, t => 1 + 0.35 * Math.sin(t / 3.1) * Math.cos(t / 1.7), "µV")],
      "Si47902 data short: integrated active Band III buffer. Digital AGC (DAGC) is a listed feature of Si47902, Si47952, Si47962, Si47992 and Si47942.", [find("Si47902"), FEAT]],
    ["Mixer → I/Q", "Mixer to zero IF: I and Q", "rf", "A local oscillator at 227.36 MHz shifts the block down to 0 Hz; two mixers 90° apart give I and Q, so frequencies above and below the centre stay apart.",
      () => [spectrum("At zero IF", [-3, 3], [-95, -10], kHz(-3, 3, 1), dBmTicks(-90, -10), "offset from 227.36 MHz (MHz)", noisy(spec(-3, 3, dabBb(false, false)), 3), {ylab: "dB", bands: [[-0.768, 0.768, "wanted", BLUE]]}),
        iqPlot("I and Q, analogue", 160, 4, false, "≈ 80 µs")],
      "The car tuners with DAB (Si47902, Si47962) hand the block on as digital I/Q (data shorts: digital I/Q interface to the DAB processor).", [find("Si47962")]],
    ["ADC", "Analogue to digital", "dig", "I and Q become numbers at a fixed sample rate; from here on everything is arithmetic, and the converter adds a small flat noise floor of its own.",
      () => [spectrum("After the ADC", [-3, 3], [-95, -10], kHz(-3, 3, 1), dBmTicks(-90, -10), "offset (MHz)", noisy(spec(-3, 3, dabBb(false, true)), 5), {ylab: "dBFS", bands: [[-0.768, 0.768, "wanted", BLUE]]}),
        iqPlot("I and Q, sampled", 40, 4, true, "40")],
      null, []],
    ["Channel filter", "Digital channel filter", "dig", "A sharp digital filter keeps only the 1.536 MHz of our block; the neighbour blocks are gone and the rate drops to 2.048 million I/Q pairs per second.",
      () => [spectrum("After the channel filter", [-3, 3], [-95, -10], kHz(-3, 3, 1), dBmTicks(-90, -10), "offset (MHz)", noisy(spec(-3, 3, dabBb(true, true)), 6), {ylab: "dBFS", series: [{pts: spec(-3, 3, f => brick(f, 0, 0.85, -12, 14)), color: RED, dash: "4 3", label: "filter", at: 200}, {pts: noisy(spec(-3, 3, dabBb(true, true)), 6), color: BLUE, fill: true}]}),
        iqPlot("I/Q at 2.048 MS/s", 40, 8, true, "≈ 20 µs")],
      "Here the tuner's job ends in a car radio: digital I/Q (ZIF: ZIFI / ZIFQ plus ZIFCLK / ZIFFS) goes to the Si469xx coprocessor, which has four ZIF inputs.", [find("Si469"), CFG]],
    ["OFDM / FFT", "OFDM: one FFT per symbol", "demod", "Every 1.246 ms the demodulator drops the 246 µs guard and runs a 2048-point FFT: the noise-like I/Q turns into 1536 separate carriers, each with a phase.",
      v => [carrierComb(), constellation(0.55 - v.snr / 70)],
      "DAB demodulation runs in the Si469x2 (DAB / DAB+) coprocessor; a consumer Si468x does tuner and demodulator in one chip.", [find("Si469"), find("Si4684"), ENS]],
    ["Bits + Viterbi", "DQPSK demapping, de-interleaving, Viterbi", "demod", "Each carrier's phase change gives 2 bits; de-interleaving spreads the errors of a fade over time, and the Viterbi decoder uses the added redundancy to correct most of them.",
      v => [bitStrip(v.snr < 12 ? [3, 9, 10, 11, 22, 30, 41] : [9, 30], v.snr < 8 ? [10, 30] : []), plot({label: "Soft bits", x: [0, 47], y: [-2, 2], xt: [[0, "0"], [47, "48 bits"]], yt: [[1, "+1"], [-1, "−1"]], xlab: "bit number", ylab: "soft value", series: [{pts: (() => { const r = rnd(17), g = rnd(3); return Array.from({length: 48}, (_, i) => [i, (r() > 0.5 ? 1 : -1) + gauss(g) * (0.9 - v.snr / 40)]); })(), color: BLUE, dots: true}]})],
      null, [ENS]],
    ["Audio decode", "Pick the station, decode the audio", "demod", "Only the sub-channel of the chosen station is kept out of the ensemble; Reed-Solomon fixes the last errors and the HE-AAC v2 decoder rebuilds the sound (DAB+).",
      () => [cuBar(), timePlot("Compressed frames", [0, 120], [-0.2, 1.3], [t => ((t % 24) < 22 ? 1 : 0)], [GREEN], "time (ms)", "", [[0, "0"], [60, "60"], [120, "120 ms"]], {n: 240, yt: [], o: {note: "one superframe = 5 × 24 ms"}})],
      "Si4684 product brief: DAB+ (HE-AAC v2) and DAB (MPEG Audio Layer 2) decoding.", [find("Si4684"), ENS]],
    ["Audio out", "Audio out", "out", "Out comes plain stereo audio, 48 000 samples per second, on I2S to the amplifier (or through a DAC); text and pictures travel alongside.",
      () => [spectrum("Audio spectrum", [0, 20], [-80, 0], kHz(0, 20, 5).map(([f, t]) => [f, t]), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", musicSpec(16, 7), {ylab: "dBFS", color: GREEN}),
        timePlot("Audio waveform", [0, 5], [-1.1, 1.1], [music, t => music(t + 0.3) * 0.9], [GREEN, ORANGE], "time (ms)", "level (full scale = 1)", [[0, "0"], [2.5, "2.5"], [5, "5 ms"]], {yt: [[1, "1"], [0, "0"], [-1, "−1"]], labels: ["L", "R"], at: [40, 140]})],
      "Digital audio out is I2S / TDM (32 to 192 kHz); the Si469xx has two I2S / TDM outputs, the Si4684 also an integrated 97 dB stereo DAC.", [find("Si4684"), CFG]],
  ];
  const FM = [
    ["Antenna", "RF at the antenna", "rf", "The whole FM band arrives at once; our station at 98.0 MHz sits between stronger and weaker neighbours, 200–400 kHz apart.",
      () => [spectrum("FM band around 98.0 MHz", [96, 100], [-112, -40], kHz(96, 100, 1), dBmTicks(-110, -50), "frequency (MHz)", noisy(spec(96, 100, fmRf(98, 0)), 11), {bands: [[97.89, 98.11, "98.0", BLUE]]}),
        rfTime("RF voltage", 20, 0.098, () => 1, "µV")],
      "The tuner's FM RF inputs FMA / FMB (two antennas for phase diversity, PD) take this signal; note the envelope is flat: FM puts the sound in the frequency, not the amplitude.", [CFG, FEAT]],
    ["LNA + AGC", "Low-noise amplifier and gain control", "rf", "Everything is about 30 dB stronger; the AGC turns the gain down when a strong neighbour (here 98.4 MHz) would overload the mixer.",
      () => [spectrum("After the LNA", [96, 100], [-82, -10], kHz(96, 100, 1), dBmTicks(-80, -20), "frequency (MHz)", noisy(spec(96, 100, fmRf(98, 30)), 12), {bands: [[97.89, 98.11, "98.0", BLUE]]}),
        rfTime("RF voltage after the LNA", 600, 0.098, () => 1, "µV")],
      "Si4706 data short: integrated FM LNA and automatic gain control (AGC); Si4734/35: AGC.", [find("Si4706"), find("Si4734")]],
    ["Mixer → I/Q", "Mixer to a low or zero IF: I and Q", "rf", "The local oscillator shifts 98.0 MHz down to near 0 Hz; neighbours land at ±400 kHz. I and Q keep above and below apart.",
      () => [spectrum("Near 0 Hz", [-700, 700], [-95, 0], [[-600, "−600"], [-300, "−300"], [0, "0"], [300, "300"], [600, "600"]], dBmTicks(-90, -10), "offset from 98.0 MHz (kHz)", noisy(spec(-700, 700, fmBb(false)), 13), {ylab: "dB", bands: [[-110, 110, "wanted", BLUE]]}),
        iqPlot("I and Q, analogue", 160, 14, false, "≈ 20 µs")],
      "Si4706 data short: image-rejection mixer, low-IF direct conversion with no external ceramic filters; Si4704/05: digital low-IF receiver.", [find("Si4706"), find("Si4704")]],
    ["ADC", "Analogue to digital", "dig", "I and Q become numbers; from here the receiver is digital signal processing.",
      () => [spectrum("After the ADC", [-700, 700], [-95, 0], [[-600, "−600"], [0, "0"], [600, "600"]], dBmTicks(-90, -10), "offset (kHz)", noisy(spec(-700, 700, fmBb(false)), 15), {ylab: "dBFS", bands: [[-110, 110, "wanted", BLUE]]}),
        iqPlot("I and Q, sampled", 40, 14, true, "40")],
      null, []],
    ["Channel filter", "Digital channel filter", "dig", "The filter keeps about ±110 kHz around our station and removes the neighbours; what is left is a phasor of constant length that spins faster or slower with the sound.",
      () => [spectrum("After the channel filter", [-700, 700], [-95, 0], [[-600, "−600"], [0, "0"], [600, "600"]], dBmTicks(-90, -10), "offset (kHz)", noisy(spec(-700, 700, fmBb(true)), 16), {ylab: "dBFS", series: [{pts: spec(-700, 700, f => brick(f, 0, 130, -6, 10)), color: RED, dash: "4 3", label: "filter", at: 170}, {pts: noisy(spec(-700, 700, fmBb(true)), 16), color: BLUE, fill: true}]}),
        timePlot("I and Q of an FM signal", [0, 60], [-1.3, 1.3], [t => Math.cos(2 * Math.PI * (0.04 * t + 0.25 * Math.sin(t / 12))), t => Math.sin(2 * Math.PI * (0.04 * t + 0.25 * Math.sin(t / 12)))], [BLUE, ORANGE], "time (µs)", "I, Q", [[0, "0"], [30, "30"], [60, "60 µs"]], {yt: [[1, "1"], [0, "0"], [-1, "−1"]], labels: ["I", "Q"], at: [60, 200]})],
      null, []],
    ["FM demod → MPX", "FM discriminator: the MPX signal", "demod", "The discriminator measures how fast the phasor turns: that speed is the baseband 'MPX' signal, 0–60 kHz, with mono audio, the 19 kHz pilot, stereo and RDS stacked in it.",
      () => [spectrum("MPX spectrum", [0, 60], [-80, 0], [[0, "0"], [15, "15"], [19, "19"], [38, "38"], [57, "57"]], [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", mpxSpec(), {ylab: "dB", bands: MPX_BANDS, vlines: [[19, "pilot", RED]]}),
        timePlot("MPX waveform", [0, 1], [-1.1, 1.1], [t => 0.55 * music(t * 3) + 0.1 * Math.sin(2 * Math.PI * 19 * t) + 0.2 * Math.sin(2 * Math.PI * 0.9 * t) * Math.sin(2 * Math.PI * 38 * t)], [PURPLE], "time (ms)", "deviation (relative)", [[0, "0"], [0.5, "0.5"], [1, "1 ms"]], {n: 600, yt: [[1, "75 kHz"], [0, "0"], [-1, "−75"]]})],
      null, [RDS]],
    ["Stereo decode", "Stereo decoder (and RDS off at 57 kHz)", "demod", "The 19 kHz pilot is doubled to 38 kHz to bring L−R back down; adding and subtracting L+R and L−R gives left and right. RDS at 57 kHz goes to the RDS decoder.",
      () => [spectrum("Left and right", [0, 20], [-80, 0], kHz(0, 20, 5), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", musicSpec(15, 18), {ylab: "dB", color: GREEN, vlines: [[15, "15 kHz limit", RED]]}),
        timePlot("Left and right", [0, 5], [-1.1, 1.1], [music, t => 0.8 * music(t + 0.6)], [GREEN, ORANGE], "time (ms)", "level", [[0, "0"], [2.5, "2.5"], [5, "5 ms"]], {yt: [[1, "1"], [0, "0"], [-1, "−1"]], labels: ["L", "R"], at: [40, 140]})],
      "Si4734/35 data short: digital FM stereo decoder. RDS / RBDS decoding: Si4705, Si4735 and the Si4706 data receiver.", [find("Si4734"), find("Si4706"), RDS]],
    ["De-emphasis", "De-emphasis 50 µs / 75 µs", "demod", "The transmitter boosted the treble; the receiver turns it back down (50 µs in Europe, 75 µs in the Americas), and the hiss at high frequencies goes down with it.",
      () => [plot({label: "De-emphasis", x: [0, 15], y: [-20, 3], xt: kHz(0, 15, 5), yt: [[0, "0"], [-10, "−10"], [-20, "−20"]], xlab: "frequency (kHz)", ylab: "gain (dB)",
        series: [{pts: spec(0, 15, f => -10 * Math.log10(1 + (2 * Math.PI * f * 1000 * 50e-6) ** 2)), color: BLUE, label: "50 µs", at: 200}, {pts: spec(0, 15, f => -10 * Math.log10(1 + (2 * Math.PI * f * 1000 * 75e-6) ** 2)), color: ORANGE, label: "75 µs", at: 120}]}),
        timePlot("Before and after", [0, 2], [-1.2, 1.2], [t => music(t * 2) + 0.18 * Math.sin(2 * Math.PI * 9.7 * t) + 0.12 * Math.sin(2 * Math.PI * 13.1 * t + 1), t => music(t * 2) * 0.95], [GREY, GREEN], "time (ms)", "level", [[0, "0"], [1, "1"], [2, "2 ms"]], {n: 500, yt: [[1, "1"], [0, "0"], [-1, "−1"]], labels: ["before (hiss)", "after"], at: [60, 380]})],
      "Si4704/05 data short: programmable de-emphasis (50 / 75 µs); Si4734/35 too.", [find("Si4704"), find("Si4734")]],
    ["Audio out", "Audio out", "out", "Left and right audio, up to 15 kHz, go out as analogue line level or as digital I2S to the amplifier.",
      () => [spectrum("Audio spectrum", [0, 20], [-80, 0], kHz(0, 20, 5), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", musicSpec(15, 19), {ylab: "dBFS", color: GREEN}),
        timePlot("Audio waveform", [0, 5], [-1.1, 1.1], [music, t => 0.8 * music(t + 0.6)], [GREEN, ORANGE], "time (ms)", "level", [[0, "0"], [2.5, "2.5"], [5, "5 ms"]], {yt: [[1, "1"], [0, "0"], [-1, "−1"]], labels: ["L", "R"], at: [40, 140]})],
      "Si4706 data short: stereo audio out and I2S digital audio out; I2S / TDM runs at 32 to 192 kHz.", [find("Si4706"), CFG]],
  ];
  const amEnv = t => 1 + 0.7 * music(t * 2.2);  // t in ms
  const AM = [
    ["Antenna", "RF at the antenna", "rf", "The medium-wave band arrives at once; stations sit 9 kHz apart (10 kHz in the Americas). Each is a carrier with the sound in two sidebands, ±4.5 kHz.",
      () => [spectrum("Medium wave around 1008 kHz", [985, 1032], [-112, -40], [[990, "990"], [999, "999"], [1008, "1008"], [1017, "1017"], [1026, "1026"]], dBmTicks(-110, -50), "frequency (kHz)", noisy(spec(985, 1032, amRf(1008, 0), 400), 21), {bands: [[1003.5, 1012.5, "1008", BLUE]]}),
        plot({label: "AM at the antenna", x: [0, 2], y: [-1.9, 1.9], xt: [[0, "0"], [1, "1"], [2, "2 ms"]], yt: [[0, "0"]], xlab: "time (ms)", ylab: "µV (relative)", areas: [{pts: lin(0, 2, 300).map(t => [t, -amEnv(t), amEnv(t)]), color: BLUE, opacity: 0.35}], series: [{pts: lin(0, 2, 300).map(t => [t, amEnv(t)]), color: BLUE, width: 1}], note: "carrier too fast to draw: the outline is the sound"})],
      "The tuner's AM input is AMI in the configurator.", [CFG, FEAT]],
    ["LNA + AGC", "Amplifier and gain control", "rf", "The weak station is amplified; the AGC holds the level steady as the signal fades (AM fades a lot at night).",
      () => [spectrum("After the amplifier", [985, 1032], [-82, -10], [[990, "990"], [1008, "1008"], [1026, "1026"]], dBmTicks(-80, -20), "frequency (kHz)", noisy(spec(985, 1032, amRf(1008, 30), 400), 22), {bands: [[1003.5, 1012.5, "1008", BLUE]]}),
        plot({label: "After the amplifier", x: [0, 2], y: [-1.9, 1.9], xt: [[0, "0"], [1, "1"], [2, "2 ms"]], yt: [[0, "0"]], xlab: "time (ms)", ylab: "mV (relative)", areas: [{pts: lin(0, 2, 300).map(t => [t, -amEnv(t), amEnv(t)]), color: BLUE, opacity: 0.35}]})],
      "Si4734/35 data short (broadcast AM/FM/SW/LW receiver): AGC.", [find("Si4734")]],
    ["Mixer → I/Q", "Mixer to a low or zero IF: I and Q", "rf", "The local oscillator brings 1008 kHz down to 0 Hz; the neighbours land at ±9 kHz.",
      () => [spectrum("Near 0 Hz", [-25, 25], [-95, 0], [[-18, "−18"], [-9, "−9"], [0, "0"], [9, "9"], [18, "18"]], dBmTicks(-90, -10), "offset from 1008 kHz (kHz)", noisy(spec(-25, 25, amBb(false), 400), 23), {ylab: "dB", bands: [[-4.5, 4.5, "wanted", BLUE]]}),
        iqPlot("I and Q, analogue", 160, 24, false, "≈ 2 ms")],
      null, []],
    ["ADC", "Analogue to digital", "dig", "I and Q become numbers; the rest is digital.",
      () => [spectrum("After the ADC", [-25, 25], [-95, 0], [[-18, "−18"], [0, "0"], [18, "18"]], dBmTicks(-90, -10), "offset (kHz)", noisy(spec(-25, 25, amBb(false), 400), 25), {ylab: "dBFS", bands: [[-4.5, 4.5, "wanted", BLUE]]}),
        iqPlot("I and Q, sampled", 40, 24, true, "40")],
      null, []],
    ["Channel filter", "Digital channel filter", "dig", "A narrow filter (about ±4.5 kHz) keeps our station and drops the neighbours; narrower means less interference but duller sound.",
      () => [spectrum("After the channel filter", [-25, 25], [-95, 0], [[-18, "−18"], [0, "0"], [18, "18"]], dBmTicks(-90, -10), "offset (kHz)", noisy(spec(-25, 25, amBb(true), 400), 26), {ylab: "dBFS", series: [{pts: spec(-25, 25, f => brick(f, 0, 5, -6, 10), 400), color: RED, dash: "4 3", label: "filter", at: 300}, {pts: noisy(spec(-25, 25, amBb(true), 400), 26), color: BLUE, fill: true}]}),
        iqPlot("I/Q after the filter", 40, 27, true, "40")],
      null, []],
    ["Envelope", "Envelope detector", "demod", "The length of each I/Q arrow, √(I² + Q²), is the AM envelope: the sound riding on a constant level from the carrier.",
      () => [spectrum("After the detector", [0, 10], [-80, 5], kHz(0, 10, 2.5), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", noisy(spec(0, 10, f => sumDb(bell(f, 0, 0.12, 0), f < 4.5 ? -18 - 2 * f : -18 - 2 * f - 40 * (f - 4.5), -85), 300), 28, 1), {ylab: "dB", vlines: [[0.15, "carrier → DC", RED]]}),
        timePlot("Envelope", [0, 2], [-0.2, 2], [amEnv], [BLUE], "time (ms)", "level", [[0, "0"], [1, "1"], [2, "2 ms"]], {yt: [[1, "DC"], [0, "0"]]})],
      null, []],
    ["Remove DC", "Remove the carrier level", "demod", "The constant part (the carrier) is removed, leaving the audio centred on zero; its size tells the AGC how strong the station is.",
      () => [spectrum("Audio only", [0, 10], [-80, 5], kHz(0, 10, 2.5), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", noisy(spec(0, 10, f => sumDb(f < 4.5 ? -18 - 2 * f : -18 - 2 * f - 40 * (f - 4.5), -85), 300), 29, 1), {ylab: "dB", color: GREEN}),
        timePlot("Audio", [0, 2], [-1.1, 1.1], [t => 0.7 * music(t * 2.2)], [GREEN], "time (ms)", "level", [[0, "0"], [1, "1"], [2, "2 ms"]], {yt: [[1, "1"], [0, "0"], [-1, "−1"]]})],
      null, []],
    ["Noise blanker", "Clean-up: noise blanker and audio filter", "demod", "Clicks from ignition and electronics are cut out and the audio is low-pass filtered; AM interference cancelling goes further.",
      () => [spectrum("Audio filter", [0, 10], [-80, 5], kHz(0, 10, 2.5), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", noisy(spec(0, 10, f => sumDb(f < 4 ? -18 - 2 * f : -18 - 2 * f - 50 * (f - 4), -85), 300), 30, 1), {ylab: "dB", color: GREEN}),
        timePlot("Click removed", [0, 2], [-1.6, 1.6], [t => 0.7 * music(t * 2.2) + (Math.abs(t - 0.62) < 0.02 ? 1.4 : 0) - (Math.abs(t - 1.41) < 0.015 ? 1.3 : 0), t => 0.7 * music(t * 2.2)], [GREY, GREEN], "time (ms)", "level", [[0, "0"], [1, "1"], [2, "2 ms"]], {n: 500, yt: [[0, "0"]], labels: ["with clicks", "blanked"], at: [124, 400]})],
      "AM interference canceller (AMIC) is a listed feature of several car tuners in the tuner feature table, e.g. Si47961, Si47962, Si47971.", [FEAT, find("Si47961")]],
    ["Audio out", "Audio out", "out", "Mono audio, typically up to 4–5 kHz, goes to the amplifier as analogue or I2S.",
      () => [spectrum("Audio spectrum", [0, 10], [-80, 5], kHz(0, 10, 2.5), [[0, "0"], [-40, "−40"], [-80, "−80"]], "frequency (kHz)", noisy(spec(0, 10, f => sumDb(f < 4 ? -18 - 2 * f : -18 - 2 * f - 50 * (f - 4), -85), 300), 31, 1), {ylab: "dBFS", color: GREEN}),
        timePlot("Audio waveform", [0, 5], [-1.1, 1.1], [t => 0.7 * music(t * 2.2)], [GREEN], "time (ms)", "level", [[0, "0"], [2.5, "2.5"], [5, "5 ms"]], {yt: [[1, "1"], [0, "0"], [-1, "−1"]]})],
      "Si4734/35 data short: analogue audio out (LOUT / ROUT); digital audio out on the Si4735 only.", [find("Si4734"), CFG]],
  ];
  const CHAINS = {dab: DAB, fm: FM, am: AM};
  const NAMES = {dab: "DAB / DAB+", fm: "FM (stereo)", am: "AM"};
  const WHERE = {rf: ["Tuner, analogue", "#dbe7f5"], dig: ["Tuner, digital", "#e3f1e6"], demod: ["Demodulator / decoder", "#efe6f7"], out: ["Audio out", "#fbefd9"]};
  window.VZ_FLOW = {CHAINS};

  V.push({
    id: "flow", group: "Broadcast radio", title: "Signal flow: from the antenna to the audio",
    explains: [["Broadcast radio tuners and demodulators", "/knowledge#p-tuners"], ["Tuners & demodulators", "/broadcast"]],
    physics: [["Mixing and the superheterodyne", "phys_mixing_superhet"], ["AM and FM", "phys_am_fm"]],
    lead: "Follow one station through the receiver, step by step: what the signal looks like at each block (spectrum and time) and what that block changed. Choose DAB, FM or AM, then use Next / Prev or click a block in the chain.",
    controls: [
      {k: "sys", label: "Radio system", type: "select", options: Object.entries(NAMES), value: "dab"},
      {k: "step", label: "Step", min: 1, max: 9, step: 1, value: 1},
      {k: "snr", label: "Signal-to-noise ratio (DAB demodulator steps)", min: 0, max: 30, step: 1, value: 18, unit: "dB", when: v => v.sys === "dab"},
    ],
    setup(el, render, setVals) {
      el.hidden = true;
      el.parentElement.querySelector(".vz-more").addEventListener("click", e => {
        const b = e.target.closest("[data-fl-step]");
        if (!b) return;
        setVals({step: Math.max(1, Math.min(9, +b.dataset.flStep))});
        render();
        const sk = el.parentElement.querySelector(".fl-now");
        if (sk && b.classList.contains("fl-blk") && sk.scrollIntoView) sk.scrollIntoView({block: "nearest", behavior: "smooth"});
      });
    },
    compute(v) {
      const chain = CHAINS[v.sys], i = Math.max(1, Math.min(chain.length, Math.round(v.step))) - 1;
      const [short, title, where, what, draw, chip, links] = chain[i];
      const [a, b] = draw(v);
      const blocks = chain.map((s, k) => `<button type="button" class="fl-blk${k === i ? " on" : ""}" data-fl-step="${k + 1}" style="--w:${WHERE[s[2]][1]}" aria-pressed="${k === i}"><b>${k + 1}</b> ${esc(s[0])}</button>`).join('<span class="fl-arr" aria-hidden="true">›</span>');
      const legend = Object.values(WHERE).map(([l, c]) => `<span><i style="background:${c}"></i>${esc(l)}</span>`).join("");
      const html = `<div class="fl">
        <nav class="fl-chain" aria-label="Signal chain">${blocks}</nav>
        <p class="fl-legend small">${legend}</p>
        <div class="fl-now">
          <div class="fl-head"><button type="button" class="outline secondary small-btn fl-nav" data-fl-step="${i}"${i === 0 ? " disabled" : ""}>‹ Prev</button>
            <h3>Step ${i + 1} of ${chain.length}: ${esc(title)}</h3>
            <button type="button" class="small-btn fl-nav" data-fl-step="${i + 2}"${i === chain.length - 1 ? " disabled" : ""}>Next ›</button></div>
          <p class="fl-what"><b>What changed:</b> ${esc(what)}</p>
          <div class="fl-sk">${a}${b}</div>
          ${chip ? `<p class="fl-chip small"><b>On our chips:</b> ${esc(chip)}${links.length ? " · " + links.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ") : ""}</p>` : links.length ? `<p class="fl-chip small">See also: ${links.map(([l, h]) => `<a href="${h}">${esc(l)}</a>`).join(" · ")}</p>` : ""}
        </div>
        <p class="small muted">Illustrative sketches: the shapes and axes are plausible, the levels are made up. Chip notes repeat only what our data shorts, product briefs and the configurator data say; check the data sheet for a design.</p></div>`;
      return {
        outputs: [["System", NAMES[v.sys]], ["Step", `${i + 1} / ${chain.length}: ${short}`], ["Where", WHERE[where][0]]],
        eq: v.sys === "dab" ? "I/Q → FFT (2048 points per 1.246 ms symbol) → DQPSK → de-interleave → Viterbi → sub-channel → Reed-Solomon → HE-AAC → audio"
          : v.sys === "fm" ? "f<sub>inst</sub> = (1/2π)·dφ/dt → MPX = (L+R) + pilot 19 kHz + (L−R)·sin(2π·38 kHz·t) + RDS at 57 kHz → L, R → de-emphasis τ = 50 / 75 µs"
            : "envelope = √(I² + Q²) = A<sub>c</sub>·(1 + m·s(t)) → remove A<sub>c</sub> → audio s(t)",
        eqn: v.sys === "fm" ? "de-emphasis −3 dB corner: 1 / (2π·50 µs) = 3.18 kHz (Europe), 1 / (2π·75 µs) = 2.12 kHz (Americas)"
          : v.sys === "dab" ? "2.048 MS/s × 1 ms = 2048 samples per useful symbol, + 504 samples guard (246 µs) = 2552 samples per symbol" : "channel 9 kHz (Europe) / 10 kHz (Americas) → audio up to about 4.5 kHz",
        html, nochart: true,
        note: "The order of blocks is the textbook one; real chips merge or split some of them. In a car radio the tuner does steps 1–5 and a separate coprocessor the DAB demodulation; FM and AM are demodulated in the tuner itself.",
      };
    },
    related: [["DAB ensemble and I/Q", "#dab"], ["RDS", "#rds"], ["AM vs FM modulation", "#mod"], ["Cascaded noise figure", "#nf"], ["Broadcast configurations", "/broadcast"]],
  });
});
