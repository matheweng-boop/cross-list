// Interactive visual "DAB: from I/Q samples to the ensemble and the audio" (owner, 23 Oct 2026: "add I/Q data and the
// I/Q data description for DAB ... a visualization of DAB ensembles, how it is decoded and what the tuner sees vs. what
// the audio is that is produced"). Registers with the visuals engine in visuals.js (window.VZ_ADD). Transmission mode I
// numbers from ETSI EN 300 401; the example ensemble is made up; thresholds marked est are BizDev's own.
(window.VZ_ADD = window.VZ_ADD || []).push(({V, C, num, esc, log10, bandStrip}) => {
  // Band III block raster (ETSI EN 300 401, centre frequencies in MHz); the extra N blocks 10N, 11N and 12N are left out
  const BLOCKS = [["5A", 174.928], ["5B", 176.640], ["5C", 178.352], ["5D", 180.064], ["6A", 181.936], ["6B", 183.648], ["6C", 185.360], ["6D", 187.072],
    ["7A", 188.928], ["7B", 190.640], ["7C", 192.352], ["7D", 194.064], ["8A", 195.936], ["8B", 197.648], ["8C", 199.360], ["8D", 201.072],
    ["9A", 202.928], ["9B", 204.640], ["9C", 206.352], ["9D", 208.064], ["10A", 209.936], ["10B", 211.648], ["10C", 213.360], ["10D", 215.072],
    ["11A", 216.928], ["11B", 218.640], ["11C", 220.352], ["11D", 222.064], ["12A", 223.936], ["12B", 225.648], ["12C", 227.360], ["12D", 229.072],
    ["13A", 230.784], ["13B", 232.496], ["13C", 234.208], ["13D", 235.776], ["13E", 237.488], ["13F", 239.200]];
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

  // ------------------------------------------------------------------ blocks and ensembles (owner, 25 Oct 2026: "Can you
  // visualize the DAB Blocks and Ensembles better"): the Band III raster, the 96 ms transmission frame (FIC + MSC) and
  // one 24 ms CIF as a map of 864 capacity units with each service's sub-channel. Click a block or a service.
  const SHORT = ["City Pop", "News", "Classics", "Sport", "Jazz", "Rock", "Dance", "Kids", "Local", "Chill", "TPEG", "EPG"];
  function rasterSvg(fc) {
    const W = 340, H = 86, x = f => 8 + ((f - 174) / 66) * (W - 16);
    const rects = BLOCKS.map(([b, f]) => { const on = f === fc;
      return `<g class="dab-rb" data-dab-blk="${f}" tabindex="0" role="button" aria-label="Block ${b}, ${f} MHz"${on ? ' aria-pressed="true"' : ""}><title>${b} · ${f} MHz</title>`
        + `<rect x="${x(f - 0.856).toFixed(1)}" y="22" width="${(x(f + 0.856) - x(f - 0.856)).toFixed(1)}" height="38" fill="transparent"/>`
        + `<rect x="${x(f - 0.768).toFixed(1)}" y="26" width="${(x(f + 0.768) - x(f - 0.768)).toFixed(1)}" height="30" rx="1" fill="${on ? C.blue : "#9fb4cc"}" opacity="${on ? 1 : 0.55}"${on ? ' stroke="#1d2228" stroke-width="1.2"' : ""}/></g>`; }).join("");
    const chans = [5, 6, 7, 8, 9, 10, 11, 12, 13].map(n => { const fs = BLOCKS.filter(([b]) => parseInt(b, 10) === n).map(([, f]) => f);
      const a = x(Math.min(...fs) - 0.768), b = x(Math.max(...fs) + 0.768);
      return `<line x1="${a.toFixed(1)}" x2="${b.toFixed(1)}" y1="63" y2="63" stroke="#8a94a3"/><text x="${((a + b) / 2).toFixed(1)}" y="73" text-anchor="middle" class="dab-t">${n}</text>`; }).join("");
    const sel = BLOCKS.find(b => b[1] === fc);
    return `<svg viewBox="0 0 ${W} ${H}" class="dab-svg" role="group" aria-label="DAB Band III block raster, click a block">
      <text x="${x(fc).toFixed(1)}" y="16" text-anchor="${fc > 222 ? "end" : fc < 192 ? "start" : "middle"}" class="dab-t" font-weight="700">${sel[0]} · ${fc} MHz · 1.536 MHz wide</text>${rects}${chans}
      <text x="8" y="${H - 1}" class="dab-t">174 MHz</text><text x="${W / 2}" y="${H - 1}" text-anchor="middle" class="dab-t">channels 5–13, blocks A–D (13: A–F)</text><text x="${W - 8}" y="${H - 1}" text-anchor="end" class="dab-t">240 MHz</text></svg>`;
  }
  function frameSvg() {  // transmission mode I: 96 ms = null (1.297 ms) + phase reference + 3 FIC + 72 MSC symbols (1.246 ms each)
    const W = 340, x = ms => 8 + (ms / 96) * (W - 16), Ts = 1.246, nul = 1.297, fic0 = nul + Ts, msc0 = fic0 + 3 * Ts;
    const cif = k => { const a = msc0 + k * 18 * Ts, b = a + 18 * Ts;
      return `<rect x="${x(a).toFixed(1)}" y="30" width="${(x(b) - x(a) - 0.8).toFixed(1)}" height="22" fill="${C.green}" opacity="${k === 0 ? 0.75 : 0.35}"/><text x="${((x(a) + x(b)) / 2).toFixed(1)}" y="45" text-anchor="middle" class="dab-t">CIF ${k + 1} · 24 ms</text>`; };
    return `<svg viewBox="0 0 ${W} 94" class="dab-svg" role="img" aria-label="DAB transmission frame of 96 ms">
      <rect x="${x(0)}" y="30" width="${(x(nul) - x(0)).toFixed(1)}" height="22" fill="#1d2228"/><rect x="${x(nul).toFixed(1)}" y="30" width="${(x(fic0) - x(nul)).toFixed(1)}" height="22" fill="${C.grey}"/>
      <rect x="${x(fic0).toFixed(1)}" y="30" width="${(x(msc0) - x(fic0)).toFixed(1)}" height="22" fill="${C.orange}"/>${[0, 1, 2, 3].map(cif).join("")}
      <path d="M${x(nul / 2).toFixed(1)} 30 L12 12" stroke="#1d2228" fill="none"/><text x="12" y="9" class="dab-t">null symbol + phase reference (sync)</text>
      <path d="M${x((fic0 + msc0) / 2).toFixed(1)} 30 L${x(14).toFixed(1)} 22" stroke="${C.orange}" fill="none"/><text x="${x(14.5).toFixed(1)}" y="24" class="dab-t" fill="${C.orange}">FIC: the table of contents (3 symbols)</text>
      <text x="${x(0)}" y="64" class="dab-t">0</text><text x="${x(96)}" y="64" text-anchor="end" class="dab-t">96 ms</text>
      <text x="${x(50)}" y="64" text-anchor="middle" class="dab-t" fill="${C.green}">MSC: the programmes (72 symbols)</text>
      <path d="M${x(msc0).toFixed(1)} 69 L8 80 M${x(msc0 + 18 * Ts).toFixed(1)} 69 L${W - 8} 80" stroke="#8a94a3" stroke-dasharray="3 2" fill="none"/>
      <text x="${W / 2}" y="90" text-anchor="middle" class="dab-t">each CIF, zoomed below: 864 capacity units (CU) of 64 bits</text></svg>`;
  }
  function cifSvg(rows, sel, used) {
    const W = 340, scale = Math.max(864, used), x = cu => 8 + (cu / scale) * (W - 16);
    let at = 0;
    const segs = rows.map((r, i) => { const a = x(at), b = x(at + r.cu); r.start = at; at += r.cu; const on = i === sel, w = b - a;
      const lab = w > 20 ? `<text x="${((a + b) / 2).toFixed(1)}" y="31" text-anchor="middle" class="dab-t dab-tw">${esc(SHORT[i].slice(0, Math.floor(w / 5.2)))}</text>` : "";
      return `<g class="dab-sv" data-dab-svc="${i}" role="button" tabindex="0" aria-label="${esc(SERVICES[i][0])}: sub-channel ${i}, ${r.cu} CU"${on ? ' aria-pressed="true"' : ""}><title>${esc(SERVICES[i][0])} · ${r.cu} CU</title><rect x="${a.toFixed(1)}" y="12" width="${Math.max(0.8, w - 0.8).toFixed(1)}" height="30" fill="${COL[i]}" opacity="${on ? 1 : 0.6}"${on ? ' stroke="#1d2228" stroke-width="2"' : ""}/>${lab}</g>`; }).join("");
    const free = used < 864 ? `<rect x="${x(used).toFixed(1)}" y="12" width="${(x(864) - x(used)).toFixed(1)}" height="30" fill="#eef1f4" stroke="#d5dae0" stroke-dasharray="3 2"/><text x="${((x(used) + x(864)) / 2).toFixed(1)}" y="31" text-anchor="middle" class="dab-t">free ${864 - used}</text>` : "";
    const lim = used > 864 ? `<line x1="${x(864).toFixed(1)}" x2="${x(864).toFixed(1)}" y1="8" y2="46" stroke="${C.red}" stroke-width="2"/>` : "";
    const r = rows[sel], a = x(r.start), b = x(r.start + r.cu);
    return `<svg viewBox="0 0 ${W} 68" class="dab-svg" role="group" aria-label="One CIF: 864 capacity units shared by the sub-channels, click a service">${segs}${free}${lim}
      <path d="M${a.toFixed(1)} 44 v6 h${(b - a).toFixed(1)} v-6" stroke="#1d2228" fill="none"/><text x="${Math.min(W - 120, Math.max(8, a)).toFixed(1)}" y="61" class="dab-t" font-weight="700">sub-channel ${sel}: CU ${r.start}–${r.start + r.cu - 1}</text>
      <text x="8" y="8" class="dab-t">CU 0</text><text x="${W - 8}" y="8" text-anchor="end" class="dab-t">${used > 864 ? `${used} CU: does not fit (limit 864)` : "CU 863"}</text></svg>`;
  }
  const sid = i => "0x" + (SERVICES[i][2] === "audio" ? 0xD210 + i * 0x11 : 0xE0D210 + i).toString(16).toUpperCase();

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
    setup(el, render, setVals) {  // clicks on a Band III block or a service in the ensemble pictures
      el.hidden = true;
      const more = el.parentElement.querySelector(".vz-more");
      const pick = t => {
        const b = t.closest("[data-dab-blk]"), s = t.closest("[data-dab-svc]");
        if (b) setVals({blk: b.dataset.dabBlk}); else if (s) setVals({svc: s.dataset.dabSvc}); else return false;
        render();
        return true;
      };
      more.addEventListener("click", e => pick(e.target));
      more.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && pick(e.target)) e.preventDefault(); });
    },
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
      const audio = s[2] === "audio", blkName = BLOCKS.find(b => b[1] === fc)[0];
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
      <section class="dab-ens" aria-label="Blocks and ensembles">
        <h3>Blocks and ensembles</h3>
        <p class="small">A DAB <b>block</b> is one 1.536 MHz slot on a fixed raster in Band III (blocks 5A to 13F). One block carries exactly one <b>ensemble</b> (also called a multiplex): a bundle of about 10–18 stations and data services from one operator, sent together on one frequency. Click a block, then a service.</p>
        <div class="dab-ens-g">
          <div class="dab-ens-c"><h4>1 · Band III: the block raster</h4>${rasterSvg(fc)}
            <p class="small">${BLOCKS.length} blocks, 1.712 MHz apart. A region may use several blocks (several ensembles); the tuner tunes to one block at a time.</p></div>
          <div class="dab-ens-c"><h4>2 · Block ${blkName}: one ensemble, framed every 96 ms</h4>${frameSvg()}
            <p class="small">The <b>FIC</b> (fast information channel) lists the ensemble "BizDev Demo" (made up) and each service: name, service ID, which sub-channel, where it starts and how it is protected. The <b>MSC</b> (main service channel) carries the programmes themselves.</p></div>
          <div class="dab-ens-c dab-wide"><h4>3 · Inside one CIF: each service has its own sub-channel</h4>${cifSvg(rows, sel, used)}
            <div class="dab-ens-two"><table class="dab-tbl small"><thead><tr><th>Service</th><th>kbit/s</th><th>CU</th><th>start</th></tr></thead><tbody>
              ${SERVICES.map((x, i) => `<tr data-dab-svc="${i}" tabindex="0" role="button"${i === sel ? ' class="on" aria-pressed="true"' : ""}><td><i style="background:${COL[i]}"></i>${esc(x[0])}${x[2] === "data" ? " <span class=\"muted\">data</span>" : ""}</td><td>${x[1]}</td><td>${rows[i].cu}</td><td>${rows[i].start}</td></tr>`).join("")}
              <tr class="dab-sum"><td>Total</td><td>${SERVICES.reduce((a, x) => a + x[1], 0)}</td><td>${used}</td><td>of 864</td></tr></tbody></table>
            <div class="dab-detail" style="border-color:${COL[sel]}"><b>${esc(s[0])}</b> <span class="muted small">${audio ? "audio service, DAB+ (HE-AAC v2)" : "data service, packet mode"}</span>
              <dl><dt>Service ID (SId)</dt><dd>${sid(sel)}</dd><dt>Sub-channel</dt><dd>${sel}</dd><dt>Start address</dt><dd>CU ${rows[sel].start}</dd><dt>Size</dt><dd>${rows[sel].cu} CU = ${rows[sel].cu * 64} bit per 24 ms</dd>
                <dt>Bit rate</dt><dd>${s[1]} kbit/s</dd><dt>Protection</dt><dd>EEP-${esc(v.eep)}, code rate ${rate}</dd><dt>Share of ensemble</dt><dd>${num((100 * rows[sel].cu) / 864)} % of the CUs</dd></dl>
              <p class="small">${rows[sel].cu} CU = ${s[1]} kbit/s × ${cuPer} CU per kbit/s at EEP-${esc(v.eep)}: stronger protection costs more CUs for the same bit rate.</p></div></div></div>
        </div>
      </section>
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
