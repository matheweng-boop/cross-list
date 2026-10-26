// Data management › Data flow (owner, 26 Oct 2026): the chart of every path the data takes, drawn from
// data/manage/data_flow.yaml (sent in #df-data). The owner drags boxes, connects them by dragging a box's round handle
// onto another box, double-taps to edit, adds steps and notes, zooms (pinch / wheel) and pans; Save sends the whole
// chart to /manage/data-flow/save, which stores a version and answers with the change list against the file version.
// Pointer events only, so mouse, pen and touch (iPad) work the same. Self-contained: no libraries.
(() => {
  const $ = s => document.querySelector(s);
  const D = JSON.parse($("#df-data").textContent);
  const svg = $("#df-svg"), frame = $("#df-frame"), status = $("#df-status");
  const NW = D.nodeW, LW = D.laneW, LEFT = D.left, NOTE_W = 180;
  const fileNode = Object.fromEntries(D.file.nodes.map(n => [n.id, n]));
  const S = JSON.parse(JSON.stringify(D.state));
  let view = null, sel = null, dirty = false, action = null, pinch = null, lastTap = {id: null, t: 0};
  const pointers = new Map();
  let smooth = false;
  try { smooth = localStorage.getItem("df-smooth") === "1"; } catch (e) { /* storage blocked: square lines */ }

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const say = t => { status.textContent = t; };
  const byId = () => Object.fromEntries(S.nodes.map(n => [n.id, n]));
  const newId = p => `${p}-${Math.random().toString(36).slice(2, 8)}`;

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
  const tagOf = n => n.gate ? (n.status === "planned" ? "REVIEW GATE · PLANNED" : "REVIEW GATE") : (n.status === "planned" ? "PLANNED" : "");
  function nodeBox(n) {
    const lines = wrap(n.label, 27, 3);
    const h = 14 + lines.length * 15 + (tagOf(n) ? 13 : 0) + (n.note ? 14 : 0) + 4;
    return {x: n.x, y: n.y, w: NW, h, lines};
  }
  function noteBox(t) {
    const lines = wrap(t.text, 26, 7);
    return {x: t.x, y: t.y, w: NOTE_W, h: 12 + lines.length * 15, lines};
  }

  // ---- edges: each leaves the side facing the other box; ports spread along a side; square or smooth lines
  const cx = R => R.x + R.w / 2, cy = R => R.y + R.h / 2;
  function routes(boxes) {
    const N = byId(), items = [];
    S.edges.forEach((e, i) => {
      const a = N[e.from], b = N[e.to];
      if (!a || !b) return;
      const A = boxes[a.id], B = boxes[b.id];
      let sa, sb;
      if (B.x >= A.x + A.w + 16) { sa = "r"; sb = "l"; }
      else if (B.x + B.w + 16 <= A.x) { sa = "l"; sb = "r"; }
      else if (cy(B) >= cy(A)) { sa = "b"; sb = "t"; }
      else { sa = "t"; sb = "b"; }
      items.push({i, e, a, A, B, sa, sb});
    });
    const sides = {};
    for (const it of items) {
      (sides[`${it.e.from}|${it.sa}`] ||= []).push([it, "a"]);
      (sides[`${it.e.to}|${it.sb}`] ||= []).push([it, "b"]);
    }
    for (const [key, list] of Object.entries(sides)) {
      const side = key.split("|").pop(), vert = side === "l" || side === "r";
      const other = ([it, end]) => end === "a" ? it.B : it.A;
      list.sort((p, q) => vert ? cy(other(p)) - cy(other(q)) : cx(other(p)) - cx(other(q)));
      list.forEach(([it, end], k) => {
        const f = (k + 1) / (list.length + 1), R = end === "a" ? it.A : it.B;
        const pt = side === "r" ? {x: R.x + R.w, y: R.y + R.h * f} : side === "l" ? {x: R.x, y: R.y + R.h * f}
          : side === "b" ? {x: R.x + R.w * f, y: R.y + R.h} : {x: R.x + R.w * f, y: R.y};
        it[end === "a" ? "pa" : "pb"] = pt;
      });
    }
    // vertical runs that share a gap between lanes sit side by side
    const gaps = {};
    for (const it of items) if (it.sa === "r" || it.sa === "l") (gaps[Math.round((it.pa.x + it.pb.x) / 80)] ||= []).push(it);
    for (const list of Object.values(gaps)) {
      list.sort((p, q) => p.pa.y - q.pa.y);
      list.forEach((it, k) => { it.mx = (it.pa.x + it.pb.x) / 2 + (k - (list.length - 1) / 2) * Math.min(7, 40 / list.length); });
    }
    const dir = {r: [1, 0], l: [-1, 0], b: [0, 1], t: [0, -1]};
    for (const it of items) {
      const {pa, pb} = it;
      if (smooth) {
        const c = Math.max(40, Math.hypot(pb.x - pa.x, pb.y - pa.y) / 3);
        const c1 = {x: pa.x + dir[it.sa][0] * c, y: pa.y + dir[it.sa][1] * c}, c2 = {x: pb.x + dir[it.sb][0] * c, y: pb.y + dir[it.sb][1] * c};
        it.d = `M${pa.x} ${pa.y}C${c1.x} ${c1.y} ${c2.x} ${c2.y} ${pb.x} ${pb.y}`;
        it.lx = (pa.x + 3 * c1.x + 3 * c2.x + pb.x) / 8; it.ly = (pa.y + 3 * c1.y + 3 * c2.y + pb.y) / 8 - 4;
      } else if (it.sa === "r" || it.sa === "l") {
        it.d = Math.abs(pa.y - pb.y) < 1 ? `M${pa.x} ${pa.y}H${pb.x}` : `M${pa.x} ${pa.y}H${it.mx}V${pb.y}H${pb.x}`;
        it.lx = it.mx; it.ly = (pa.y + pb.y) / 2;
      } else {
        const my = (pa.y + pb.y) / 2;
        it.d = Math.abs(pa.x - pb.x) < 1 ? `M${pa.x} ${pa.y}V${pb.y}` : `M${pa.x} ${pa.y}V${my}H${pb.x}V${pb.y}`;
        it.lx = (pa.x + pb.x) / 2; it.ly = my - 4;
      }
    }
    return items;
  }

  // ---- drawing
  function extent(boxes) {
    const all = [...Object.values(boxes), ...S.notes.map(noteBox)];
    const x0 = Math.min(0, ...all.map(b => b.x)), y0 = Math.min(0, ...all.map(b => b.y));
    const x1 = Math.max(LEFT + D.lanes.length * LW - (LW - NW), ...all.map(b => b.x + b.w));
    const y1 = Math.max(400, ...all.map(b => b.y + b.h));
    return {x: x0 - 20, y: y0 - 10, w: x1 - x0 + 40, h: y1 - y0 + 40};
  }
  function render() {
    const boxes = Object.fromEntries(S.nodes.map(n => [n.id, nodeBox(n)]));
    const ext = extent(boxes), m = (LW - NW) / 2;
    const out = [`<defs>${["", "public", "owner", "guest", "sel"].map(k =>
      `<marker id="df-m${k ? "-" + k : ""}" class="m-${k || "def"}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker>`).join("")}</defs>`];
    out.push('<g class="lanes">');
    D.lanes.forEach((l, i) => {
      const x = LEFT - m + i * LW + 6;
      out.push(`<g class="lane"><rect x="${x}" y="${ext.y + 4}" width="${LW - 12}" height="${ext.h - 8}" rx="14"/><text x="${x + 14}" y="${Math.max(ext.y + 30, 40)}">${esc(l.label)}</text></g>`);
    });
    out.push('</g><g class="edges">');
    for (const it of routes(boxes)) {
      const k = it.a.kind, isSel = sel && sel.type === "edge" && sel.i === it.i;
      const cls = ["public", "owner", "guest"].includes(k) ? ` e-${k}` : "";
      const mk = isSel ? "df-m-sel" : cls ? `df-m-${k}` : "df-m";
      out.push(`<g class="edge${cls}${isSel ? " sel" : ""}" data-edge="${it.i}"><path class="hit" d="${it.d}"/><path class="line" d="${it.d}" marker-end="url(#${mk})"/>` +
        (it.e.label ? `<text x="${it.lx}" y="${it.ly}" text-anchor="middle">${esc(it.e.label)}</text>` : "") + "</g>");
    }
    out.push('</g><g class="nodes">');
    for (const n of S.nodes) {
      const b = boxes[n.id], tag = tagOf(n), isSel = sel && sel.type === "node" && sel.id === n.id;
      const cls = `node k-${esc(n.kind)}${n.gate ? " gate" : ""}${n.status === "planned" ? " planned" : ""}${isSel ? " sel" : ""}`;
      let y = 12;
      const parts = [`<rect class="box" width="${b.w}" height="${b.h}" rx="10"/>`];
      if (tag) { parts.push(`<text class="tag" x="10" y="${y + 4}">${tag}</text>`); y += 13; }
      b.lines.forEach((ln, k) => parts.push(`<text x="10" y="${y + 12 + k * 15}" font-weight="600">${esc(ln)}</text>`));
      y += 12 + b.lines.length * 15;
      if (n.note) parts.push(`<text class="notemark" x="10" y="${y + 2}">✎ ${esc(n.note.slice(0, 30))}${n.note.length > 30 ? "…" : ""}</text>`);
      parts.push(`<circle class="handle-hit" data-handle="${esc(n.id)}" cx="${b.w}" cy="${b.h / 2}" r="16"/><circle class="handle" cx="${b.w}" cy="${b.h / 2}" r="6"/>`);
      out.push(`<g class="${cls}" data-node="${esc(n.id)}" transform="translate(${n.x},${n.y})"><title>${esc(n.desc || n.label)}</title>${parts.join("")}</g>`);
    }
    out.push('</g><g class="notes">');
    for (const t of S.notes) {
      const b = noteBox(t), isSel = sel && sel.type === "note" && sel.id === t.id;
      out.push(`<g class="note${isSel ? " sel" : ""}" data-note="${esc(t.id)}" transform="translate(${t.x},${t.y})"><rect class="paper" width="${b.w}" height="${b.h}" rx="4"/>` +
        b.lines.map((ln, k) => `<text x="9" y="${18 + k * 15}">${esc(ln)}</text>`).join("") + "</g>");
    }
    out.push('</g><path class="temp" id="df-temp" d=""/>');
    svg.innerHTML = out.join("");
    $("#df-edit").disabled = $("#df-delete").disabled = !sel;
    showInfo();
  }
  // tap a box: what it is, what falls under it (Sources) and where it lives
  function showInfo() {
    const box = $("#df-info"), n = sel && sel.type === "node" ? byId()[sel.id] : null;
    if (!n) { box.hidden = true; box.innerHTML = ""; return; }
    const f = fileNode[n.id] || {}, inc = f.includes || [];
    const where = f.link ? (f.link.startsWith("/") ? ` · <a href="${esc(f.link)}">Open the page</a>` : ` · <code>${esc(f.link)}</code>`) : "";
    box.innerHTML = `<b>${esc(n.label)}</b> <span class="muted">· ${esc(D.kinds[n.kind] || n.kind)}${f.gate ? " · review gate" : ""}${f.status === "planned" ? " · planned" : ""}</span><br>` +
      `${esc(f.desc || "Your own step.")}${where}` + (inc.length ? `<ul>${inc.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "") +
      (n.note ? `<p class="df-info-note">Your note: ${esc(n.note)}</p>` : "");
    box.hidden = false;
  }

  // ---- view: zoom and pan inside the frame (the page never scrolls sideways)
  function applyView() {
    const r = svg.getBoundingClientRect(), aspect = (r.height || 1) / (r.width || 1);
    view.h = view.w * aspect;
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
    svg.setAttribute("preserveAspectRatio", "none");
  }
  function fit() {
    const e = extent(Object.fromEntries(S.nodes.map(n => [n.id, nodeBox(n)])));
    const r = svg.getBoundingClientRect(), aspect = (r.height || 1) / (r.width || 1);
    const w = Math.max(e.w, e.h / aspect);
    view = {x: e.x, y: e.y, w, h: w * aspect};
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
      render();
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
      $("#df-d-info").innerHTML = (f && f.desc ? esc(f.desc) : "Your own step.") + (f && f.link ? ` · ${f.link.startsWith("/") ? `<a href="${esc(f.link)}">Open the page</a>` : `<code>${esc(f.link)}</code>`}` : "");
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
    const c = center(), n = {id: newId("n"), label: "New step", kind: "step", note: "", x: Math.round(c.x - NW / 2), y: Math.round(c.y - 25)};
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
    const e = extent(Object.fromEntries(S.nodes.map(n => [n.id, nodeBox(n)])));
    const want = e.h * frame.clientWidth / e.w + 4;
    if (want < frame.clientHeight) frame.style.height = `${Math.max(360, Math.round(want))}px`;
  })();
  fit();
  new ResizeObserver(() => { if (view) applyView(); }).observe(frame);
})();
