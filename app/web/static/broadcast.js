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
  const CONF = JSON.parse(document.getElementById("bc-presets").textContent);
  const GUIDE = JSON.parse(document.getElementById("bc-guidance").textContent);
  const TF = JSON.parse(document.getElementById("bc-features").textContent), LAYOUTS = TF.layouts || {};
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
    S.blocks = S.blocks.filter(b => used.has(b.id) || (b.kind === "note" && b.free) || (b.kind === "supply" && b.volts));
  }

  // ---------------------------------------------------------------- actions on a pin
  // Supply rails: one block per voltage. A pin that accepts several voltages ("1.8 or 3.3") goes on
  // the rail chosen for I/O (S.vio), or on whichever of its rails already exists.
  // an I/O supply pin whose data brief gives no voltage (Si469x VIO0 / VIO1) follows the I/O rail of the tuners
  // it talks to; that link is labelled "assumed" until the full datasheet confirms it
  const assumedIo = (o, p) => !volts(o, p) && /^VIO/i.test(p.name);
  const voltOptions = (o, p) => (volts(o, p) || (assumedIo(o, p) ? "1.8 or 3.3" : "")).split(/\s*(?:or|\/)\s*/).map(v => v.replace(/\s*V$/, "").trim()).filter(Boolean);
  const railLabel = (o, p) => (assumedIo(o, p) ? "assumed: I/O rail (no voltage in data brief)" : "");
  const railOf = v => S.blocks.find(b => b.kind === "supply" && b.volts === v);
  function rail(v) {
    return railOf(v) || Object.assign(addBlock("supply", `${v} V`, ""), {volts: v});
  }
  const powerLink = (d, n) => S.links.find(l => l.kind === "power" && endHas(l.a, d, n));
  function attachSupply(d, p) {
    const opts = voltOptions(dev(d), p);
    if (!opts.length) {
      link({d, pins: [p.n]}, {blk: sharedBlock("supply", "Supply, voltage unknown", "voltage not in data short").id}, "power");
      return;
    }
    const v = opts.length === 1 ? opts[0] : opts.includes(S.vio || "3.3") ? S.vio || "3.3" : opts.find(railOf) || opts[opts.length - 1];
    const old = powerLink(d, p.n);
    if (old) S.links = S.links.filter(l => l !== old);
    link({d, pins: [p.n]}, {blk: rail(v).id}, "power", railLabel(dev(d), p));
  }
  // Connect every supply pin of every chip that accepts v; pins that also accept another voltage move to v.
  function connectRail(v) {
    let n = 0;
    for (const o of S.devices)
      for (const p of pinsOf(o).filter(p => p.fn === "power")) {
        const opts = voltOptions(o, p);
        if (!opts.includes(v)) continue;
        const cur = powerLink(o.id, p.n), curB = cur && block(cur.b.blk);
        if (curB && curB.volts === v) { n++; continue; }
        if (cur) S.links = S.links.filter(l => l !== cur);
        link({d: o.id, pins: [p.n]}, {blk: rail(v).id}, "power", railLabel(o, p));
        n++;
      }
    if (S.devices.some(o => pinsOf(o).some(p => p.fn === "power" && !assumedIo(o, p) && voltOptions(o, p).length > 1 && voltOptions(o, p).includes(v)))) S.vio = v;
    rail(v);
    pruneBlocks();
    return n;
  }
  function updateRails() {
    for (const b of S.blocks.filter(b => b.kind === "supply")) {
      const ls = S.links.filter(l => l.b.blk === b.id && l.a.d);
      const chips = [...new Set(ls.map(l => { const o = dev(l.a.d); return o ? o.slot || o.mpn : ""; }))].filter(Boolean);
      const n = ls.reduce((k, l) => k + l.a.pins.length, 0);
      if (b.volts) b.detail = n ? `${n} pin${n > 1 ? "s" : ""} · ${chips.join(", ")}` : "not connected";
    }
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
  // Front-end parts on the RF pins an antenna feeds (application guidance), shown inside the antenna block
  function frontEnd(b) {
    const items = [], seen = new Set();
    for (const l of S.links.filter(l => l.b.blk === b.id && l.a.d)) {
      const o = dev(l.a.d);
      for (const n of l.a.pins) {
        const p = o && pin(o, n);
        for (const g of p ? guidanceFor(o, p) : []) {
          const key = g.label + g.detail;
          if (seen.has(key)) continue;
          seen.add(key);
          items.push({label: g.label, detail: g.detail, note: g.note || "", pin: p.name});
        }
      }
    }
    b.items = items;
  }

  function attachAntenna(d, p) {
    const band = p.band || (/AM/.test(p.name) ? "AM" : /FM/.test(p.name) ? "FM" : /B3|DAB/.test(p.name) ? "DAB Band III" : "");
    const b = addBlock("antenna", `${band || "RF"} antenna`, p.name);
    link({d, pins: [p.n]}, {blk: b.id}, "rf");
    frontEnd(b);
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
      case "power": {
        const opts = voltOptions(D, p);
        if (!opts.length) {
          add("Add to the 'voltage unknown' supply", () => attachSupply(d, p), "voltage not in the data short");
          for (const r of S.blocks.filter(b => b.kind === "supply" && b.volts))
            add(`Connect to the ${r.volts} V rail`, () => { const old = powerLink(d, p.n); if (old) S.links = S.links.filter(l => l !== old); link({d, pins: [p.n]}, {blk: r.id}, "power"); }, "check the datasheet first");
        }
        for (const v of opts) add(`Connect to the ${v} V rail`, () => { const old = powerLink(d, p.n); if (old) S.links = S.links.filter(l => l !== old); link({d, pins: [p.n]}, {blk: rail(v).id}, "power"); },
          opts.length > 1 ? "this pin accepts " + opts.join(" or ") + " V" : "");
        for (const v of opts) add(`Connect ${v} V to every chip that accepts it`, () => connectRail(v));
        break;
      }
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
    for (const g of p.fn === "rf_in" ? [] : guidanceFor(D, p)) add(`Add ${g.label}: ${g.detail}`, () => addGuidance(D, p, g), hasGuidance(D, p, g) ? "already added" : "application guidance");
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
        else if (!S.usecase && ["host", "interrupt", "reset"].includes(p.fn) && !(p.bus && seenBus.has(p.bus))) { attachHost(o.id, p); if (p.bus) seenBus.add(p.bus); }
        else if (p.fn === "flash" && !seenBus.has("flash")) { link(endOf(o.id, p), {blk: addBlock("flash", "SPI flash", "firmware / NVM").id}, "flash", p.bus); seenBus.add("flash"); }
      }
      if (!S.usecase && pinsOf(o).some(p => p.fn === "xtal" && free(p))) attachCrystal(o.id);
      for (const p of pinsOf(o).filter(p => p.fn !== "rf_in")) for (const g of guidanceFor(o, p)) if (!hasGuidance(o, p, g)) addGuidance(o, p, g);
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
    if (S.usecase) return; // the configuration wires audio to the SoC itself
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
  const ROW = 17, HEAD = 46, DEV_W = 230, BLK_W = 140, BLK_H = 34, GAP = 50;
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

  // Block sizes: antennas carry their front-end parts as sub-rows, supply rails list their pins.
  const ANT_W = 210, LANE_GAP = 120, COL_GAP = 50;
  function blockSize(b) {
    if (b.kind === "antenna") return {w: ANT_W, h: BLK_H + (b.items || []).length * 14};
    if (b.kind === "supply") return {w: 150, h: BLK_H};
    return {w: BLK_W, h: BLK_H};
  }

  function layout() {
    const cols = [S.devices.filter(o => info(o).role !== "coprocessor"), S.devices.filter(o => info(o).role === "coprocessor")].filter(c => c.length);
    const X = {ant: 20};
    // add-on blocks sit LANE_GAP away from the chip so pin names, numbers and net labels stay visible
    let x = X.ant + ANT_W + 40;
    const colX = cols.map(() => {
      const c = {laneL: x, dev: x + BLK_W + LANE_GAP};
      c.laneR = c.dev + DEV_W + LANE_GAP;
      x = c.laneR + BLK_W + COL_GAP;
      return c;
    });
    X.spk = x;
    // top band: supply rails, ground, host
    const out = {};
    let tx = X.ant, topH = 0;
    for (const b of S.blocks.filter(b => ["supply", "ground", "host"].includes(b.kind))) {
      if (!S.links.some(l => l.b.blk === b.id || l.a.blk === b.id) && b.kind !== "supply") continue;
      const sz = blockSize(b);
      out[b.id] = {x: tx, y: 20, ...sz};
      tx += sz.w + 14;
      topH = Math.max(topH, sz.h);
    }
    const pos = {}, top = 20 + topH + 60;
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
    // antennas far left, speakers far right, everything else in the lane beside the pin it hangs on
    const lanes = {};
    for (const b of S.blocks) {
      if (out[b.id]) continue;
      const ls = S.links.filter(l => l.b.blk === b.id || l.a.blk === b.id);
      if (!ls.length) continue;
      const e = ls[0].a.d ? ls[0].a : ls[0].b;
      const p = pinXY(e.d, e.pins[0]);
      if (!p) continue;
      const ys = ls.map(l => (l.a.d ? l.a : l.b)).flatMap(e => e.pins.map(n => pinXY(e.d, n))).filter(Boolean).map(q => q.y);
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2, sz = blockSize(b);
      let lane, bx;
      if (b.kind === "antenna") { lane = "ant"; bx = X.ant; }
      else if (b.kind === "speaker") { lane = "spk"; bx = X.spk; }
      else { const c = colX[pos[e.d].col]; lane = `${pos[e.d].col}${p.side}`; bx = p.side === "L" ? c.laneL : c.laneR; }
      (lanes[lane] ||= []).push({b, x: bx, y: cy - sz.h / 2, ...sz});
    }
    for (const ws of Object.values(lanes)) {
      ws.sort((a, b) => a.y - b.y);
      let floor = -1e9;
      for (const w of ws) { const y = Math.max(w.y, floor); out[w.b.id] = {x: w.x, y, w: w.w, h: w.h}; floor = y + w.h + 10; }
    }
    const W = Math.max(X.spk + BLK_W + 20, ...Object.values(out).map(r => r.x + r.w + 20), 600);
    const H = Math.max(...Object.values(pos).map(p => p.y + p.h + 40), ...Object.values(out).map(r => r.y + r.h + 40), 300);
    return {pos, blocks: out, pinXY, W, H};
  }

  const curve = (a, b, da, db) => `M${a.x},${a.y} C${a.x + da},${a.y} ${b.x + db},${b.y} ${b.x},${b.y}`;

  function render() {
    updateRails();
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
        `<text class="blk-detail" x="${r.x + 8}" y="${r.y + 27}">${esc(b.detail.length > 30 ? b.detail.slice(0, 29) + "…" : b.detail)}</text>` +
        (b.items || []).map((it, i) => `<line class="blk-sep" x1="${r.x + 6}" x2="${r.x + r.w - 6}" y1="${r.y + BLK_H + i * 14 - 2}" y2="${r.y + BLK_H + i * 14 - 2}"/>` +
          `<text class="blk-item" x="${r.x + 10}" y="${r.y + BLK_H + i * 14 + 9}">▸ ${esc((it.label + (it.detail ? ` · ${it.detail}` : "")).slice(0, 38))}</text>`).join("") + `</g>`);
    }
    if (!S.devices.length) parts.push(`<text class="empty" x="40" y="160">Add a device, or start from the standards you need.</text>`);
    const svg = $("#bc-svg");
    lastLay = Lay;
    svg.innerHTML = parts.join("");
    applyView();
    renderSummary();
    renderUseCase();
    renderFocusButtons();
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
        {label: "Zoom to this chip and its connections", fn: () => { focusId = d; }},
        {label: "Fill in surroundings (supplies, crystal, antennas, host…)", fn: autoComplete},
        ...same.map(c => ({label: `Replace with ${c.mpn}`, hint: [...c.analog, ...c.digital_decode, ...c.digital_iq.map(s => s + " I/Q")].join(" "), fn: () => replaceDevice(d, c.mpn)})),
        ...(I.source && I.source.url ? [{label: "Open data short", fn: () => window.open(I.source.url, "_blank", "noopener")}] : []),
        {label: `Remove ${o.mpn}`, fn: () => removeDevice(d)},
      ]);
    }
    const b = block(t.dataset.blk);
    if (b.kind === "antenna") explain("antenna_block", b.label);
    if (b.kind === "supply") explain("supply", b.label);
    if (b.kind === "supply" && b.volts) return openMenu(ev, `<b>${esc(b.label)} rail</b><br><small>${esc(b.detail)}</small>`, [
      {label: `Connect every supply pin that accepts ${b.volts} V`, fn: () => connectRail(b.volts)},
      {label: "Disconnect all pins from this rail", fn: () => removeLinks(l => l.b.blk === b.id)},
      {label: "Remove rail", fn: () => { removeLinks(l => l.b.blk === b.id); S.blocks = S.blocks.filter(x => x !== b); }},
    ], EXPLAIN.supply || "");
    if (b.kind === "antenna" && (b.items || []).length) return openMenu(ev, `<b>${esc(b.label)}</b><br><small>${esc(b.detail)}</small>` +
      b.items.map(it => `<br><small><b>${esc(it.label)}</b> (${esc(it.pin)}): ${esc(it.detail)}${it.note ? ` — ${esc(it.note)}` : ""}</small>`).join(""), [
      {label: "Rename…", fn: () => { const v = prompt("Label", b.label); if (v) b.label = v; }},
      ...(b.uc ? [] : [{label: "Remove", fn: () => removeLinks(l => l.a.blk === b.id || l.b.blk === b.id)}]),
    ], EXPLAIN.antenna_block || "");
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

  // ---------------------------------------------------------------- configuration: region, hardware, software
  // S.usecase = {region, hardware, notes, ics: {IC0..IC3: {mpn}}, antennas: [{id, label, bands, splitter}],
  //   rf: {IC0: {pin: "ANT1" | "loop:IC0.LTB"}}, iq: {"IC0.T0": "ZIF I/Q 0"}, control: "demod" | "soc",
  //   route: "direct" | "via_demod", clock: {master, crystal, feed}, audio: {fs, bits, slots, format},
  //   memory: {IC0: "4 MB"}, modes: [{name, linking, notes, tuners: {IC0: [job, job]}, channels: [{job, source}]}], mode}
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
  const FEEDS_STD = {HD: ["amfm_audio", "fm_audio", "am_audio", "fm_pd", "fm_mrc", "fm_scan", "am_scan"], DAB: ["dab", "fm_dab_scan"], DRM: ["drm"], CDR: ["fm_audio", "fm_scan", "amfm_audio"]};
  const LOOP_OUT = /^(LT[AB]|FMO|B3O|AMO|LBO)$/; // loop-through (buffer) outputs
  const PIN_PF = (GUIDE.clock && GUIDE.clock.input_pf) || [4.5, 5];
  const MAX_PF = (GUIDE.clock && GUIDE.clock.clko_max_load_pf) || 50;
  const ZIF_MAX_PF = (GUIDE.zif && GUIDE.zif.clk_fs_max_load_pf) || 50;

  const slotDev = slot => S.devices.find(o => o.slot === slot);
  const tunerCount = o => (o ? info(o).tuners || 1 : 0);
  const demodChannels = o => (o ? info(o).channels || 4 : 0);
  const U = () => S.usecase;
  const baseName = n => String(n).split("/")[0];
  const pinByName = (o, name) => pinsOf(o).find(p => p.name === name) || pinsOf(o).find(p => baseName(p.name) === baseName(name));
  const bandsOf = p => String(p.band || "").toUpperCase().split("/").map(b => (b.includes("DAB") ? "DAB" : b.trim())).filter(Boolean);
  const tunerOfPin = (o, p) => {
    if (tunerCount(o) < 2) return 0;
    const m = p.name.split("/")[0].match(/([AB01])$/);
    return m ? (m[1] === "A" || m[1] === "0" ? 0 : 1) : null;
  };
  const clockIn = o => pinsOf(o).find(p => p.fn === "refclk") || pinByName(o, "XTALI") || pinsOf(o).find(p => p.fn === "xtal");
  const busPinsByName = (o, bus) => pinsOf(o).filter(p => p.bus === bus);

  // ---- software modes
  const blankMode = name => ({name, linking: false, notes: "", tuners: {}, channels: []});
  function mode() {
    const u = U();
    if (!u.modes.length) u.modes.push(blankMode("Listening mode 1"));
    u.mode = Math.min(Math.max(0, u.mode || 0), u.modes.length - 1);
    return u.modes[u.mode];
  }
  function tunersOf(slot, m = mode()) {
    const arr = (m.tuners[slot] ||= []), n = tunerCount(slotDev(slot));
    while (arr.length < n) arr.push("off");
    arr.length = n;
    return arr;
  }
  function channelsOf(m = mode()) {
    const arr = (m.channels ||= []), n = demodChannels(slotDev(DEMOD_SLOT));
    while (arr.length < n) arr.push({job: "unused"});
    arr.length = n;
    return arr;
  }

  function jobLines(o) {
    const u = U();
    if (!u || !o.slot) return [];
    if (o.slot === DEMOD_SLOT)
      return channelsOf().map((c, i) => `DMOD${i}: ${DEMOD_JOBS[c.job]?.label || c.job}${c.source && c.job !== "unused" ? ` ← ${c.source.replace(".", " ")}` : ""}`);
    return tunersOf(o.slot).map((j, i) => `T${i}: ${TUNER_JOBS[j]?.label || j}`);
  }

  function normalise(u) {
    u.rf ||= {}; u.antennas ||= []; u.iq ||= {}; u.memory ||= {}; u.modes ||= []; u.mode ||= 0;
    u.ics ||= {};
    for (const s of ALL_SLOTS) u.ics[s] = typeof u.ics[s] === "string" ? {mpn: u.ics[s]} : u.ics[s] || {mpn: null};
    u.control ||= "demod"; u.route ||= "direct";
    u.clock = Object.assign({master: "IC0", crystal: (GUIDE.clock && GUIDE.clock.crystal) || "", feed: {}}, u.clock || {});
    u.audio = Object.assign({fs: 48, bits: 32, slots: 2, format: "I2S"}, u.audio || {});
    return u;
  }

  // I/Q pairs of the tuners, in order: IC0 T0, IC0 T1, IC1 T0 ...; each wired to a demod ZIF port
  function iqPairs() {
    const out = [];
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot);
      if (!o || !pinsOf(o).some(p => p.fn === "iq_out")) continue;
      for (let t = 0; t < tunerCount(o); t++) out.push(`${slot}.T${t}`);
    }
    return out;
  }
  function defaultIq(u) {
    const d = slotDev(DEMOD_SLOT);
    if (!d) return;
    const ports = uniqueBus(d, "iq_in").map(p => p.bus);
    const used = new Set(Object.values(u.iq).filter(Boolean));
    for (const pair of iqPairs()) {
      if (u.iq[pair] !== undefined) continue;
      const free = ports.find(p => !used.has(p));
      u.iq[pair] = free || null;
      if (free) used.add(free);
    }
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
    }
    defaultIq(u);
    S.links = S.links.filter(l => l.auto !== "uc");
    S.blocks = S.blocks.filter(b => !b.uc);
    const ucBlock = (kind, label, detail) => Object.assign(addBlock(kind, label, detail), {uc: true});
    const ucLink = (a, b, kind, label = "") => link(a, b, kind, label, "uc");
    // antennas (one block each, band splitter and front-end parts inside) and loop-throughs
    const antBlock = {};
    for (const a of u.antennas) antBlock[a.id] = Object.assign(ucBlock("antenna", `${a.id} ${a.label || ""}`.trim(), (a.bands || []).join(" / ")), {splitter: !!a.splitter});
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
          if (sp) ucLink({d: so.id, pins: [sp.n]}, {d: o.id, pins: [p.n]}, "rf", `loop-through ${out}`);
        } else if (antBlock[feed]) (byAnt[feed] ||= []).push(p.n);
      }
      for (const [ant, pins] of Object.entries(byAnt)) ucLink({d: o.id, pins}, {blk: antBlock[ant].id}, "rf");
    }
    Object.values(antBlock).forEach(b => { frontEnd(b); if (b.splitter) b.items.unshift({label: "Band splitter", detail: "AM/FM and Band III to separate inputs", note: "", pin: "all"}); });
    // reference clock
    const master = slotDev(u.clock.master);
    if (master) {
      const x = pinsOf(master).filter(p => p.fn === "xtal");
      if (x.length) ucLink({d: master.id, pins: x.map(p => p.n)}, {blk: ucBlock("crystal", "Crystal", `${u.clock.crystal || "frequency: see datasheet"} · system reference`).id}, "xtal");
      for (const slot of ALL_SLOTS) {
        const o = slotDev(slot);
        if (!o || o === master) continue;
        const md = u.clock.feed[slot] || "star", inp = clockIn(o);
        if (!inp) continue;
        if (md === "own") {
          const xs = pinsOf(o).filter(p => p.fn === "xtal");
          if (xs.length) ucLink({d: o.id, pins: xs.map(p => p.n)}, {blk: ucBlock("crystal", "Crystal", "own crystal").id}, "xtal");
        } else {
          const src = md.startsWith("chain:") ? slotDev(md.slice(6)) : master;
          const out = src && pinsOf(src).find(p => p.fn === "clock_out" && /CLKO/.test(p.name));
          if (out) ucLink({d: src.id, pins: [out.n]}, {d: o.id, pins: [inp.n]}, "clock", `${u.clock.crystal || "ref clock"}${md.startsWith("chain:") ? " (daisy chain)" : ""}`);
        }
      }
    }
    const demod = slotDev(DEMOD_SLOT);
    // I/Q: each tuner's data pair plus the shared ZIFCLK / ZIFFS into its demod port
    if (demod) {
      for (const [pair, port] of Object.entries(u.iq)) {
        if (!port) continue;
        const [slot, t] = pair.split("."), o = slotDev(slot), ti = +String(t).slice(1);
        const portPin = uniqueBus(demod, "iq_in").find(p => p.bus === port);
        if (!o || !portPin || ti >= tunerCount(o)) continue;
        const iq = pinsOf(o).filter(p => p.fn === "iq_out");
        const data = iq.filter(p => /ZIF[IQ]/.test(p.name)).filter(p => { const m = p.name.match(/ZIF[IQ](\d)/); return !m || +m[1] === ti; });
        const shared = iq.filter(p => /CLK|FS/.test(p.name));
        if (!data.length) continue;
        // one line per signal into the matching pin of the demod port: ZIFCLK, ZIFFS (shared by both tuners of
        // a dual), ZIFI, ZIFQ; falls back to the whole port when the demod pins are not named that way
        const inPins = busPins(demod, port), k = port.replace(/\D+/g, "");
        const target = sig => inPins.find(q => new RegExp(`^ZIF${sig}${k}$`).test(q.name));
        const sigOf = p => (p.name.match(/ZIF(CLK|FS|I|Q)/) || [])[1];
        const pairs = [...shared, ...data].map(p => [p, sigOf(p) && target(sigOf(p))]);
        if (pairs.every(([, q]) => q)) {
          for (const [p, q] of pairs) ucLink({d: o.id, pins: [p.n]}, {d: demod.id, pins: [q.n]}, "iq", `${slot} ${t} ${sigOf(p) === "CLK" || sigOf(p) === "FS" ? "ZIF" + sigOf(p) : sigOf(p)} → ${q.name}`);
        } else ucLink({d: o.id, pins: [...shared, ...data].map(p => p.n), bus: `${port} from ${t}`}, endOf(demod.id, portPin), "iq", `${slot} ${t} I/Q → ${port.replace("ZIF I/Q ", "ZIF")}`);
      }
    }
    // control: SoC -> demod -> tuners (tuner SPI + per-tuner select / reset), or SoC -> every IC
    const soc = ucBlock("host", "SoC", u.control === "demod" && demod ? "SPI to IC3" : "SPI / I2C to every IC");
    const hostBus = o => uniqueBus(o, "host")[0];
    if (u.control === "demod" && demod) {
      const h = hostBus(demod);
      if (h) ucLink(endOf(demod.id, h), {blk: soc.id}, "host", h.bus);
      const tspi = pinsOf(demod).find(p => p.bus === "Tuner SPI 0");
      TUNER_SLOTS.forEach((slot, k) => {
        const o = slotDev(slot);
        if (!o) return;
        const th = hostBus(o);
        if (tspi && th) ucLink(endOf(demod.id, tspi), endOf(o.id, th), "spi", "tuner SPI");
        const ctl = busPinsByName(demod, `Tuner ${k} control`), rst = pinsOf(o).find(p => p.fn === "reset");
        if (ctl.length && rst) ucLink({d: demod.id, pins: ctl.map(p => p.n), bus: `Tuner ${k} control`}, {d: o.id, pins: [rst.n]}, "spi", `select / reset T${k}`);
      });
    } else {
      for (const o of S.devices.filter(o => o.slot)) {
        const h = hostBus(o);
        if (h) ucLink(endOf(o.id, h), {blk: soc.id}, "host", h.bus);
        for (const p of pinsOf(o).filter(p => p.fn === "reset" || (p.fn === "interrupt" && !p.bus))) ucLink({d: o.id, pins: [p.n]}, {blk: soc.id}, "host", p.name);
      }
    }
    // audio to the SoC
    const socAudio = ucBlock("soc_audio", "SoC audio in", `${u.audio.format} ${u.audio.fs} kHz`);
    const i2sOut = o => uniqueBus(o, "i2s_out"), i2sIn = o => uniqueBus(o, "i2s_in");
    const ic0 = slotDev("IC0");
    if (u.route === "via_demod" && demod) {
      TUNER_SLOTS.forEach((slot, k) => {
        const o = slotDev(slot), out = o && i2sOut(o)[0], inp = i2sIn(demod)[k];
        if (out && inp) ucLink(endOf(o.id, out), endOf(demod.id, inp), "i2s", `${slot} audio → ${inp.bus}`);
      });
      if (i2sOut(demod)[0]) ucLink(endOf(demod.id, i2sOut(demod)[0]), {blk: socAudio.id}, "audio", "I2S to SoC");
    } else if (ic0) {
      const outs = i2sOut(ic0);
      if (outs[0]) ucLink(endOf(ic0.id, outs[0]), {blk: socAudio.id}, "audio", "I2S to SoC");
      else { const a = pinsOf(ic0).find(p => p.fn === "audio_out"); if (a) ucLink({d: ic0.id, pins: [a.n]}, {blk: socAudio.id}, "audio", "analog audio"); }
      if (demod) {
        if (outs[1] && i2sIn(demod)[0]) ucLink(endOf(ic0.id, outs[1]), endOf(demod.id, i2sIn(demod)[0]), "i2s", "FM audio for blending / linking");
        if (i2sOut(demod)[0]) ucLink(endOf(demod.id, i2sOut(demod)[0]), {blk: socAudio.id}, "audio", "digital audio to SoC");
      }
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

  // ---- checks: [level, text]; level ok / info / warn / error
  function hardwareChecks() {
    const u = U(), out = [];
    const antIcs = {};
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot);
      if (!o) continue;
      for (const [name, feed] of Object.entries(u.rf[slot] || {})) {
        if (!feed) continue;
        if (!pinByName(o, name)) { out.push(["warn", `${slot} (${o.mpn}) has no pin ${name}; its antenna assignment is ignored.`]); continue; }
        if (feed.startsWith("loop:")) {
          const [src, pin] = feed.slice(5).split(".");
          if (src === slot) out.push(["error", `${slot} ${name} cannot loop through from its own IC.`]);
          else if (!slotDev(src)) out.push(["error", `${slot} ${name} loops through from ${src}, which is not populated.`]);
          else if (!pinByName(slotDev(src), pin)) out.push(["error", `${src} has no ${pin} loop-through output.`]);
        } else (antIcs[feed] ||= new Set()).add(slot);
      }
    }
    for (const a of u.antennas) {
      const ics = antIcs[a.id];
      if (!ics) out.push(["warn", `${a.id} is not connected to any tuner.`]);
      else if (ics.size > 1 && !a.splitter) out.push(["warn", `${a.id} goes directly into ${[...ics].join(" and ")}: that needs a band splitter (tick "splitter") or the loop-through of the first IC.`]);
      else if (ics.size > 1) out.push(["info", `${a.id} band splitter feeds ${[...ics].join(" and ")}.`]);
    }
    const demod = slotDev(DEMOD_SLOT);
    if (demod) {
      const perIc = {};
      for (const [pair, port] of Object.entries(u.iq)) if (port && slotDev(pair.split(".")[0])) perIc[pair.split(".")[0]] = (perIc[pair.split(".")[0]] || 0) + 1;
      for (const [slot, n] of Object.entries(perIc)) {
        const pf = n * PIN_PF[1];
        out.push([pf > ZIF_MAX_PF ? "error" : "info", `${slot} ZIFCLK / ZIFFS drive ${n} demod port${n > 1 ? "s" : ""}: ${(n * PIN_PF[0]).toFixed(1)}–${pf.toFixed(1)} pF of the ${ZIF_MAX_PF} pF limit, ≈${Math.max(0, ZIF_MAX_PF - pf).toFixed(0)} pF left for traces.`]);
      }
      const ports = Object.values(u.iq).filter(Boolean);
      if (new Set(ports).size < ports.length) out.push(["error", "Two tuners are wired to the same demod I/Q port."]);
      const nT = TUNER_SLOTS.filter(slotDev).length;
      if (u.control === "demod" && !pinsOf(demod).some(p => p.bus === "Tuner SPI 0")) out.push(["warn", `${demod.mpn}: no tuner SPI found in its data short; let the SoC control the tuners.`]);
      if (u.control === "demod" && nT > 5) out.push(["error", "The demod controls at most five tuner ICs."]);
    } else if (u.control === "demod" && S.devices.some(o => o.slot)) out.push(["info", "No demod populated: the SoC controls the tuners directly."]);
    if (u.route === "via_demod" && !demod) out.push(["warn", "Audio via the demod needs a demod; IC0 sends its I2S to the SoC directly."]);
    // clock tree
    const master = slotDev(u.clock.master);
    if (master) {
      const loads = {};
      for (const slot of ALL_SLOTS) {
        const o = slotDev(slot);
        if (!o || o === master) continue;
        const md = u.clock.feed[slot] || "star";
        if (md === "own") { out.push(["info", `${slot} uses its own crystal instead of the system reference from ${u.clock.master}.`]); continue; }
        const src = md.startsWith("chain:") ? md.slice(6) : u.clock.master;
        if (md.startsWith("chain:")) out.push(["warn", `${slot} takes its clock from ${src} CLKO (daisy chain). This degrades phase noise; feed it from ${u.clock.master} CLKO directly.`]);
        if (!slotDev(src)) out.push(["error", `${slot} takes its clock from ${src}, which is not populated.`]);
        loads[src] = (loads[src] || 0) + 1;
      }
      for (const [src, n] of Object.entries(loads)) {
        const pf = n * PIN_PF[1];
        out.push([pf > MAX_PF ? "error" : "info", `${src} CLKO drives ${n} clock input${n > 1 ? "s" : ""}: ${(n * PIN_PF[0]).toFixed(1)}–${pf.toFixed(1)} pF of the ${MAX_PF} pF limit, ≈${Math.max(0, MAX_PF - pf).toFixed(0)} pF left for traces.`]);
      }
    }
    const a = u.audio;
    out.push(["info", `Audio ${a.format}: ${a.fs} kHz × ${a.bits} bit × ${a.slots} slots → bit clock ${(a.fs * a.bits * a.slots / 1000).toFixed(3)} MHz.`]);
    return out;
  }

  function modeChecks(m = mode()) {
    const u = U(), out = [];
    let audio = 0;
    for (const [slot, jobs] of Object.entries(m.tuners))
      if (!slotDev(slot) && jobs.some(j => j !== "off")) out.push(["error", `${slot} is not populated in this hardware, but the mode gives it a job.`]);
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot);
      if (!o) continue;
      const rf = u.rf[slot] || {}, ts = tunersOf(slot, m);
      const fed = (i, band) => Object.entries(rf).some(([name, feed]) => {
        const p = pinByName(o, name);
        return feed && p && bandsOf(p).includes(band) && [i, null].includes(tunerOfPin(o, p));
      });
      ts.forEach((j, i) => {
        const J = TUNER_JOBS[j] || {};
        if (j === "off") return;
        const missing = [...(J.analog || []).filter(x => !info(o).analog.includes(x)), ...(J.iq || []).filter(x => !info(o).digital_iq.includes(x))];
        if (missing.length) out.push(["error", `${slot} T${i} (${o.mpn}) cannot do ${J.label}: no ${missing.join(", ")} in its data short.`]);
        if (J.fg) audio++;
        for (const band of J.band || []) if (!fed(i, band)) out.push(["error", `${slot} T${i} (${J.label}) has no ${band} antenna or loop-through on its ${band} input.`]);
      });
      const pd = ts.map((j, i) => [j, i]).filter(([j]) => j === "fm_pd");
      if (pd.length === 1) out.push(["error", `${slot}: FM phase diversity needs both tuners of the IC.`]);
      if (pd.length === 2) {
        audio--;
        const fmAnt = i => Object.entries(rf).filter(([n, f]) => { const p = pinByName(o, n); return p && f && bandsOf(p).includes("FM") && tunerOfPin(o, p) === i; }).map(([, f]) => f);
        const a0 = fmAnt(0), a1 = fmAnt(1);
        if (u.antennas.length < 2) out.push(["error", `${slot}: phase diversity needs two antennas; this hardware has one.`]);
        else if (a0.length && a1.length && a0.every(f => a1.includes(f))) out.push(["error", `${slot}: both FM inputs are on ${a0[0]}. Phase diversity needs the two FM inputs on different antennas.`]);
      }
    }
    const demod = slotDev(DEMOD_SLOT);
    let hd = 0, hdMrc = false;
    const chans = demod ? channelsOf(m) : (m.channels || []);
    if (!demod && chans.some(c => c.job !== "unused")) out.push(["error", "The mode uses demod channels, but no demod is populated."]);
    if (demod) chans.forEach((c, i) => {
      const J = DEMOD_JOBS[c.job] || {};
      if (c.job === "unused") return;
      if (J.audio) audio++;
      if (J.std === "HD") hd++;
      if (c.job === "hd_mrc") hdMrc = true;
      if (!info(demod).digital_decode.includes(J.std)) out.push(["error", `DMOD${i}: ${demod.mpn} does not decode ${J.std} (its ordering code covers ${info(demod).digital_decode.join(", ") || "none"}).`]);
      const [slot, tn] = (c.source || "").split(".");
      const o = slotDev(slot), j = o && tunersOf(slot, m)[+String(tn).slice(1)];
      if (!o || !j) { out.push(["error", `DMOD${i} (${J.label}) has no source tuner.`]); return; }
      if (!info(o).digital_iq.includes(J.std)) out.push(["error", `DMOD${i}: ${slot} (${o.mpn}) has no ${J.std} I/Q output.`]);
      if (!u.iq[c.source]) out.push(["error", `DMOD${i}: ${c.source} has no I/Q connection to the demod in this hardware.`]);
      if (!(FEEDS_STD[J.std] || []).includes(j)) out.push(["warn", `DMOD${i} (${J.label}) is fed by ${slot} ${tn}, which is set to "${TUNER_JOBS[j]?.label}".`]);
      if (J.mrc) {
        const primary = chans.find(x => x !== c && DEMOD_JOBS[x.job]?.std === J.std && !DEMOD_JOBS[x.job]?.mrc);
        if (!primary) out.push(["error", `DMOD${i}: MRC needs a main ${J.std} channel to combine with.`]);
        else if (primary.source === c.source) out.push(["error", `DMOD${i}: MRC needs the second branch from the other tuner, not ${c.source} again.`]);
        else if (u.antennas.length < 2) out.push(["warn", `DMOD${i}: MRC combines two antennas; with one antenna both branches see the same signal and gain little.`]);
      }
    });
    if (!audio && S.devices.some(o => o.slot)) out.push(["error", "No tuner or demod channel plays audio in the foreground."]);
    if (m.linking) {
      if (!demod || !info(demod).options.some(x => /seamless/i.test(x))) out.push(["error", "Seamless linking needs a demodulator with seamless blending / linking."]);
      const all = TUNER_SLOTS.filter(slotDev).flatMap(s => tunersOf(s, m).map((j, i) => ({s, i, j})));
      const fmFg = all.filter(x => ["fm_audio", "amfm_audio", "fm_pd"].includes(x.j));
      const linkTuner = all.find(x => !TUNER_JOBS[x.j]?.fg && x.j !== "off" && info(slotDev(x.s)).digital_iq.includes("DAB"));
      if (fmFg.length && !linkTuner)
        out.push(["error", fmFg.some(x => x.j === "fm_pd")
          ? "Seamless linking FM ↔ DAB needs a free DAB tuner, but phase diversity occupies the dual tuner. Step out of phase diversity to link, or add a tuner IC."
          : "Seamless linking FM ↔ DAB needs a second, DAB-capable tuner that is not playing audio."]);
    }
    if (hd) out.push(["info", `Licences in this mode: ${hd} HD I/Q channel licence${hd > 1 ? "s" : ""}${hdMrc ? " + 1 HD MRC licence" : ""}.`]);
    return out;
  }
  // licences the hardware needs: the most any mode uses at once
  function licenceSummary() {
    const u = U();
    let hd = 0, mrc = false;
    for (const m of u.modes) {
      const ch = (m.channels || []).filter(c => c.job !== "unused");
      hd = Math.max(hd, ch.filter(c => DEMOD_JOBS[c.job]?.std === "HD").length);
      mrc ||= ch.some(c => c.job === "hd_mrc");
    }
    return hd ? `${hd} HD I/Q channel licence${hd > 1 ? "s" : ""}${mrc ? " + 1 HD MRC licence" : ""} (the most any mode uses)` : "";
  }

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

  // ---- presets
  const compatible = m => Object.entries(m.tuners || {}).every(([slot, jobs]) => jobs.every(j => j === "off") || tunerCount(slotDev(slot)) >= jobs.length)
    && (!(m.channels || []).some(c => c.job !== "unused") || !!slotDev(DEMOD_SLOT));
  const modeFromPreset = sw => ({name: sw.name, linking: !!sw.linking, notes: sw.notes || "", tuners: JSON.parse(JSON.stringify(sw.tuners || {})), channels: JSON.parse(JSON.stringify(sw.channels || []))});
  // ---- on-chip audio (audio DSP + audio ADC inputs): the question that decides IC0
  const hasAudio = mpn => { const c = BY_MPN[mpn]; return !!c && (FEATS(c).includes("AUDIO") || c.options.some(o => /audio dsp/i.test(o))); };
  // ---- feature sets (data/broadcast/tuner_features.yaml): required features and the audio choice decide IC0
  const FEATS = c => (c && c.features) || [];
  const REGION_STD = {"North America": "HD", Europe: "DAB", "Rest of world": "DRM"};
  const regionStd = () => REGION_STD[S.region];
  // tuners per slot for a given total: dual tuners first, the odd one as a single
  const slotTuners = (slot, n) => ({IC0: n === 1 ? 1 : 2, IC1: n >= 4 ? 2 : n === 3 ? 1 : 0, IC2: n === 6 ? 2 : n === 5 ? 1 : 0}[slot]);
  // features that matter for the chosen region and digital standard; the others are not offered
  const RELEVANT = {
    "North America": {true: ["WB", "HD", "HD_MRC", "PD", "AMIC", "DAGC"], false: ["WB", "PD", "AMIC", "DAGC"]},
    Europe: {true: ["DAB", "DAB_MRC", "DAB_NC", "PD", "AMIC", "DAGC"], false: ["PD", "AMIC", "DAGC"]},
    "Rest of world": {true: ["DRM", "PD", "AMIC", "WB"], false: ["PD", "AMIC", "WB"]},
  };
  const relevant = () => ((RELEVANT[S.region] || {})[String(S.digital !== false)] || []);
  S.features ||= [];
  const ic0Ok = c => !!c && c.role === "tuner" && c.pins.length > 0 && FEATS(c).includes("AM") && FEATS(c).includes("FM") &&
    (!S.tuners || (c.tuners || 1) === slotTuners("IC0", S.tuners)) && (S.digital !== true || S.region === "Europe" || FEATS(c).includes(regionStd())) && (S.audio == null || FEATS(c).includes("AUDIO") === S.audio) && S.features.every(f => FEATS(c).includes(f));
  // closest part to `mpn` that meets the requirements: keeps most of its features, same layout, fewest extras
  function substitute(mpn, tuners) {
    const cur = BY_MPN[mpn], keep = FEATS(cur).filter(f => f !== "AUDIO");
    const score = c => [-keep.filter(f => FEATS(c).includes(f)).length, c.layout === (cur && cur.layout) ? 0 : 1, FEATS(c).length];
    const cands = CATALOG.filter(c => ic0Ok(c) && (c.tuners || 1) === tuners);
    cands.sort((a, b) => { const x = score(a), y = score(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2]; });
    return cands[0] ? cands[0].mpn : null;
  }
  const RF_EQUIV = {FMB: ["FMI"], FMA: ["FMI"], "B3A/WXI": ["B3A", "B3I/WXI"], B3A: ["B3A/WXI"], FMI: ["FMB", "FMA"]};
  // carry an RF assignment over to another part: same name, same base name, or the equivalent input
  function mapPin(mpn, name) {
    const pins = (BY_MPN[mpn] || {}).pins || [];
    const hit = pins.find(p => p.name === name) || pins.find(p => baseName(p.name) === baseName(name)) ||
      pins.find(p => (RF_EQUIV[name] || []).includes(p.name));
    return hit ? hit.name : null;
  }
  // a hardware preset as it looks with or without on-chip audio on IC0 (null: no such variant)
  function presetVariant(h) {
    if (S.audio == null && !S.features.length) return h;
    const ic0 = h.ics && h.ics.IC0;
    if (!ic0) return null;
    if (ic0Ok(BY_MPN[ic0])) return h;
    const twin = substitute(ic0, (BY_MPN[ic0] || {}).tuners || 1);
    if (!twin) return null;
    const v = JSON.parse(JSON.stringify(h));
    v.ics.IC0 = twin;
    v.name = `${h.name} · IC0 ${twin}`;
    const rf0 = {};
    for (const [pin, feed] of Object.entries((h.rf || {}).IC0 || {})) { const np = mapPin(twin, pin); if (np && !rf0[np]) rf0[np] = feed; }
    v.rf = {...h.rf, IC0: rf0};
    for (const [slot, pins] of Object.entries(v.rf)) for (const [pin, feed] of Object.entries(pins))
      if (feed && feed.startsWith("loop:IC0.") && !mapPin(twin, feed.slice(9))) delete pins[pin];
    v.notes = `${h.notes || ""} IC0 replaced by ${twin} to meet the chosen features${S.audio != null ? (S.audio ? " and on-chip audio" : " without on-chip audio") : ""}; RF inputs carried over by name.`;
    return v;
  }
  // part lists narrow as the choices are made: region, on-chip audio for IC0, plain tuners for IC1/IC2
  function partAllowed(c, slot) {
    if (S.showAll) return true;
    const std = [...c.analog, ...c.digital_iq, ...c.digital_decode];
    if (slot === DEMOD_SLOT) {
      if (S.digital === false) return false;
      if (S.region === "North America") return c.digital_decode.includes("HD") || c.digital_decode.length > 2;
      if (S.region === "Europe") return c.digital_decode.includes("DAB");
      return true;
    }
    if (c.role === "coprocessor") return false;
    if (S.region === "North America" && !(std.includes("AM") && std.includes("FM"))) return false;
    if (S.region === "Europe" && S.digital !== false && slot !== "IC0" && !std.includes("DAB")) return false;
    if (S.region === "North America" && S.digital === true && !std.includes("HD")) return false;
    if (slot === "IC0") return ic0Ok(c);
    if (S.tuners && slot !== "IC0" && (c.tuners || 1) !== slotTuners(slot, S.tuners)) return false;
    if (slot !== "IC0") return c.role === "tuner" && !hasAudio(c.mpn); // companions: plain tuners
    return true;
  }

  const hwTuners = h => TUNER_SLOTS.reduce((n, s) => n + (h.ics && h.ics[s] ? (BY_MPN[h.ics[s]] || {}).tuners || 1 : 0), 0);
  // A sensible N-tuner design for a region: dual tuners first, the odd tuner as a single-tuner IC,
  // the demod sized to the tuners, two antennas when phase diversity is possible, loop-through to the next ICs.
  function generateHardware(region, n) {
    const eu = region === "Europe", na = region === "North America";
    const dual = eu ? "Si47962" : "Si47961", single = eu ? "Si47952" : "Si47951";
    const chips = TUNER_SLOTS.map(sl => slotTuners(sl, n)).filter(Boolean).map(t => (t === 2 ? dual : single));
    const plainIc0 = chips[0];
    if (!ic0Ok(BY_MPN[chips[0]])) chips[0] = substitute(chips[0], n >= 2 ? 2 : 1) || chips[0];
    // candidates ticked by the user win
    TUNER_SLOTS.forEach((sl, k) => { if (S.pick && S.pick[sl] && chips[k]) chips[k] = S.pick[sl]; });
    const ics = {IC0: chips[0] || null, IC1: chips[1] || null, IC2: chips[2] || null, IC3: null};
    if (na && S.digital !== false) ics.IC3 = n >= 2 ? "Si46931A1GE1AM" : "Si46921A1GE1AM";
    if (eu && S.digital !== false) ics.IC3 = n >= 5 ? "Si46942A1GE1AM" : n >= 4 ? "Si46932A1GE1AM" : "Si46922A1GE1AM";
    if (region === "Rest of world" && S.digital === true) ics.IC3 = n >= 3 ? "Si46934A1GE1AM" : "Si46924A1GE1AM";
    if (S.pick && S.pick.IC3 && ics.IC3) ics.IC3 = S.pick.IC3;
    const two = n >= 2;
    const antennas = [{id: "ANT1", label: eu ? "AM/FM/DAB" : "AM/FM", bands: eu ? ["AM", "FM", "DAB"] : ["AM", "FM"]}];
    if (two) antennas.push({id: "ANT2", label: eu ? "FM/DAB" : "FM", bands: eu ? ["FM", "DAB"] : ["FM"]});
    const rf0 = plainIc0 === dual ? {AMI: "ANT1", FMA: "ANT1", FMB: two ? "ANT2" : "ANT1"} : {AMI: "ANT1", FMB: "ANT1"};
    if (eu) Object.assign(rf0, plainIc0 === dual ? {"B3A/WXI": "ANT1", B3B: "ANT2"} : {"B3A/WXI": "ANT1"});
    const rf = {IC0: {}};
    for (const [pin, feed] of Object.entries(rf0)) { const np = mapPin(chips[0], pin); if (np && !rf.IC0[np]) rf.IC0[np] = feed; }
    // one loop-through output feeds one input: LTB carries FM to the next IC, LTA Band III (as in the superset design)
    // Europe: the companion IC is the DAB tuner, Band III on both inputs; elsewhere it carries FM
    const carry = (mpn, pins) => Object.fromEntries(Object.entries(pins).map(([p, f]) => [mapPin(mpn, p), f]).filter(([p]) => p));
    if (chips[1]) rf.IC1 = carry(chips[1], eu ? {"B3A/WXI": "loop:IC0.LTA", ...((BY_MPN[chips[1]] || {}).tuners === 2 ? {B3B: "loop:IC0.LTB"} : {})} : {FMB: "loop:IC0.LTB"});
    if (chips[2]) rf.IC2 = carry(chips[2], eu ? {"B3A/WXI": "loop:IC1.LTA"} : {FMB: "loop:IC1.LTB"});
    return {name: `${n} tuner${n > 1 ? "s" : ""}, IC0 ${chips[0]}, generated`, regions: [region], antennas, ics, rf, control: ics.IC3 ? "demod" : "soc", audio: "direct",
      notes: `Generated for ${region}: ${chips.join(" + ")}${ics.IC3 ? ` + ${ics.IC3}` : ""}. ${two ? "Two antennas on IC0 (phase diversity possible)" : "One antenna (no phase diversity)"}${chips.length > 1 ? "; further ICs fed from the loop-through outputs" : ""}. Check the loop-through bands against the full datasheet.`};
  }

  function applyHardware(i) {
    const hw = JSON.parse(JSON.stringify(typeof i === "object" ? i : presetVariant(CONF.hardware[i]) || CONF.hardware[i]));
    S.devices = []; S.blocks = []; S.links = [];
    S.usecase = normalise({region: S.region, digital: S.digital, audioDsp: S.audio, features: [...S.features], hardware: hw.name, notes: hw.notes || "", ics: hw.ics, antennas: hw.antennas, rf: hw.rf,
      control: hw.control, route: hw.audio, clock: hw.clock, memory: {}, modes: [], mode: 0});
    syncUseCase();
    S.usecase.modes = CONF.software.filter(sw => sw.region === S.region).map(modeFromPreset).filter(compatible);
    if (!S.usecase.modes.length) S.usecase.modes.push(blankMode("Listening mode 1"));
    syncUseCase();
    autoComplete();
    if (!$("#bc-name").value || CONF.hardware.some(x => x.name === $("#bc-name").value) || /^(North America|Europe|Rest of world) · /.test($("#bc-name").value))
      $("#bc-name").value = `${S.region} · ${hw.name}`;
  }

  function opt(value, label, sel) { return `<option value="${esc(value)}"${value === sel ? " selected" : ""}>${esc(label)}</option>`; }
  const mark = l => ({ok: "✓", info: "ℹ", warn: "⚠", error: "✗"}[l]);

  function renderUseCase() {
    renderSteps();
    const box = $("#bc-usecase"), u = U();
    if (!u) {
      box.innerHTML = `<p class="small muted">Pick a region and a hardware configuration above, or <button type="button" class="outline small-btn" data-uc="blank">start empty hardware</button>.</p>`;
      box.querySelector("[data-uc=blank]").onclick = () => {
        S.usecase = normalise({region: S.region || "", antennas: [{id: "ANT1", label: "AM/FM", bands: ["AM", "FM"]}], ics: {}, modes: [blankMode("Listening mode 1")]});
        syncUseCase(); changed();
      };
      return;
    }
    const m = mode();
    const catFor = slot => CATALOG.filter(c => (slot === DEMOD_SLOT ? c.role === "coprocessor" : c.role !== "coprocessor") && (partAllowed(c, slot) || c.mpn === u.ics[slot].mpn));
    const demodsCat = catFor(DEMOD_SLOT);
    const feedOpts = (slot, sel) => opt("", "—", sel || "") + u.antennas.map(a => opt(a.id, a.id, sel)).join("") +
      TUNER_SLOTS.filter(s => s !== slot && slotDev(s)).flatMap(s => pinsOf(slotDev(s)).filter(q => LOOP_OUT.test(q.name)).map(q => opt(`loop:${s}.${q.name}`, `loop ${s} ${q.name}`, sel))).join("");
    const clockOpts = (slot, sel) => opt("star", `${u.clock.master} CLKO (star)`, sel) + opt("own", "own crystal", sel) +
      ALL_SLOTS.filter(s => s !== slot && s !== u.clock.master && slotDev(s)).map(s => opt(`chain:${s}`, `${s} CLKO (daisy chain)`, sel)).join("");
    const demod = slotDev(DEMOD_SLOT), ports = demod ? uniqueBus(demod, "iq_in").map(p => p.bus) : [];
    // hardware rows
    let hw = "";
    for (const slot of TUNER_SLOTS) {
      const ic = u.ics[slot], o = slotDev(slot);
      const rfPins = o ? pinsOf(o).filter(p => p.fn === "rf_in") : [];
      hw += `<tr><th>${slot}</th><td><select data-slot="${slot}" aria-label="${slot} part">${opt("", "Not populated", ic.mpn || "")}${catFor(slot).map(c => opt(c.mpn, `${c.mpn} · ${c.tuners || 1} tuner${(c.tuners || 1) > 1 ? "s" : ""} · ${[...c.analog, ...c.digital_iq.map(s => s + " I/Q"), ...c.digital_decode].join(" ")}`, ic.mpn || "")).join("")}</select>` +
        (o && info(o).layout ? (() => {
          const same = CATALOG.filter(c => c.layout === info(o).layout && c.mpn !== o.mpn && c.pins.length);
          return same.length ? `<div class="uc-layout" data-explain="layout"><small class="muted">Same layout (${esc((LAYOUTS[info(o).layout] || {}).label || info(o).layout)}):</small> ` +
            same.map(c => `<button type="button" class="bc-chip bc-chip-sm" data-swap="${slot}|${esc(c.mpn)}" title="${esc(FEATS(c).join(", "))}">${esc(c.mpn)} · ${c.tuners || 1}T</button>`).join("") + `</div>` : "";
        })() : "") +
        (o ? `<div class="uc-rf">${rfPins.map(p => `<label>${esc(p.name)}<select data-rf="${slot}|${esc(p.name)}" data-xp="feed:" aria-label="${slot} ${esc(p.name)} antenna">${feedOpts(slot, (u.rf[slot] || {})[p.name])}</select></label>`).join("")}</div>` : "") +
        `</td><td>` + (o ? (slot !== u.clock.master ? `<label class="uc-clock">Clock <select data-clock="${slot}" data-xp="clock:">${clockOpts(slot, u.clock.feed[slot] || "star")}</select></label>` : `<p class="small muted uc-clock">Crystal ${esc(u.clock.crystal)} · system reference</p>`) +
          (demod && pinsOf(o).some(p => p.fn === "iq_out") ? `<div class="uc-rf">${Array.from({length: tunerCount(o)}, (_, t) => `<label>T${t} I/Q<select data-iq="${slot}.T${t}" data-explain="iq_map">${opt("", "—", u.iq[`${slot}.T${t}`] || "")}${ports.map(p => opt(p, p.replace("ZIF I/Q ", "ZIF"), u.iq[`${slot}.T${t}`] || "")).join("")}</select></label>`).join("")}</div>` : "") : "") + `</td></tr>`;
    }
    hw += `<tr><th>${DEMOD_SLOT}</th><td><select data-slot="${DEMOD_SLOT}" aria-label="Demodulator part">${opt("", "Not populated", u.ics[DEMOD_SLOT].mpn || "")}${demodsCat.map(c => opt(c.mpn, `${c.mpn} · ${c.digital_decode.join("/") || "AM/FM"} · ${c.channels || "SW-defined"} ch${c.options.length ? " · " + c.options.join(", ") : ""}`, u.ics[DEMOD_SLOT].mpn || "")).join("")}</select></td><td>` +
      (demod && DEMOD_SLOT !== u.clock.master ? `<label class="uc-clock">Clock <select data-clock="${DEMOD_SLOT}" data-xp="clock:">${clockOpts(DEMOD_SLOT, u.clock.feed[DEMOD_SLOT] || "star")}</select></label>` : "") + `</td></tr>`;
    // software rows (current mode)
    let sw = "";
    for (const slot of TUNER_SLOTS) {
      const o = slotDev(slot);
      if (!o) continue;
      sw += `<tr><th>${slot}</th><td>${tunersOf(slot).map((j, i) => `<div class="uc-row"><b>T${i}</b><select data-job="${slot}.${i}" data-xp="job:" aria-label="${slot} tuner ${i} job">${Object.entries(TUNER_JOBS).map(([k, J]) => opt(k, J.label, j)).join("")}</select></div>`).join("")}</td></tr>`;
    }
    if (demod) {
      const srcOpts = sel => opt("", "— source —", sel || "") + iqPairs().map(p => opt(p, `${p.replace(".", " ")}${u.iq[p] ? "" : " (no I/Q wired)"}`, sel)).join("");
      sw += `<tr><th>${DEMOD_SLOT}</th><td>${channelsOf().map((c, i) => `<div class="uc-row"><b>DMOD${i}</b><select data-djob="${i}" data-xp="djob:" aria-label="DMOD${i} job">${Object.entries(DEMOD_JOBS).map(([k, J]) => opt(k, J.label, c.job)).join("")}</select>` +
        `<select data-dsrc="${i}" aria-label="DMOD${i} source">${srcOpts(c.source)}</select></div>`).join("")}</td></tr>`;
    }
    const ants = u.antennas.map((a, i) => `<span class="uc-ant"><b>${esc(a.id)}</b> <input data-alabel="${i}" value="${esc(a.label || "")}" aria-label="${esc(a.id)} label">` +
      ["AM", "FM", "DAB"].map(b => `<label><input type="checkbox" data-aband="${i}" value="${b}"${(a.bands || []).includes(b) ? " checked" : ""}> ${b}</label>`).join("") +
      `<label data-explain="splitter"><input type="checkbox" data-asplit="${i}"${a.splitter ? " checked" : ""}> splitter</label>` +
      `<button type="button" class="outline secondary small-btn" data-adel="${i}" aria-label="Remove ${esc(a.id)}">×</button></span>`).join("");
    const memSlots = ALL_SLOTS.filter(s => slotDev(s) && pinsOf(slotDev(s)).some(p => p.fn === "flash" || p.fn === "memory"));
    const hc = hardwareChecks(), mc = modeChecks(), a = u.audio, lic = licenceSummary();
    const problems = [...hc, ...mc].filter(([l]) => l === "warn" || l === "error");
    const infos = [...hc, ...mc].filter(([l]) => l === "info");
    box.innerHTML = `
      <section class="uc-sec"><h3 class="uc-h" data-explain="hardware">Hardware <span class="muted">· ${esc(u.hardware || "custom")}</span></h3>
      ${u.notes ? `<p class="small muted">${esc(u.notes)}</p>` : ""}
      <div class="uc-ants" data-explain="antennas">Antennas (${u.antennas.length}): ${ants} <button type="button" class="outline small-btn" id="uc-addant">+ antenna</button></div>
      <label class="bc-check uc-showall" data-explain="show_all"><input type="checkbox" id="uc-showall"${S.showAll ? " checked" : ""}> Show all parts in the part lists</label>
      <div class="table-wrap"><table class="uc-table"><thead><tr><th></th><th>Part · RF inputs</th><th>Clock · I/Q to demod</th></tr></thead><tbody>${hw}</tbody></table></div>
      <div class="uc-misc">
        <label data-xp="control:" data-explain="control:${u.control}">Control <select id="uc-control">${opt("demod", "SoC → IC3 → tuners (tuner SPI)", u.control)}${opt("soc", "SoC → every IC", u.control)}</select></label>
        <label data-explain="route:${u.route}">Audio to SoC <select id="uc-route">${opt("direct", "IC0 I2S direct (+ demod I2S)", u.route)}${opt("via_demod", "all tuners via the demod", u.route)}</select></label>
        <label data-explain="crystal">Crystal on ${esc(u.clock.master)} <input id="uc-xtal" value="${esc(u.clock.crystal)}"></label>
        <label data-explain="audio">Audio <select id="uc-format">${["I2S", "TDM"].map(f => opt(f, f, a.format)).join("")}</select>
          <select id="uc-fs">${((GUIDE.i2s && GUIDE.i2s.sample_rates_khz) || [48]).map(f => opt(String(f), `${f} kHz`, String(a.fs))).join("")}</select>
          <select id="uc-bits">${[16, 24, 32].map(b => opt(String(b), `${b} bit`, String(a.bits))).join("")}</select>
          <select id="uc-slots">${[2, 4, 8].map(n => opt(String(n), `${n} slots`, String(a.slots))).join("")}</select></label>
        ${memSlots.map(s => `<label data-explain="memory">${s} flash <input data-mem="${s}" value="${esc(u.memory[s] || "")}" placeholder="size"></label>`).join("")}
      </div>
      ${lic ? `<p class="small" data-explain="licences">Licences: ${esc(lic)}</p>` : ""}</section>
      <section class="uc-sec"><h3 class="uc-h" data-explain="software">Software · <input id="uc-mode-name" value="${esc(m.name)}" aria-label="Listening mode name"></h3>
      ${m.notes ? `<p class="small muted">${esc(m.notes)}</p>` : ""}
      <label class="bc-check" data-explain="linking"><input type="checkbox" id="uc-linking"${m.linking ? " checked" : ""}> Seamless linking</label>
      <div class="table-wrap"><table class="uc-table"><tbody>${sw || `<tr><td class="muted">Populate a tuner IC first.</td></tr>`}</tbody></table></div></section>
      <ul class="uc-checks">${problems.length ? problems.map(([l, t]) => `<li class="uc-${l}">${mark(l)} ${esc(t)}</li>`).join("") : `<li class="uc-ok">✓ No conflicts in this hardware and listening mode.</li>`}</ul>
      <details class="uc-checks"><summary>Clock, I/Q loading, licences, audio (${infos.length})</summary><ul>${infos.map(([, t]) => `<li class="uc-info">ℹ ${esc(t)}</li>`).join("")}</ul></details>`;
    const upd = fn => e => {
      const k = keyOf(e.target), t = titleOf(e.target);
      fn(e.target); syncUseCase(); changed();
      if (k) explain(k, t);
    };
    box.querySelectorAll("[data-slot]").forEach(el => (el.onchange = upd(t => (u.ics[t.dataset.slot].mpn = t.value || null))));
    box.querySelectorAll("[data-job]").forEach(el => (el.onchange = upd(t => { const [s, i] = t.dataset.job.split("."); tunersOf(s)[+i] = t.value; })));
    box.querySelectorAll("[data-rf]").forEach(el => (el.onchange = upd(t => { const [s, n] = t.dataset.rf.split("|"); (u.rf[s] ||= {})[n] = t.value || null; })));
    box.querySelectorAll("[data-iq]").forEach(el => (el.onchange = upd(t => (u.iq[t.dataset.iq] = t.value || null))));
    box.querySelectorAll("[data-clock]").forEach(el => (el.onchange = upd(t => (u.clock.feed[t.dataset.clock] = t.value))));
    box.querySelectorAll("[data-djob]").forEach(el => (el.onchange = upd(t => (channelsOf()[+t.dataset.djob].job = t.value))));
    box.querySelectorAll("[data-dsrc]").forEach(el => (el.onchange = upd(t => (channelsOf()[+t.dataset.dsrc].source = t.value || null))));
    box.querySelectorAll("[data-alabel]").forEach(el => (el.onchange = upd(t => (u.antennas[+t.dataset.alabel].label = t.value))));
    box.querySelectorAll("[data-asplit]").forEach(el => (el.onchange = upd(t => (u.antennas[+t.dataset.asplit].splitter = t.checked))));
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
    $("#uc-linking").onchange = upd(t => (m.linking = t.checked));
    $("#uc-mode-name").onchange = upd(t => (m.name = t.value || m.name));
    $("#uc-control").onchange = upd(t => (u.control = t.value));
    $("#uc-showall").onchange = e => { S.showAll = e.target.checked; render(); };
    box.querySelectorAll("[data-swap]").forEach(el => (el.onclick = upd(t => { const [slot, mpn] = t.dataset.swap.split("|"); u.ics[slot].mpn = mpn; })));
    $("#uc-route").onchange = upd(t => (u.route = t.value));
    $("#uc-xtal").onchange = upd(t => (u.clock.crystal = t.value));
    $("#uc-format").onchange = upd(t => (a.format = t.value));
    $("#uc-fs").onchange = upd(t => (a.fs = +t.value));
    $("#uc-bits").onchange = upd(t => (a.bits = +t.value));
    $("#uc-slots").onchange = upd(t => (a.slots = +t.value));
  }

  // ---- step bar: 1 region, 2 hardware, 3 software modes
  // candidates per slot for the chosen tuner count; tick one per slot, then create the block diagram
  // short comment next to a candidate: channels for a demod; for a tuner, the features that matter in this
  // region beyond AM/FM (the slot already says how many tuners)
  function candNote(c, sl) {
    if (sl === DEMOD_SLOT) return [c.channels ? `${c.channels} ch` : "", c.digital_decode.join("/")].filter(Boolean).join(" · ");
    const rel = relevant(), f = FEATS(c);
    const shown = f.filter(x => rel.includes(x) && !["AM", "FM"].includes(x));
    return [...shown.map(x => ({HD_MRC: "MRC", DAB_MRC: "MRC", AUDIO: "audio"}[x] || x)), ...(f.includes("AUDIO") && !shown.includes("AUDIO") ? ["audio"] : [])]
      .filter((x, i, a) => a.indexOf(x) === i).join(" · ");
  }
  function renderCandidates() {
    const box = $("#bc-cands");
    if (!box || !S.tuners) return;
    S.pick ||= {};
    const slots = [...TUNER_SLOTS.filter(sl => slotTuners(sl, S.tuners)), ...(S.digital ? [DEMOD_SLOT] : [])];
    const save = S.showAll; S.showAll = false;
    const html = slots.map(sl => {
      const cands = CATALOG.filter(c => (sl === DEMOD_SLOT ? c.role === "coprocessor" : c.role === "tuner") && c.pins.length && partAllowed(c, sl))
        .filter(c => sl === DEMOD_SLOT || (c.tuners || 1) === slotTuners(sl, S.tuners));
      if (S.pick[sl] && !cands.some(c => c.mpn === S.pick[sl])) delete S.pick[sl];
      const role = sl === "IC0" ? "primary tuner" : sl === DEMOD_SLOT ? "demod" : "companion tuner";
      return `<div class="cand-slot"><b>${sl}</b> <span class="muted small">${role}${sl !== DEMOD_SLOT ? `, ${slotTuners(sl, S.tuners)}T` : ""} · ${cands.length}</span>
        <div class="cand-list">${cands.map(c => `<label class="cand${c.borrowed_pins ? " borrowed" : ""}"><input type="checkbox" data-pick="${sl}|${esc(c.mpn)}"${S.pick[sl] === c.mpn ? " checked" : ""}> ${esc(c.mpn)}${c.borrowed_pins ? "*" : ""} <span class="cand-note">${esc(candNote(c, sl))}</span></label>`).join("") || `<span class="small uc-error">none</span>`}</div></div>`;
    }).join("");
    S.showAll = save;
    box.innerHTML = html + `<div class="cand-actions"><button type="button" class="small-btn" id="bc-create">Create block diagram</button>
      <span class="small muted">Unticked slots get the default part. * pinout borrowed (no data short).</span></div>`;
    box.querySelectorAll("[data-pick]").forEach(cb => (cb.onchange = () => {
      const [sl, mpn] = cb.dataset.pick.split("|");
      if (cb.checked) S.pick[sl] = mpn; else delete S.pick[sl];
      renderCandidates();
      const c = BY_MPN[mpn];
      if (c && cb.checked) explainBox.innerHTML = `<b>${esc(mpn)}</b><p>${esc([`${c.tuners || c.channels || ""}${c.tuners ? " tuner(s)" : c.channels ? " channels" : ""}`, (FEATS(c).length ? FEATS(c) : c.digital_decode).join(", "), c.note || ""].filter(Boolean).join(" · "))}</p>`;
    }));
    box.querySelector("#bc-create").onclick = () => {
      if (S.devices.length && !confirm("Replace the current hardware and its listening modes?")) return;
      const hw = generateHardware(S.region, S.tuners);
      applyHardware(hw); changed();
      explainBox.innerHTML = `<b>${esc(hw.name)}</b><p>${esc(hw.notes)}</p>`;
    };
  }

  function renderSteps() {
    const u = U();
    S.region ||= u && u.region;
    root.querySelectorAll("[data-region]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.region === S.region)));
    const hwBox = $("#bc-hw-cards"), swBox = $("#bc-sw-cards");
    if (!S.region) { hwBox.innerHTML = `<span class="muted small">pick a region first</span>`; swBox.innerHTML = ""; return; }
    root.querySelectorAll("[data-tuners]").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.tuners === S.tuners)));
    root.querySelectorAll("[data-audio]").forEach(b => b.setAttribute("aria-pressed", String(S.audio != null && String(S.audio) === b.dataset.audio)));
    // progressive: region -> digital -> on-chip audio -> tuners -> features + candidates
    const rel = relevant();
    S.features = S.features.filter(f => rel.includes(f));
    root.querySelectorAll("[data-feat]").forEach(b => { b.hidden = !rel.includes(b.dataset.feat); b.setAttribute("aria-pressed", String(S.features.includes(b.dataset.feat))); });
    root.querySelectorAll("[data-audio]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.audio === "any" ? S.audioAsked && S.audio == null : S.audio != null && String(S.audio) === b.dataset.audio)));
    $("#st-hw").hidden = S.digital == null;
    $("#st-tuners").hidden = !S.audioAsked;
    $("#st-feats").hidden = !S.tuners;
    $("#bc-cands").hidden = !S.tuners;
    $("#bc-hw-cards").hidden = !S.tuners;
    $("#st-sw").hidden = !u;
    $("#st-sw").classList.toggle("closed", !!S.swClosed);
    $("#bc-usecase").hidden = !!S.swClosed;
    renderCandidates();
    const fit = CATALOG.filter(ic0Ok);
    $("#bc-feat-match").innerHTML = S.audio == null && !S.features.length ? "" : fit.length
      ? `IC0 candidates: ${fit.map(c => `<b>${esc(c.mpn)}</b> <span class="muted">(${c.tuners || 1}T${c.borrowed_pins ? ", borrowed pinout" : ""})</span>`).join(", ")}`
      : `<span class="uc-error">No tuner has all of these features.</span>`;
    root.querySelectorAll("[data-digital]").forEach(b => b.setAttribute("aria-pressed", String(S.digital != null && String(S.digital) === b.dataset.digital)));
    const dig = $("#bc-digital");
    if (dig) dig.hidden = !S.region;
    root.querySelectorAll("[data-digital-label]").forEach(el => (el.textContent = { "North America": "HD Radio", Europe: "DAB", "Rest of world": "DRM" }[S.region] || "digital"));
    const list = CONF.hardware.map((h, i) => [presetVariant(h), i]).filter(([h]) => h && (h.regions || []).includes(S.region) && (!S.tuners || hwTuners(h) === S.tuners)
      && (S.digital == null || !!h.ics.IC3 === S.digital));
    hwBox.innerHTML = list.map(([h, i]) => `<button type="button" class="bc-chip" data-hw="${i}" aria-pressed="${String(!!u && u.hardware === h.name)}">${esc(h.name)} <span class="muted">· ${hwTuners(h)}T</span></button>`).join("") +
      (S.tuners ? `<button type="button" class="bc-chip bc-chip-gen" data-gen="${S.tuners}" data-explain="generate">Generate ${S.tuners}-tuner hardware</button>` : list.length ? "" : `<span class="muted small">no preset for this region</span>`);
    if (!u) { swBox.innerHTML = `<span class="muted small">pick a hardware configuration first</span>`; return; }
    const errs = i => [...modeChecks(u.modes[i])].filter(([l]) => l === "error").length;
    swBox.innerHTML = u.modes.map((m, i) => { const e = errs(i); return `<button type="button" class="bc-chip${e ? " has-err" : ""}" data-mode="${i}" aria-pressed="${String(i === u.mode)}" title="${e ? `${e} conflict${e > 1 ? "s" : ""}` : "no conflicts"}">${e ? "✗ " : "✓ "}${esc(m.name)}</button>`; }).join("") +
      `<select id="bc-add-mode" class="small-sel" aria-label="Add a listening mode"><option value="">+ mode…</option><option value="blank">Blank mode</option>` +
      CONF.software.map((sw, i) => [sw, i]).filter(([sw]) => sw.region === S.region).map(([sw, i]) => `<option value="${i}">${esc(sw.name)}</option>`).join("") + `</select>` +
      (u.modes.length > 1 ? `<button type="button" class="outline secondary small-btn" id="bc-del-mode">Remove mode</button>` : "");
  }
  root.addEventListener("click", e => {
    const r = e.target.closest("[data-region]"), h = e.target.closest("[data-hw]"), md = e.target.closest("[data-mode]");
    const tn = e.target.closest("[data-tuners]"), gen = e.target.closest("[data-gen]"), au = e.target.closest("[data-audio]");
    const dg = e.target.closest("[data-digital]");
    if (e.target.closest("#bc-sw-toggle")) { S.swClosed = !S.swClosed; render(); return; }
    if (dg) {
      const v = dg.dataset.digital === "true";
      S.digital = S.digital === v ? null : v;
      render();
      explain(`digital:${S.region}`, dg.textContent);
      return;
    }
    const ft = e.target.closest("[data-feat]");
    if (ft) {
      const f = ft.dataset.feat;
      S.features = S.features.includes(f) ? S.features.filter(x => x !== f) : [...S.features, f];
      render();
      explain(`feature:${f}`, ft.textContent);
      return;
    }
    if (au) {
      S.audioAsked = true;
      const v = au.dataset.audio === "any" ? null : au.dataset.audio === "true";
      S.audio = v;
      render();
      explain("audio_dsp", S.audio == null ? "On-chip audio: either" : S.audio ? "On-chip audio required" : "No on-chip audio");
      return;
    }
    if (tn) { S.tuners = S.tuners === +tn.dataset.tuners ? null : +tn.dataset.tuners; renderSteps(); explain("tuners", `${tn.dataset.tuners} tuner${tn.dataset.tuners > 1 ? "s" : ""}`); return; }
    if (gen) {
      if (!S.region) return;
      if (S.devices.length && !confirm("Replace the current hardware and its listening modes?")) return;
      const hw = generateHardware(S.region, +gen.dataset.gen);
      applyHardware(hw); changed();
      explainBox.innerHTML = `<b>${esc(hw.name)}</b><p>${esc(hw.notes)}</p>`;
      return;
    }
    if (r) { S.region = r.dataset.region; if (U()) U().region = S.region; render(); explain(`region:${S.region}`, S.region); }
    else if (h) {
      if (S.devices.length && !confirm("Replace the current hardware and its listening modes?")) return;
      applyHardware(+h.dataset.hw); changed();
      const hw = CONF.hardware[+h.dataset.hw];
      explainBox.innerHTML = `<b>${esc(hw.name)}</b><p>${esc(hw.notes || "")}</p>`;
    } else if (md) {
      U().mode = +md.dataset.mode; render();
      const m = mode();
      explainBox.innerHTML = `<b>${esc(m.name)}</b><p>${esc(m.notes || "Listening mode: what every tuner and demod channel does.")}</p>`;
    } else if (e.target.id === "bc-del-mode") {
      const u = U();
      if (!confirm(`Remove listening mode "${mode().name}"?`)) return;
      u.modes.splice(u.mode, 1); u.mode = 0; changed();
    }
  });
  root.addEventListener("change", e => {
    if (e.target.id !== "bc-add-mode" || !e.target.value) return;
    const u = U(), v = e.target.value;
    u.modes.push(v === "blank" ? blankMode(`Listening mode ${u.modes.length + 1}`) : modeFromPreset(CONF.software[+v]));
    u.mode = u.modes.length - 1;
    changed();
    const m = mode();
    explainBox.innerHTML = `<b>${esc(m.name)}</b><p>${esc(m.notes || "")}</p>`;
  });

  // ---------------------------------------------------------------- toolbar
  // ---- magnifier: the diagram always fits the window; zoom to everything, to one chip, or in / out
  let lastLay = null, view = null, focusId = null; // view = {x, y, w, h} in diagram units, null = all
  function applyView() {
    const svg = $("#bc-svg"), L = lastLay;
    if (!L) return;
    if (focusId && !dev(focusId)) { focusId = null; view = null; }
    if (focusId) view = focusBox(focusId);
    const v = view || {x: 0, y: 0, w: L.W, h: L.H};
    svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
    const cw = $(".bc-canvas").clientWidth || 900, maxH = Math.max(320, window.innerHeight * 0.78);
    svg.setAttribute("width", cw);
    svg.setAttribute("height", Math.min(maxH, cw * v.h / v.w));
    svg.setAttribute("preserveAspectRatio", "xMidYMin meet");
    root.querySelectorAll("[data-focus]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.focus === (focusId || "all"))));
  }
  // a chip plus every block and chip pin wired to it
  function focusBox(id) {
    const L = lastLay, P = L.pos[id];
    if (!P) return null;
    let x0 = P.x - 20, y0 = P.y - 10, x1 = P.x + P.w + 20, y1 = P.y + P.h + 10;
    const grow = (x, y, w = 0, h = 0) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + w); y1 = Math.max(y1, y + h); };
    for (const l of S.links.filter(l => l.a.d === id || l.b.d === id)) {
      if (NET.includes(l.kind)) continue;
      const other = l.a.d === id ? l.b : l.a;
      if (other.blk && L.blocks[other.blk]) { const r = L.blocks[other.blk]; grow(r.x, r.y, r.w, r.h); }
      if (other.d && other.d !== id) for (const n of other.pins || []) { const q = L.pinXY(other.d, n); if (q) grow(q.x - 60, q.y - 10, 120, 20); }
    }
    const pad = 30;
    return {x: x0 - pad, y: y0 - pad, w: x1 - x0 + 2 * pad, h: y1 - y0 + 2 * pad};
  }
  function zoomBy(f) {
    const L = lastLay;
    if (!L) return;
    const v = view || {x: 0, y: 0, w: L.W, h: L.H};
    const w = Math.min(L.W * 1.2, Math.max(200, v.w * f)), h = v.h * (w / v.w);
    view = {x: v.x + (v.w - w) / 2, y: v.y + (v.h - h) / 2, w, h};
    focusId = null;
    applyView();
  }
  function renderFocusButtons() {
    const box = $("#bc-focus");
    if (!box) return;
    box.innerHTML = `<button type="button" class="bc-chip" data-focus="all">All chips</button>` +
      S.devices.map(o => `<button type="button" class="bc-chip" data-focus="${o.id}">${esc(o.slot ? `${o.slot} · ${o.mpn}` : o.mpn)}</button>`).join("");
    applyView();
  }
  root.addEventListener("click", e => {
    const f = e.target.closest("[data-focus]");
    if (!f) return;
    focusId = f.dataset.focus === "all" ? null : f.dataset.focus;
    if (!focusId) view = null;
    applyView();
    explain("magnifier", f.textContent);
  });
  window.addEventListener("resize", applyView);
  // drag to pan when zoomed in
  (() => {
    const svg = $("#bc-svg");
    let drag = null;
    svg.addEventListener("pointerdown", e => {
      if (!view || e.target.closest(".pin, .dev-head, .blk")) return;
      const v = view, s = v.w / svg.clientWidth;
      drag = {x: e.clientX, y: e.clientY, v: {...v}, s};
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", e => {
      if (!drag) return;
      focusId = null;
      view = {...drag.v, x: drag.v.x - (e.clientX - drag.x) * drag.s, y: drag.v.y - (e.clientY - drag.y) * drag.s};
      applyView();
    });
    svg.addEventListener("pointerup", () => (drag = null));
  })();
  function changed() { dirty = true; $("#bc-status").textContent = "Unsaved changes"; render(); }
  $("#bc-add").addEventListener("change", e => { if (e.target.value) { addDevice(e.target.value); e.target.value = ""; changed(); } });
  $("#bc-auto").addEventListener("click", () => { autoComplete(); changed(); });
  root.querySelectorAll("[data-rail]").forEach(b => (b.onclick = () => {
    let v = b.dataset.rail;
    if (v === "other") { v = (prompt("Rail voltage in V (e.g. 5, 2.5)") || "").replace(/\s*V$/i, "").trim(); if (!v) return; }
    const n = connectRail(v);
    changed();
    explain("supply", `${v} V rail · ${n} pin${n === 1 ? "" : "s"} connected`);
  }));
  $("#bc-compact").checked = S.compact;
  $("#bc-compact").addEventListener("change", e => { S.compact = e.target.checked; render(); });
  $("#bc-zoom-in").addEventListener("click", () => zoomBy(0.7));
  $("#bc-zoom-out").addEventListener("click", () => zoomBy(1.4));
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
      const k = keyOf(el);
      if (k) explain(k, titleOf(el));
    });
  if (S.usecase) { normalise(S.usecase); S.region ||= S.usecase.region; if (S.audio == null && S.usecase.audioDsp != null) S.audio = S.usecase.audioDsp; if (!S.features.length && S.usecase.features) S.features = [...S.usecase.features]; if (S.digital == null && S.usecase.digital != null) S.digital = S.usecase.digital; }
  render();
})();
