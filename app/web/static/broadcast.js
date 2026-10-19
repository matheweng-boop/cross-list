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
  const GUIDE = JSON.parse(document.getElementById("bc-guidance").textContent);
  const EXPLAIN = JSON.parse(document.getElementById("bc-explanations").textContent);
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
    for (const g of guidanceFor(D, p)) add(`Add ${g.label}: ${g.detail}`, () => addGuidance(D, p, g), hasGuidance(D, p, g) ? "already added" : "application guidance");
    add("Add note…", () => noteOn(d, p));
    if (conn.length) add(`Disconnect (${conn.length})`, () => removeLinks(l => conn.includes(l)));
    return items;
  }

  // Application guidance (data/broadcast/guidance.yaml): extra parts on named pins of matching families
  function guidanceFor(o, p) {
    if (!GUIDE || !GUIDE.pins || !new RegExp(GUIDE.applies_to || ".").test(o.mpn)) return [];
    return GUIDE.pins[p.name] || [];
  }
  const hasGuidance = (o, p, g) => linksAt(o.id, p.n).some(l => { const b = block(l.b.blk); return b && b.label === g.label && b.detail === g.detail; });
  function addGuidance(o, p, g) {
    const b = addBlock(g.kind === "cap" ? "cap" : "guide", g.label, g.detail);
    if (g.note) b.note = g.note;
    link({d: o.id, pins: [p.n]}, {blk: b.id}, g.kind === "cap" ? "cap" : "guide");
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
      if (!S.usecase && pinsOf(o).some(p => p.fn === "xtal" && free(p))) attachCrystal(o.id);
      for (const p of pinsOf(o)) for (const g of guidanceFor(o, p)) if (!hasGuidance(o, p, g)) addGuidance(o, p, g);
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
  function openMenu(ev, title, items, xp = "") {
    menu.innerHTML = `<div class="bc-menu-title">${title}</div>` + (xp ? `<div class="bc-menu-xp">${esc(xp)}</div>` : "") + items.map((it, i) =>
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
      explain(`fn:${p.fn}`, `${o.mpn} · ${p.name}`);
      const title = `${esc(o.mpn)} · ${p.num === "" ? "signal" : `pin ${p.num ?? p.n}`} <b>${esc(p.name)}</b><br><small>${esc(FN_LABEL[p.fn] || p.fn)}${p.bus ? ` · ${esc(p.bus)}` : ""}${p.band ? ` · ${esc(p.band)}` : ""}${p.note ? ` · ${esc(p.note)}` : ""}</small>`;
      return openMenu(ev, title, pinMenu(d, p), EXPLAIN[`fn:${p.fn}`] || "");
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
    openMenu(ev, `<b>${esc(b.label)}</b>${b.detail ? `<br><small>${esc(b.detail)}</small>` : ""}${b.note ? `<br><small class="muted">${esc(b.note)}</small>` : ""}${b.kind === "guide" ? `<br><small class="muted">${esc(GUIDE.source || "")}</small>` : ""}`, [
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
  //   rf: {IC0: {pinName: "ANT1" | "loop:IC0.LTA"}},
  //   clock: {master: "IC0", crystal: "36.864 MHz", feed: {IC1: "star" | "own" | "chain:ICx"}},
  //   audio: {fs: 48, bits: 32, slots: 2, format: "I2S"}, memory: {IC0: "4 MB"},
  //   ics: {IC0..IC2: {mpn, tuners: [{job}]}, IC3: {mpn, channels: [{job, source}]}}}
  const TUNER_SLOTS = ["IC0", "IC1", "IC2"], DEMOD_SLOT = "IC3", ALL_SLOTS = [...TUNER_SLOTS, DEMOD_SLOT];
  const TUNER_JOBS = {
    off: {label: "Not used"},
    amfm_audio: {label: "AM or FM audio (foreground)", fg: true, analog: ["AM", "FM"], band: ["AM", "FM"]},
    fm_audio: {label: "FM audio (foreground)", fg: true, analog: ["FM"], band: ["FM"]},
    am_audio: {label: "AM audio (foreground)", fg: true, analog: ["AM"], band: ["AM"]},
    fm_pd: {label: "FM phase diversity audio", fg: true, pd: true, analog: ["FM"], band: ["FM"]},
    fm_mrc: {label: "FM, second branch for HD MRC", analog: ["FM"], iq: ["HD"], band: ["FM"]},
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
    hd_mrc: {label: "HD MRC (second branch)", std: "HD", mrc: true},
    dab_audio: {label: "DAB audio", std: "DAB", audio: true},
    dab_scanless: {label: "DAB scanless / service list", std: "DAB"},
    dab_mrc: {label: "DAB MRC (second branch)", std: "DAB", mrc: true},
    drm_audio: {label: "DRM audio", std: "DRM", audio: true},
    cdr_audio: {label: "CDR audio", std: "CDR", audio: true},
  };
  // tuner jobs that can feed a demod channel of a given standard
  const FEEDS_STD = {HD: ["amfm_audio", "fm_audio", "am_audio", "fm_pd", "fm_mrc", "fm_scan", "am_scan"], DAB: ["dab", "fm_dab_scan"], DRM: ["drm"], CDR: ["fm_audio", "fm_scan", "amfm_audio"]};
  const LOOP_OUT = /^(LT[AB]|FMO|B3O|AMO|LBO)$/; // loop-through (buffer) outputs
  const PIN_PF = (GUIDE.clock && GUIDE.clock.input_pf) || [4.5, 5];
  const MAX_PF = (GUIDE.clock && GUIDE.clock.clko_max_load_pf) || 50;
  const ZIF_MAX_PF = (GUIDE.zif && GUIDE.zif.clk_fs_max_load_pf) || 50;

  const slotDev = slot => S.devices.find(o => o.slot === slot);
  const tunerCount = o => (o ? info(o).tuners || 1 : 0);
  const demodChannels = o => (o ? info(o).channels || 4 : 0);
  const U = () => S.usecase;
  const pinByName = (o, name) => pinsOf(o).find(p => p.name === name);
  const bandsOf = p => String(p.band || "").toUpperCase().split("/").map(b => (b.includes("DAB") ? "DAB" : b.trim())).filter(Boolean);
  // tuner index of an RF pin on a dual tuner: A/0 -> 0, B/1 -> 1, otherwise shared (null)
  const tunerOfPin = (o, p) => {
    if (tunerCount(o) < 2) return 0;
    const m = p.name.split("/")[0].match(/([AB01])$/);
    return m ? (m[1] === "A" || m[1] === "0" ? 0 : 1) : null;
  };
  const clockIn = o => pinsOf(o).find(p => p.fn === "refclk") || pinByName(o, "XTALI") || pinsOf(o).find(p => p.fn === "xtal");

  function jobLines(o) {
    const u = U();
    if (!u || !o.slot || !u.ics[o.slot]) return [];
    const ic = u.ics[o.slot];
    if (o.slot === DEMOD_SLOT)
      return (ic.channels || []).map((c, i) => `DMOD${i}: ${DEMOD_JOBS[c.job]?.label || c.job}${c.source && c.job !== "unused" ? ` ← ${c.source.replace(".", " ")}` : ""}`);
    return (ic.tuners || []).map((t, i) => `T${i}: ${TUNER_JOBS[t.job]?.label || t.job}`);
  }

  function normalise(u) {
    u.rf ||= {}; u.antennas ||= [];
    u.clock = Object.assign({master: "IC0", crystal: (GUIDE.clock && GUIDE.clock.crystal) || "", feed: {}}, u.clock || {});
    u.audio = Object.assign({fs: 48, bits: 32, slots: 2, format: "I2S"}, u.audio || {});
    u.memory ||= {};
    for (const s of ALL_SLOTS) u.ics[s] ||= {mpn: null};
    return u;
  }

  function syncUseCase() {
    const u = U();
    if (!u) return;
    normalise(u);
    for (const slot of ALL_SLOTS) {
      const ic = u.ics[slot], o = slotDev(slot);
      if (ic.mpn && !o) addDevice(ic.mpn).slot = slot;
      else if (ic.mpn && o && o.mpn !== ic.mpn) replaceDevice(o.id, ic.mpn);
      else if (!ic.mpn && o) removeDevice(o.id);
      const d = slotDev(slot);
      if (slot === DEMOD_SLOT) ic.channels = Array.from({length: demodChannels(d)}, (_, i) => (ic.channels || [])[i] || {job: "unused"});
      else ic.tuners = Array.from({length: tunerCount(d)}, (_, i) => (ic.tuners || [])[i] || {job: "off"});
    }
    S.links = S.links.filter(l => l.auto !== "uc");
    S.blocks = S.blocks.filter(b => !b.uc);
    const ucBlock = (kind, label, detail) => Object.assign(addBlock(kind, label, detail), {uc: true});
    // antennas and loop-throughs, per RF pin
    const antBlock = {};
    for (const a of u.antennas) antBlock[a.id] = ucBlock("antenna", `${a.id} ${a.label || ""}`.trim(), (a.bands || []).join(" / "));
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot);
      if (!o) continue;
      const byAnt = {};
      for (const [name, feed] of Object.entries(u.rf[slot] || {})) {
        const p = pinByName(o, name);
        if (!p || !feed) continue;
        if (feed.startsWith("loop:")) {
          const [src, out] = feed.slice(5).split(".");
          const so = slotDev(src), sp = so && pinByName(so, out);
          if (sp) link({d: so.id, pins: [sp.n]}, {d: o.id, pins: [p.n]}, "rf", `loop-through ${out}`, "uc");
        } else if (antBlock[feed]) (byAnt[feed] ||= []).push(p.n);
      }
      for (const [ant, pins] of Object.entries(byAnt)) link({d: o.id, pins}, {blk: antBlock[ant].id}, "rf", "", "uc");
    }
    // reference clock: crystal on the master, CLKO of the master to every other IC (star)
    const master = slotDev(u.clock.master);
    if (master) {
      const x = pinsOf(master).filter(p => p.fn === "xtal");
      if (x.length) link({d: master.id, pins: x.map(p => p.n)}, {blk: ucBlock("crystal", "Crystal", `${u.clock.crystal || "frequency: see datasheet"} · system reference`).id}, "xtal", "", "uc");
      for (const slot of ALL_SLOTS) {
        const o = slotDev(slot);
        if (!o || o === master) continue;
        const mode = u.clock.feed[slot] || "star", inp = clockIn(o);
        if (!inp) continue;
        if (mode === "own") {
          const xs = pinsOf(o).filter(p => p.fn === "xtal");
          if (xs.length) link({d: o.id, pins: xs.map(p => p.n)}, {blk: ucBlock("crystal", "Crystal", "own crystal").id}, "xtal", "", "uc");
        } else {
          const src = mode.startsWith("chain:") ? slotDev(mode.slice(6)) : master;
          const out = src && pinsOf(src).find(p => p.fn === "clock_out" && /CLKO/.test(p.name));
          if (out) link({d: src.id, pins: [out.n]}, {d: o.id, pins: [inp.n]}, "clock", `${u.clock.crystal || "ref clock"}${mode.startsWith("chain:") ? " (daisy chain)" : ""}`, "uc");
        }
      }
    }
    // I/Q: each source tuner's I/Q pair (shared ZIFCLK / ZIFFS) to its own demod port
    const demod = slotDev(DEMOD_SLOT);
    if (demod) {
      const ports = uniqueBus(demod, "iq_in");
      const chans = u.ics[DEMOD_SLOT].channels;
      const sources = [...new Set(chans.filter(c => c.job !== "unused" && c.source).map(c => c.source))];
      sources.forEach((src, k) => {
        const [slot, t] = src.split("."), o = slotDev(slot), port = ports[k];
        if (!o || !port) return;
        const ti = +t.slice(1), iq = pinsOf(o).filter(p => p.fn === "iq_out");
        const data = iq.filter(p => /ZIF[IQ]/.test(p.name)).filter(p => { const m = p.name.match(/ZIF[IQ](\d)/); return !m || +m[1] === ti; });
        const shared = iq.filter(p => /CLK|FS/.test(p.name));
        const used = chans.map((c, i) => (c.source === src && c.job !== "unused" ? `DMOD${i}` : null)).filter(Boolean);
        if (data.length) link({d: o.id, pins: [...shared, ...data].map(p => p.n), bus: `${port.bus} from ${t}`}, endOf(demod.id, port), "iq", `${t} I/Q → ${used.join(", ")}`, "uc");
      });
    }
    // flash blocks show the size entered for their IC
    for (const slot of ALL_SLOTS) {
      const o = slotDev(slot);
      if (!o) continue;
      for (const l of S.links.filter(l => l.kind === "flash" && l.a.d === o.id)) {
        const b = block(l.b.blk);
        if (b) b.detail = u.memory[slot] ? `size: ${u.memory[slot]}` : "size: not in data short";
      }
    }
    pruneBlocks();
  }

  // Checks: [level, text]; level ok / info / warn / error.
  function checks() {
    const u = U(), out = [];
    if (!u) return out;
    let audio = 0;
    const antIcs = {};
    const featureText = o => (info(o).features || []).join(" ");
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot), ic = u.ics[slot];
      if (!o) continue;
      const rf = u.rf[slot] || {};
      const ts = ic.tuners || [];
      for (const [name, feed] of Object.entries(rf)) {
        if (!feed) continue;
        if (!pinByName(o, name)) { out.push(["warn", `${slot} (${o.mpn}) has no pin ${name}; its antenna assignment is ignored.`]); continue; }
        if (feed.startsWith("loop:")) {
          const [src, pin] = feed.slice(5).split(".");
          if (src === slot) out.push(["error", `${slot} ${name} cannot loop through from its own IC.`]);
          else if (!slotDev(src)) out.push(["error", `${slot} ${name} loops through from ${src}, which is not populated.`]);
          else if (!pinByName(slotDev(src), pin)) out.push(["error", `${src} has no ${pin} loop-through output.`]);
        } else (antIcs[feed] ||= new Set()).add(slot);
      }
      const fed = (i, band) => Object.entries(rf).some(([name, feed]) => {
        const p = pinByName(o, name);
        return feed && p && bandsOf(p).includes(band) && [i, null].includes(tunerOfPin(o, p));
      });
      ts.forEach((t, i) => {
        const J = TUNER_JOBS[t.job] || {};
        if (t.job === "off") return;
        const missing = [...(J.analog || []).filter(x => !info(o).analog.includes(x)), ...(J.iq || []).filter(x => !info(o).digital_iq.includes(x))];
        if (missing.length) out.push(["error", `${slot} T${i} (${o.mpn}) cannot do ${J.label}: no ${missing.join(", ")} in its data short.`]);
        if (J.fg) audio++;
        for (const band of J.band || []) if (!fed(i, band)) out.push(["error", `${slot} T${i} (${J.label}) has no ${band} antenna or loop-through on its ${band} input.`]);
      });
      const pd = ts.map((t, i) => [t, i]).filter(([t]) => t.job === "fm_pd");
      if (pd.length === 1) out.push(["error", `${slot}: FM phase diversity needs both tuners of the IC.`]);
      if (pd.length === 2) {
        audio--; // the pair is one listening source
        const fmAnt = i => Object.entries(rf).filter(([n, f]) => { const p = pinByName(o, n); return p && f && bandsOf(p).includes("FM") && tunerOfPin(o, p) === i; }).map(([, f]) => f);
        const a0 = fmAnt(0), a1 = fmAnt(1);
        if (u.antennas.length < 2) out.push(["error", `${slot}: phase diversity needs two antennas; this is a single-antenna system.`]);
        else if (a0.length && a1.length && a0.every(f => a1.includes(f))) out.push(["error", `${slot}: both FM inputs are on ${a0[0]}. Phase diversity needs the two FM inputs on different antennas.`]);
      }
    }
    for (const [ant, ics] of Object.entries(antIcs))
      if (ics.size > 1) out.push(["warn", `${ant} goes directly into ${[...ics].join(" and ")}: that needs a splitter. Usually the antenna enters one IC and the next IC is fed from its loop-through outputs.`]);
    for (const a of u.antennas) if (!antIcs[a.id]) out.push(["warn", `${a.id} is not connected to any tuner.`]);

    const demod = slotDev(DEMOD_SLOT);
    let hdCh = 0, hdMrc = false;
    if (demod) {
      const chans = u.ics[DEMOD_SLOT].channels || [];
      chans.forEach((c, i) => {
        const J = DEMOD_JOBS[c.job] || {};
        if (c.job === "unused") return;
        if (J.audio) audio++;
        if (J.std === "HD") hdCh++;
        if (c.job === "hd_mrc") hdMrc = true;
        if (!info(demod).digital_decode.includes(J.std)) out.push(["error", `DMOD${i}: ${demod.mpn} does not decode ${J.std} (its ordering code covers ${info(demod).digital_decode.join(", ") || "none"}).`]);
        const [slot, tn] = (c.source || "").split(".");
        const o = slotDev(slot), t = o && (u.ics[slot].tuners || [])[+String(tn).slice(1)];
        if (!o || !t) { out.push(["error", `DMOD${i} (${J.label}) has no source tuner.`]); return; }
        if (!info(o).digital_iq.includes(J.std)) out.push(["error", `DMOD${i}: ${slot} (${o.mpn}) has no ${J.std} I/Q output.`]);
        if (!(FEEDS_STD[J.std] || []).includes(t.job)) out.push(["warn", `DMOD${i} (${J.label}) is fed by ${slot} ${tn}, which is set to "${TUNER_JOBS[t.job]?.label}".`]);
        if (J.mrc) {
          const primary = chans.find(x => x !== c && DEMOD_JOBS[x.job]?.std === J.std && !DEMOD_JOBS[x.job]?.mrc);
          if (!primary) out.push(["error", `DMOD${i}: MRC needs a main ${J.std} channel to combine with.`]);
          else if (primary.source === c.source) out.push(["error", `DMOD${i}: MRC needs the second branch from the other tuner, not ${c.source} again.`]);
          if (!/MRC/.test(featureText(o))) out.push(["warn", `${slot} (${o.mpn}): its data short does not mention ${J.std} MRC.`]);
        }
      });
      const ports = uniqueBus(demod, "iq_in").length, srcs = new Set(chans.filter(c => c.job !== "unused" && c.source).map(c => c.source));
      if (srcs.size > ports) out.push(["error", `${demod.mpn} has ${ports} I/Q input ports for ${srcs.size} tuner I/Q pairs.`]);
      // shared ZIFCLK / ZIFFS fan-out per tuner IC
      const perIc = {};
      srcs.forEach(s => (perIc[s.split(".")[0]] = (perIc[s.split(".")[0]] || 0) + 1));
      for (const [slot, n] of Object.entries(perIc)) if (n > 1) {
        const pf = n * PIN_PF[1];
        out.push([pf > ZIF_MAX_PF ? "error" : "info", `${slot} ZIFCLK / ZIFFS drive ${n} demod inputs: ${(n * PIN_PF[0]).toFixed(1)}–${pf.toFixed(1)} pF of the ${ZIF_MAX_PF} pF limit, leaving ≈${Math.max(0, ZIF_MAX_PF - pf).toFixed(0)} pF for traces.`]);
      }
    }
    if (!audio && S.devices.some(o => o.slot)) out.push(["error", "No tuner or demod channel plays audio in the foreground."]);

    // clock tree
    const master = slotDev(u.clock.master);
    if (master) {
      const loads = {};
      for (const slot of ALL_SLOTS) {
        const o = slotDev(slot);
        if (!o || o === master) continue;
        const mode = u.clock.feed[slot] || "star";
        if (mode === "own") { out.push(["info", `${slot} uses its own crystal instead of the system reference from ${u.clock.master}.`]); continue; }
        const src = mode.startsWith("chain:") ? mode.slice(6) : u.clock.master;
        if (mode.startsWith("chain:")) out.push(["warn", `${slot} takes its clock from ${src} CLKO (daisy chain). This degrades phase noise; feed it from ${u.clock.master} CLKO directly.`]);
        if (!slotDev(src)) out.push(["error", `${slot} takes its clock from ${src}, which is not populated.`]);
        loads[src] = (loads[src] || 0) + 1;
        if (!clockIn(o)) out.push(["warn", `${slot} (${o.mpn}): no clock input pin found in its data short.`]);
      }
      for (const [src, n] of Object.entries(loads)) {
        const pf = n * PIN_PF[1];
        out.push([pf > MAX_PF ? "error" : "info", `${src} CLKO drives ${n} clock input${n > 1 ? "s" : ""}: ${(n * PIN_PF[0]).toFixed(1)}–${pf.toFixed(1)} pF of the ${MAX_PF} pF limit, leaving ≈${Math.max(0, MAX_PF - pf).toFixed(0)} pF for traces.`]);
      }
    }
    // seamless linking FM <-> DAB needs a DAB-capable tuner that is not playing audio
    if (u.linking) {
      if (!demod || !info(demod).options.some(x => /seamless/i.test(x))) out.push(["error", "Seamless linking needs a demodulator with seamless blending / linking."]);
      const all = TUNER_SLOTS.flatMap(s => (u.ics[s].tuners || []).map((t, i) => ({s, i, t}))).filter(x => slotDev(x.s));
      const fmFg = all.filter(x => ["fm_audio", "amfm_audio", "fm_pd"].includes(x.t.job));
      const linkTuner = all.find(x => !TUNER_JOBS[x.t.job]?.fg && info(slotDev(x.s)).digital_iq.includes("DAB"));
      if (fmFg.length && !linkTuner)
        out.push(["error", fmFg.some(x => x.t.job === "fm_pd")
          ? "Seamless linking FM ↔ DAB needs a free DAB tuner, but phase diversity occupies the dual tuner. Step out of phase diversity to link, or add a tuner IC."
          : "Seamless linking FM ↔ DAB needs a second, DAB-capable tuner that is not playing audio."]);
    }
    // licences (application guidance)
    if (hdCh) out.push(["info", `Licences: ${hdCh} HD I/Q channel licence${hdCh > 1 ? "s" : ""}${hdMrc ? " + 1 HD MRC licence" : ""}.`]);
    const a = u.audio;
    out.push(["info", `Audio ${a.format}: ${a.fs} kHz × ${a.bits} bit × ${a.slots} slots → bit clock ${(a.fs * a.bits * a.slots / 1000).toFixed(3)} MHz.`]);
    if (!out.some(([l]) => l === "warn" || l === "error")) out.unshift(["ok", "No conflicts found."]);
    return out;
  }

  // Pin menu entries for an RF input of a device in a use case
  function rfMenu(D, p) {
    const u = U(), items = [], rf = (u.rf[D.slot] ||= {});
    const set = v => () => { rf[p.name] = v; syncUseCase(); };
    for (const a of u.antennas) items.push({label: `Connect ${a.id} (${(a.bands || []).join("/")})`, fn: set(a.id), hint: rf[p.name] === a.id ? "connected" : ""});
    for (const s of TUNER_SLOTS) {
      const so = slotDev(s);
      if (s === D.slot || !so) continue;
      for (const q of pinsOf(so).filter(q => LOOP_OUT.test(q.name))) items.push({label: `Loop-through from ${s} ${q.name}`, fn: set(`loop:${s}.${q.name}`), hint: q.note || ""});
    }
    items.push({label: "Add a new antenna here", fn: () => {
      let k = u.antennas.length + 1;
      while (u.antennas.some(a => a.id === `ANT${k}`)) k++;
      u.antennas.push({id: `ANT${k}`, label: bandsOf(p).join("/"), bands: bandsOf(p).length ? bandsOf(p) : ["FM"]});
      set(`ANT${k}`)();
    }});
    if (rf[p.name]) items.push({label: "Disconnect antenna", fn: set(null)});
    return items;
  }

  function applyPreset(i) {
    const pr = JSON.parse(JSON.stringify(PRESETS[i]));
    S.devices = []; S.blocks = []; S.links = [];
    S.usecase = normalise({name: pr.name, region: pr.region, linking: !!pr.linking, notes: pr.notes || "", antennas: pr.antennas || [],
      rf: pr.rf || {}, clock: pr.clock, audio: pr.audio, memory: pr.memory, ics: pr.ics || {}});
    syncUseCase();
    autoComplete();
    if (!$("#bc-name").value || PRESETS.some(x => x.name === $("#bc-name").value)) $("#bc-name").value = pr.name;
  }

  function opt(value, label, sel) { return `<option value="${esc(value)}"${value === sel ? " selected" : ""}>${esc(label)}</option>`; }

  function renderUseCase() {
    const box = $("#bc-usecase"), u = U();
    if (!u) {
      box.innerHTML = `<p class="small muted">No use case yet. Pick one above, or <button type="button" class="outline small-btn" data-uc="blank">start an empty use case</button>.</p>`;
      box.querySelector("[data-uc=blank]").onclick = () => {
        S.usecase = normalise({name: "", region: "", linking: false, notes: "", antennas: [{id: "ANT1", label: "AM/FM", bands: ["AM", "FM"]}], ics: {}});
        syncUseCase(); changed();
      };
      return;
    }
    const tunersCat = CATALOG.filter(c => c.role !== "coprocessor"), demodsCat = CATALOG.filter(c => c.role === "coprocessor");
    const srcOpts = sel => opt("", "— source —", sel || "") + TUNER_SLOTS.filter(slotDev).flatMap(s => (u.ics[s].tuners || []).map((_, i) => opt(`${s}.T${i}`, `${s} T${i}`, sel))).join("");
    const feedOpts = (slot, sel) => opt("", "—", sel || "") + u.antennas.map(a => opt(a.id, a.id, sel)).join("") +
      TUNER_SLOTS.filter(s => s !== slot && slotDev(s)).flatMap(s => pinsOf(slotDev(s)).filter(q => LOOP_OUT.test(q.name)).map(q => opt(`loop:${s}.${q.name}`, `loop ${s} ${q.name}`, sel))).join("");
    const clockOpts = (slot, sel) => opt("star", `${u.clock.master} CLKO (star)`, sel) + opt("own", "own crystal", sel) +
      ALL_SLOTS.filter(s => s !== slot && s !== u.clock.master && slotDev(s)).map(s => opt(`chain:${s}`, `${s} CLKO (daisy chain)`, sel)).join("");
    let rows = "";
    for (const slot of TUNER_SLOTS) {
      const ic = u.ics[slot], o = slotDev(slot);
      const rfPins = o ? pinsOf(o).filter(p => p.fn === "rf_in") : [];
      rows += `<tr><th>${slot}</th><td><select data-slot="${slot}" aria-label="${slot} part">${opt("", "Not populated", ic.mpn || "")}${tunersCat.map(c => opt(c.mpn, `${c.mpn} · ${c.tuners || 1} tuner${(c.tuners || 1) > 1 ? "s" : ""} · ${[...c.analog, ...c.digital_iq.map(s => s + " I/Q"), ...c.digital_decode].join(" ")}`, ic.mpn || "")).join("")}</select>` +
        (o ? `<div class="uc-rf">${rfPins.map(p => `<label>${esc(p.name)}<select data-rf="${slot}|${esc(p.name)}" data-xp="feed:" aria-label="${slot} ${esc(p.name)} antenna">${feedOpts(slot, (u.rf[slot] || {})[p.name])}</select></label>`).join("")}</div>` +
          (slot !== u.clock.master ? `<label class="uc-clock">Clock <select data-clock="${slot}" data-xp="clock:">${clockOpts(slot, u.clock.feed[slot] || "star")}</select></label>` : `<p class="small muted uc-clock">Crystal ${esc(u.clock.crystal)} · system reference</p>`) : "") +
        `</td><td>` + (ic.tuners || []).map((t, i) => `<div class="uc-row"><b>T${i}</b><select data-job="${slot}.${i}" data-xp="job:" aria-label="${slot} tuner ${i} job">${Object.entries(TUNER_JOBS).map(([k, j]) => opt(k, j.label, t.job)).join("")}</select></div>`).join("") + `</td></tr>`;
    }
    const dm = u.ics[DEMOD_SLOT], dO = slotDev(DEMOD_SLOT);
    rows += `<tr><th>${DEMOD_SLOT}</th><td><select data-slot="${DEMOD_SLOT}" aria-label="Demodulator part">${opt("", "Not populated", dm.mpn || "")}${demodsCat.map(c => opt(c.mpn, `${c.mpn} · ${c.digital_decode.join("/") || "AM/FM"} · ${c.channels || "SW-defined"} ch${c.options.length ? " · " + c.options.join(", ") : ""}`, dm.mpn || "")).join("")}</select>` +
      (dO && DEMOD_SLOT !== u.clock.master ? `<label class="uc-clock">Clock <select data-clock="${DEMOD_SLOT}" data-xp="clock:">${clockOpts(DEMOD_SLOT, u.clock.feed[DEMOD_SLOT] || "star")}</select></label>` : "") + `</td><td>` +
      (dm.channels || []).map((c, i) => `<div class="uc-row"><b>DMOD${i}</b><select data-djob="${i}" data-xp="djob:" aria-label="DMOD${i} job">${Object.entries(DEMOD_JOBS).map(([k, j]) => opt(k, j.label, c.job)).join("")}</select>` +
        `<select data-dsrc="${i}" aria-label="DMOD${i} source">${srcOpts(c.source)}</select></div>`).join("") + `</td></tr>`;
    const ants = u.antennas.map((a, i) => `<span class="uc-ant"><b>${esc(a.id)}</b> <input data-alabel="${i}" value="${esc(a.label || "")}" aria-label="${esc(a.id)} label">` +
      ["AM", "FM", "DAB"].map(b => `<label><input type="checkbox" data-aband="${i}" value="${b}"${(a.bands || []).includes(b) ? " checked" : ""}> ${b}</label>`).join("") +
      `<button type="button" class="outline secondary small-btn" data-adel="${i}" aria-label="Remove ${esc(a.id)}">×</button></span>`).join("");
    const memSlots = ALL_SLOTS.filter(s => slotDev(s) && pinsOf(slotDev(s)).some(p => p.fn === "flash" || p.fn === "memory"));
    const cs = checks();
    const a = u.audio;
    box.innerHTML = `<div class="uc-head"><b>${esc(u.name || "Use case")}</b>${u.region ? ` <span class="muted">· ${esc(u.region)}</span>` : ""}
        <label class="bc-check" data-explain="linking"><input type="checkbox" id="uc-linking"${u.linking ? " checked" : ""}> Seamless linking</label></div>
      ${u.notes ? `<p class="small muted">${esc(u.notes)}</p>` : ""}
      <div class="uc-ants" data-explain="antennas">Antennas (${u.antennas.length}): ${ants} <button type="button" class="outline small-btn" id="uc-addant">+ antenna</button></div>
      <div class="table-wrap"><table class="uc-table"><thead><tr><th></th><th>Part · RF inputs · clock</th><th>Jobs</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="uc-misc">
        <label data-explain="crystal">Crystal on ${esc(u.clock.master)} <input id="uc-xtal" value="${esc(u.clock.crystal)}"></label>
        <label data-explain="audio">Audio <select id="uc-format">${["I2S", "TDM"].map(f => opt(f, f, a.format)).join("")}</select>
          <select id="uc-fs">${((GUIDE.i2s && GUIDE.i2s.sample_rates_khz) || [48]).map(f => opt(String(f), `${f} kHz`, String(a.fs))).join("")}</select>
          <select id="uc-bits">${[16, 24, 32].map(b => opt(String(b), `${b} bit`, String(a.bits))).join("")}</select>
          <select id="uc-slots">${[2, 4, 8].map(n => opt(String(n), `${n} slots`, String(a.slots))).join("")}</select></label>
        ${memSlots.map(s => `<label data-explain="memory">${s} flash size <input data-mem="${s}" value="${esc(u.memory[s] || "")}" placeholder="not in data short"></label>`).join("")}
      </div>
      <ul class="uc-checks">${cs.filter(([l]) => l !== "info").map(([l, t]) => `<li class="uc-${l}">${{ok: "✓", warn: "⚠", error: "✗"}[l]} ${esc(t)}</li>`).join("")}</ul>
      <details class="uc-checks"><summary>Clock, I/Q loading, licences, audio (${cs.filter(([l]) => l === "info").length})</summary><ul>${cs.filter(([l]) => l === "info").map(([, t]) => `<li class="uc-info">ℹ ${esc(t)}</li>`).join("")}</ul></details>`;
    const upd = fn => e => {
      const k = keyOf(e.target), t = titleOf(e.target);
      fn(e.target); syncUseCase(); changed();
      if (k) explain(k, t);
    };
    box.querySelectorAll("[data-slot]").forEach(el => (el.onchange = upd(t => (u.ics[t.dataset.slot].mpn = t.value || null))));
    box.querySelectorAll("[data-job]").forEach(el => (el.onchange = upd(t => { const [s, i] = t.dataset.job.split("."); u.ics[s].tuners[+i].job = t.value; })));
    box.querySelectorAll("[data-rf]").forEach(el => (el.onchange = upd(t => { const [s, n] = t.dataset.rf.split("|"); (u.rf[s] ||= {})[n] = t.value || null; })));
    box.querySelectorAll("[data-clock]").forEach(el => (el.onchange = upd(t => (u.clock.feed[t.dataset.clock] = t.value))));
    box.querySelectorAll("[data-djob]").forEach(el => (el.onchange = upd(t => (u.ics[DEMOD_SLOT].channels[+t.dataset.djob].job = t.value))));
    box.querySelectorAll("[data-dsrc]").forEach(el => (el.onchange = upd(t => (u.ics[DEMOD_SLOT].channels[+t.dataset.dsrc].source = t.value || null))));
    box.querySelectorAll("[data-alabel]").forEach(el => (el.onchange = upd(t => (u.antennas[+t.dataset.alabel].label = t.value))));
    box.querySelectorAll("[data-aband]").forEach(el => (el.onchange = upd(t => {
      const an = u.antennas[+t.dataset.aband];
      an.bands = t.checked ? [...new Set([...(an.bands || []), t.value])] : (an.bands || []).filter(b => b !== t.value);
    })));
    box.querySelectorAll("[data-adel]").forEach(el => (el.onclick = upd(t => {
      const id = u.antennas[+t.dataset.adel].id;
      u.antennas.splice(+t.dataset.adel, 1);
      for (const s of TUNER_SLOTS) for (const n of Object.keys(u.rf[s] || {})) if (u.rf[s][n] === id) u.rf[s][n] = null;
    })));
    box.querySelectorAll("[data-mem]").forEach(el => (el.onchange = upd(t => (u.memory[t.dataset.mem] = t.value))));
    $("#uc-addant").onclick = upd(() => {
      let k = u.antennas.length + 1;
      while (u.antennas.some(x => x.id === `ANT${k}`)) k++;
      u.antennas.push({id: `ANT${k}`, label: "", bands: ["FM"]});
    });
    $("#uc-linking").onchange = upd(t => (u.linking = t.checked));
    $("#uc-xtal").onchange = upd(t => (u.clock.crystal = t.value));
    $("#uc-format").onchange = upd(t => (a.format = t.value));
    $("#uc-fs").onchange = upd(t => (a.fs = +t.value));
    $("#uc-bits").onchange = upd(t => (a.bits = +t.value));
    $("#uc-slots").onchange = upd(t => (a.slots = +t.value));
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

  // ---------------------------------------------------------------- explanations, system, presets
  const explainBox = $("#bc-explain");
  function explain(key, title) {
    const text = EXPLAIN[key];
    if (!text) return;
    const head = title || key.replace(/^[a-z]+:/, "").replace(/_/g, " ");
    explainBox.innerHTML = `<b>${esc(head)}</b><p>${esc(text)}</p>`;
  }
  // key of a control: fixed data-explain, or data-xp prefix + current value
  function keyOf(el) {
    if (el.dataset.explain) return el.dataset.explain;
    if (!el.dataset.xp) return null;
    const v = el.value || "";
    if (el.dataset.xp === "feed:") return v.startsWith("loop:") ? "feed:loop" : v ? "feed:antenna" : null;
    if (el.dataset.xp === "clock:") return `clock:${v.split(":")[0]}`;
    return el.dataset.xp + v;
  }
  const titleOf = el => (el.tagName === "SELECT" && el.selectedOptions[0] ? el.selectedOptions[0].textContent
    : el.tagName === "BUTTON" ? el.textContent : "").trim().slice(0, 60) || undefined;
  for (const evName of ["mouseover", "focusin"])
    root.addEventListener(evName, e => {
      const el = e.target.closest("[data-explain], [data-xp]");
      if (!el || el.closest("#bc-svg")) return;
      if (el.dataset.preset !== undefined) return showPreset(+el.dataset.preset);
      const k = keyOf(el);
      if (k) explain(k, titleOf(el));
    });
  function showPreset(i) {
    const pr = PRESETS[i];
    explainBox.innerHTML = `<b>${esc(pr.name)}</b><p>${esc(pr.notes || "")}</p>`;
  }
  function renderPresets() {
    root.querySelectorAll("[data-system]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.system === S.system)));
    const box = $("#bc-preset-cards");
    if (!S.system) { box.innerHTML = `<span class="muted small">pick a system first</span>`; return; }
    const list = PRESETS.map((p, i) => [p, i]).filter(([p]) => p.system === S.system);
    box.innerHTML = list.map(([p, i]) => `<button type="button" class="bc-chip" data-preset="${i}" data-explain="preset">${esc(p.name)}</button>`).join("") +
      `<button type="button" class="bc-chip" data-blank="1" data-explain="antennas">Empty use case</button>`;
    box.querySelectorAll("[data-preset]").forEach(b => (b.onclick = () => {
      if (S.devices.length && !confirm("Replace the current diagram with this use case?")) return;
      applyPreset(+b.dataset.preset);
      changed();
      showPreset(+b.dataset.preset);
    }));
    box.querySelector("[data-blank]").onclick = () => {
      if (S.devices.length && !confirm("Start an empty use case and clear the diagram?")) return;
      S.devices = []; S.blocks = []; S.links = [];
      S.usecase = normalise({name: "", region: "", linking: S.system === "DAB", notes: "", antennas: [{id: "ANT1", label: "AM/FM", bands: ["AM", "FM"]}], ics: {}});
      syncUseCase(); changed();
    };
  }
  root.querySelectorAll("[data-system]").forEach(b => (b.onclick = () => { S.system = b.dataset.system; renderPresets(); explain(`system:${S.system}`, b.textContent); }));

  if (!S.system && S.usecase) S.system = (PRESETS.find(p => p.name === S.usecase.name) || {}).system;
  renderPresets();
  render();
})();
