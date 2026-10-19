// Broadcast block-diagram editor. Devices (tuners, receivers, coprocessors) are drawn as
// schematic symbols with every pin clickable; a pin's menu offers what belongs on it
// (supply, crystal, antenna, I/Q or I2S connection, speaker, host, flash, note).
//
// State (saved as JSON):
//   devices: [{id, mpn}]
//   blocks:  [{id, kind, label, detail}]          kind: antenna supply ground cap crystal osc
//                                                  speaker host flash memory note
//   links:   [{id, a: End, b: End, kind, label}]  End = {d: deviceId, pins: [n...], bus?} | {blk: blockId}
(() => {
  const root = document.getElementById("bc-editor");
  if (!root) return;
  const CATALOG = JSON.parse(document.getElementById("bc-catalog").textContent);
  const BY_MPN = Object.fromEntries(CATALOG.map(d => [d.mpn, d]));
  const initial = JSON.parse(document.getElementById("bc-config").textContent);
  const PRESETS = JSON.parse(document.getElementById("bc-presets").textContent);
  const $ = sel => root.querySelector(sel);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  let configId = initial.id;
  let S = Object.assign({devices: [], blocks: [], links: [], compact: true}, initial.data || {});
  let seq = 1 + Math.max(0, ...[...S.devices, ...S.blocks, ...S.links].map(x => +String(x.id).replace(/\D/g, "") || 0));
  const uid = p => `${p}${seq++}`;
  let dirty = false;

  // ---------------------------------------------------------------- pin classification
  const LEFT = ["power", "bypass", "xtal", "refclk", "rf_in", "rf_aux", "iq_in", "i2s_in", "audio_in", "mode", "reset"];
  const RIGHT = ["iq_out", "i2s_out", "audio_out", "clock_out", "host", "interrupt", "flash", "memory", "gpio", "debug", "other", "nc", "ground"];
  const FN_LABEL = {
    power: "Supply", ground: "Ground", bypass: "Decoupling / reference", xtal: "Crystal", refclk: "Reference clock in",
    clock_out: "Clock out", rf_in: "RF input", rf_aux: "RF auxiliary", iq_out: "Digital I/Q out", iq_in: "Digital I/Q in",
    i2s_out: "I2S audio out", i2s_in: "I2S audio in", audio_out: "Analog audio out", audio_in: "Analog audio in",
    host: "Host interface", flash: "SPI flash master", memory: "External memory", reset: "Reset", interrupt: "Interrupt",
    gpio: "GPIO", mode: "Mode strap", debug: "Debug / test", nc: "No connect", other: "Other",
  };
  const ROLE_LABEL = {tuner: "Tuner", receiver: "Receiver", coprocessor: "Coprocessor (demod)"};
  const dev = id => S.devices.find(d => d.id === id);
  const info = d => BY_MPN[d.mpn] || {pins: [], supplies: [], role: "tuner", mpn: d.mpn};
  const pinsOf = d => info(d).pins || [];
  const pin = (d, n) => pinsOf(d).find(p => p.n === n);
  const busPins = (d, bus) => pinsOf(d).filter(p => p.bus === bus);
  const sideOf = p => (LEFT.includes(p.fn) ? "L" : "R");
  const isDigitalStd = s => ["HD", "DAB", "DMB", "DRM", "CDR"].includes(s);

  function volts(d, p) {
    if (p.volts) return String(p.volts);
    const s = (info(d).supplies || []).find(x => (x.pins || []).includes(p.name));
    return s && s.volts ? String(s.volts) : null;
  }

  // ---------------------------------------------------------------- link helpers
  const endHas = (e, d, n) => e && e.d === d && (e.pins || []).includes(n);
  const linksAt = (d, n) => S.links.filter(l => endHas(l.a, d, n) || endHas(l.b, d, n));
  const busTaken = (d, bus) => S.links.some(l => (l.a.d === d && l.a.bus === bus) || (l.b.d === d && l.b.bus === bus));
  const block = id => S.blocks.find(b => b.id === id);
  const endOf = (d, p) => (p.bus ? {d, bus: p.bus, pins: busPins(dev(d), p.bus).map(x => x.n)} : {d, pins: [p.n]});

  function addBlock(kind, label, detail = "") {
    const b = {id: uid("b"), kind, label, detail};
    S.blocks.push(b);
    return b;
  }
  function link(a, b, kind, label = "", auto = undefined) {
    S.links.push({id: uid("l"), a, b, kind, label, ...(auto ? {auto} : {})});
  }
  function sharedBlock(kind, label, detail = "") {
    return S.blocks.find(b => b.kind === kind && b.label === label) || addBlock(kind, label, detail);
  }
  function removeLinks(pred) {
    S.links = S.links.filter(l => !pred(l));
    pruneBlocks();
  }
  function pruneBlocks() {
    const used = new Set(S.links.flatMap(l => [l.a.blk, l.b.blk]).filter(Boolean));
    S.blocks = S.blocks.filter(b => used.has(b.id) || b.kind === "note" && b.free);
  }

  // ---------------------------------------------------------------- actions on a pin
  function attachSupply(d, p) {
    const v = volts(dev(d), p);
    const rail = sharedBlock("supply", v ? `${v} V` : `${p.name} supply`, v ? "" : "voltage not in data short");
    link(endOf(d, p), {blk: rail.id}, "power");
  }
  function attachGround(d, p) {
    link({d, pins: [p.n]}, {blk: sharedBlock("ground", "GND").id}, "ground");
  }
  function attachHost(d, p) {
    const host = sharedBlock("host", "Host MCU", "SPI / I2C, GPIO");
    link(endOf(d, p), {blk: host.id}, "host", p.bus || FN_LABEL[p.fn]);
  }
  function attachCrystal(d) {
    const x = pinsOf(dev(d)).filter(p => p.fn === "xtal");
    link({d, pins: x.map(p => p.n)}, {blk: addBlock("crystal", "Crystal", "frequency: see datasheet").id}, "xtal");
  }
  function attachSpeaker(d, p) {
    link(endOf(d, p), {blk: addBlock("speaker", "Amplifier + speaker", p.fn === "audio_out" ? "analog in" : "I2S in").id}, "audio", p.bus || p.name);
  }
  function attachAntenna(d, p) {
    const band = p.band || (/AM/.test(p.name) ? "AM" : /FM/.test(p.name) ? "FM" : /B3|DAB/.test(p.name) ? "DAB Band III" : "");
    link({d, pins: [p.n]}, {blk: addBlock("antenna", `${band || "RF"} antenna`, p.name).id}, "rf");
  }

  // Bus endpoints of other devices a pin can be wired to: I/Q out -> I/Q in, I2S out -> I2S in, clock out -> refclk.
  const PARTNER = {iq_out: "iq_in", iq_in: "iq_out", i2s_out: "i2s_in", i2s_in: "i2s_out", clock_out: "refclk", refclk: "clock_out"};
  function partners(d, p) {
    const want = PARTNER[p.fn];
    if (!want) return [];
    const out = [];
    for (const o of S.devices) {
      if (o.id === d) continue;
      const seen = new Set();
      for (const q of pinsOf(o).filter(q => q.fn === want)) {
        const key = q.bus || `#${q.n}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({o, q, taken: q.bus ? busTaken(o.id, q.bus) : linksAt(o.id, q.n).length > 0});
      }
    }
    return out;
  }
  function connect(d, p, o, q) {
    const out = ["iq_out", "i2s_out", "clock_out"].includes(p.fn);
    const [src, dst] = out ? [endOf(d, p), endOf(o.id, q)] : [endOf(o.id, q), endOf(d, p)];
    const kind = p.fn.startsWith("iq") ? "iq" : p.fn.startsWith("i2s") ? "i2s" : "clock";
    link(src, dst, kind, src.bus || pin(dev(src.d), src.pins[0]).name);
  }

  function pinMenu(d, p) {
    const D = dev(d), items = [];
    const conn = linksAt(d, p.n);
    const add = (label, fn, hint = "") => items.push({label, fn, hint});
    switch (p.fn) {
      case "power": add(`Add power supply${volts(D, p) ? ` (${volts(D, p)} V)` : ""}`, () => attachSupply(d, p)); break;
      case "ground": add("Connect to ground", () => attachGround(d, p)); break;
      case "bypass": add("Add decoupling capacitor", () => link({d, pins: [p.n]}, {blk: addBlock("cap", "Capacitor", `${p.name}: value see datasheet`).id}, "cap")); break;
      case "xtal": add("Add crystal (XTALI / XTALO)", () => attachCrystal(d)); break;
      case "rf_in":
        if (D.slot && S.usecase) { rfMenu(D, p).forEach(it => items.push(it)); break; }
        add(`Add antenna${p.band ? ` (${p.band})` : ""}`, () => attachAntenna(d, p)); break;
      case "rf_aux": add("Add note (RF front-end component)", () => noteOn(d, p)); break;
      case "audio_out": add("Add amplifier + speaker", () => attachSpeaker(d, p)); break;
      case "audio_in": add("Add analog audio source (note)", () => noteOn(d, p, "Analog audio source")); break;
      case "flash": add("Add SPI flash", () => link(endOf(d, p), {blk: addBlock("flash", "SPI flash", "firmware / NVM").id}, "flash", p.bus)); break;
      case "memory": add("Add external memory", () => link(endOf(d, p), {blk: addBlock("memory", "Memory", "type: see datasheet").id}, "memory", p.bus)); break;
      case "host": case "interrupt": case "reset": case "gpio": case "mode":
        add("Connect to host MCU", () => attachHost(d, p)); break;
      case "refclk": add("Add reference oscillator", () => link({d, pins: [p.n]}, {blk: addBlock("osc", "Reference clock", "see datasheet").id}, "clock")); break;
    }
    for (const {o, q, taken} of partners(d, p)) {
      const what = q.bus || q.name;
      add(`Connect to ${o.mpn} · ${what}`, () => connect(d, p, o, q), taken ? "already in use" : "");
    }
    if (p.fn === "iq_out") {
      const stds = info(D).digital_iq || [];
      for (const c of CATALOG.filter(c => c.role === "coprocessor" && stds.some(s => c.digital_decode.includes(s))).slice(0, 8))
        add(`Add coprocessor ${c.mpn} (${c.digital_decode.join("/")}, ${c.channels || "?"} ch) and connect`, () => {
          const o = addDevice(c.mpn);
          const q = pinsOf(o).find(q => q.fn === "iq_in");
          if (q) connect(d, p, o, q);
        });
    }
    if (p.fn === "i2s_out") {
      const copro = S.devices.some(o => info(o).role === "coprocessor");
      add(copro ? "Send to amplifier + speaker instead" : "Add amplifier + speaker (no coprocessor)", () => attachSpeaker(d, p));
    }
    add("Add note…", () => noteOn(d, p));
    if (conn.length) add(`Disconnect (${conn.length})`, () => removeLinks(l => conn.includes(l)));
    return items;
  }

  function noteOn(d, p, preset) {
    const text = preset || prompt(`Note for ${dev(d).mpn} ${p.name}`);
    if (text) link({d, pins: [p.n]}, {blk: addBlock("note", text).id}, "note");
  }

  // ---------------------------------------------------------------- devices
  function addDevice(mpn) {
    const d = {id: uid("d"), mpn};
    S.devices.push(d);
    return d;
  }
  function removeDevice(d) {
    const slot = dev(d) && dev(d).slot;
    if (slot && S.usecase && S.usecase.ics[slot]) S.usecase.ics[slot].mpn = null;
    const wasCopro = info(dev(d)).role === "coprocessor";
    S.devices = S.devices.filter(x => x.id !== d);
    removeLinks(l => l.a.d === d || l.b.d === d);
    if (wasCopro && !S.devices.some(o => info(o).role === "coprocessor")) ensureAudio();
  }
  // Swap a part, keeping every connection whose pin (by name) or bus exists on the new part.
  function replaceDevice(d, mpn) {
    const D = dev(d), oldPins = pinsOf(D);
    D.mpn = mpn;
    if (D.slot && S.usecase && S.usecase.ics[D.slot]) S.usecase.ics[D.slot].mpn = mpn;
    const fix = e => {
      if (e.d !== d) return e;
      if (e.bus) {
        const bp = busPins(D, e.bus);
        return bp.length ? {...e, pins: bp.map(p => p.n)} : null;
      }
      const pins = e.pins.map(n => oldPins.find(p => p.n === n)).map(op => op && pinsOf(D).find(p => p.name === op.name)).filter(Boolean);
      return pins.length ? {...e, pins: pins.map(p => p.n)} : null;
    };
    S.links = S.links.map(l => ({...l, a: fix(l.a), b: fix(l.b)})).filter(l => l.a && l.b);
    pruneBlocks();
  }
  // Without a coprocessor each tuner / receiver plays its own audio: give it a speaker.
  function ensureAudio() {
    for (const o of S.devices.filter(o => info(o).role !== "coprocessor")) {
      const ps = pinsOf(o);
      const hasSink = S.links.some(l => l.kind === "audio" && l.a.d === o.id);
      const out = ps.find(p => p.fn === "i2s_out" && !busTaken(o.id, p.bus)) || ps.find(p => p.fn === "audio_out" && !linksAt(o.id, p.n).length);
      if (!hasSink && out) attachSpeaker(o.id, out);
    }
  }

  // Fill in the obvious surroundings of every device (supplies, ground, crystal, antennas, host,
  // flash, I/Q and audio paths). Pins already connected are left alone.
  function autoComplete() {
    const copros = S.devices.filter(o => info(o).role === "coprocessor");
    for (const o of S.devices) {
      const free = p => !linksAt(o.id, p.n).length;
      const seenBus = new Set();
      for (const p of pinsOf(o)) {
        if (!free(p)) continue;
        if (p.fn === "power") attachSupply(o.id, p);
        else if (p.fn === "ground") attachGround(o.id, p);
        else if (p.fn === "rf_in" && !S.usecase) attachAntenna(o.id, p);
        else if (["host", "interrupt", "reset"].includes(p.fn) && !(p.bus && seenBus.has(p.bus))) { attachHost(o.id, p); if (p.bus) seenBus.add(p.bus); }
        else if (p.fn === "flash" && !seenBus.has("flash")) { link(endOf(o.id, p), {blk: addBlock("flash", "SPI flash", "firmware / NVM").id}, "flash", p.bus); seenBus.add("flash"); }
      }
      if (pinsOf(o).some(p => p.fn === "xtal" && free(p))) attachCrystal(o.id);
    }
    // tuner I/Q -> free coprocessor I/Q inputs, in order (a use case wires these itself)
    for (const t of S.usecase ? [] : S.devices.filter(o => info(o).role === "tuner")) {
      for (const p of uniqueBus(t, "iq_out")) {
        if (busTaken(t.id, p.bus)) continue;
        for (const c of copros) {
          const q = uniqueBus(c, "iq_in").find(q => !busTaken(c.id, q.bus));
          if (q) { connect(t.id, p, c, q); break; }
        }
      }
    }
    // audio: tuner I2S out -> coprocessor I2S in (blending), coprocessor I2S out -> speaker;
    // without a coprocessor, the tuner / receiver drives the speaker itself
    if (copros.length) {
      for (const t of S.devices.filter(o => info(o).role === "tuner")) {
        const p = uniqueBus(t, "i2s_out").find(p => !busTaken(t.id, p.bus));
        const c = copros.find(c => uniqueBus(c, "i2s_in").some(q => !busTaken(c.id, q.bus)));
        if (p && c && !S.links.some(l => l.kind === "i2s" && l.a.d === t.id)) connect(t.id, p, c, uniqueBus(c, "i2s_in").find(q => !busTaken(c.id, q.bus)));
      }
      for (const c of copros) {
        const p = uniqueBus(c, "i2s_out").find(p => !busTaken(c.id, p.bus));
        if (p && !S.links.some(l => l.kind === "audio" && l.a.d === c.id)) attachSpeaker(c.id, p);
      }
    } else ensureAudio();
  }
  const uniqueBus = (o, fn) => {
    const seen = new Set();
    return pinsOf(o).filter(p => p.fn === fn && (p.bus ? !seen.has(p.bus) && seen.add(p.bus) : true));
  };

  // ---------------------------------------------------------------- layout + drawing
  const ROW = 17, HEAD = 46, DEV_W = 230, BLK_W = 140, BLK_H = 34, GAP = 70;
  const NET = ["power", "ground", "host"]; // shown as net labels at the pin, not as wires

  function visiblePins(o) {
    const ps = [...pinsOf(o)];
    const order = fn => (LEFT.includes(fn) ? LEFT.indexOf(fn) : RIGHT.indexOf(fn));
    const sort = arr => arr.sort((a, b) => order(a.fn) - order(b.fn) || String(a.bus || "").localeCompare(String(b.bus || "")) || a.n - b.n);
    let L = sort(ps.filter(p => sideOf(p) === "L")), R = sort(ps.filter(p => sideOf(p) === "R"));
    if (S.compact) {
      const hide = p => (p.fn === "ground" || p.fn === "nc") && !linksAt(o.id, p.n).some(l => !NET.includes(l.kind));
      const hidden = R.filter(hide);
      R = R.filter(p => !hide(p));
      if (hidden.length) R.push({summary: true, n: hidden[0].n, pins: hidden, name: `GND / NC ×${hidden.length}`, fn: "ground"});
    }
    return {L, R};
  }

  function layout() {
    const cols = [S.devices.filter(o => info(o).role !== "coprocessor"), S.devices.filter(o => info(o).role === "coprocessor")].filter(c => c.length);
    const X = {ant: 20};
    let x = X.ant + BLK_W + 40;
    const colX = cols.map(() => {
      const c = {laneL: x, dev: x + BLK_W + 30};
      c.laneR = c.dev + DEV_W + 30;
      x = c.laneR + BLK_W + 90;
      return c;
    });
    X.spk = x - 50;
    const pos = {}, top = 110;
    cols.forEach((col, ci) => {
      let y = top;
      for (const o of col) {
        const {L, R} = visiblePins(o);
        const head = HEAD + jobLines(o).length * 12;
        const h = head + Math.max(L.length, R.length, 2) * ROW + 12;
        const pinY = {};
        L.forEach((p, i) => (pinY[p.n] = {y: y + head + i * ROW + ROW / 2, side: "L"}));
        R.forEach((p, i) => { const e = {y: y + head + i * ROW + ROW / 2, side: "R"}; (p.summary ? p.pins : [p]).forEach(q => (pinY[q.n] = e)); });
        pos[o.id] = {x: colX[ci].dev, y, w: DEV_W, h, head, L, R, pinY, col: ci};
        y += h + GAP;
      }
    });
    const pinXY = (d, n) => {
      const P = pos[d], e = P && P.pinY[n];
      return e ? {x: e.side === "L" ? P.x - 14 : P.x + P.w + 14, y: e.y, side: e.side} : null;
    };
    // place blocks: antennas far left, speakers far right, shared nets in the top band,
    // everything else in the lane beside the pin it hangs on
    const lanes = {};
    const want = [];
    for (const b of S.blocks) {
      const ls = S.links.filter(l => l.b.blk === b.id || l.a.blk === b.id);
      if (!ls.length) continue;
      const e = ls[0].a.d ? ls[0].a : ls[0].b;
      const p = pinXY(e.d, e.pins[0]);
      if (!p) continue;
      const ys = ls.map(l => (l.a.d ? l.a : l.b)).flatMap(e => e.pins.map(n => pinXY(e.d, n))).filter(Boolean).map(q => q.y);
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      let lane, bx;
      if (["supply", "ground", "host"].includes(b.kind)) { lane = "top"; }
      else if (b.kind === "antenna") { lane = "ant"; bx = X.ant; }
      else if (b.kind === "speaker") { lane = "spk"; bx = X.spk; }
      else { const c = colX[pos[e.d].col]; lane = `${pos[e.d].col}${p.side}`; bx = p.side === "L" ? c.laneL : c.laneR; }
      want.push({b, lane, x: bx, y: cy - BLK_H / 2});
    }
    const out = {};
    for (const w of want) (lanes[w.lane] ||= []).push(w);
    for (const [lane, ws] of Object.entries(lanes)) {
      if (lane === "top") { ws.forEach((w, i) => (out[w.b.id] = {x: X.ant + i * (BLK_W + 16), y: 20, w: BLK_W, h: BLK_H})); continue; }
      ws.sort((a, b) => a.y - b.y);
      let floor = -1e9;
      for (const w of ws) { const y = Math.max(w.y, floor); out[w.b.id] = {x: w.x, y, w: BLK_W, h: BLK_H}; floor = y + BLK_H + 8; }
    }
    const W = Math.max(X.spk + BLK_W + 20, ...Object.values(out).map(r => r.x + r.w + 20), 600);
    const H = Math.max(...Object.values(pos).map(p => p.y + p.h + 40), ...Object.values(out).map(r => r.y + r.h + 40), 300);
    return {pos, blocks: out, pinXY, W, H};
  }

  const curve = (a, b, da, db) => `M${a.x},${a.y} C${a.x + da},${a.y} ${b.x + db},${b.y} ${b.x},${b.y}`;

  function render() {
    const Lay = layout();
    const parts = [];
    // links
    for (const l of S.links) {
      if (NET.includes(l.kind)) continue;
      const ea = l.a.d ? l.a : null, eb = l.b.d ? l.b : null;
      const A = ea && Lay.pinXY(ea.d, ea.pins[0]);
      if (!A) continue;
      let B, db;
      if (eb) { B = Lay.pinXY(eb.d, eb.pins[0]); if (!B) continue; db = B.side === "L" ? -80 : 80; }
      else { const r = Lay.blocks[l.b.blk]; if (!r) continue; const left = r.x + r.w / 2 < A.x; B = {x: left ? r.x + r.w : r.x, y: r.y + r.h / 2}; db = left ? 40 : -40; }
      const da = A.side === "L" ? -60 : 60;
      parts.push(`<path class="wire w-${l.kind}${l.a.bus ? " bus" : ""}" d="${curve(A, B, da, db)}"/>`);
      if (eb && l.label) parts.push(`<text class="wire-label" x="${(A.x + B.x) / 2}" y="${(A.y + B.y) / 2 - 6}" text-anchor="middle">${esc(l.label)}</text>`);
    }
    // devices
    for (const o of S.devices) {
      const P = Lay.pos[o.id];
      if (!P) continue;
      const I = info(o);
      parts.push(`<g class="dev role-${I.role}"><rect class="dev-body" x="${P.x}" y="${P.y}" width="${P.w}" height="${P.h}" rx="6"/>`);
      parts.push(`<g class="dev-head" data-dev="${o.id}" tabindex="0" role="button" aria-label="${esc(o.mpn)} options"><rect class="dev-headbg" x="${P.x}" y="${P.y}" width="${P.w}" height="${P.head - 8}" rx="6"/>` +
        `<text class="dev-mpn" x="${P.x + 10}" y="${P.y + 17}">${o.slot ? `${esc(o.slot)} · ` : ""}${esc(o.mpn)} ▾</text>` +
        jobLines(o).map((t, i) => `<text class="dev-job" x="${P.x + 10}" y="${P.y + 44 + i * 12}">${esc(t)}</text>`).join("") +
        `<text class="dev-sub" x="${P.x + 10}" y="${P.y + 31}">${esc(ROLE_LABEL[I.role] || I.role)} · ${esc((I.package || {}).type || "")}-${esc((I.package || {}).pins || "?")}${I.numbered ? "" : " · signals only (no pinout in data short)"}</text></g>`);
      for (const side of ["L", "R"]) {
        for (const p of P[side]) {
          const y = P.pinY[p.n].y, x0 = side === "L" ? P.x : P.x + P.w, x1 = side === "L" ? P.x - 14 : P.x + P.w + 14;
          const ls = (p.summary ? p.pins : [p]).flatMap(q => linksAt(o.id, q.n));
          const net = ls.find(l => NET.includes(l.kind));
          const tag = net ? (block(net.b.blk) || {}).label : "";
          parts.push(`<g class="pin fn-${p.fn}${ls.length ? " on" : ""}" data-dev="${o.id}" data-n="${p.n}"${p.summary ? ' data-summary="1"' : ""} tabindex="0" role="button" aria-label="Pin ${p.n} ${esc(p.name)}">` +
            `<rect class="pin-hit" x="${side === "L" ? x1 - 4 : P.x + P.w / 2}" y="${y - ROW / 2}" width="${P.w / 2 + 18}" height="${ROW}"/>` +
            `<line class="pin-stub" x1="${x0}" y1="${y}" x2="${x1}" y2="${y}"/><circle class="pin-dot" cx="${x1}" cy="${y}" r="3"/>` +
            `<text class="pin-num" x="${side === "L" ? x0 - 4 : x0 + 4}" y="${y - 3}" text-anchor="${side === "L" ? "end" : "start"}">${p.summary ? "" : esc(p.num ?? p.n)}</text>` +
            `<text class="pin-name" x="${side === "L" ? x0 + 6 : x0 - 6}" y="${y + 4}" text-anchor="${side === "L" ? "start" : "end"}">${esc(p.name)}</text>` +
            (tag ? `<text class="net-tag" x="${side === "L" ? x1 - 6 : x1 + 6}" y="${y + 4}" text-anchor="${side === "L" ? "end" : "start"}">${esc(tag)}</text>` : "") +
            `</g>`);
        }
      }
      parts.push(`</g>`);
    }
    // blocks
    for (const b of S.blocks) {
      const r = Lay.blocks[b.id];
      if (!r) continue;
      parts.push(`<g class="blk k-${b.kind}" data-blk="${b.id}" tabindex="0" role="button" aria-label="${esc(b.label)}"><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="5"/>` +
        `<text class="blk-label" x="${r.x + 8}" y="${r.y + 14}">${esc(b.label.length > 22 ? b.label.slice(0, 21) + "…" : b.label)}</text>` +
        `<text class="blk-detail" x="${r.x + 8}" y="${r.y + 27}">${esc(b.detail.length > 26 ? b.detail.slice(0, 25) + "…" : b.detail)}</text></g>`);
    }
    if (!S.devices.length) parts.push(`<text class="empty" x="40" y="160">Add a device, or start from the standards you need.</text>`);
    const svg = $("#bc-svg");
    svg.setAttribute("viewBox", `0 0 ${Lay.W} ${Lay.H}`);
    svg.setAttribute("width", Lay.W * zoom);
    svg.setAttribute("height", Lay.H * zoom);
    svg.innerHTML = parts.join("");
    renderSummary();
    renderUseCase();
  }

  function renderSummary() {
    const rows = S.devices.map(o => {
      const I = info(o);
      const std = [...(I.analog || []), ...(I.digital_decode || []), ...(I.digital_iq || []).map(s => `${s} I/Q`)];
      return `<li><b>${esc(o.mpn)}</b> <span class="muted">${esc(ROLE_LABEL[I.role] || "")}</span> · ${esc(std.join(", "))}` +
        `${I.options && I.options.length ? ` · <small>${esc(I.options.join("; "))}</small>` : ""}` +
        `${I.source && I.source.url ? ` · <a href="${esc(I.source.url)}" target="_blank" rel="noopener">data short</a>` : ""}</li>`;
    });
    const bom = {};
    S.blocks.forEach(b => (bom[b.label] = (bom[b.label] || 0) + 1));
    $("#bc-summary").innerHTML = (rows.length ? `<ul>${rows.join("")}</ul>` : "") +
      (S.blocks.length ? `<p class="small muted">Added: ${Object.entries(bom).map(([k, n]) => `${esc(k)}${n > 1 ? ` ×${n}` : ""}`).join(" · ")}</p>` : "");
  }

  // ---------------------------------------------------------------- menus
  const menu = $("#bc-menu");
  function openMenu(ev, title, items) {
    menu.innerHTML = `<div class="bc-menu-title">${title}</div>` + items.map((it, i) =>
      `<button type="button" data-i="${i}">${esc(it.label)}${it.hint ? ` <small class="muted">${esc(it.hint)}</small>` : ""}</button>`).join("");
    menu.hidden = false;
    const box = root.getBoundingClientRect();
    const x = Math.min(ev.clientX - box.left, box.width - 300);
    menu.style.left = `${Math.max(4, x)}px`;
    menu.style.top = `${ev.clientY - box.top + 8}px`;
    menu.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => {
      menu.hidden = true;
      items[+btn.dataset.i].fn();
      changed();
    }));
    menu.querySelector("button")?.focus();
  }
  const closeMenu = () => (menu.hidden = true);
  document.addEventListener("keydown", e => e.key === "Escape" && closeMenu());
  document.addEventListener("click", e => { if (!e.target.closest("#bc-menu, #bc-svg")) closeMenu(); });

  function onActivate(ev) {
    const t = ev.target.closest(".pin, .dev-head, .blk");
    if (!t) return closeMenu();
    ev.stopPropagation();
    if (t.classList.contains("pin")) {
      const d = t.dataset.dev, n = +t.dataset.n, o = dev(d);
      if (t.dataset.summary) {
        const hidden = visiblePins(o).R.find(p => p.summary).pins;
        return openMenu(ev, `${esc(o.mpn)} · ${hidden.length} ground / no-connect pins`, [
          {label: "Connect all ground pins to GND", fn: () => hidden.filter(p => p.fn === "ground" && !linksAt(d, p.n).length).forEach(p => attachGround(d, p))},
          {label: "Show these pins", fn: () => (S.compact = false)},
        ]);
      }
      const p = pin(o, n);
      const title = `${esc(o.mpn)} · ${p.num === "" ? "signal" : `pin ${p.num ?? p.n}`} <b>${esc(p.name)}</b><br><small>${esc(FN_LABEL[p.fn] || p.fn)}${p.bus ? ` · ${esc(p.bus)}` : ""}${p.band ? ` · ${esc(p.band)}` : ""}${p.note ? ` · ${esc(p.note)}` : ""}</small>`;
      return openMenu(ev, title, pinMenu(d, p));
    }
    if (t.classList.contains("dev-head")) {
      const d = t.dataset.dev, o = dev(d), I = info(o);
      const same = CATALOG.filter(c => c.role === I.role && c.mpn !== o.mpn);
      return openMenu(ev, `<b>${esc(o.mpn)}</b> · ${esc(I.description || "")}`, [
        {label: "Fill in surroundings (supplies, crystal, antennas, host…)", fn: autoComplete},
        ...same.map(c => ({label: `Replace with ${c.mpn}`, hint: [...c.analog, ...c.digital_decode, ...c.digital_iq.map(s => s + " I/Q")].join(" "), fn: () => replaceDevice(d, c.mpn)})),
        ...(I.source && I.source.url ? [{label: "Open data short", fn: () => window.open(I.source.url, "_blank", "noopener")}] : []),
        {label: `Remove ${o.mpn}`, fn: () => removeDevice(d)},
      ]);
    }
    const b = block(t.dataset.blk);
    openMenu(ev, `<b>${esc(b.label)}</b>${b.detail ? `<br><small>${esc(b.detail)}</small>` : ""}`, [
      {label: "Rename…", fn: () => { const v = prompt("Label", b.label); if (v) b.label = v; }},
      {label: "Edit detail…", fn: () => { const v = prompt("Detail (value, part number…)", b.detail); if (v !== null) b.detail = v; }},
      {label: "Remove", fn: () => removeLinks(l => l.a.blk === b.id || l.b.blk === b.id)},
    ]);
  }
  $("#bc-svg").addEventListener("click", onActivate);
  $("#bc-svg").addEventListener("keydown", e => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    const r = e.target.getBoundingClientRect();
    onActivate({target: e.target, clientX: r.left + r.width / 2, clientY: r.bottom, stopPropagation() {}});
  });

  // ---------------------------------------------------------------- use case
  // S.usecase = {name, region, linking, notes, antennas: [{id, label, bands}],
  //   ics: {IC0..IC2: {mpn, tuners: [{job, feed: {antenna} | {loop}}]}, IC3: {mpn, channels: [{job, source}]}}}
  const TUNER_SLOTS = ["IC0", "IC1", "IC2"], DEMOD_SLOT = "IC3";
  const TUNER_JOBS = {
    off: {label: "Not used"},
    amfm_audio: {label: "AM or FM audio (foreground)", fg: true, analog: ["AM", "FM"], band: ["AM", "FM"]},
    fm_audio: {label: "FM audio (foreground)", fg: true, analog: ["FM"], band: ["FM"]},
    am_audio: {label: "AM audio (foreground)", fg: true, analog: ["AM"], band: ["AM"]},
    fm_pd: {label: "FM phase diversity audio", fg: true, pd: true, analog: ["FM"], band: ["FM"]},
    fm_scan: {label: "FM background scan / station list", analog: ["FM"], band: ["FM"]},
    am_scan: {label: "AM background scan", analog: ["AM"], band: ["AM"]},
    dab: {label: "DAB (I/Q to demod)", iq: ["DAB"], band: ["DAB"]},
    fm_dab_scan: {label: "FM / DAB background scan", analog: ["FM"], iq: ["DAB"], band: ["FM", "DAB"]},
    drm: {label: "DRM (I/Q to demod)", iq: ["DRM"], band: ["AM", "FM"]},
  };
  const DEMOD_JOBS = {
    unused: {label: "Not used"},
    hd_audio: {label: "HD audio", std: "HD", audio: true},
    hd_data: {label: "HD data / station list (background)", std: "HD"},
    dab_audio: {label: "DAB audio", std: "DAB", audio: true},
    dab_scanless: {label: "DAB scanless / service list", std: "DAB"},
    drm_audio: {label: "DRM audio", std: "DRM", audio: true},
    cdr_audio: {label: "CDR audio", std: "CDR", audio: true},
  };
  // which tuner jobs can feed a demod channel of a given standard
  const FEEDS_STD = {HD: ["amfm_audio", "fm_audio", "am_audio", "fm_pd", "fm_scan", "am_scan"], DAB: ["dab", "fm_dab_scan"], DRM: ["drm"], CDR: ["fm_audio", "fm_scan", "amfm_audio"]};
  // loop-through (buffer) outputs per band, by pin name
  const LOOP_PIN = {FM: /^FMO\b/, DAB: /^(LT[AB]|B3O)\b/, AM: /^AMO\b/};

  const slotDev = slot => S.devices.find(o => o.slot === slot);
  const tunerCount = o => (o ? info(o).tuners || 1 : 0);
  const demodChannels = o => (o ? info(o).channels || 4 : 0);
  const U = () => S.usecase;

  function jobLines(o) {
    const u = U();
    if (!u || !o.slot || !u.ics[o.slot]) return [];
    const ic = u.ics[o.slot];
    if (o.slot === DEMOD_SLOT)
      return (ic.channels || []).map((c, i) => `DMOD${i}: ${DEMOD_JOBS[c.job]?.label || c.job}${c.source && c.job !== "unused" ? ` ← ${c.source.replace(".", " ")}` : ""}`);
    return (ic.tuners || []).map((t, i) => `T${i}: ${TUNER_JOBS[t.job]?.label || t.job}${feedText(t.feed)}`);
  }
  const feedText = f => (!f ? "" : f.antenna ? ` · ${f.antenna}` : f.loop ? ` · loop from ${f.loop}` : "");

  // RF input pins belonging to tuner t of a device (A/0 pins = tuner 0, B/1 pins = tuner 1, others shared)
  function rfPins(o, t, bands) {
    const two = tunerCount(o) > 1;
    return pinsOf(o).filter(p => p.fn === "rf_in").filter(p => {
      if (two) {
        const m = p.name.split("/")[0].match(/([AB01])$/);
        if (m && (m[1] === "A" || m[1] === "0" ? 0 : 1) !== t) return false;
      }
      const pb = String(p.band || "").toUpperCase();
      return !bands || bands.some(b => pb.includes(b));
    });
  }
  const bandsOfJob = job => (TUNER_JOBS[job] || {}).band || [];

  function syncUseCase() {
    const u = U();
    if (!u) return;
    for (const slot of [...TUNER_SLOTS, DEMOD_SLOT]) {
      const ic = u.ics[slot] || (u.ics[slot] = {mpn: null});
      const o = slotDev(slot);
      if (ic.mpn && !o) addDevice(ic.mpn).slot = slot;
      else if (ic.mpn && o && o.mpn !== ic.mpn) replaceDevice(o.id, ic.mpn);
      else if (!ic.mpn && o) removeDevice(o.id);
      const d = slotDev(slot);
      if (slot === DEMOD_SLOT) {
        ic.channels = Array.from({length: demodChannels(d)}, (_, i) => (ic.channels || [])[i] || {job: "unused"});
      } else {
        ic.tuners = Array.from({length: tunerCount(d)}, (_, i) => (ic.tuners || [])[i] || {job: "off"});
      }
    }
    // regenerate the use-case wiring: antennas, loop-throughs, I/Q
    S.links = S.links.filter(l => l.auto !== "uc");
    S.blocks = S.blocks.filter(b => !b.uc);
    const antBlock = {};
    for (const a of u.antennas) {
      const b = addBlock("antenna", `${a.id} ${a.label || ""}`.trim(), (a.bands || []).join(" / "));
      b.uc = true;
      antBlock[a.id] = b;
    }
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot), ic = u.ics[slot];
      if (!o) continue;
      (ic.tuners || []).forEach((t, i) => {
        if (!t.feed || t.job === "off") return;
        if (t.feed.antenna && antBlock[t.feed.antenna]) {
          const a = u.antennas.find(a => a.id === t.feed.antenna);
          const pins = rfPins(o, i, (a.bands || []).filter(b => bandsOfJob(t.job).includes(b)));
          if (pins.length) link({d: o.id, pins: pins.map(p => p.n)}, {blk: antBlock[a.id].id}, "rf", "", "uc");
        } else if (t.feed.loop) {
          const src = slotDev(t.feed.loop);
          if (!src) return;
          for (const band of bandsOfJob(t.job)) {
            const out = pinsOf(src).find(p => LOOP_PIN[band] && LOOP_PIN[band].test(p.name));
            const pins = rfPins(o, i, [band]);
            if (out && pins.length) link({d: src.id, pins: [out.n]}, {d: o.id, pins: pins.map(p => p.n)}, "rf", `loop-through ${band}`, "uc");
          }
        }
      });
    }
    const demod = slotDev(DEMOD_SLOT);
    if (demod) {
      const ports = uniqueBus(demod, "iq_in");
      const sources = [...new Set((u.ics[DEMOD_SLOT].channels || []).filter(c => c.job !== "unused" && c.source).map(c => c.source.split(".")[0]))];
      sources.forEach((slot, k) => {
        const o = slotDev(slot), out = o && uniqueBus(o, "iq_out")[0], port = ports[k];
        if (!out || !port) return;
        const chans = u.ics[DEMOD_SLOT].channels.map((c, i) => (c.source && c.source.startsWith(slot + ".") && c.job !== "unused" ? `DMOD${i}` : null)).filter(Boolean);
        link(endOf(o.id, out), endOf(demod.id, port), "iq", `${out.bus} → ${chans.join(", ")}`, "uc");
      });
    }
    pruneBlocks();
  }

  // Checks are the rules from the use cases: each result is [level, text], level ok / warn / error.
  function checks() {
    const u = U(), out = [];
    if (!u) return out;
    const has = (o, std) => [...info(o).analog, ...info(o).digital_iq, ...info(o).digital_decode].includes(std);
    let audio = 0;
    const direct = {};
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot), ic = u.ics[slot];
      if (!o) continue;
      const ts = ic.tuners || [];
      ts.forEach((t, i) => {
        const J = TUNER_JOBS[t.job] || {};
        if (t.job === "off") return;
        const missing = [...(J.analog || []).filter(s => !info(o).analog.includes(s)), ...(J.iq || []).filter(s => !info(o).digital_iq.includes(s))];
        if (missing.length) out.push(["error", `${slot} T${i} (${o.mpn}) cannot do ${J.label}: no ${missing.join(", ")} in its data short.`]);
        if (J.fg) audio++;
        if (!t.feed) out.push(["error", `${slot} T${i} has no antenna feed.`]);
        else if (t.feed.antenna) (direct[t.feed.antenna] ||= new Set()).add(slot);
        else if (t.feed.loop) {
          const src = slotDev(t.feed.loop);
          if (!src) out.push(["error", `${slot} T${i} loops through from ${t.feed.loop}, which is not populated.`]);
          else for (const band of J.band || []) if (!pinsOf(src).some(p => LOOP_PIN[band] && LOOP_PIN[band].test(p.name)))
            out.push(["warn", `${t.feed.loop} (${src.mpn}) has no ${band} loop-through output pin in its data short (looked for ${LOOP_PIN[band]}).`]);
          if (t.feed.loop === slot) out.push(["error", `${slot} T${i} cannot loop through from its own IC.`]);
        }
      });
      const pd = ts.map((t, i) => [t, i]).filter(([t]) => t.job === "fm_pd");
      if (pd.length === 1) out.push(["error", `${slot}: FM phase diversity needs both tuners of the IC.`]);
      if (pd.length === 2) {
        audio--; // the pair is one listening source
        if (pd[0][0].feed?.antenna && pd[0][0].feed.antenna === pd[1][0].feed?.antenna) out.push(["warn", `${slot}: phase diversity with both tuners on ${pd[0][0].feed.antenna}; diversity needs two antennas.`]);
      }
    }
    for (const [ant, slots] of Object.entries(direct))
      if (slots.size > 1) out.push(["warn", `${ant} feeds ${[...slots].join(" and ")} directly. One antenna connects to one IC; feed the next IC through the loop-through or add an antenna.`]);
    for (const a of u.antennas) if (!direct[a.id]) out.push(["warn", `${a.id} is not connected to any tuner.`]);
    const demod = slotDev(DEMOD_SLOT);
    if (demod) {
      const chans = u.ics[DEMOD_SLOT].channels || [];
      const used = chans.filter(c => c.job !== "unused");
      chans.forEach((c, i) => {
        const J = DEMOD_JOBS[c.job] || {};
        if (c.job === "unused") return;
        if (J.audio) audio++;
        if (!info(demod).digital_decode.includes(J.std)) out.push(["error", `DMOD${i}: ${demod.mpn} does not decode ${J.std} (licensed for ${info(demod).digital_decode.join(", ") || "none"}).`]);
        const [slot, tn] = (c.source || "").split(".");
        const o = slotDev(slot), t = o && (u.ics[slot].tuners || [])[+String(tn).slice(1)];
        if (!o || !t) out.push(["error", `DMOD${i} (${J.label}) has no source tuner.`]);
        else {
          if (!info(o).digital_iq.includes(J.std)) out.push(["error", `DMOD${i}: ${slot} (${o.mpn}) has no ${J.std} I/Q output.`]);
          if (!(FEEDS_STD[J.std] || []).includes(t.job)) out.push(["warn", `DMOD${i} (${J.label}) is fed by ${slot} ${tn}, which is set to "${TUNER_JOBS[t.job]?.label}".`]);
        }
      });
      const srcIcs = new Set(used.map(c => (c.source || "").split(".")[0]).filter(Boolean));
      if (srcIcs.size > uniqueBus(demod, "iq_in").length) out.push(["error", `${demod.mpn} has ${uniqueBus(demod, "iq_in").length} I/Q input ports for ${srcIcs.size} tuner ICs.`]);
    }
    if (!audio && S.devices.some(o => o.slot)) out.push(["error", "No tuner or demod channel plays audio in the foreground."]);
    if (u.linking) {
      if (!demod || !info(demod).options.some(x => /seamless/i.test(x))) out.push(["error", "Seamless linking needs a demodulator with seamless blending / linking."]);
      // FM <-> DAB linking needs a tuner that can take DAB while FM keeps playing
      const fmFg = TUNER_SLOTS.flatMap(s => (u.ics[s].tuners || []).map((t, i) => ({s, i, t}))).filter(x => slotDev(x.s) && ["fm_audio", "amfm_audio", "fm_pd"].includes(x.t.job));
      const linkTuner = TUNER_SLOTS.flatMap(s => (u.ics[s].tuners || []).map((t, i) => ({s, i, t}))).find(x => slotDev(x.s) && !TUNER_JOBS[x.t.job]?.fg && has(slotDev(x.s), "DAB"));
      if (fmFg.length && !linkTuner) {
        const pdOn = fmFg.some(x => x.t.job === "fm_pd");
        out.push(["error", pdOn
          ? "Seamless linking FM ↔ DAB needs a free DAB tuner, but phase diversity occupies the dual tuner. Step out of phase diversity to link, or add a tuner IC."
          : "Seamless linking FM ↔ DAB needs a second, DAB-capable tuner that is not playing audio."]);
      }
    }
    if (!out.some(([l]) => l !== "ok")) out.push(["ok", "No conflicts found in the data-short rules."]);
    return out;
  }

  function rfMenu(D, p) {
    const u = U(), items = [];
    const ic = u.ics[D.slot];
    const idx = tunerCount(D) > 1 ? ((m => (m ? (m[1] === "A" || m[1] === "0" ? 0 : 1) : null))(p.name.split("/")[0].match(/([AB01])$/))) : 0;
    const tuners = idx === null ? ic.tuners.map((_, i) => i) : [idx];
    const set = feed => () => tuners.forEach(i => (ic.tuners[i].feed = feed));
    for (const a of u.antennas) items.push({label: `Feed ${tuners.map(i => "T" + i).join("+")} from ${a.id} (${(a.bands || []).join("/")})`, fn: () => { set({antenna: a.id})(); syncUseCase(); }});
    for (const s of TUNER_SLOTS) if (s !== D.slot && slotDev(s)) items.push({label: `Loop-through from ${s} (${slotDev(s).mpn})`, fn: () => { set({loop: s})(); syncUseCase(); }});
    items.push({label: "Add a new antenna here", fn: () => {
      const id = `ANT${u.antennas.length + 1}`;
      u.antennas.push({id, label: p.band || "", bands: String(p.band || "FM").toUpperCase().split("/").map(b => (b.includes("DAB") ? "DAB" : b))});
      set({antenna: id})();
      syncUseCase();
    }});
    return items;
  }

  function applyPreset(i) {
    const pr = JSON.parse(JSON.stringify(PRESETS[i]));
    S.devices = []; S.blocks = []; S.links = [];
    S.usecase = {name: pr.name, region: pr.region, linking: !!pr.linking, notes: pr.notes || "", antennas: pr.antennas || [], ics: pr.ics || {}};
    syncUseCase();
    autoComplete();
    if (!$("#bc-name").value || PRESETS.some(x => x.name === $("#bc-name").value)) $("#bc-name").value = pr.name;
  }

  function opt(value, label, sel) { return `<option value="${esc(value)}"${value === sel ? " selected" : ""}>${esc(label)}</option>`; }

  function renderUseCase() {
    const box = $("#bc-usecase"), u = U();
    if (!u) {
      box.innerHTML = `<p class="small muted">No use case yet. Pick a preset above, or <button type="button" class="outline small-btn" data-uc="blank">start an empty use case</button>.</p>`;
      box.querySelector("[data-uc=blank]").onclick = () => {
        S.usecase = {name: "", region: "", linking: false, notes: "", antennas: [{id: "ANT1", label: "AM/FM", bands: ["AM", "FM"]}], ics: {IC0: {mpn: null}, IC1: {mpn: null}, IC2: {mpn: null}, IC3: {mpn: null}}};
        syncUseCase(); changed();
      };
      return;
    }
    const tunersCat = CATALOG.filter(c => c.role !== "coprocessor"), demodsCat = CATALOG.filter(c => c.role === "coprocessor");
    const feedOpts = (slot, f) => opt("", "— no feed —", "") + u.antennas.map(a => opt(`a:${a.id}`, `${a.id} ${a.label || ""} (${(a.bands || []).join("/")})`, f && f.antenna ? `a:${f.antenna}` : "")).join("") +
      TUNER_SLOTS.filter(s => s !== slot && slotDev(s)).map(s => opt(`l:${s}`, `loop-through from ${s}`, f && f.loop ? `l:${f.loop}` : "")).join("");
    const srcOpts = sel => opt("", "— source —", sel || "") + TUNER_SLOTS.filter(slotDev).flatMap(s => (u.ics[s].tuners || []).map((_, i) => opt(`${s}.T${i}`, `${s} T${i}`, sel))).join("");
    let rows = "";
    for (const slot of TUNER_SLOTS) {
      const ic = u.ics[slot];
      rows += `<tr><th>${slot}</th><td><select data-slot="${slot}" aria-label="${slot} part">${opt("", "Not populated", ic.mpn || "")}${tunersCat.map(c => opt(c.mpn, `${c.mpn} · ${c.tuners || 1} tuner${(c.tuners || 1) > 1 ? "s" : ""} · ${[...c.analog, ...c.digital_iq.map(s => s + " I/Q"), ...c.digital_decode].join(" ")}`, ic.mpn || "")).join("")}</select></td><td>` +
        (ic.tuners || []).map((t, i) => `<div class="uc-row"><b>T${i}</b><select data-job="${slot}.${i}" aria-label="${slot} tuner ${i} job">${Object.entries(TUNER_JOBS).map(([k, j]) => opt(k, j.label, t.job)).join("")}</select>` +
          `<select data-feed="${slot}.${i}" aria-label="${slot} tuner ${i} antenna">${feedOpts(slot, t.feed)}</select></div>`).join("") + `</td></tr>`;
    }
    const dm = u.ics[DEMOD_SLOT];
    rows += `<tr><th>${DEMOD_SLOT}</th><td><select data-slot="${DEMOD_SLOT}" aria-label="Demodulator part">${opt("", "Not populated", dm.mpn || "")}${demodsCat.map(c => opt(c.mpn, `${c.mpn} · ${c.digital_decode.join("/") || "AM/FM"} · ${c.channels || "SW-defined"} ch${c.options.length ? " · " + c.options.join(", ") : ""}`, dm.mpn || "")).join("")}</select></td><td>` +
      (dm.channels || []).map((c, i) => `<div class="uc-row"><b>DMOD${i}</b><select data-djob="${i}" aria-label="DMOD${i} job">${Object.entries(DEMOD_JOBS).map(([k, j]) => opt(k, j.label, c.job)).join("")}</select>` +
        `<select data-dsrc="${i}" aria-label="DMOD${i} source">${srcOpts(c.source)}</select></div>`).join("") + `</td></tr>`;
    const ants = u.antennas.map((a, i) => `<span class="uc-ant"><b>${esc(a.id)}</b> <input data-alabel="${i}" value="${esc(a.label || "")}" aria-label="${esc(a.id)} label">` +
      ["AM", "FM", "DAB"].map(b => `<label><input type="checkbox" data-aband="${i}" value="${b}"${(a.bands || []).includes(b) ? " checked" : ""}> ${b}</label>`).join("") +
      `<button type="button" class="outline secondary small-btn" data-adel="${i}" aria-label="Remove ${esc(a.id)}">×</button></span>`).join("");
    const cs = checks();
    box.innerHTML = `<div class="uc-head"><b>${esc(u.name || "Use case")}</b>${u.region ? ` <span class="muted">· ${esc(u.region)}</span>` : ""}
        <label class="bc-check"><input type="checkbox" id="uc-linking"${u.linking ? " checked" : ""}> Seamless linking</label></div>
      ${u.notes ? `<p class="small muted">${esc(u.notes)}</p>` : ""}
      <div class="uc-ants">Antennas: ${ants} <button type="button" class="outline small-btn" id="uc-addant">+ antenna</button></div>
      <div class="table-wrap"><table class="uc-table"><tbody>${rows}</tbody></table></div>
      <ul class="uc-checks">${cs.map(([l, t]) => `<li class="uc-${l}">${l === "ok" ? "✓" : l === "warn" ? "⚠" : "✗"} ${esc(t)}</li>`).join("")}</ul>`;
    const upd = fn => e => { fn(e.target); syncUseCase(); changed(); };
    box.querySelectorAll("[data-slot]").forEach(el => (el.onchange = upd(t => (u.ics[t.dataset.slot].mpn = t.value || null))));
    box.querySelectorAll("[data-job]").forEach(el => (el.onchange = upd(t => { const [s, i] = t.dataset.job.split("."); u.ics[s].tuners[+i].job = t.value; })));
    box.querySelectorAll("[data-feed]").forEach(el => (el.onchange = upd(t => {
      const [s, i] = t.dataset.feed.split("."), v = t.value;
      u.ics[s].tuners[+i].feed = !v ? null : v.startsWith("a:") ? {antenna: v.slice(2)} : {loop: v.slice(2)};
    })));
    box.querySelectorAll("[data-djob]").forEach(el => (el.onchange = upd(t => (u.ics[DEMOD_SLOT].channels[+t.dataset.djob].job = t.value))));
    box.querySelectorAll("[data-dsrc]").forEach(el => (el.onchange = upd(t => (u.ics[DEMOD_SLOT].channels[+t.dataset.dsrc].source = t.value || null))));
    box.querySelectorAll("[data-alabel]").forEach(el => (el.onchange = upd(t => (u.antennas[+t.dataset.alabel].label = t.value))));
    box.querySelectorAll("[data-aband]").forEach(el => (el.onchange = upd(t => {
      const a = u.antennas[+t.dataset.aband];
      a.bands = t.checked ? [...new Set([...(a.bands || []), t.value])] : (a.bands || []).filter(b => b !== t.value);
    })));
    box.querySelectorAll("[data-adel]").forEach(el => (el.onclick = upd(t => {
      const id = u.antennas[+t.dataset.adel].id;
      u.antennas.splice(+t.dataset.adel, 1);
      TUNER_SLOTS.forEach(s => (u.ics[s].tuners || []).forEach(x => { if (x.feed && x.feed.antenna === id) x.feed = null; }));
    })));
    $("#uc-addant").onclick = upd(() => {
      let k = u.antennas.length + 1;
      while (u.antennas.some(a => a.id === `ANT${k}`)) k++;
      u.antennas.push({id: `ANT${k}`, label: "", bands: ["FM"]});
    });
    $("#uc-linking").onchange = upd(t => (u.linking = t.checked));
  }

  // ---------------------------------------------------------------- toolbar
  let zoom = 1;
  function changed() { dirty = true; $("#bc-status").textContent = "Unsaved changes"; render(); }
  $("#bc-add").addEventListener("change", e => { if (e.target.value) { addDevice(e.target.value); e.target.value = ""; changed(); } });
  $("#bc-auto").addEventListener("click", () => { autoComplete(); changed(); });
  $("#bc-compact").checked = S.compact;
  $("#bc-compact").addEventListener("change", e => { S.compact = e.target.checked; render(); });
  $("#bc-zoom-in").addEventListener("click", () => { zoom = Math.min(2, zoom + 0.15); render(); });
  $("#bc-zoom-out").addEventListener("click", () => { zoom = Math.max(0.4, zoom - 0.15); render(); });
  $("#bc-clear").addEventListener("click", () => { if (confirm("Remove everything from the diagram?")) { S.devices = []; S.blocks = []; S.links = []; changed(); } });
  $("#bc-name").value = initial.name || "";
  $("#bc-name").addEventListener("input", () => { dirty = true; $("#bc-status").textContent = "Unsaved changes"; });

  $("#bc-save").addEventListener("click", async () => {
    const body = JSON.stringify({name: $("#bc-name").value, data: S});
    const res = await fetch(configId ? `/api/broadcast/configs/${configId}` : "/api/broadcast/configs",
      {method: configId ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body});
    if (!res.ok) { $("#bc-status").textContent = `Not saved (${res.status})`; return; }
    const out = await res.json();
    if (!configId) { configId = out.id; history.replaceState(null, "", `/broadcast/configurations/${configId}`); }
    $("#bc-name").value = out.name;
    dirty = false;
    $("#bc-status").textContent = "Saved";
  });
  window.addEventListener("beforeunload", e => { if (dirty) e.preventDefault(); });

  const download = (name, type, text) => {
    const a = Object.assign(document.createElement("a"), {href: URL.createObjectURL(new Blob([text], {type})), download: name});
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  const fileBase = () => ($("#bc-name").value || "configuration").replace(/[^\w.-]+/g, "_");
  $("#bc-svg-dl").addEventListener("click", () => {
    const svg = $("#bc-svg").cloneNode(true);
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.insertAdjacentHTML("afterbegin", `<style>${document.getElementById("bc-svg-style").textContent}</style>`);
    download(`${fileBase()}.svg`, "image/svg+xml", svg.outerHTML);
  });
  $("#bc-json-dl").addEventListener("click", () => download(`${fileBase()}.json`, "application/json", JSON.stringify({name: $("#bc-name").value, data: S}, null, 1)));
  $("#bc-json-ul").addEventListener("change", async e => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      S = Object.assign({devices: [], blocks: [], links: [], compact: true}, j.data || j);
      if (j.name) $("#bc-name").value = j.name;
      changed();
    } catch { alert("That file is not a saved configuration."); }
    e.target.value = "";
  });

  // ---------------------------------------------------------------- start from standards
  function suggestions(want, paths) {
    const digital = want.filter(isDigitalStd), analog = want.filter(s => !isDigitalStd(s));
    const covers = (have, need) => need.every(s => have.includes(s));
    const out = [];
    if (paths === 1)
      for (const r of CATALOG.filter(c => c.role === "receiver" && covers([...c.analog, ...c.digital_decode], want)))
        out.push({title: `${r.mpn} single-chip receiver`, devices: [r.mpn], why: [...r.analog, ...r.digital_decode].join(", ")});
    const tuners = CATALOG.filter(c => c.role === "tuner" && covers(c.analog, analog) && covers(c.digital_iq, digital));
    const copros = CATALOG.filter(c => c.role === "coprocessor" && covers(c.digital_decode, digital) && (c.channels || 0) >= paths);
    for (const t of tuners) {
      const n = Math.ceil(paths / (t.tuners || 1));
      const ts = Array(n).fill(t.mpn);
      if (!digital.length) { out.push({title: `${n}× ${t.mpn}`, devices: ts, why: t.analog.join(", ")}); continue; }
      const c = copros.sort((a, b) => a.channels - b.channels || a.options.length - b.options.length)[0];
      if (c) out.push({title: `${n}× ${t.mpn} + ${c.mpn}`, devices: [...ts, c.mpn], why: `${t.mpn}: ${t.analog.join(", ")}; ${c.mpn}: ${c.digital_decode.join("/")} ${c.channels} ch${c.options.length ? `, ${c.options.join("; ")}` : ""}`});
    }
    return out.slice(0, 12);
  }
  $("#bc-suggest").addEventListener("click", () => {
    const want = [...root.querySelectorAll("input[name=std]:checked")].map(i => i.value);
    const paths = +$("#bc-paths").value;
    const list = suggestions(want, paths);
    $("#bc-suggestions").innerHTML = list.length
      ? list.map((s, i) => `<li><button type="button" class="outline small-btn" data-i="${i}">Use</button> <b>${esc(s.title)}</b><br><small class="muted">${esc(s.why)}</small></li>`).join("")
      : `<li class="muted">No combination in the data shorts covers ${esc(want.join(", ") || "nothing selected")} with ${paths} path${paths > 1 ? "s" : ""}.</li>`;
    $("#bc-suggestions").querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
      if (S.devices.length && !confirm("Replace the current diagram?")) return;
      S.devices = []; S.blocks = []; S.links = [];
      list[+b.dataset.i].devices.forEach(addDevice);
      autoComplete();
      changed();
    }));
  });

  $("#bc-preset").addEventListener("change", e => {
    const i = e.target.value;
    if (i === "") return;
    if (S.devices.length && !confirm("Replace the current diagram with this use case?")) { e.target.value = ""; return; }
    applyPreset(+i);
    e.target.value = "";
    changed();
  });

  render();
  if (!S.devices.length) $("#bc-start").open = true;
})();
