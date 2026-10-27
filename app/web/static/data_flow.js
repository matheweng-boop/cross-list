// Data management › Data flow (owner, 26 Oct 2026; four columns 27 Oct 2026): the chart of every path the data takes,
// drawn from data/manage/data_flow.yaml (sent in #df-data). Column 1 holds the inputs in two bracketed groups (Inputs,
// Searches), column 2 the cross process around the CROSS ENGINE, column 3 the data checks around DATA CHECKS, column 4
// the research process around RESEARCH; the three hubs sit on one level. The hubs' links to the checks (`shown`) and
// the purple handovers between the two processes are always labelled. Every other line is thin grey and shows its
// label only when it or one of its boxes is tapped; input lines into the checks or research travel as one bundled
// arrow below the cross process. Boxes carry 1-3 words; tapping one shows what it is, where its data is kept and its
// lines in the info box under the chart.
// The owner drags boxes, connects them by dragging a box's round handle onto another box, double-taps to edit, adds
// steps and notes, zooms (pinch / wheel) and pans; Save sends the whole chart to /manage/data-flow/save, which stores a
// version and answers with the change list against the file version. Pointer events only, so mouse, pen and touch
// (iPad) work the same. Self-contained: no libraries.
(() => {
  const $ = s => document.querySelector(s);
  const D = JSON.parse($("#df-data").textContent);
  const svg = $("#df-svg"), frame = $("#df-frame"), status = $("#df-status");
  const NW = D.nodeW, NH = D.nodeH, NOTE_W = D.noteW;
  const LANES = D.lanes, laneById = Object.fromEntries(LANES.map(l => [l.id, l]));
  const fileNode = Object.fromEntries(D.file.nodes.map(n => [n.id, n]));
  const S = JSON.parse(JSON.stringify(D.state));
  for (const n of S.nodes) { n.w = n.w || fileNode[n.id]?.w || NW; n.h = n.h || fileNode[n.id]?.h || NH; }
  let view = null, sel = null, dirty = false, action = null, pinch = null, lastTap = {id: null, t: 0};
  const pointers = new Map();
  let smooth = false, frameQueued = false;
  try { smooth = localStorage.getItem("df-smooth") === "1"; } catch (e) { /* storage blocked: square lines */ }

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const say = t => { status.textContent = t; };
  const byId = () => Object.fromEntries(S.nodes.map(n => [n.id, n]));
  const newId = p => `${p}-${Math.random().toString(36).slice(2, 8)}`;
  // the column a box stands in (same rule as app/services/data_flow.py lane_at)
  function laneAt(x, w) {
    const c = x + w / 2;
    let best = null, off = Infinity;
    for (const l of LANES) {
      const o = c >= l.x && c < l.x + l.w ? 0 : Math.min(Math.abs(c - l.x), Math.abs(c - l.x - l.w));
      if (o < off) { off = o; best = l.id; }
    }
    return best || "";
  }
  const laneOf = n => laneAt(n.x, n.w);

  function wrap(text, width, max) {
    const words = String(text || "").split(/\s+/).filter(Boolean), lines = [];
    let cur = "";
    for (const w of words) {
      if (cur && (cur + " " + w).length > width) { lines.push(cur); cur = w; } else cur = cur ? cur + " " + w : w;
    }
    if (cur) lines.push(cur);
    if (lines.length > max) { lines.length = max; lines[max - 1] = lines[max - 1].replace(/.{0,2}$/, "…"); }
    return lines.length ? lines : [""];
  }
  function nodeBox(n) {
    const w = n.w || NW;
    if (n.hub) return {x: n.x, y: n.y, w, h: n.h || 72, lines: wrap(n.label, Math.floor(w / 13), 2)};
    const lines = wrap(n.label, Math.floor((w - 22) / 6.3), 2);
    return {x: n.x, y: n.y, w, h: Math.max(n.h || NH, 15 + lines.length * 15 + 6), lines};
  }
  function noteBox(t) {
    const lines = wrap(t.text, 27, 6);
    return {x: t.x, y: t.y, w: NOTE_W, h: 9 + lines.length * 13, lines};
  }

  // ---- layout around the boxes: the column panels, the two input brackets and the bundle under the cross process
  function frameOf(boxes) {
    const N = byId(), panels = {};
    for (const l of LANES) panels[l.id] = {x: l.x, y: 0, w: l.w, h: l.h, lane: l};
    for (const n of S.nodes) {
      const p = panels[laneOf(n)], b = boxes[n.id];
      if (p) p.h = Math.max(p.h, b.y + b.h + 26);
    }
    // the inputs in their groups (what people enter, what we look up), each with a neutral bracket and its name
    const brackets = [], inputs = laneById.inputs;
    for (const g of inputs ? inputs.groups : []) {
      const list = S.nodes.filter(n => n.group === g.id && laneOf(n) === "inputs").map(n => boxes[n.id]);
      if (!list.length) continue;
      const x = Math.max(...list.map(b => b.x + b.w)) + 4, y0 = Math.min(...list.map(b => b.y)), y1 = Math.max(...list.map(b => b.y + b.h));
      brackets.push({group: g.id, label: g.label, x, y0, y1, lx: Math.min(...list.map(b => b.x))});
    }
    // input lines into the checks or research leave on the left, down one spine, under the cross process (a bundle)
    const cross = panels.crosses, from = S.nodes.filter(n => laneOf(n) === "inputs");
    const bundled = S.edges.map((e, i) => [e, i]).filter(([e]) => isBundled(e, N)).map(([, i]) => i);
    let bundle = null;
    if (cross && from.length && bundled.length) {
      const srcs = [...new Set(bundled.map(i => S.edges[i].from))].map(id => boxes[id]);
      const lanesTo = [...new Set(bundled.map(i => laneOf(N[S.edges[i].to])))].map(id => panels[id]).filter(Boolean);
      const sx = Math.min(...from.map(n => n.x)) - 8;
      const y = Math.max(...Object.values(panels).filter(p => p.lane.id !== "inputs").map(p => p.y + p.h), ...srcs.map(b => b.y + b.h)) + 30;
      bundle = {sx, y, stubs: srcs.map(b => [b.x, b.y + b.h / 2]), y0: Math.min(...srcs.map(b => b.y + b.h / 2)),
        ends: lanesTo.map(p => [p.x + 12, p.y + p.h]), edges: bundled};  // up the column's left gutter
      if (panels.inputs) panels.inputs.h = Math.max(panels.inputs.h, y + 40);
    }
    return {panels, brackets, bundle};
  }
  // an input line into the checks or the research: inside the one bundle, its own line only when tapped
  function isBundled(e, N) {
    const a = N[e.from], b = N[e.to];
    if (!a || !b || e.handover || laneOf(a) !== "inputs") return false;
    const lb = laneOf(b);
    return lb !== "inputs" && lb !== "crosses";
  }

  // ---- edges: square lines that go around the boxes (candidate shapes, the clear and short one wins)
  const R = b => ({l: b.x, r: b.x + b.w, t: b.y, b: b.y + b.h, cx: b.x + b.w / 2, cy: b.y + b.h / 2});
  function segHits(p, q, o) {
    const pad = 3;
    const x0 = Math.min(p[0], q[0]), x1 = Math.max(p[0], q[0]), y0 = Math.min(p[1], q[1]), y1 = Math.max(p[1], q[1]);
    return x1 > o.l - pad && x0 < o.r + pad && y1 > o.t - pad && y0 < o.b + pad;
  }
  // a line through a box costs most; running along another line (not of the same box) costs too, then length and bends
  function overlaps(p, q, u) {
    const h = Math.abs(p[1] - q[1]) < 0.5, uh = Math.abs(u.p[1] - u.q[1]) < 0.5;
    if (h !== uh) return false;
    const [a, b] = h ? [p[1], u.p[1]] : [p[0], u.p[0]];
    if (Math.abs(a - b) > 4) return false;
    const i = h ? 0 : 1, lo = Math.max(Math.min(p[i], q[i]), Math.min(u.p[i], u.q[i])), hi = Math.min(Math.max(p[i], q[i]), Math.max(u.p[i], u.q[i]));
    return hi - lo > 6;
  }
  function cost(pts, obstacles, used, e) {
    let hits = 0, len = 0, over = 0;
    for (let k = 1; k < pts.length; k++) {
      len += Math.abs(pts[k][0] - pts[k - 1][0]) + Math.abs(pts[k][1] - pts[k - 1][1]);
      for (const o of obstacles) if (segHits(pts[k - 1], pts[k], o)) hits++;
      if (used) for (const u of used) if (u.from !== e.from && overlaps(pts[k - 1], pts[k], u)) over++;
    }
    return hits * 1000 + over * 300 + len + (pts.length - 2) * 25;
  }
  function between(lo, hi, cuts) {
    const out = [(lo + hi) / 2];
    for (const c of cuts) if (c > lo + 6 && c < hi - 6) out.push(c);
    return out;
  }
  function candidates(a, b, xs, ys) {
    const out = [];
    for (const d of [-11, 11, 0]) {  // a second line between the same two boxes runs beside the first
      if (b.l >= a.r + 10) for (const mx of between(a.r, b.l, xs)) out.push([[a.r, a.cy + d], [mx, a.cy + d], [mx, b.cy + d], [b.l, b.cy + d]]);
      if (a.l >= b.r + 10) for (const mx of between(b.r, a.l, xs)) out.push([[a.l, a.cy + d], [mx, a.cy + d], [mx, b.cy + d], [b.r, b.cy + d]]);
    }
    if (b.t >= a.b + 8) for (const my of between(a.b, b.t, ys)) out.push([[a.cx, a.b], [a.cx, my], [b.cx, my], [b.cx, b.t]]);
    if (a.t >= b.b + 8) for (const my of between(b.b, a.t, ys)) out.push([[a.cx, a.t], [a.cx, my], [b.cx, my], [b.cx, b.b]]);
    // L shapes: out of a side, into the top or bottom (and the other way round)
    const side = b.cx > a.cx ? a.r : a.l, into = b.cx > a.cx ? b.l : b.r;
    if (b.t > a.cy + 8) out.push([[side, a.cy], [b.cx, a.cy], [b.cx, b.t]]);
    if (b.b < a.cy - 8) out.push([[side, a.cy], [b.cx, a.cy], [b.cx, b.b]]);
    if (b.cy > a.b + 8) out.push([[a.cx, a.b], [a.cx, b.cy], [into, b.cy]]);
    if (b.cy < a.t - 8) out.push([[a.cx, a.t], [a.cx, b.cy], [into, b.cy]]);
    // over the top or under the bottom of both
    const y0 = Math.min(a.t, b.t) - 14, y1 = Math.max(a.b, b.b) + 14;
    out.push([[a.cx, a.t], [a.cx, y0], [b.cx, y0], [b.cx, b.t]], [[a.cx, a.b], [a.cx, y1], [b.cx, y1], [b.cx, b.b]]);
    // across a whole column: out of the side, along a free row between its boxes, into the side
    const right = b.l >= a.r + 30, left = a.l >= b.r + 30;
    if (right || left) {
      const x1 = right ? a.r + 16 : a.l - 16, x2 = right ? b.l - 16 : b.r + 16, s1 = right ? a.r : a.l, s2 = right ? b.l : b.r;
      for (const yc of ys) out.push([[s1, a.cy], [x1, a.cy], [x1, yc], [x2, yc], [x2, b.cy], [s2, b.cy]]);
    }
    // down a free corridor between the boxes
    if (b.t >= a.b + 30) for (const cx of xs) out.push([[a.cx, a.b], [a.cx, a.b + 12], [cx, a.b + 12], [cx, b.t - 12], [b.cx, b.t - 12], [b.cx, b.t]]);
    return out;
  }
  // drop repeated points and the middle of straight runs
  function tidy(pts) {
    const q = pts.filter((p, k) => !k || Math.abs(p[0] - pts[k - 1][0]) + Math.abs(p[1] - pts[k - 1][1]) > 0.5);
    return q.filter((p, k) => k === 0 || k === q.length - 1 ||
      !((Math.abs(q[k - 1][0] - p[0]) < 0.5 && Math.abs(q[k + 1][0] - p[0]) < 0.5) || (Math.abs(q[k - 1][1] - p[1]) < 0.5 && Math.abs(q[k + 1][1] - p[1]) < 0.5)));
  }
  function pathD(pts) {
    if (!smooth || pts.length < 3) return "M" + pts.map(p => `${p[0]} ${p[1]}`).join("L");
    let d = `M${pts[0][0]} ${pts[0][1]}`;
    for (let k = 1; k < pts.length - 1; k++) {  // rounded corners
      const [p, q, r] = [pts[k - 1], pts[k], pts[k + 1]];
      const l1 = Math.hypot(q[0] - p[0], q[1] - p[1]), l2 = Math.hypot(r[0] - q[0], r[1] - q[1]), c = Math.min(14, l1 / 2, l2 / 2);
      const s = [q[0] - (q[0] - p[0]) * c / (l1 || 1), q[1] - (q[1] - p[1]) * c / (l1 || 1)], t = [q[0] + (r[0] - q[0]) * c / (l2 || 1), q[1] + (r[1] - q[1]) * c / (l2 || 1)];
      d += `L${s[0]} ${s[1]}Q${q[0]} ${q[1]} ${t[0]} ${t[1]}`;
    }
    const z = pts[pts.length - 1];
    return d + `L${z[0]} ${z[1]}`;
  }
  const always = e => e.handover || e.shown;
  function routes(boxes, layout) {
    const N = byId(), items = [], all = Object.entries(boxes), used = [];
    const xs = [], ys = [];
    for (const [, b] of all) { xs.push(b.x - 12, b.x + b.w + 12); ys.push(b.y - 12, b.y + b.h + 12); }
    const gutter = {};
    // the labelled lines first, so the others go round them
    const order = S.edges.map((e, i) => i).sort((p, q) => always(S.edges[q]) - always(S.edges[p]));
    for (const i of order) {
      const e = S.edges[i], a = N[e.from], b = N[e.to];
      if (!a || !b) continue;
      const A = R(boxes[a.id]), B = R(boxes[b.id]);
      const obstacles = all.filter(([id]) => id !== a.id && id !== b.id).map(([, o]) => R(o));
      if (layout.bundle && isBundled(e, N)) {  // along the bundle: down the spine, under the cross process, up the gutter of its column
        const lane = layout.panels[laneOf(b)], k = gutter[lane.lane.id] = (gutter[lane.lane.id] || 0) + 1;
        const gx = lane.x + 8 + (k % 4) * 3, y = layout.bundle.y, sx = layout.bundle.sx;
        const head = [[A.l, A.cy], [sx, A.cy], [sx, y], [gx, y]];
        const legs = [[[gx, B.cy], [B.l, B.cy]], [[gx, B.t - 12], [B.cx, B.t - 12], [B.cx, B.t]],
          [[gx, B.b + 12], [B.cx, B.b + 12], [B.cx, B.b]]];
        let leg = legs[0], lc = Infinity;
        for (const l of legs) { const v = cost([[gx, y], ...l], obstacles); if (v < lc) { lc = v; leg = l; } }
        items.push({i, e, a, b, pts: tidy([...head, ...leg]), from: head.length - 1, bundled: true});
        continue;
      }
      let best = null, bc = Infinity;
      for (const c of candidates(A, B, xs, ys)) {
        const v = cost(c, obstacles, used, e);
        if (v < bc) { bc = v; best = c; }
      }
      const pts = tidy(best || [[A.cx, A.cy], [B.cx, B.cy]]);
      for (let k = 1; k < pts.length; k++) used.push({p: pts[k - 1], q: pts[k], from: e.from, to: e.to});
      items.push({i, e, a, b, pts});
    }
    items.sort((p, q) => p.i - q.i);
    // arrows into the same side of a box sit side by side
    const sides = {};
    for (const it of items) {
      if (it.bundled || it.e.shown || it.pts.length < 3) continue;  // a hub pair keeps its own two rows
      const [p, q] = it.pts.slice(-2), vert = Math.abs(p[0] - q[0]) < 0.5;
      (sides[`${it.e.to}|${vert ? (q[1] > p[1] ? "t" : "b") : (q[0] > p[0] ? "l" : "r")}`] ||= []).push([it, vert]);
    }
    for (const list of Object.values(sides)) {
      if (list.length < 2) continue;
      const vert = list[0][1], B = boxes[list[0][0].e.to];
      list.sort(([p], [q]) => vert ? p.pts[p.pts.length - 3][0] - q.pts[q.pts.length - 3][0] : p.pts[p.pts.length - 3][1] - q.pts[q.pts.length - 3][1]);
      list.forEach(([it], j) => {
        const f = (j + 1) / (list.length + 1), n = it.pts.length, z = it.pts[n - 1], y = it.pts[n - 2];
        if (vert) { z[0] = y[0] = B.x + B.w * (0.25 + 0.5 * f); } else { z[1] = y[1] = B.y + B.h * (0.2 + 0.6 * f); }
      });
    }
    // labels: an always-labelled line's sits in the first gap between two columns it crosses; any other line's on
    // its longest run
    const panels = Object.values(layout.panels).sort((p, q) => p.x - q.x);
    const gaps = panels.slice(1).map((p, k) => (panels[k].x + panels[k].w + p.x) / 2);
    for (const it of items) {
      it.anchor = "middle";
      const segs = it.pts.slice(1).map((q, k2) => [it.pts[k2], q]).slice(it.from || 0);  // a bundled line: its own leg only
      let done = false;
      if (always(it.e)) {
        for (const [p, q] of segs) {
          if (Math.abs(p[1] - q[1]) > 0.5) continue;
          const inGap = gaps.filter(g => g >= Math.min(p[0], q[0]) && g <= Math.max(p[0], q[0])).sort((g, h) => Math.abs(g - p[0]) - Math.abs(h - p[0]));
          if (inGap.length) { it.lx = inGap[0]; it.ly = p[1] - 6; done = true; break; }  // just above the line
        }
      }
      if (done) continue;
      const s = segs.reduce((m, x) => Math.hypot(x[1][0] - x[0][0], x[1][1] - x[0][1]) > Math.hypot(m[1][0] - m[0][0], m[1][1] - m[0][1]) ? x : m, segs[0]);
      it.lx = (s[0][0] + s[1][0]) / 2; it.ly = (s[0][1] + s[1][1]) / 2 - 5;
    }
    return items;
  }


  // ---- drawing
  function extent(boxes, layout) {
    const all = [...Object.values(boxes), ...S.notes.map(noteBox), ...Object.values(layout.panels)];
    const x0 = Math.min(0, ...all.map(b => b.x)), y0 = Math.min(0, ...all.map(b => b.y));
    const x1 = Math.max(...all.map(b => b.x + b.w)), y1 = Math.max(400, ...all.map(b => b.y + b.h));
    return {x: x0 - 12, y: y0 - 12, w: x1 - x0 + 24, h: y1 - y0 + 24};
  }
  const layoutNow = () => { const boxes = Object.fromEntries(S.nodes.map(n => [n.id, nodeBox(n)])); return {boxes, layout: frameOf(boxes)}; };
  function render() {
    const {boxes, layout} = layoutNow(), N = byId();
    const selNode = sel && sel.type === "node" ? sel.id : null;
    const out = [`<defs>${["", "handover", "hl"].map(k =>
      `<marker id="df-m${k ? "-" + k : ""}" class="m-${k || "def"}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="${k === "handover" ? 5 : 7}" markerHeight="${k === "handover" ? 5 : 7}" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker>`).join("")}</defs>`];
    out.push('<g class="lanes">');
    for (const l of LANES) {
      const p = layout.panels[l.id];
      out.push(`<g class="lane lane-${esc(l.id)}"><rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="16"/>` +
        `<text class="lane-title" x="${p.x + 20}" y="${p.y + 34}">${esc(l.label)}</text>` +
        (l.subtitle ? `<text class="lane-sub" x="${p.x + 20}" y="${p.y + 54}">${esc(l.subtitle)}</text>` : "") +
        l.captions.map(c => `<text class="caption" x="${c.x}" y="${c.y}">${esc(c.text)}</text>`).join("") + "</g>");
    }
    for (const b of layout.brackets) {
      out.push(`<path class="bracket g-${esc(b.group)}" d="M${b.x} ${b.y0}H${b.x + 10}V${b.y1}H${b.x}"/>` +
        `<text class="group-label" x="${b.lx}" y="${b.y0 - 7}">${esc(b.label)}</text>`);
    }
    const bu = layout.bundle;
    if (bu) {
      const far = Math.max(...bu.ends.map(p => p[0]));
      out.push(`<g class="bundle"><title>Inputs to the data checks and the research: one arrow under the cross process, never through it. Tap an input for its own lines.</title>` +
        bu.stubs.map(([x, y]) => `<path class="stub" d="M${x} ${y}H${bu.sx}"/>`).join("") +
        `<path d="M${bu.sx} ${bu.y0}V${bu.y}H${far}" />` +
        bu.ends.map(([x, y]) => `<path d="M${x} ${bu.y}V${y + 2}" marker-end="url(#df-m)"/>`).join("") +
        `<text x="${layout.panels.crosses ? layout.panels.crosses.x + 20 : bu.sx + 20}" y="${bu.y - 7}">inputs to the checks and research</text></g>`);
    }
    out.push('</g><g class="edges">');
    const items = routes(boxes, layout);
    for (const it of items) {
      const isSel = sel && sel.type === "edge" && sel.i === it.i, hl = isSel || (selNode && (it.e.from === selNode || it.e.to === selNode));
      if (it.bundled && !hl) continue;  // inside the bundle
      const cls = (it.e.handover ? " handover" : "") + (it.e.shown ? " shown" : "") + (it.e.status === "planned" ? " planned" : "") + (hl ? " hl" : "") + (isSel ? " sel" : "");
      const mk = hl ? "df-m-hl" : it.e.handover ? "df-m-handover" : "df-m";
      const label = it.e.label ? esc(it.e.label) + (it.e.status === "planned" ? " (planned)" : "") : "";
      out.push(`<g class="edge${cls}" data-edge="${it.i}"><path class="hit" d="${pathD(it.pts)}"/><path class="line" d="${pathD(it.pts)}" marker-end="url(#${mk})"/>` +
        (label && (always(it.e) || hl) ? `<text x="${it.lx}" y="${it.ly}" text-anchor="${it.anchor}">${label}</text>` : "") + "</g>");
    }
    out.push('</g><g class="nodes">');
    for (const n of S.nodes) {
      const b = boxes[n.id], isSel = selNode === n.id, lane = laneOf(n);
      const cls = `node k-${esc(n.kind)} p-${esc(lane)}${n.group ? " g-" + esc(n.group) : ""}${n.gate ? " gate" : ""}${n.status === "planned" ? " planned" : ""}${n.hub ? " hub" : ""}${isSel ? " sel" : ""}`;
      const parts = [`<rect class="box" width="${b.w}" height="${b.h}" rx="${n.hub ? 14 : n.kind === "output" ? 18 : 9}"/>`];
      if (n.hub) b.lines.forEach((ln, k) => parts.push(`<text class="hub-label" x="${b.w / 2}" y="${b.h / 2 + 7 + (k - (b.lines.length - 1) / 2) * 22}" text-anchor="middle">${esc(ln)}</text>`));
      else b.lines.forEach((ln, k) => parts.push(`<text x="12" y="${23 + k * 15}">${esc(ln)}</text>`));
      if (n.note) parts.push(`<text class="notemark" x="${b.w - 6}" y="13" text-anchor="end">✎</text>`);
      parts.push(`<circle class="handle-hit" data-handle="${esc(n.id)}" cx="${b.w}" cy="${b.h / 2}" r="14"/><circle class="handle" cx="${b.w}" cy="${b.h / 2}" r="5"/>`);
      out.push(`<g class="${cls}" data-node="${esc(n.id)}" transform="translate(${n.x},${n.y})"><title>${esc(n.label)}</title>${parts.join("")}</g>`);
    }
    out.push('</g><g class="notes">');
    for (const t of S.notes) {
      const b = noteBox(t), isSel = sel && sel.type === "note" && sel.id === t.id;
      out.push(`<g class="note${isSel ? " sel" : ""}" data-note="${esc(t.id)}" transform="translate(${t.x},${t.y})"><rect class="paper" width="${b.w}" height="${b.h}" rx="4"/>` +
        b.lines.map((ln, k) => `<text x="7" y="${15 + k * 13}">${esc(ln)}</text>`).join("") + "</g>");
    }
    out.push('</g><path class="temp" id="df-temp" d=""/>');
    svg.innerHTML = out.join("");
    svg.classList.toggle("has-sel", !!sel);
    $("#df-edit").disabled = $("#df-delete").disabled = !sel;
    showInfo(N);
  }
  // tap a box or a line: what it is, where its data is kept, what falls under it, and its lines with their labels
  const linkHtml = l => l ? (l.startsWith("/") ? ` · <a href="${esc(l)}">Open the page</a>` : ` · <code>${esc(l)}</code>`) : "";
  function showInfo(N) {
    const box = $("#df-info");
    if (sel && sel.type === "edge" && S.edges[sel.i]) {
      const e = S.edges[sel.i];
      box.innerHTML = `<b>${esc(N[e.from]?.label)} → ${esc(N[e.to]?.label)}</b>${e.label ? `: ${esc(e.label)}` : ""} <span class="muted">${e.handover ? "· handover between the processes" : e.shown ? "· to or from the data checks" : ""}${e.status === "planned" ? " · planned" : ""}</span>`;
      box.hidden = false;
      return;
    }
    const n = sel && sel.type === "node" ? N[sel.id] : null;
    if (!n) { box.hidden = true; box.innerHTML = ""; return; }
    const f = fileNode[n.id] || {}, inc = f.includes || [], lane = laneById[laneOf(n)];
    const g = n.group && laneOf(n) === "inputs" ? (laneById.inputs?.groups || []).find(x => x.id === n.group) : null;
    const group = g ? ` · ${esc(g.label)}` : "";
    const lines = S.edges.filter(e => e.from === n.id || e.to === n.id).map(e => e.from === n.id
      ? `→ ${esc(N[e.to]?.label)}${e.label ? `: ${esc(e.label)}` : ""}` : `← ${esc(N[e.from]?.label)}${e.label ? `: ${esc(e.label)}` : ""}`);
    box.innerHTML = `<b>${esc(n.label)}</b> <span class="muted">· ${esc(D.kinds[n.kind] || n.kind)}${lane ? " · " + esc(lane.label) : ""}${group}${f.gate ? " · review gate" : ""}${f.status === "planned" ? " · planned" : ""}</span><br>` +
      `${esc(f.desc || "Your own step.")}${linkHtml(f.link)}` + (f.kept ? `<br><span class="df-kept">Kept in: ${esc(f.kept)}</span>` : "") +
      (inc.length ? `<ul>${inc.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "") +
      (lines.length ? `<p class="df-info-lines">${lines.join("<br>")}</p>` : "") +
      (n.note ? `<p class="df-info-note">✎ Your note: ${esc(n.note)}</p>` : "");
    box.hidden = false;
  }

  // ---- view: zoom and pan inside the frame (the page never scrolls sideways)
  function applyView() {
    const r = svg.getBoundingClientRect(), aspect = (r.height || 1) / (r.width || 1);
    view.h = view.w * aspect;
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
    svg.setAttribute("preserveAspectRatio", "none");
  }
  function chartExtent() { const {boxes, layout} = layoutNow(); return extent(boxes, layout); }
  function fit() {
    const e = chartExtent();
    const r = svg.getBoundingClientRect(), aspect = (r.height || 1) / (r.width || 1);
    const w = Math.max(e.w, e.h / aspect);
    view = {x: e.x - (w - e.w) / 2, y: e.y, w, h: w * aspect};
    applyView();
  }
  function zoomAt(f, p) {
    const w = Math.min(8000, Math.max(220, view.w * f)), k = w / view.w;
    view = {x: p.x - (p.x - view.x) * k, y: p.y - (p.y - view.y) * k, w, h: view.h * k};
    applyView();
  }
  const center = () => ({x: view.x + view.w / 2, y: view.y + view.h / 2});
  function toSvg(e) {
    const r = svg.getBoundingClientRect();
    return {x: view.x + (e.clientX - r.left) * view.w / r.width, y: view.y + (e.clientY - r.top) * view.h / r.height};
  }

  function changed(msg) {
    dirty = true;
    say((msg ? msg + " " : "") + "Not saved yet: tap Save to keep it.");
    render();
  }

  // ---- pointer input: one finger or the mouse drags, connects, selects or pans; two fingers pinch-zoom
  function nodeAt(e) {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    return el && el.closest ? el.closest("[data-node]") : null;
  }
  svg.addEventListener("pointerdown", e => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
    try { svg.setPointerCapture(e.pointerId); } catch (err) { /* already released */ }
    if (pointers.size === 2) {
      const [p, q] = [...pointers.values()];
      pinch = {d: Math.hypot(p.x - q.x, p.y - q.y) || 1, view: {...view}, mid: toSvg({clientX: (p.x + q.x) / 2, clientY: (p.y + q.y) / 2})};
      action = null;
      $("#df-temp")?.setAttribute("d", "");
      return;
    }
    if (pointers.size > 2) return;
    const p = toSvg(e), t = e.target.closest ? e.target.closest("[data-handle], [data-node], [data-note], [data-edge]") : null;
    if (t && t.dataset.handle) {
      const n = byId()[t.dataset.handle], b = nodeBox(n);
      action = {type: "connect", from: n.id, start: {x: n.x + b.w, y: n.y + b.h / 2}, moved: false};
    } else if (t && (t.dataset.node || t.dataset.note)) {
      const isNode = !!t.dataset.node, id = isNode ? t.dataset.node : t.dataset.note;
      const obj = (isNode ? S.nodes : S.notes).find(x => x.id === id);
      action = {type: "move", kind: isNode ? "node" : "note", id, obj, p, ox: obj.x, oy: obj.y, moved: false};
    } else if (t && t.dataset.edge) {
      action = {type: "edge", i: +t.dataset.edge};
    } else {
      action = {type: "pan", sx: e.clientX, sy: e.clientY, view: {...view}, moved: false};
      svg.classList.add("panning");
    }
    e.preventDefault();
  });
  svg.addEventListener("pointermove", e => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pinch && pointers.size >= 2) {
      const [p, q] = [...pointers.values()];
      const k = pinch.d / (Math.hypot(p.x - q.x, p.y - q.y) || 1);
      const w = Math.min(8000, Math.max(220, pinch.view.w * k)), s = w / pinch.view.w;
      const r = svg.getBoundingClientRect(), mx = ((p.x + q.x) / 2 - r.left) / r.width, my = ((p.y + q.y) / 2 - r.top) / r.height;
      view = {x: pinch.mid.x - mx * w, y: pinch.mid.y - my * pinch.view.h * s, w, h: pinch.view.h * s};
      applyView();
      return;
    }
    if (!action) return;
    if (action.type === "move") {
      const p = toSvg(e), dx = p.x - action.p.x, dy = p.y - action.p.y;
      if (!action.moved && Math.hypot(dx, dy) < 5 * view.w / svg.getBoundingClientRect().width) return;
      action.moved = true;
      action.obj.x = Math.round(action.ox + dx); action.obj.y = Math.round(action.oy + dy);
      if (!frameQueued) { frameQueued = true; requestAnimationFrame(() => { frameQueued = false; render(); }); }  // one redraw per frame
    } else if (action.type === "connect") {
      const p = toSvg(e), s = action.start;
      action.moved = true;
      $("#df-temp").setAttribute("d", `M${s.x} ${s.y}L${p.x} ${p.y}`);
      svg.querySelectorAll(".node.target").forEach(x => x.classList.remove("target"));
      const t = nodeAt(e);
      if (t && t.dataset.node !== action.from) t.classList.add("target");
    } else if (action.type === "pan") {
      const r = svg.getBoundingClientRect(), s = view.w / r.width;
      if (Math.hypot(e.clientX - action.sx, e.clientY - action.sy) > 4) action.moved = true;
      view = {...action.view, x: action.view.x - (e.clientX - action.sx) * s, y: action.view.y - (e.clientY - action.sy) * s};
      applyView();
    }
  });
  function tap(kind, id) {
    const now = Date.now(), key = `${kind}:${id}`, double = lastTap.id === key && now - lastTap.t < 450;
    lastTap = double ? {id: null, t: 0} : {id: key, t: now};
    sel = kind === "edge" ? {type: "edge", i: id} : {type: kind, id};
    render();
    if (double) openEdit();
  }
  function end(e, cancelled) {
    pointers.delete(e.pointerId);
    if (pinch) { if (pointers.size < 2) pinch = null; action = null; return; }
    const a = action;
    action = null;
    svg.classList.remove("panning");
    if (!a || cancelled) { $("#df-temp")?.setAttribute("d", ""); return; }
    if (a.type === "move") {
      if (a.moved) { sel = {type: a.kind, id: a.id}; changed(`Moved “${a.kind === "node" ? a.obj.label : "note"}”.`); }
      else tap(a.kind, a.id);
    } else if (a.type === "connect") {
      $("#df-temp").setAttribute("d", "");
      const t = nodeAt(e), to = t && t.dataset.node;
      if (to && to !== a.from) {
        const N = byId();
        let i = S.edges.findIndex(x => x.from === a.from && x.to === to);
        if (i < 0) { S.edges.push({from: a.from, to, label: ""}); i = S.edges.length - 1; }
        sel = {type: "edge", i};
        changed(`Connected “${N[a.from].label}” → “${N[to].label}”. Double-tap the line to name it.`);
      } else render();
    } else if (a.type === "edge") tap("edge", a.i);
    else if (a.type === "pan" && !a.moved && sel) { sel = null; render(); }
  }
  svg.addEventListener("pointerup", e => end(e, false));
  svg.addEventListener("pointercancel", e => end(e, true));
  svg.addEventListener("wheel", e => { e.preventDefault(); zoomAt(Math.exp(e.deltaY * 0.0015), toSvg(e)); }, {passive: false});

  // ---- editing: one dialog for a box, a line or a note
  const dlg = $("#df-dialog");
  function openEdit() {
    if (!sel) return;
    const show = (id, on) => { $(id).hidden = !on; };
    const N = byId();
    if (sel.type === "node") {
      const n = N[sel.id], f = fileNode[n.id];
      $("#df-d-title").textContent = "Edit step";
      $("#df-d-label").value = n.label; $("#df-d-kind").value = n.kind; $("#df-d-note").value = n.note || "";
      $("#df-d-info").innerHTML = (f && f.desc ? esc(f.desc) : "Your own step.") + linkHtml(f && f.link);
      show("#df-d-label-wrap", true); show("#df-d-kind-wrap", true); show("#df-d-note-wrap", true);
    } else if (sel.type === "edge") {
      const e = S.edges[sel.i];
      $("#df-d-title").textContent = "Name the line";
      $("#df-d-label").value = e.label || "";
      $("#df-d-info").textContent = `${N[e.from]?.label} → ${N[e.to]?.label}`;
      show("#df-d-label-wrap", true); show("#df-d-kind-wrap", false); show("#df-d-note-wrap", false);
    } else {
      const t = S.notes.find(x => x.id === sel.id);
      $("#df-d-title").textContent = "Note";
      $("#df-d-note").value = t.text;
      $("#df-d-info").textContent = "A free note on the chart; tonight's run reads it.";
      show("#df-d-label-wrap", false); show("#df-d-kind-wrap", false); show("#df-d-note-wrap", true);
    }
    dlg.returnValue = "";
    dlg.showModal();
  }
  dlg.addEventListener("close", () => {
    if (dlg.returnValue !== "ok" || !sel) { if (sel && sel.type === "note" && !S.notes.find(x => x.id === sel.id)?.text) deleteSel(true); return; }
    const label = $("#df-d-label").value.trim().slice(0, 80), note = $("#df-d-note").value.trim().slice(0, 500);
    if (sel.type === "node") {
      const n = byId()[sel.id];
      Object.assign(n, {label: label || n.label, kind: $("#df-d-kind").value, note});
      changed(`Edited “${n.label}”.`);
    } else if (sel.type === "edge") {
      S.edges[sel.i].label = label;
      changed("Line named.");
    } else {
      const t = S.notes.find(x => x.id === sel.id);
      if (!note) { deleteSel(); return; }
      t.text = note;
      changed("Note written.");
    }
  });
  function deleteSel(quiet) {
    if (!sel) return;
    let msg = "";
    if (sel.type === "node") {
      const n = byId()[sel.id];
      S.nodes = S.nodes.filter(x => x.id !== sel.id);
      S.edges = S.edges.filter(x => x.from !== sel.id && x.to !== sel.id);
      msg = `Deleted “${n.label}” and its lines.`;
    } else if (sel.type === "edge") {
      S.edges.splice(sel.i, 1);
      msg = "Deleted the line.";
    } else {
      S.notes = S.notes.filter(x => x.id !== sel.id);
      msg = "Deleted the note.";
    }
    sel = null;
    if (quiet) render(); else changed(msg);
  }
  $("#df-edit").onclick = openEdit;
  $("#df-delete").onclick = () => deleteSel();
  document.addEventListener("keydown", e => {
    if (dlg.open || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "")) return;
    if ((e.key === "Delete" || e.key === "Backspace") && sel) { e.preventDefault(); deleteSel(); }
  });
  $("#df-add-node").onclick = () => {
    const c = center(), n = {id: newId("n"), label: "New step", kind: "step", note: "", x: Math.round(c.x - NW / 2), y: Math.round(c.y - NH / 2), w: NW, h: NH};
    S.nodes.push(n);
    sel = {type: "node", id: n.id};
    changed("Added a step.");
    openEdit();
  };
  $("#df-add-note").onclick = () => {
    const c = center(), t = {id: newId("t"), text: "", x: Math.round(c.x - NOTE_W / 2), y: Math.round(c.y - 20)};
    S.notes.push(t);
    sel = {type: "note", id: t.id};
    render();
    openEdit();
  };
  const styleBtn = $("#df-style");
  const showStyle = () => { styleBtn.textContent = smooth ? "Square lines" : "Smooth lines"; styleBtn.setAttribute("aria-pressed", String(smooth)); };
  styleBtn.onclick = () => {
    smooth = !smooth;
    try { localStorage.setItem("df-smooth", smooth ? "1" : "0"); } catch (e) { /* not remembered */ }
    showStyle(); render();
  };
  $("#df-zoom-in").onclick = () => zoomAt(0.75, center());
  $("#df-zoom-out").onclick = () => zoomAt(1.33, center());
  $("#df-fit").onclick = fit;
  $("#df-reset").onclick = () => {
    for (const n of S.nodes) { const f = fileNode[n.id]; if (f) { n.x = f.x; n.y = f.y; } }
    changed("Boxes back in their file places.");
    fit();
  };

  // ---- save: a new version in the database; the answer is the change list against the file version
  function showChanges(list) {
    const ul = $("#df-changes");
    ul.innerHTML = list.length ? list.map(c => `<li>${esc(c.text)}${c.held.length ? ` <span class="df-held small">held for your look: ${esc(c.held.join(", "))}</span>` : ""}</li>`).join("")
      : '<li class="muted">None yet: your saved chart is the same as the file version.</li>';
  }
  function showHistory(list) {
    $("#df-history").innerHTML = list.map(h => `<li${h.undone ? ' class="muted"' : ""}>${esc(h.at)} · ${esc(h.author)}${h.undone ? " · undone" : ""} – ${esc(h.note)}</li>`).join("");
    if (!document.querySelector(".df-undo")) {
      const f = document.createElement("form");
      f.method = "post"; f.action = "/manage/data-flow/undo"; f.className = "df-undo";
      f.innerHTML = '<button type="submit" class="secondary">Undo last save</button>';
      $("#df-save").after(f);
    }
  }
  $("#df-save").onclick = async () => {
    const btn = $("#df-save");
    btn.disabled = true; btn.setAttribute("aria-busy", "true");
    try {
      const body = {nodes: S.nodes.map(({id, label, kind, note, x, y}) => ({id, label, kind, note, x, y})),
        edges: S.edges.map(({from, to, label}) => ({from, to, label})), notes: S.notes.filter(t => t.text)};
      const res = await fetch("/manage/data-flow/save", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      const out = await res.json().catch(() => ({}));
      if (!res.ok || !out.ok) { say(out.message || "Not saved: the site did not answer. Try again."); return; }
      dirty = false;
      showChanges(out.changes); showHistory(out.history);
      say(out.message);
    } catch (err) {
      say("Not saved: no connection. Your changes are still on the screen; try again.");
    } finally { btn.disabled = false; btn.removeAttribute("aria-busy"); }
  };
  window.addEventListener("beforeunload", e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  showStyle();
  render();
  (() => {  // the frame no taller than the chart needs at full width (no empty band under it)
    const e = chartExtent();
    const want = e.h * frame.clientWidth / e.w + 4;
    if (want < frame.clientHeight) frame.style.height = `${Math.max(360, Math.round(want))}px`;
  })();
  fit();
  new ResizeObserver(() => { if (view) applyView(); }).observe(frame);
})();
