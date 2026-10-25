// Interactive visual "DAB: from I/Q samples to the ensemble and the audio" (owner, 23 Oct 2026: "add I/Q data and the
// I/Q data description for DAB ... a visualization of DAB ensembles, how it is decoded and what the tuner sees vs. what
// the audio is that is produced"). Registers with the visuals engine in visuals.js (window.VZ_ADD). Transmission mode I
// numbers from ETSI EN 300 401; the example ensemble is made up; thresholds marked est are BizDev's own.
(window.VZ_ADD = window.VZ_ADD || []).push(({V, C, num, esc, log10, bandStrip}) => {
  const BLOCKS = [["5C", 178.352], ["8A", 195.936], ["10B", 211.648], ["11D", 222.064], ["12B", 225.648], ["12C", 227.360], ["12D", 229.072]];
  // protection level -> CU per kbit/s (EEP-A: 12n, 8n, 6n, 4n CU for 8n kbit/s), code rate, rough C/N needed (est)
  const EEP = {"1A": [1.5, "1/4", 5], "2A": [1, "3/8", 6.5], "3A": [0.75, "1/2", 8], "4A": [0.5, "3/4", 11]};
  const SERVICES = [  // a made-up ensemble: name, kbit/s, kind, what the display shows
    ["City Pop", 96, "audio", "Now playing: The Example Band – Summer Song"], ["News 24", 48, "audio", "Headlines at the top of every hour"],
    ["Classics", 80, "audio", "Symphony No. 5, 2nd movement"], ["Sport Live", 64, "audio", "Live: second half, 1–1"],
    ["Jazz Lounge", 64, "audio", "Late-night jazz until 2 am"], ["Rock One", 80, "audio", "Guitar classics, no talk"],
    ["Dance", 64, "audio", "Club mix, live from the studio"], ["Kids Radio", 48, "audio", "Story time"],
    ["Local", 48, "audio", "Traffic: 10 min delay on the ring road"], ["Chill", 48, "audio", "Relax and unwind"],
    ["Traffic data", 32, "data", "TPEG traffic messages for the navigation"], ["Programme guide", 16, "data", "EPG: what is on next"],
  ];
  const est = '<span class="kn-est" title="BizDev\'s own reasoning, not from a source">est</span>';
  const COL = [C.blue, C.orange, C.green, C.purple, C.teal, C.red, "#a16207", "#be185d", "#4d7c0f", "#0369a1", C.grey, "#6b7280"];
  const rnd = seed => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const gauss = r => Math.sqrt(-2 * Math.log(Math.max(1e-9, r()))) * Math.cos(2 * Math.PI * r());

  function spectrumSvg(fc, snr) {
    const W = 320, H = 130, x = f => 20 + ((f - fc + 3) / 6) * (W - 40), top = 30, floor = Math.min(H - 25, top + (H - 55) * (1 - Math.min(snr, 30) / 30) + 5);
    const blk = (f, on, lab) => `<rect x="${x(f - 0.768)}" y="${top}" width="${x(f + 0.768) - x(f - 0.768)}" height="${H - 25 - top}" fill="${on ? C.blue : C.grey}" opacity="${on ? 0.75 : 0.25}"/><text x="${x(f)}" y="${top - 6}" text-anchor="middle" class="dab-t">${esc(lab)}</text>`;
    const i = BLOCKS.findIndex(b => b[1] === fc);
    return `<svg viewBox="0 0 ${W} ${H}" class="dab-svg" role="img" aria-label="Spectrum: the 1.536 MHz DAB block">
      ${blk(fc - 1.712, false, "neighbour")}${blk(fc, true, `${BLOCKS[i][0]} · ${fc} MHz`)}${blk(fc + 1.712, false, "neighbour")}
      <line x1="20" x2="${W - 20}" y1="${floor}" y2="${floor}" stroke="${C.orange}" stroke-dasharray="4 3"/><text x="${W - 22}" y="${floor - 3}" text-anchor="end" class="dab-t" fill="${C.orange}">noise</text>
      <line x1="20" x2="${W - 20}" y1="${H - 25}" y2="${H - 25}" stroke="#8a94a3"/>
      <text x="${x(fc - 0.768)}" y="${H - 10}" text-anchor="middle" class="dab-t">−768 kHz</text><text x="${x(fc + 0.768)}" y="${H - 10}" text-anchor="middle" class="dab-t">+768 kHz</text></svg>`;
  }
  function scatterSvg(pts, label, color, ref) {
    const S = 150, c = S / 2, k = S / 6;
    const dots = pts.map(([a, b]) => `<circle cx="${(c + a * k).toFixed(1)}" cy="${(c - b * k).toFixed(1)}" r="1.6" fill="${color}" opacity=".55"/>`).join("");
    const refs = (ref || []).map(([a, b]) => `<circle cx="${c + a * k}" cy="${c - b * k}" r="4" fill="none" stroke="#1d2228" stroke-width="1.5"/>`).join("");
    return `<svg viewBox="0 0 ${S} ${S + 16}" class="dab-svg dab-sq" role="img" aria-label="${esc(label)}"><rect x="0" y="0" width="${S}" height="${S}" fill="#fcfcfd" stroke="#e3e6ea"/>
      <line x1="${c}" x2="${c}" y1="0" y2="${S}" stroke="#d5dae0"/><line x1="0" x2="${S}" y1="${c}" y2="${c}" stroke="#d5dae0"/>${dots}${refs}
      <text x="${S - 4}" y="${c - 4}" text-anchor="end" class="dab-t">I</text><text x="${c + 4}" y="11" class="dab-t">Q</text><text x="${c}" y="${S + 13}" text-anchor="middle" class="dab-t">${esc(label)}</text></svg>`;
  }
  function iqTraceSvg(iq) {
    const W = 320, H = 110, n = iq.length, x = i => 10 + (i / (n - 1)) * (W - 20), y = (v, o) => o - v * 14;
    const line = (k, o, col) => `<polyline fill="none" stroke="${col}" stroke-width="1.6" points="${iq.map((p, i) => `${x(i).toFixed(1)},${y(p[k], o).toFixed(1)}`).join(" ")}"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" class="dab-svg" role="img" aria-label="I and Q samples over time">${line(0, 30, C.blue)}${line(1, 80, C.orange)}
      <text x="12" y="12" class="dab-t" fill="${C.blue}">I (in-phase)</text><text x="12" y="62" class="dab-t" fill="${C.orange}">Q (quadrature)</text>
      <text x="${W - 10}" y="${H - 2}" text-anchor="end" class="dab-t">${n} samples = ${num(n / 2.048)} µs at 2.048 MS/s</text></svg>`;
  }
  function ensembleSvg(rows, sel, cap) {
    const W = 320, H = 46, x = cu => 4 + (Math.min(cu, Math.max(cap, 864)) / Math.max(cap, 864)) * (W - 8);
    let at = 0;
    const segs = rows.map((r, i) => { const a = x(at); at += r.cu; const b = x(at); return `<rect x="${a.toFixed(1)}" y="6" width="${Math.max(0.5, b - a - 0.6).toFixed(1)}" height="24" fill="${COL[i]}" opacity="${i === sel ? 1 : 0.45}"${i === sel ? ' stroke="#1d2228" stroke-width="1.5"' : ""}/>`; }).join("");
    const lim = x(864);
    return `<svg viewBox="0 0 ${W} ${H}" class="dab-svg" role="img" aria-label="Capacity units used by each service">${segs}
      <line x1="${lim}" x2="${lim}" y1="2" y2="34" stroke="${C.red}" stroke-width="2"/><text x="${lim - 2}" y="${H - 2}" text-anchor="end" class="dab-t" fill="${C.red}">864 CU limit</text></svg>`;
  }
  const slideSvg = (name, i) => `<svg viewBox="0 0 160 120" class="dab-svg dab-slide" role="img" aria-label="Slideshow image"><rect width="160" height="120" fill="${COL[i]}" opacity=".85"/>
    <circle cx="125" cy="30" r="16" fill="#fff" opacity=".35"/><path d="M0 120 L50 70 L80 95 L110 60 L160 110 L160 120 Z" fill="#fff" opacity=".3"/>
    <text x="10" y="24" fill="#fff" font-size="14" font-weight="700">${esc(name)}</text><text x="10" y="112" fill="#fff" font-size="9">MOT slideshow, 320 × 240</text></svg>`;

  V.push({
    id: "dab", group: "Broadcast radio", title: "DAB: from I/Q samples to the ensemble and the audio",
    explains: [["Broadcast radio tuners and demodulators", "/knowledge#p-tuners"], ["Si468x digital radios", "/find?q=Si468"], ["Si4790x / Si4796x tuners", "/find?q=Si479"], ["Si469xx DAB coprocessors", "/find?q=Si469"]],
    physics: [["Mixing and the superheterodyne", "phys_mixing_superhet"], ["AM and FM", "phys_am_fm"]],
    lead: "What the tuner sees is not audio: it is a 1.536 MHz wide block of 1536 carriers that carries a whole multiplex (an ensemble) of stations. Follow one block from the antenna to I/Q samples, through the OFDM demodulator to the ensemble, and out as the one station you picked: sound, scrolling text and a picture.",
    controls: [
      {k: "blk", label: "DAB block (Band III)", type: "select", options: BLOCKS.map(([b, f]) => [String(f), `${b} · ${f} MHz`]), value: "227.36"},
      {k: "svc", label: "Station you select", type: "select", options: SERVICES.map((s, i) => [String(i), `${s[0]} (${s[1]} kbit/s${s[2] === "data" ? ", data" : ""})`]), value: "0"},
      {k: "eep", label: "Protection level (EEP)", type: "select", options: [["1A", "EEP-1A, code rate 1/4 (strongest)"], ["2A", "EEP-2A, 3/8"], ["3A", "EEP-3A, 1/2 (common)"], ["4A", "EEP-4A, 3/4 (weakest)"]], value: "3A"},
      {k: "snr", label: "Signal-to-noise ratio at the tuner", min: 0, max: 30, step: 0.5, value: 15, unit: "dB"},
    ],
    compute(v) {
      const fc = +v.blk, sel = +v.svc, [cuPer, rate, need] = EEP[v.eep], s = SERVICES[sel];
      const rows = SERVICES.map(x => ({cu: Math.round(x[1] * cuPer)})), used = rows.reduce((a, r) => a + r.cu, 0);
      const fits = used <= 864, margin = v.snr - need;
      const state = margin >= 2 ? ["clean audio", "ok"] : margin >= 0 ? ["bubbling, drop-outs (est)", "warn"] : ["muted: errors not correctable (est)", "bad"];
      const r = rnd(11), snr = 10 ** (v.snr / 10), sn = Math.sqrt(1 / (2 * snr));
      const iq = Array.from({length: 48}, () => [gauss(r) * 0.7, gauss(r) * 0.7]);
      const raw = Array.from({length: 260}, () => [gauss(r) * 0.8, gauss(r) * 0.8]);
      const ideal = [[1, 1], [-1, 1], [-1, -1], [1, -1]].map(([a, b]) => [a * 1.6, b * 1.6]);
      const cons = Array.from({length: 260}, (_, i) => { const p = ideal[i % 4]; return [p[0] + gauss(r) * sn * 2.2 * Math.SQRT2, p[1] + gauss(r) * sn * 2.2 * Math.SQRT2]; });
      const msc = 72 * 1536 * 2;  // bits per 96 ms frame in the 72 MSC symbols
      const list = SERVICES.map((x, i) => `<li${i === sel ? ' class="on"' : ""}><i style="background:${COL[i]}"></i>${esc(x[0])} <span class="muted">${x[1]} kbit/s · ${rows[i].cu} CU${x[2] === "data" ? " · data" : ""}</span></li>`).join("");
      const audio = s[2] === "audio";
      const html = `<style>
        .dab-flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(17rem,100%),1fr));gap:.6rem;margin:.4rem 0}
        .dab-card{border:1px solid var(--pico-muted-border-color);border-radius:.45rem;padding:.5rem .7rem;background:#fff;min-width:0}
        .dab-card h3{font-size:.95rem;margin:0 0 .3rem}.dab-card p{font-size:.84rem;margin:.3rem 0}
        .dab-step{display:inline-block;min-width:1.4rem;height:1.4rem;border-radius:50%;background:var(--pico-primary);color:#fff;text-align:center;font-size:.8rem;line-height:1.4rem;margin-right:.3rem}
        .dab-svg{display:block;width:100%;height:auto;max-width:100%}.dab-sq{max-width:11rem}.dab-pair{display:flex;gap:.5rem;flex-wrap:wrap}
        .dab-pair>svg{flex:1 1 8rem}.dab-t{font-size:9px;fill:#3a4450}.dab-slide{max-width:12rem;border-radius:.3rem}
        .dab-list{list-style:none;padding:0;margin:.3rem 0;font-size:.8rem;columns:2 9rem}.dab-list li{margin:0 0 .15rem;break-inside:avoid}
        .dab-list i{display:inline-block;width:.7rem;height:.7rem;border-radius:2px;margin-right:.3rem;vertical-align:-1px}.dab-list li.on{font-weight:700}
        .dab-dls{font-family:ui-monospace,monospace;background:#1d2228;color:#9fe3b0;padding:.3rem .5rem;border-radius:.3rem;font-size:.8rem;overflow-wrap:anywhere}
        .dab-sees{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(14rem,100%),1fr));gap:.6rem;margin:.6rem 0}
        .dab-sees>div{border-left:4px solid var(--pico-primary);padding:.3rem .6rem;background:#f6f8fb;font-size:.85rem}
      </style>
      <div class="dab-sees"><div><b>What the tuner sees</b><br>One 1.536 MHz block at ${fc} MHz: about 2 million I/Q number pairs per second that look like noise, carrying the whole ensemble (${SERVICES.length} services) at once.</div>
        <div><b>What comes out</b><br>${audio ? `One station: ${s[1]} kbit/s DAB+ audio (HE-AAC), its scrolling text (DLS) and slideshow pictures.` : `One data service: ${s[1]} kbit/s of ${esc(s[0].toLowerCase())} for the head unit; no sound.`} The other ${SERVICES.length - 1} services are skipped after the FFT.</div></div>
      <div class="dab-flow">
        <div class="dab-card"><h3><span class="dab-step">1</span>At the antenna</h3>${spectrumSvg(fc, v.snr)}${bandStrip(fc, {lo: 150, hi: 260, n: 3, caption: "The block is one slot in DAB Band III, a range (from the RF bands chart)"})}
          <p>One DAB block is 1.536 MHz wide; blocks sit 1.712 MHz apart in Band III (174–240 MHz). Inside are 1536 carriers, 1 kHz apart (transmission mode I).</p></div>
        <div class="dab-card"><h3><span class="dab-step">2</span>What the tuner hands over: I/Q</h3>${iqTraceSvg(iq)}
          <p><b>I/Q in plain words:</b> the tuner shifts the block down to around 0 Hz with two copies of its oscillator, 90° apart. The first output is I (in-phase), the second Q (quadrature). Each I/Q pair is one arrow: its length is the signal strength and its angle the phase at that instant. With only one output, a carrier 1 kHz above the tuned frequency and one 1 kHz below would look the same; with I and Q the demodulator can tell them apart. In a car radio the tuner (Si4790x / Si4796x) sends these samples digitally (ZIF I/Q) to the DAB coprocessor (Si469xx); a consumer Si468x does both in one chip.</p></div>
        <div class="dab-card"><h3><span class="dab-step">3</span>OFDM: FFT, then the carriers</h3><div class="dab-pair">${scatterSvg(raw, "raw I/Q: a cloud", C.grey)}${scatterSvg(cons, "after FFT: DQPSK", C.blue, ideal)}</div>
          <p>Every 1.246 ms (1 ms symbol + 246 µs guard against echoes) the demodulator takes 2048 samples and runs an FFT: out come 1536 carriers. Each carrier's <i>change</i> of phase from the last symbol is one of four values (differential QPSK), i.e. 2 bits. Noise spreads the four clusters; at ${num(v.snr)} dB they are ${margin >= 2 ? "well apart" : margin >= 0 ? "starting to touch" : "merged"}.</p></div>
        <div class="dab-card"><h3><span class="dab-step">4</span>The ensemble (multiplex)</h3>${ensembleSvg(rows, sel, used)}
          <ul class="dab-list">${list}</ul>
          <p>After de-interleaving and the Viterbi decoder, a 96 ms frame holds the FIC (the table of contents: which services, which sub-channel, which protection) and the MSC: 864 capacity units (CU) every 24 ms = 2.304 Mbit/s gross. At ${esc(v.eep)} each kbit/s costs ${cuPer} CU: this ensemble uses ${used} of 864 CU${fits ? "" : ": it does not fit, so drop a service or choose weaker protection"}.</p></div>
        <div class="dab-card"><h3><span class="dab-step">5</span>What you hear and see</h3>
          ${audio ? `<p><b>${esc(s[0])}</b> · DAB+ HE-AAC, ${s[1]} kbit/s · ${esc(state[0])}</p>${slideSvg(s[0], sel)}<p class="dab-dls">${esc(s[3])}</p>
          <p>Only the selected sub-channel is decoded: Reed-Solomon error correction, then the AAC decoder makes 48 kHz audio for the I2S output. Text (DLS) and pictures (MOT slideshow) travel inside the audio stream as programme-associated data.</p>`
            : `<p><b>${esc(s[0])}</b> · ${s[1]} kbit/s data, no audio</p><p class="dab-dls">${esc(s[3])}</p><p>Data services go to the navigation or the programme guide instead of the speakers.</p>`}</div>
      </div>
      <p class="small">Thresholds for "clean", "bubbling" and "muted" are rough Gaussian-channel figures ${est}; in a moving car, fading needs several dB more. The made-up ensemble is for illustration.</p>`;
      return {
        outputs: [["Block", `${BLOCKS.find(b => b[1] === fc)[0]} · ${fc} MHz`], ["Carriers", "1536 × 1 kHz, DQPSK"], ["Symbol", "1 ms + 246 µs guard"],
          ["Ensemble capacity used", `${used} / 864 CU`, fits ? "ok" : "bad"], ["Selected", `${s[0]} · ${s[1]} kbit/s`], ["Reception", state[0], state[1]]],
        eq: "T<sub>s</sub> = T<sub>u</sub> + Δ = 1 ms + 246 µs &nbsp;·&nbsp; frame 96 ms = null + phase reference + 3 FIC + 72 MSC symbols &nbsp;·&nbsp; MSC = 72 × 1536 carriers × 2 bit = 4 × 864 CU × 64 bit &nbsp;·&nbsp; sub-channel size (EEP-A) = k × bit rate",
        eqn: `72 × 1536 × 2 = ${msc} bit per frame = 4 × 864 × 64 → ${msc} bit / 96 ms = 2.304 Mbit/s · ${s[0]}: ${s[1]} kbit/s × ${cuPer} = ${rows[sel].cu} CU at code rate ${rate} · need ≈ ${need} dB C/N (est), have ${num(v.snr)} dB`,
        html, nochart: true,
        note: "Sampling at 2.048 MS/s gives exactly 2048 samples per 1 ms symbol, so one FFT per symbol. The tuner never sees 'stations': it sees one block; the station list comes from the FIC after decoding.",
      };
    },
    related: [["AM vs FM modulation", "#mod"], ["Cascaded noise figure", "#nf"], ["Broadcast configurations", "/broadcast"]],
  });
});
