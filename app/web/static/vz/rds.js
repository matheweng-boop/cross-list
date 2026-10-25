// Interactive visual "RDS: the data under FM" (owner, 25 Oct 2026: "Make a section for RDS"). Where RDS sits in the
// FM MPX signal, how a group is built (4 blocks of 16 data bits + 10 check bits), what the fields mean (PI, PTY, TP/TA,
// PS name, AF list, RadioText, clock time) and what the car radio does with them; RBDS for the US. Group and block
// layout, offset words and check polynomial as in the RDS standard (IEC 62106); the example station is made up.
// The bit maths sits in window.VZ_RDS (plain functions), so the tests can check it directly.
(() => {
  // ------------------------------------------------------------------ bit maths
  const POLY = 0x5B9;  // g(x) = x^10 + x^8 + x^7 + x^5 + x^4 + x^3 + 1
  const OFFSET = {A: 0x0FC, B: 0x198, C: 0x168, "C'": 0x350, D: 0x1B4};
  function check(info) {  // 10-bit CRC of a 16-bit information word (remainder of info · x^10 mod g)
    let r = (info & 0xFFFF) << 10;
    for (let b = 25; b >= 10; b--) if (r & (1 << b)) r ^= POLY << (b - 10);
    return r & 0x3FF;
  }
  const checkword = (info, off) => check(info) ^ OFFSET[off];
  const syndromeOk = (info, cw, off) => checkword(info, off) === cw;  // what the receiver tests for each block
  const afCode = mhz => Math.round((mhz - 87.5) * 10);  // 1..204 -> 87.6..107.9 MHz
  const afMhz = code => +(87.5 + code / 10).toFixed(1);
  const mjd = (y, m, d) => Math.round(Date.UTC(y, m - 1, d) / 86400000) + 40587;  // Modified Julian Day
  function fromMjd(n) { const t = new Date((n - 40587) * 86400000); return [t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()]; }
  // RBDS (US): PI from the call letters (K: 4096 + …, W: 21672 + …; A = 0 … Z = 25)
  function rbdsPi(call) {
    const s = String(call).toUpperCase(), base = {K: 4096, W: 21672}[s[0]], n = c => c.charCodeAt(0) - 65;
    if (!base || !/^[KW][A-Z]{3}$/.test(s)) return null;
    return base + 676 * n(s[1]) + 26 * n(s[2]) + n(s[3]);
  }
  const PTY = {  // a few codes: the same number means different things in RDS (Europe) and RBDS (North America)
    1: ["News", "News"], 3: ["Information", "Sports"], 10: ["Pop Music", "Country"], 5: ["Education", "Rock"],
  };
  // st: {pi, tp, ta, pty, ps, af: [MHz], rt, ab, ms, stereo, utc: [y, m, d, h, min], offsetHalfHours}
  // returns 4 blocks: {off, info, cw, fields: [[name, hi, lo, value, meaning]]}
  function group(type, seg, st) {
    const b2 = (code, ver, low5) => ((code & 15) << 12) | ((ver & 1) << 11) | ((st.tp & 1) << 10) | ((st.pty & 31) << 5) | (low5 & 31);
    const common = code => [["Group type", 15, 12, code, `${code}A`], ["Version", 11, 11, 0, "A"], ["TP", 10, 10, st.tp, st.tp ? "carries traffic news" : "no traffic news"],
      ["PTY", 9, 5, st.pty, (PTY[st.pty] || ["", ""])[st.rbds ? 1 : 0]]];
    const blk = (off, info, fields) => ({off, info, cw: checkword(info, off), fields});
    const piB = blk("A", st.pi, [["PI", 15, 0, st.pi, `station code 0x${st.pi.toString(16).toUpperCase().padStart(4, "0")}`]]);
    const ch = (s, i) => (s.charCodeAt(i) || 32) & 255;
    if (type === "0A") {
      seg &= 3;
      const di = [st.dynpty || 0, 0, 0, st.stereo ? 1 : 0][seg];  // segment 0 carries d3 … segment 3 carries d0
      const afs = [224 + st.af.length, ...st.af.map(afCode)], pair = [afs[(2 * seg) % afs.length], afs[(2 * seg + 1) % afs.length] ?? 205];
      const b = b2(0, 0, ((st.ta & 1) << 4) | ((st.ms & 1) << 3) | (di << 2) | seg);
      return [piB,
        blk("B", b, [...common(0), ["TA", 4, 4, st.ta, st.ta ? "traffic announcement on air now" : "no announcement now"], ["M/S", 3, 3, st.ms, st.ms ? "music" : "speech"],
          ["DI", 2, 2, di, `${["d3 dynamic PTY", "d2 compressed", "d1 artificial head", "d0 stereo"][seg]} = ${di}`], ["Segment", 1, 0, seg, `PS characters ${2 * seg + 1}–${2 * seg + 2}`]]),
        blk("C", (pair[0] << 8) | pair[1], pair.map((c, k) => [`AF ${k + 1}`, 15 - 8 * k, 8 - 8 * k, c, c >= 224 && c <= 249 ? `${c - 224} alternative frequencies follow` : c >= 1 && c <= 204 ? `${afMhz(c)} MHz` : "filler"])),
        blk("D", (ch(st.ps, 2 * seg) << 8) | ch(st.ps, 2 * seg + 1), [0, 1].map(k => [`PS char ${2 * seg + k + 1}`, 15 - 8 * k, 8 - 8 * k, ch(st.ps, 2 * seg + k), `"${String.fromCharCode(ch(st.ps, 2 * seg + k))}"`]))];
    }
    if (type === "2A") {
      seg &= 15;
      const rt = (st.rt.length < 64 ? st.rt + "\r" : st.rt.slice(0, 64)).padEnd(64, " ");
      const c = k => rt.charCodeAt(4 * seg + k) & 255, show = k => (c(k) === 13 ? "end of text (CR)" : `"${String.fromCharCode(c(k))}"`);
      return [piB,
        blk("B", b2(2, 0, ((st.ab & 1) << 4) | seg), [...common(2), ["Text A/B", 4, 4, st.ab, "flips when a new text starts: clear the display"], ["Segment", 3, 0, seg, `RadioText characters ${4 * seg + 1}–${4 * seg + 4}`]]),
        blk("C", (c(0) << 8) | c(1), [0, 1].map(k => [`RT char ${4 * seg + k + 1}`, 15 - 8 * k, 8 - 8 * k, c(k), show(k)])),
        blk("D", (c(2) << 8) | c(3), [2, 3].map((k, j) => [`RT char ${4 * seg + k + 1}`, 15 - 8 * j, 8 - 8 * j, c(k), show(k)]))];
    }
    // 4A: clock time and date (UTC + local offset in half hours)
    const [y, m, d, h, mi] = st.utc, n = mjd(y, m, d), off = st.offsetHalfHours, sign = off < 0 ? 1 : 0;
    return [piB,
      blk("B", b2(4, 0, (n >> 15) & 3), [...common(4), ["spare", 4, 2, 0, "0"], ["MJD bits 16–15", 1, 0, (n >> 15) & 3, "date, top bits"]]),
      blk("C", ((n & 0x7FFF) << 1) | ((h >> 4) & 1), [["MJD bits 14–0", 15, 1, n & 0x7FFF, `day number ${n} = ${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`], ["Hour bit 4", 0, 0, (h >> 4) & 1, "hour, top bit"]]),
      blk("D", ((h & 15) << 12) | ((mi & 63) << 6) | (sign << 5) | (Math.abs(off) & 31), [["Hour bits 3–0", 15, 12, h & 15, `${h} h UTC`], ["Minute", 11, 6, mi, `${mi} min`],
        ["Offset sign", 5, 5, sign, sign ? "minus" : "plus"], ["Offset", 4, 0, Math.abs(off), `${Math.abs(off) / 2} h → local ${String((h + off / 2 + 24) % 24).padStart(2, "0")}:${String(mi).padStart(2, "0")}`]])];
  }
  const bits = (v, n) => v.toString(2).padStart(n, "0");
  window.VZ_RDS = {check, checkword, syndromeOk, afCode, afMhz, mjd, fromMjd, rbdsPi, group, bits, OFFSET, PTY};

  // ------------------------------------------------------------------ the visual
  (window.VZ_ADD = window.VZ_ADD || []).push(({V, C, num}) => {
    const {esc, lin, rnd, gauss, sumDb, brick, bell, spec, plot} = window.VZ_SKETCH;
    const STATION = {pi: 0xD3C2, ps: "BIZ FM  ", af: [89.1, 94.6, 101.3], rt: "Traffic: 10 min delay on the ring road. Next: the evening show", utc: [2026, 10, 25, 17, 42], offsetHalfHours: 2, ms: 1, stereo: 1, ab: 0};
    const CALL = "WXYZ";
    const FCOL = ["#1f5fa8", "#c2410c", "#15803d", "#7e22ce", "#0f766e", "#b91c1c", "#a16207", "#be185d"];
    const est = '<span class="kn-est" title="BizDev\'s own reasoning, not from a source">est</span>';

    function mpxSvg() {
      const r = rnd(41), pts = spec(0, 62, f => sumDb(f > 0.03 && f < 15 ? -14 - 0.6 * f : -95, bell(f, 19, 0.15, -22),
        f > 23 && f < 53 ? -28 - 0.6 * Math.abs(f - 38) + (Math.abs(f - 38) < 0.4 ? -40 : 0) : -95, brick(f, 57, 2.4, -40, 3) + (Math.abs(f - 57) < 0.3 ? -12 : 0), -85), 420).map(([f, d]) => [f, d + gauss(r)]);
      return plot({label: "FM MPX spectrum with RDS at 57 kHz", w: 340, h: 150, x: [0, 62], y: [-80, 0], xt: [[0, "0"], [15, "15"], [19, "19"], [23, "23"], [38, "38"], [53, "53"], [57, "57"]],
        yt: [[0, "0"], [-40, "−40"], [-80, "−80"]], xlab: "frequency in the MPX signal after the FM discriminator (kHz)", ylab: "dB",
        bands: [[0.03, 15, "mono L+R", "#1f5fa8"], [23, 53, "stereo L−R", "#7e22ce"], [54.6, 59.4, "RDS", "#15803d"]], vlines: [[19, "pilot", "#b42318"]],
        series: [{pts, color: "#1f5fa8", fill: true}]});
    }
    function blocksHtml(g) {
      return g.map((b, bi) => {
        const cells = [];
        for (let i = 15; i >= 0; i--) {
          const fi = b.fields.findIndex(([, hi, lo]) => i <= hi && i >= lo);
          cells.push(`<span class="rd-b" style="--c:${FCOL[(fi + bi * 2) % FCOL.length]}" title="${esc(b.fields[fi][0])}">${(b.info >> i) & 1}</span>`);
        }
        const cw = bits(b.cw, 10).split("").map(x => `<span class="rd-b rd-cw">${x}</span>`).join("");
        const leg = b.fields.map(([n, hi, lo, val, mean], fi) => `<tr><td><i style="background:${FCOL[(fi + bi * 2) % FCOL.length]}"></i>${esc(n)}</td><td class="rd-mono">${hi === lo ? `bit ${hi}` : `bits ${hi}–${lo}`}</td><td class="rd-mono">${val}</td><td>${esc(mean)}</td></tr>`).join("");
        return `<div class="rd-blk"><div class="rd-bh"><b>Block ${bi + 1}</b> <span class="muted small">offset ${b.off} · info 0x${b.info.toString(16).toUpperCase().padStart(4, "0")} · check ${bits(b.cw, 10)}</span></div>
          <div class="rd-bits" aria-label="26 bits of block ${bi + 1}">${cells.join("")}<span class="rd-sep"></span>${cw}</div>
          <table class="rd-leg small"><tbody>${leg}</tbody></table></div>`;
      }).join("");
    }
    function radioHtml(st, type, seg) {
      const psDone = type === "0A" ? st.ps.slice(0, 2 * (seg + 1)).padEnd(8, "_") : st.ps;
      const rtDone = type === "2A" ? st.rt.slice(0, 4 * (seg + 1)) : st.rt;
      const local = (st.utc[3] + st.offsetHalfHours / 2) % 24;
      return `<div class="rd-radio" aria-label="What the car radio shows"><div class="rd-ps">${esc(psDone)}</div>
        <div class="rd-ind"><span class="${st.tp ? "on" : ""}">TP</span><span class="${st.ta ? "on ta" : ""}">TA</span><span class="on">${esc((PTY[st.pty] || ["", ""])[st.rbds ? 1 : 0])}</span><span>${String(local).padStart(2, "0")}:${String(st.utc[4]).padStart(2, "0")}</span></div>
        <div class="rd-rt">${esc(rtDone)}${type === "2A" && rtDone.length < st.rt.length ? "▌" : ""}</div></div>`;
    }

    V.push({
      id: "rds", group: "Broadcast radio", title: "RDS: the data under FM (PS name, traffic, AF, clock)",
      explains: [["Broadcast radio tuners and demodulators", "/knowledge#p-tuners"], ["Si4705 / Si4735 RDS receivers", "/find?q=Si4735"], ["Si4706 RDS data receiver", "/find?q=Si4706"]],
      physics: [["AM and FM", "phys_am_fm"]],
      lead: "RDS (Radio Data System; RBDS in the US) is a slow data stream hidden in every FM station: a 57 kHz subcarrier above the stereo signal, 1187.5 bit/s. It gives the station name on the display, traffic announcements and the list of other frequencies the car radio switches to. Pick a group type and step through its segments to see the bits decoded.",
      controls: [
        {k: "grp", label: "Group type", type: "select", options: [["0A", "0A: station name (PS), TA, AF list"], ["2A", "2A: RadioText (64 characters)"], ["4A", "4A: clock time and date (CT)"]], value: "0A"},
        {k: "seg", label: "Segment (which part of the name / text)", min: 0, max: 15, step: 1, value: 0},
        {k: "reg", label: "Region", type: "select", options: [["rds", "Europe and most countries: RDS"], ["rbds", "North America: RBDS"]], value: "rds"},
        {k: "pty", label: "Programme type code (PTY)", type: "select", options: [["10", "10"], ["1", "1"], ["3", "3"], ["5", "5"]], value: "10"},
        {k: "ta", label: "Traffic announcement (TA)", type: "select", options: [["0", "off: normal programme"], ["1", "on: announcement now"]], value: "0"},
      ],
      compute(v) {
        const rbds = v.reg === "rbds", piUs = rbdsPi(CALL);
        const st = {...STATION, pi: rbds ? piUs : STATION.pi, tp: 1, ta: +v.ta, pty: +v.pty, rbds};
        const maxSeg = v.grp === "0A" ? 3 : v.grp === "2A" ? Math.ceil((st.rt.length + 1) / 4) - 1 : 0, seg = Math.min(Math.round(v.seg), maxSeg);
        const g = group(v.grp, seg, st), ok = g.every(b => syndromeOk(b.info, b.cw, b.off));
        const ptyName = (PTY[st.pty] || ["", ""])[rbds ? 1 : 0], ptyOther = (PTY[st.pty] || ["", ""])[rbds ? 0 : 1];
        const groupMs = 104 / 1187.5 * 1000;
        const seq = ["0A", "0A", "2A", "0A", "2A", "0A", "2A", "0A", "2A", "0A", "4A"].map((t, i) => `<span class="rd-g${t === v.grp ? " on" : ""}">${t}</span>`).join("");
        const html = `<div class="rd">
          <div class="rd-two"><div><h3>Where RDS sits</h3>${mpxSvg()}
            <p class="small">After the FM discriminator the station's baseband (MPX) holds mono audio 0–15 kHz, the 19 kHz pilot, stereo 23–53 kHz around a suppressed 38 kHz carrier, and RDS at 57 kHz (3 × the pilot), about ±2.4 kHz wide. RDS is so quiet it does not disturb the sound. Illustrative levels.</p></div>
          <div><h3>On the display</h3>${radioHtml(st, v.grp, seg)}
            <p class="small">${v.grp === "0A" ? `The 8-character name arrives 2 characters per 0A group: after segment ${seg} the radio has "${esc(st.ps.slice(0, 2 * (seg + 1)).trim())}". A full name takes 4 groups, about ${num(4 * groupMs)} ms.` : v.grp === "2A" ? `RadioText arrives 4 characters per 2A group, up to 64 characters (segments 0–15); this text ends with a CR at segment ${maxSeg}.` : "One 4A group a minute sets the clock: date as a day number (MJD), UTC hour and minute, and the local offset in half hours."}</p></div></div>
          <h3>Group ${esc(v.grp)}, segment ${seg}: 4 blocks × 26 bits = 104 bits, ${num(groupMs)} ms</h3>
          <p class="small">Each block is 16 data bits plus a 10-bit check word (CRC plus a fixed offset word A, B, C or D). The offset tells the receiver where the block sits in the group, so it can lock on without any other framing; ${ok ? "all four check words here are correct" : "a check word failed"}. Coloured bits: fields; grey: check word.</p>
          <div class="rd-blocks">${blocksHtml(g)}</div>
          <p class="small">A second of RDS, about ${num(1187.5 / 104)} groups: <span class="rd-seq">${seq}</span> (a typical mix; the station chooses).</p>
          <div class="rd-two"><div><h3>What the car radio does with it</h3><ul class="small rd-ul">
            <li><b>PS name:</b> shows "${esc(st.ps.trim())}" instead of a frequency.</li>
            <li><b>AF list (alternative frequencies):</b> ${st.af.join(", ")} MHz carry the same programme. When the signal fades, the radio checks these (a background tuner does it without a gap) and switches to the one with the same PI code.</li>
            <li><b>PI code</b> 0x${st.pi.toString(16).toUpperCase()}: the station's identity; the radio only switches to a frequency with the same PI.</li>
            <li><b>TP / TA:</b> TP = 1 says this station carries traffic news. When TA goes to 1 ${st.ta ? "(now)" : ""}, the radio interrupts the CD, phone music or another source, raises the volume and returns when TA drops.</li>
            <li><b>PTY:</b> code ${st.pty} = "${esc(ptyName)}" here (it means "${esc(ptyOther)}" in ${rbds ? "RDS" : "RBDS"}); used to search for a programme type.</li>
            <li><b>CT:</b> sets the dashboard clock. <b>RadioText:</b> song title or news line.</li></ul></div>
          <div><h3>RBDS in North America</h3><p class="small">RBDS is the US version of the same signal: same 57 kHz, same 1187.5 bit/s, same groups. Two differences matter in a car radio: the programme type list is different (code 10 is "Pop Music" in RDS but "Country" in RBDS), and the PI code is worked out from the call letters. Example: call letters ${CALL} → 21672 + 676 × X + 26 × Y + Z = ${piUs} = 0x${piUs.toString(16).toUpperCase()} (made-up station). AF lists are rare in the US because stations seldom have repeaters ${est}.</p>
            <p class="small"><b>On our chips:</b> the Si4705 and Si4735 receivers list an RDS / RBDS decoder, the Si4706 is a dedicated RDS / RBDS data receiver (TMC / ODA), and the car receivers (Si479xx) list an on-chip soft-decision RDS / RBDS demodulator and decoder (data shorts). A background FM tuner keeps the RDS station list fresh (configurator job "FM scan"). <a href="/broadcast">Tuners & demodulators</a> · <a href="#flow">Signal flow (FM)</a></p></div></div>
          <p class="small muted">Group layout, offset words and check polynomial as in the RDS standard (IEC 62106). The station, PI code, texts and frequencies are made up for illustration.</p></div>`;
        return {
          outputs: [["Subcarrier", "57 kHz = 3 × 19 kHz"], ["Bit rate", "1187.5 bit/s"], ["Group", `${v.grp} · segment ${seg}`], ["PI", `0x${st.pi.toString(16).toUpperCase()}`], ["PTY", `${st.pty} = ${ptyName}`], ["Check words", ok ? "all OK" : "error", ok ? "ok" : "bad"]],
          eq: "bit rate = 57 kHz / 48 = 1187.5 bit/s &nbsp;·&nbsp; group = 4 blocks × (16 data + 10 check) = 104 bits &nbsp;·&nbsp; check = (data · x<sup>10</sup> mod g(x)) ⊕ offset, g(x) = x<sup>10</sup>+x<sup>8</sup>+x<sup>7</sup>+x<sup>5</sup>+x<sup>4</sup>+x<sup>3</sup>+1",
          eqn: `57 000 / 48 = 1187.5 bit/s → 104 bits take ${num(groupMs)} ms → ${num(1187.5 / 104)} groups/s · block 2 data 0x${g[1].info.toString(16).toUpperCase().padStart(4, "0")} → check ${bits(g[1].cw, 10)} (offset B)`,
          html, nochart: true,
          note: "The receiver slides along the bit stream until the check words fit with offsets A, B, C, D in a row: that is how it finds the start of a group. A block with a wrong check word is thrown away; the next repetition fills the gap.",
        };
      },
      related: [["Signal flow (FM)", "#flow"], ["DAB ensemble", "#dab"], ["AM vs FM modulation", "#mod"], ["Broadcast configurations", "/broadcast"]],
    });
  });
})();
