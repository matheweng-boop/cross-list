// Block-diagram generator. A diagram is groups (dotted frames on a grid) holding blocks; each block is a
// system function that a Skyworks part in Cross List may fill. State (saved as JSON):
//   groups: [{id, label, col, row, w, blocks: [{id, fn, label, qty, part}]}]
//   links:  [[fromGroup, toGroup, label]]
(() => {
  const root = document.getElementById("bk");
  if (!root) return;
  const $ = s => root.querySelector(s);
  const J = id => JSON.parse(document.getElementById(id).textContent);
  const CAT = J("bk-catalogue"), design = J("bk-design"), tpl = J("bk-template"), REQ = J("bk-reqdata");
  let COUNTS = J("bk-counts");
  const FN = CAT.functions, CATS = CAT.categories;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  let seq = 1;
  const uid = p => `${p}${Date.now().toString(36)}${seq++}`;
  let S = design.data || fromTemplate(tpl) || {groups: [], links: []};
  S.req ||= {}; // requirement answers per function: {fn: {reqId: value}}; unanswered = no filter
  S.qa ||= {}; // answers to the template's design questions: {questionId: choice}; unanswered = nothing assumed
  let sel = null; // {group} or {group, block}
  let dirty = false;
  let configId = design.id;

  function fromTemplate(t) {
    if (!t) return null;
    const groups = t.groups.map(g => ({
      id: g.id, label: g.label, col: g.col || 0, row: g.row || 0, w: g.w || 1,
      blocks: (g.blocks || []).map(b => {
        if (typeof b === "object") return {id: uid("b"), fn: b.fn, label: b.label || "", qty: b.qty || 1, part: null};
        const [fn, q] = b.split(/\s+x/);
        return {id: uid("b"), fn, label: "", qty: q ? +q : 1, part: null};
      }),
    }));
    return {groups, links: (t.links || []).map(l => [...l]), questions: t.questions || [], sources: t.sources || []};
  }

  // ---- block status
  const fnOf = b => FN[b.fn] || {label: b.fn};
  function status(b) {
    if (b.part) return "part";
    const n = COUNTS[b.fn];
    return n === null ? "ext" : n ? "have" : "opp";
  }
  const STATUS_TEXT = {part: "Part chosen", have: "Skyworks / Qorvo parts fit", opp: "Opportunity: no Skyworks or Qorvo part in Cross List yet", ext: "Customer part"};

  // ---- layout
  const CELL = 250, GAP_X = 40, GAP_Y = 36, BW = 112, BH = 46, BG = 8, HEAD = 26, PAD = 9;
  function layout() {
    const rects = {};
    const rowH = {};
    for (const g of S.groups) {
      const w = (g.w || 1) * CELL + ((g.w || 1) - 1) * GAP_X;
      const cols = Math.max(1, Math.floor((w - 2 * PAD + BG) / (BW + BG)));
      const rows = Math.max(1, Math.ceil(g.blocks.length / cols));
      const h = HEAD + rows * (BH + BG) + PAD;
      rects[g.id] = {w, h, cols};
      rowH[g.row] = Math.max(rowH[g.row] || 0, h);
    }
    const rowsSorted = Object.keys(rowH).map(Number).sort((a, b) => a - b);
    const rowY = {};
    let y = 20;
    for (const r of rowsSorted) { rowY[r] = y; y += rowH[r] + GAP_Y; }
    let W = 600;
    for (const g of S.groups) {
      const r = rects[g.id];
      r.x = 20 + g.col * (CELL + GAP_X);
      r.y = rowY[g.row];
      W = Math.max(W, r.x + r.w + 20);
    }
    return {rects, W, H: Math.max(260, y)};
  }

  // point on the edge of rect a towards rect b
  function edge(a, b) {
    const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
    const dx = bx - ax, dy = by - ay;
    const s = Math.min(Math.abs((a.w / 2) / (dx || 1e-6)), Math.abs((a.h / 2) / (dy || 1e-6)));
    return {x: ax + dx * s, y: ay + dy * s};
  }

  function render() {
    const L = layout(), parts = [];
    parts.push(`<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#3a3f47"/></marker></defs>`);
    for (const [a, b, label] of S.links) {
      const ra = L.rects[a], rb = L.rects[b];
      if (!ra || !rb) continue;
      const p = edge(ra, rb), q = edge(rb, ra);
      parts.push(`<line class="link" x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}"/>`);
      if (label) parts.push(`<text class="link-label" x="${(p.x + q.x) / 2}" y="${(p.y + q.y) / 2 - 4}" text-anchor="middle">${esc(label)}</text>`);
    }
    for (const g of S.groups) {
      const r = L.rects[g.id];
      parts.push(`<g class="grp${sel && sel.group === g.id && !sel.block ? " sel" : ""}"><rect class="frame" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="4"/>` +
        `<text class="grp-title" data-group="${g.id}" x="${r.x + 8}" y="${r.y + 17}" tabindex="0" role="button">${esc(g.label)}</text>`);
      g.blocks.forEach((b, i) => {
        const cx = r.x + PAD + (i % r.cols) * (BW + BG), cy = r.y + HEAD + Math.floor(i / r.cols) * (BH + BG);
        const st = status(b), f = fnOf(b);
        const label = b.label || f.label;
        const sub = b.part || (st === "have" ? `${COUNTS[b.fn]} parts` : st === "opp" ? "opportunity" : st === "ext" ? "customer part" : "");
        parts.push(`<g class="blk st-${st}${sel && sel.block === b.id ? " sel" : ""}" data-group="${g.id}" data-block="${b.id}" tabindex="0" role="button" aria-label="${esc(label)}">` +
          `<rect x="${cx}" y="${cy}" width="${BW}" height="${BH}"/>` +
          wrap(label, 16).slice(0, 2).map((t, k) => `<text class="b-label" x="${cx + BW / 2}" y="${cy + 15 + k * 13}" text-anchor="middle">${esc(t)}</text>`).join("") +
          `<text class="b-sub" x="${cx + BW / 2}" y="${cy + BH - 5}" text-anchor="middle">${esc(sub.slice(0, 19))}${b.qty > 1 ? ` ×${b.qty}` : ""}</text></g>`);
      });
      parts.push(`</g>`);
    }
    if (!S.groups.length) parts.push(`<text x="40" y="80" fill="#888" font-size="14">Add a group, then add functions to it.</text>`);
    const svg = $("#bk-svg");
    lastL = L;
    svg.innerHTML = parts.join("");
    applyView();
    renderSummary();
  }
  const wrap = (s, n) => {
    const out = [];
    let line = "";
    for (const w of String(s).split(" ")) {
      if ((line + " " + w).trim().length > n && line) { out.push(line); line = w; } else line = (line + " " + w).trim();
    }
    if (line) out.push(line);
    return out;
  };

  // ---- magnifier: fit the window, zoom in / out, drag to pan
  let lastL = null, view = null;
  function applyView() {
    const svg = $("#bk-svg"), L = lastL;
    if (!L) return;
    const v = view || {x: 0, y: 0, w: L.W, h: L.H};
    svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
    const cw = $(".bc-canvas").clientWidth || 900;
    svg.setAttribute("width", cw);
    svg.setAttribute("height", Math.min(window.innerHeight * 0.8, cw * v.h / v.w));
    svg.setAttribute("preserveAspectRatio", "xMidYMin meet");
  }
  function zoomBy(f) {
    const L = lastL, v = view || {x: 0, y: 0, w: L.W, h: L.H};
    const w = Math.min(L.W * 1.2, Math.max(260, v.w * f)), h = v.h * (w / v.w);
    view = {x: v.x + (v.w - w) / 2, y: v.y + (v.h - h) / 2, w, h};
    applyView();
  }
  $("#bk-zoom-in").onclick = () => zoomBy(0.7);
  $("#bk-zoom-out").onclick = () => zoomBy(1.4);
  $("#bk-zoom-all").onclick = () => { view = null; applyView(); };
  (() => {
    const svg = $("#bk-svg");
    let drag = null;
    svg.addEventListener("pointerdown", e => {
      if (!view || e.target.closest("[data-block], [data-group]")) return;
      drag = {x: e.clientX, y: e.clientY, v: {...view}, s: view.w / svg.clientWidth};
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", e => { if (drag) { view = {...drag.v, x: drag.v.x - (e.clientX - drag.x) * drag.s, y: drag.v.y - (e.clientY - drag.y) * drag.s}; applyView(); } });
    svg.addEventListener("pointerup", () => (drag = null));
  })();
  // the side panel is a drawer that opens on a selection
  const openPanel = () => root.classList.add("panel-open");
  $("#bk-close").onclick = () => { root.classList.remove("panel-open"); sel = null; render(); };

  // ---- summary: Skyworks content vs opportunities
  function renderSummary() {
    const all = S.groups.flatMap(g => g.blocks);
    const by = {part: 0, have: 0, opp: 0, ext: 0};
    all.forEach(b => (by[status(b)] += b.qty || 1));
    const opp = {}, chosen = [];
    all.forEach(b => { if (status(b) === "opp") opp[fnOf(b).label] = (opp[fnOf(b).label] || 0) + (b.qty || 1); if (b.part) chosen.push(`${b.part}${b.qty > 1 ? ` ×${b.qty}` : ""}`); });
    $("#bk-summary").innerHTML = `<div class="tiles">
        <div class="tile"><b>${by.part}</b>parts chosen</div><div class="tile"><b>${by.have}</b>blocks Skyworks / Qorvo can fill</div>
        <div class="tile"><b>${by.opp}</b>opportunities</div><div class="tile"><b>${by.ext}</b>customer parts</div></div>` +
      (chosen.length ? `<p><b>Skyworks bill of materials:</b> ${esc(chosen.join(", "))}</p>` : "") +
      (Object.keys(opp).length ? `<p><b>Opportunities</b> (no Skyworks or Qorvo part in Cross List yet): ${Object.entries(opp).map(([k, n]) => `${esc(k)}${n > 1 ? ` ×${n}` : ""}`).join(" · ")}</p>` : "");
  }

  // ---- side panel
  const panel = $("#bk-panel-body");
  const group = id => S.groups.find(g => g.id === id);
  const blockOf = (g, id) => g && g.blocks.find(b => b.id === id);
  const partsCache = {};
  async function parts(fn, q = "") {
    const req = JSON.stringify(S.req[fn] || {});
    const key = `${fn}|${q}|${req}`;
    if (!partsCache[key]) partsCache[key] = fetch(`/api/blocks/parts?fn=${encodeURIComponent(fn)}&q=${encodeURIComponent(q)}&req=${encodeURIComponent(req)}`).then(r => r.json());
    return partsCache[key];
  }
  async function refreshCounts() {
    const res = await fetch("/api/blocks/counts", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({req: S.req})});
    if (res.ok) COUNTS = await res.json();
    render();
  }
  // requirement questions of a function as form controls; nothing is pre-selected
  function reqControls(fn) {
    const ans = S.req[fn] || {};
    return (REQ[fn] || []).map(r => r.choices
      ? `<label class="small req-row">${esc(r.label)} <select data-req="${fn}|${r.id}"><option value="">any</option>${r.choices.map(c => `<option value="${esc(c)}"${String(ans[r.id] ?? "") === String(c) ? " selected" : ""}>${esc(c)}</option>`).join("")}</select></label>`
      : `<label class="small req-row"><input type="checkbox" data-req="${fn}|${r.id}"${ans[r.id] ? " checked" : ""}> ${esc(r.label)}</label>`).join("");
  }
  function bindReq(box, after) {
    box.querySelectorAll("[data-req]").forEach(el => (el.onchange = async () => {
      const [fn, rid] = el.dataset.req.split("|");
      const a = (S.req[fn] ||= {});
      const v = el.type === "checkbox" ? el.checked : el.value;
      if (v === "" || v === false) delete a[rid]; else a[rid] = v;
      if (!Object.keys(a).length) delete S.req[fn];
      dirty = true;
      $("#bk-status").textContent = "Unsaved changes";
      await refreshCounts();
      if (after) after();
    }));
  }

  function showBlock(g, b) {
    openPanel();
    const f = fnOf(b), st = status(b);
    const comp = (f.companions || []).filter(c => FN[c]);
    panel.innerHTML = `<h3>${esc(b.label || f.label)}</h3>
      <p class="small"><span class="lg lg-${st}">${esc(STATUS_TEXT[st])}</span> · ${esc(CATS[f.category] || f.category || "")}</p>
      ${f.note ? `<p class="small muted">${esc(f.note)}</p>` : ""}
      ${b.part ? `<p>Chosen: <b>${esc(b.part)}</b> <button type="button" class="outline secondary small-btn" data-act="unpick">clear</button></p>` : ""}
      <div class="row"><label class="small">Label <input data-f="label" value="${esc(b.label || "")}" placeholder="${esc(f.label)}"></label>
        <label class="small">Qty <input data-f="qty" type="number" min="1" max="99" value="${b.qty || 1}" style="width:4rem"></label></div>
      ${(REQ[b.fn] || []).length ? `<details class="req-box"${Object.keys(S.req[b.fn] || {}).length ? " open" : ""}><summary class="small"><b>Requirements</b> (narrow the parts; nothing is assumed)</summary>${reqControls(b.fn)}</details>` : ""}
      <div id="bk-parts"></div>
      ${comp.length ? `<p class="small"><b>Usually designed in with it</b></p><div class="row">${comp.map(c => `<button type="button" class="bc-chip bc-chip-sm" data-add="${c}" title="${esc(STATUS_TEXT[COUNTS[c] === null ? "ext" : COUNTS[c] ? "have" : "opp"])}">+ ${esc(FN[c].label)}</button>`).join("")}</div>` : ""}
      <div class="row"><button type="button" class="outline secondary small-btn" data-act="remove">Remove block</button>
        <select data-act="move" class="small-sel" aria-label="Move to group"><option value="">Move to…</option>${S.groups.filter(x => x !== g).map(x => `<option value="${x.id}">${esc(x.label)}</option>`).join("")}</select></div>`;
    if (st !== "ext" && COUNTS[b.fn]) {
      const box = panel.querySelector("#bk-parts");
      const draw = async q => {
        const r = await parts(b.fn, q);
        const li = p => `<li><span><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.mpn)}</a>${p.risk ? ' <small class="worse">NRND / obsolete</small>' : ""}<br><small class="muted">${esc(p.detail)}</small></span><button type="button" class="outline small-btn" data-pick="${esc(p.mpn)}">use</button></li>`;
        box.innerHTML = `<p class="small"><b>Parts that fit</b> (${r.total}${Object.keys(S.req[b.fn] || {}).length ? " meeting the requirements" : ""})</p>
          <input type="search" placeholder="Filter parts" value="${esc(q)}" aria-label="Filter parts" data-q>` +
          (r.manufacturers.length ? r.manufacturers.map(m => `<p class="small bk-mfr"><b>${esc(m.manufacturer)}</b> · best ${m.best.length} of ${m.total}</p>
            <ul class="bk-parts">${m.best.map(li).join("")}</ul>
            ${m.total > m.best.length ? `<details><summary class="small">All ${m.total} ${esc(m.manufacturer)} parts</summary><ul class="bk-parts">${m.all.map(li).join("")}</ul></details>` : ""}`).join("")
            : `<p class="small uc-error">No part meets these requirements. Untick one, or record the gap as feedback.</p>`);
        const inp = box.querySelector("[data-q]");
        inp.oninput = () => { clearTimeout(inp._t); inp._t = setTimeout(() => draw(inp.value), 250); };
        box.querySelectorAll("[data-pick]").forEach(btn => (btn.onclick = () => { b.part = btn.dataset.pick; changed(); showBlock(g, b); }));
      };
      draw("");
    } else if (st === "opp") {
      panel.querySelector("#bk-parts").innerHTML = `<p class="small">No Skyworks part for this function is in Cross List. This can be a gap in the portfolio or a product family not imported yet (full portfolio import is on the backlog).
        <a href="/requests">Add a request</a> if a specific part should be crossed.</p>`;
    }
    bindReq(panel, () => showBlock(g, b));
    panel.querySelectorAll("[data-f]").forEach(el => (el.onchange = () => { b[el.dataset.f] = el.dataset.f === "qty" ? Math.max(1, +el.value || 1) : el.value; changed(); }));
    panel.querySelector('[data-act="remove"]').onclick = () => { g.blocks = g.blocks.filter(x => x !== b); sel = {group: g.id}; changed(); showGroup(g); };
    panel.querySelector('[data-act="unpick"]')?.addEventListener("click", () => { b.part = null; changed(); showBlock(g, b); });
    panel.querySelector('[data-act="move"]').onchange = e => { const to = group(e.target.value); if (!to) return; g.blocks = g.blocks.filter(x => x !== b); to.blocks.push(b); sel = {group: to.id, block: b.id}; changed(); showBlock(to, b); };
    panel.querySelectorAll("[data-add]").forEach(btn => (btn.onclick = () => addFunction(btn.dataset.add, g)));
  }

  function showGroup(g) {
    openPanel();
    const others = S.groups.filter(x => x !== g);
    const links = S.links.map((l, i) => [l, i]).filter(([l]) => l[0] === g.id || l[1] === g.id);
    panel.innerHTML = `<h3>${esc(g.label)}</h3>
      <div class="row"><label class="small">Name <input data-g="label" value="${esc(g.label)}"></label></div>
      <div class="row small">Move <button type="button" class="outline small-btn" data-mv="-1,0" aria-label="Left">←</button><button type="button" class="outline small-btn" data-mv="1,0" aria-label="Right">→</button>
        <button type="button" class="outline small-btn" data-mv="0,-1" aria-label="Up">↑</button><button type="button" class="outline small-btn" data-mv="0,1" aria-label="Down">↓</button>
        Width <button type="button" class="outline small-btn" data-w="-1" aria-label="Narrower">−</button><button type="button" class="outline small-btn" data-w="1" aria-label="Wider">+</button></div>
      <p class="small"><b>Connections</b></p>
      <ul>${links.map(([l, i]) => `<li class="small">${esc(group(l[0])?.label)} → ${esc(group(l[1])?.label)} ${l[2] ? `(${esc(l[2])})` : ""} <button type="button" class="outline secondary small-btn" data-unlink="${i}">×</button></li>`).join("") || `<li class="small muted">none</li>`}</ul>
      <div class="row"><select data-link class="small-sel" aria-label="Connect to group"><option value="">Connect to…</option>${others.map(x => `<option value="${x.id}">${esc(x.label)}</option>`).join("")}</select>
        <input data-link-label placeholder="label, e.g. SPI" style="width:8rem"></div>
      <p class="small">Add a function to this group with “+ Function” above while the group is selected.</p>
      <div class="row"><button type="button" class="outline secondary small-btn" data-act="delgroup">Delete group</button></div>`;
    panel.querySelector('[data-g="label"]').onchange = e => { g.label = e.target.value || g.label; changed(); };
    panel.querySelectorAll("[data-mv]").forEach(btn => (btn.onclick = () => { const [dx, dy] = btn.dataset.mv.split(",").map(Number); g.col = Math.max(0, g.col + dx); g.row = Math.max(0, g.row + dy); changed(); }));
    panel.querySelectorAll("[data-w]").forEach(btn => (btn.onclick = () => { g.w = Math.min(4, Math.max(1, (g.w || 1) + +btn.dataset.w)); changed(); }));
    panel.querySelectorAll("[data-unlink]").forEach(btn => (btn.onclick = () => { S.links.splice(+btn.dataset.unlink, 1); changed(); showGroup(g); }));
    panel.querySelector("[data-link]").onchange = e => { if (!e.target.value) return; S.links.push([g.id, e.target.value, panel.querySelector("[data-link-label]").value]); changed(); showGroup(g); };
    panel.querySelector('[data-act="delgroup"]').onclick = () => {
      if (g.blocks.length && !confirm(`Delete "${g.label}" and its ${g.blocks.length} blocks?`)) return;
      S.groups = S.groups.filter(x => x !== g); S.links = S.links.filter(l => l[0] !== g.id && l[1] !== g.id); sel = null; changed();
      panel.innerHTML = `<p class="small muted">Group deleted.</p>`;
    };
  }

  // design questions of the template: an answer narrows parts only where it maps to a function requirement
  // (question.sets); otherwise it is recorded with the design. Nothing is pre-answered.
  const filterLabel = q => (q.sets || []).map(st => FN[st.fn]?.label).filter(Boolean);
  function questionControls() {
    const qs = S.questions || [];
    if (!qs.length) return "";
    const n = Object.keys(S.qa).length;
    return `<details class="req-box" open><summary class="small"><b>Design questions</b> <span class="muted">· ${n} of ${qs.length} answered</span></summary>
      <p class="small muted">From the reference documents below. <span class="lg lg-have">narrows</span> = the answer filters parts; <span class="lg lg-ext">recorded</span> = kept with the design (no matching parameter in Cross List yet).</p>
      ${qs.map(q => {
        const fl = filterLabel(q);
        return `<label class="small req-row" title="${esc(q.source || "")}">${esc(q.question)}
          <select data-q="${esc(q.id)}"><option value="">not decided</option>${q.choices.map(c => `<option value="${esc(c)}"${S.qa[q.id] === String(c) ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>
          <span class="lg ${fl.length ? "lg-have" : "lg-ext"}" title="${esc(fl.length ? "Narrows: " + fl.join(", ") : "Recorded only")}">${fl.length ? "narrows" : "recorded"}</span></label>`;
      }).join("")}
      ${(S.sources || []).length ? `<p class="small muted">Sources: ${S.sources.map(d => `<a href="${esc(d.url)}" target="_blank" rel="noopener" title="${esc(d.title)}">${esc(d.doc)}</a>`).join(", ")} (TI, public)</p>` : ""}
    </details>`;
  }
  function applyQuestion(q, choice) {
    for (const st of q.sets || []) {
      const a = (S.req[st.fn] ||= {});
      const before = S.qa[q.id] !== undefined ? st.map[S.qa[q.id]] : undefined;
      if (before !== undefined && String(a[st.req]) === String(before)) delete a[st.req];
      const v = choice ? st.map[choice] : undefined;
      if (v !== undefined) a[st.req] = v;
      if (!Object.keys(a).length) delete S.req[st.fn];
    }
    if (choice) S.qa[q.id] = choice; else delete S.qa[q.id];
  }
  function bindQuestions(box, after) {
    box.querySelectorAll("[data-q]").forEach(el => (el.onchange = async () => {
      const q = (S.questions || []).find(x => x.id === el.dataset.q);
      if (!q) return;
      applyQuestion(q, el.value);
      dirty = true;
      $("#bk-status").textContent = "Unsaved changes";
      await refreshCounts();
      if (after) after();
    }));
  }

  // all requirement questions of the functions in the diagram, one place
  function showRequirements() {
    openPanel();
    const fns = [...new Set(S.groups.flatMap(g => g.blocks.map(b => b.fn)))].filter(fn => (REQ[fn] || []).length);
    panel.innerHTML = `<h3>Requirements</h3><p class="small muted">Answer only what the design needs; unanswered questions do not filter. Each answer narrows the parts for every block of that function.</p>` +
      questionControls() + (fns.length ? `<p class="small"><b>Per function</b></p>` : "") +
      (fns.length ? fns.map(fn => `<details class="req-box"${Object.keys(S.req[fn] || {}).length ? " open" : ""}><summary class="small"><b>${esc(FN[fn].label)}</b> <span class="muted">· ${COUNTS[fn] ?? "–"} parts fit</span></summary>${reqControls(fn)}</details>`).join("")
        : `<p class="small muted">No block in this diagram has requirement questions yet (they come with functions that have parts in Cross List).</p>`);
    bindReq(panel, showRequirements);
    bindQuestions(panel, showRequirements);
  }
  $("#bk-req").onclick = showRequirements;

  // feedback on the diagram or the selected block / group, kept for discussion
  async function showFeedback() {
    openPanel();
    const g = sel && group(sel.group), b = g && sel.block && blockOf(g, sel.block);
    const target = b ? `${g.label} / ${b.label || fnOf(b).label}` : g ? g.label : "";
    const list = configId ? await (await fetch(`/api/blocks/feedback?diagram_id=${configId}`)).json() : [];
    panel.innerHTML = `<h3>Feedback</h3><p class="small muted">Saved for discussion; nothing in the diagram or the templates changes until we agree on it. All feedback: <a href="/blocks/feedback">Block diagrams → Feedback</a>.</p>
      <label class="small">About <input data-fb-target value="${esc(target)}" placeholder="whole diagram"></label>
      <textarea data-fb-msg rows="4" placeholder="e.g. traction inverter needs an isolated temperature sensing block; Si823x lacks DESAT"></textarea>
      <div class="row"><button type="button" class="small-btn" data-fb-save>Save feedback</button><span class="small muted" data-fb-st></span></div>
      ${list.length ? `<p class="small"><b>On this diagram</b></p><ul>${list.map(f => `<li class="small">[${esc(f.status)}] ${f.target ? `<b>${esc(f.target)}</b>: ` : ""}${esc(f.message)} <span class="muted">${esc(f.created)}</span></li>`).join("")}</ul>` : ""}`;
    panel.querySelector("[data-fb-save]").onclick = async () => {
      const msg = panel.querySelector("[data-fb-msg]").value.trim();
      if (!msg) return;
      const res = await fetch("/api/blocks/feedback", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({diagram_id: configId, diagram_name: $("#bk-name").value || (tpl && tpl.name) || "", target: panel.querySelector("[data-fb-target]").value, message: msg})});
      panel.querySelector("[data-fb-st]").textContent = res.ok ? "Saved" : `Not saved (${res.status})`;
      if (res.ok) setTimeout(showFeedback, 400);
    };
  }
  $("#bk-feedback").onclick = showFeedback;

  // add a function to a group (the selected one, or a group for its category)
  function addFunction(fn, g) {
    const f = FN[fn];
    if (!f) return;
    g ||= sel && group(sel.group);
    if (!g) {
      g = S.groups.find(x => x.label === (CATS[f.category] || f.category));
      if (!g) {
        const maxRow = Math.max(-1, ...S.groups.map(x => x.row));
        const inRow = S.groups.filter(x => x.row === maxRow).length;
        g = {id: uid("g"), label: CATS[f.category] || f.category, col: inRow < 5 && maxRow >= 0 ? Math.max(...S.groups.filter(x => x.row === maxRow).map(x => x.col + (x.w || 1))) : 0, row: inRow < 5 && maxRow >= 0 ? maxRow : maxRow + 1, w: 1, blocks: []};
        S.groups.push(g);
      }
    }
    const b = {id: uid("b"), fn, label: "", qty: 1, part: null};
    g.blocks.push(b);
    sel = {group: g.id, block: b.id};
    changed();
    showBlock(g, b);
  }

  // ---- events
  $("#bk-svg").addEventListener("click", e => {
    const t = e.target.closest("[data-block], [data-group]");
    if (!t) return;
    const g = group(t.dataset.group);
    if (t.dataset.block) { const b = blockOf(g, t.dataset.block); sel = {group: g.id, block: b.id}; render(); showBlock(g, b); }
    else { sel = {group: g.id}; render(); showGroup(g); }
  });
  $("#bk-svg").addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.target.dispatchEvent(new MouseEvent("click", {bubbles: true})); } });
  $("#bk-add").addEventListener("change", e => { if (e.target.value) { addFunction(e.target.value); e.target.value = ""; } });
  $("#bk-add-group").addEventListener("click", () => {
    const name = prompt("Group name (e.g. Power rail, Timing, Networking)");
    if (!name) return;
    const maxRow = Math.max(0, ...S.groups.map(x => x.row));
    const col = Math.max(-1, ...S.groups.filter(x => x.row === maxRow).map(x => x.col + (x.w || 1) - 1)) + 1;
    const g = {id: uid("g"), label: name, col, row: maxRow, w: 1, blocks: []};
    S.groups.push(g);
    sel = {group: g.id};
    changed();
    showGroup(g);
  });
  window.addEventListener("resize", render);

  function changed() { dirty = true; $("#bk-status").textContent = "Unsaved changes"; render(); }
  $("#bk-name").value = design.name || "";
  $("#bk-name").addEventListener("input", () => { dirty = true; $("#bk-status").textContent = "Unsaved changes"; });
  $("#bk-save").addEventListener("click", async () => {
    const res = await fetch(configId ? `/api/blocks/designs/${configId}` : "/api/blocks/designs",
      {method: configId ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: $("#bk-name").value, data: S})});
    if (!res.ok) { $("#bk-status").textContent = `Not saved (${res.status})`; return; }
    const out = await res.json();
    if (!configId) { configId = out.id; history.replaceState(null, "", `/blocks/${configId}`); }
    dirty = false;
    $("#bk-status").textContent = "Saved";
  });
  window.addEventListener("beforeunload", e => { if (dirty) e.preventDefault(); });
  $("#bk-svg-dl").addEventListener("click", () => {
    const svg = $("#bk-svg").cloneNode(true);
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.insertAdjacentHTML("afterbegin", `<style>${document.getElementById("bk-svg-style").textContent}</style>`);
    const a = Object.assign(document.createElement("a"), {href: URL.createObjectURL(new Blob([svg.outerHTML], {type: "image/svg+xml"})), download: `${($("#bk-name").value || "block-diagram").replace(/[^\w.-]+/g, "_")}.svg`});
    a.click();
  });

  if (!design.data && tpl) dirty = true;
  if (Object.keys(S.req).length) refreshCounts(); else render();
  if (!design.data && (S.questions || []).length) showRequirements(); // a new diagram from a template opens on its questions
})();
