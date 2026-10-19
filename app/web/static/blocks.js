// Block-diagram generator. A diagram is groups (dotted frames on a grid) holding blocks; each block is a
// system function that a Skyworks part in Cross List may fill. State (saved as JSON):
//   groups: [{id, label, col, row, w, blocks: [{id, fn, label, qty, part}]}]
//   links:  [[fromGroup, toGroup, label]]
(() => {
  const root = document.getElementById("bk");
  if (!root) return;
  const $ = s => root.querySelector(s);
  const J = id => JSON.parse(document.getElementById(id).textContent);
  const CAT = J("bk-catalogue"), design = J("bk-design"), tpl = J("bk-template"), REQ = J("bk-reqdata"), HELP = J("bk-help");
  let COUNTS = J("bk-counts");
  const FN = CAT.functions, CATS = CAT.categories;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  let seq = 1;
  const uid = p => `${p}${Date.now().toString(36)}${seq++}`;
  let S = design.data || fromTemplate(tpl) || {groups: [], links: []};
  S.req ||= {}; // requirement answers per function: {fn: {reqId: value}}; unanswered = no filter
  S.qa ||= {}; // answers to the template's design questions: {questionId: choice}; unanswered = nothing assumed
  let sel = null; // {group} or {group, block}
  const DIM = new Set(["opp", "ext"]); // statuses greyed out in the diagram (legend buttons toggle them)
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
        parts.push(`<g class="blk st-${st}${DIM.has(st) ? " dim" : ""}${sel && sel.block === b.id ? " sel" : ""}" data-group="${g.id}" data-block="${b.id}" tabindex="0" role="button" aria-label="${esc(label)}">` +
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
    renderReqs();
    renderLegend();
    if (!(sel && sel.block)) renderBelow();
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

  // ---- legend: one button per status; a pressed button is highlighted, the others are greyed out
  function renderLegend() {
    root.querySelectorAll("[data-st]").forEach(b => b.setAttribute("aria-pressed", String(!DIM.has(b.dataset.st))));
  }
  root.querySelectorAll("[data-st]").forEach(b => (b.onclick = () => {
    const st = b.dataset.st;
    DIM.has(st) ? DIM.delete(st) : DIM.add(st);
    render();
  }));

  // a part as its full number and its features as coloured chips
  const chipKind = t => /NRND|obsolete|discontinued|no new designs/i.test(t) ? "risk" : /automotive|AEC/i.test(t) ? "auto"
    : /^(QFN|DFN|SOIC|SSOP|QSOP|LGA|BGA|MLPD|SOT|TSSOP|WLCSP|CSP|SC-?70|SSO|[A-Z]+-\d+)/i.test(t) || /\d+(\.\d+)?\s*[x×]\s*\d/.test(t) ? "pkg"
    : /(kVrms|GHz|MHz|\bA\b|\bV\b|Mbps|dB|ch\b|kV)/i.test(t) ? "spec" : /^(SP\dT|DPDT|\dP\dT|\d+\/\d+|S\dP\dT)/i.test(t) ? "cfg" : "other";
  const partRow = (p, pick) => `<li class="pt-row"><div class="pt-main"><a class="pt-mpn" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.mpn)}</a>${pick ? `<button type="button" class="outline small-btn" data-pick="${esc(p.mpn)}">use</button>` : ""}</div>
    ${(() => {
      const bits = String(p.detail || "").split(" · ").filter(Boolean).flatMap(t => (/^[A-Z0-9_]+( [A-Z0-9_]+)+$/.test(t) ? t.split(" ") : [t])), long = bits.filter(t => t.length > 40), short = bits.filter(t => t.length <= 40);
      return `<div class="pt-chips">${short.map(t => `<span class="pt-chip k-${chipKind(t)}">${esc(t)}</span>`).join("")}${p.risk ? '<span class="pt-chip k-risk">NRND / obsolete</span>' : ""}</div>` +
        long.map(t => `<div class="pt-desc small muted" title="${esc(t)}">${esc(t.length > 140 ? t.slice(0, 137) + "…" : t)}</div>`).join("");
    })()}${p.description ? `<div class="pt-text small" title="${esc(p.description)}">${esc(p.description.length > 220 ? p.description.slice(0, 217) + "…" : p.description)}</div>` : ""}
    ${p.why ? `<div class="pt-why small"><b>Why:</b> ${esc(p.why)}</div>` : ""}</li>`;

  // ---- below the diagram: the most likely parts per block (overview), or the clicked block in full
  const below = () => $("#bk-below");
  // Suggested parts load per block when its section is opened (light request: best picks only); nothing is
  // fetched up front, so large diagrams open fast. "More" fetches the full list for that block.
  function renderBelow() {
    const box = below();
    if (!box) return;
    const fns = [...new Set(S.groups.flatMap(g => g.blocks).filter(b => status(b) === "have" || status(b) === "part").map(b => b.fn))];
    if (!fns.length) { box.innerHTML = `<h3>Suggested parts</h3><p class="small muted">No block in this diagram has Skyworks or Qorvo parts in Cross List yet.</p>`; return; }
    const open = renderBelow.open || (renderBelow.open = new Set());
    box.innerHTML = `<h3>Suggested parts <span class="small muted">· open a block for its most likely parts per manufacturer, or click it in the diagram</span></h3>
      <div class="bk-sugg">${fns.map(fn => `<details class="bk-sugg-fn" data-fn="${fn}"${open.has(fn) ? " open" : ""}><summary class="small"><b>${esc(FN[fn].label)}</b> <span class="muted">· ${COUNTS[fn] ?? "–"} fit${Object.keys(S.req[fn] || {}).length ? " the requirements" : ""}</span></summary><div class="bk-sugg-body"></div></details>`).join("")}</div>`;
    box.querySelectorAll(".bk-sugg-fn").forEach(d => {
      const load = async () => {
        const body = d.querySelector(".bk-sugg-body");
        if (body.dataset.loaded === JSON.stringify(S.req[d.dataset.fn] || {})) return;
        body.innerHTML = `<p class="small muted" aria-live="polite">Loading…</p>`;
        let r;
        try { r = await parts(d.dataset.fn, "", true); } catch (e) { body.innerHTML = `<p class="small uc-error">Could not load the parts. <button type="button" class="link-btn" data-retry>Try again</button></p>`; body.querySelector("[data-retry]").onclick = () => { body.dataset.loaded = ""; load(); }; return; }
        body.dataset.loaded = JSON.stringify(S.req[d.dataset.fn] || {});
        const li = p => partRow(p, false);
        body.innerHTML = r.manufacturers.map(m => `<p class="small bk-mfr">${esc(m.manufacturer)}</p><ul class="bk-parts">${m.best.map(li).join("")}</ul>
          ${m.total > m.best.length ? `<details class="bk-more"><summary class="small">More ${esc(m.manufacturer)} (${m.total - m.best.length})</summary><ul class="bk-parts"><li class="small muted">Loading…</li></ul></details>` : ""}`).join("") || `<p class="small uc-error">None meets the requirements.</p>`;
        body.querySelectorAll(".bk-more").forEach((more, i) => more.addEventListener("toggle", async () => {
          if (!more.open || more.dataset.loaded) return;
          more.dataset.loaded = "1";
          const full = await parts(d.dataset.fn), m = full.manufacturers[i];
          more.querySelector("ul").innerHTML = m ? m.all.slice(m.best.length, 60).map(li).join("") : "";
        }));
      };
      d.addEventListener("toggle", () => { d.open ? (open.add(d.dataset.fn), load()) : open.delete(d.dataset.fn); });
      if (d.open) load();
    });
  }

  // ---- side panel
  const panel = $("#bk-panel-body");
  const group = id => S.groups.find(g => g.id === id);
  const blockOf = (g, id) => g && g.blocks.find(b => b.id === id);
  const partsCache = {};
  async function parts(fn, q = "", lite = false) {
    const req = JSON.stringify(S.req[fn] || {});
    const key = `${fn}|${q}|${req}|${lite ? 1 : 0}`;
    if (!partsCache[key]) partsCache[key] = fetch(`/api/blocks/parts?fn=${encodeURIComponent(fn)}&q=${encodeURIComponent(q)}&req=${encodeURIComponent(req)}${lite ? "&lite=1" : ""}`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch(e => { delete partsCache[key]; throw e; });
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

  // a chosen part constrains other blocks where the property is system-wide: automotive grade, reinforced
  // isolation, and the digital radio standard between tuner and demodulator. Only unanswered filters are set.
  function applyPick(fn, imp) {
    if (!imp) return [];
    const notes = [], inDiagram = [...new Set(S.groups.flatMap(g => g.blocks.map(x => x.fn)))].filter(f => f !== fn);
    const set = (f, rid, v, text) => {
      if (!(REQ[f] || []).some(x => x.id === rid)) return;
      const a = (S.req[f] ||= {});
      if (a[rid] !== undefined) { if (!Object.keys(a).length) delete S.req[f]; return; }
      a[rid] = v; notes.push(`${text} → ${FN[f].label}`);
    };
    const byParam = (param, value, text) => inDiagram.forEach(f => (FN[f].requirements || [])
      .filter(r => r.param === param && r.value === value).forEach(r => set(f, r.id, true, text)));
    if (imp.qualification === "automotive") byParam("qualification", "automotive", "automotive (AEC-Q100)");
    if (imp.isolation_class === "reinforced") byParam("isolation_class", "reinforced", "reinforced isolation");
    const digital = v => [].concat(v || []).filter(x => ["HD", "DAB", "DRM"].includes(x));
    if (fn === "am_fm_tuner" && inDiagram.includes("digital_radio_demod")) {
      const d = digital(imp.feature);
      if (d.length === 1) set("digital_radio_demod", "std", d[0], `${d[0]} demodulation`);
    }
    if (fn === "digital_radio_demod" && inDiagram.includes("am_fm_tuner"))
      digital(imp.decode).forEach(d => set("am_fm_tuner", d.toLowerCase(), true, `${d} tuner`));
    return notes;
  }

  function showBlock(g, b) {
    root.classList.remove("panel-open");
    const box = below();
    box.innerHTML = `<div class="bk-below-head"><button type="button" class="outline secondary small-btn" data-act="overview">← All blocks (deselect)</button></div><div class="bk-below-body"></div>`;
    box.querySelector('[data-act="overview"]').onclick = () => { sel = null; render(); };
    const panel = box.querySelector(".bk-below-body");
    renderReqs();
    const f = fnOf(b), st = status(b);
    const comp = (f.companions || []).filter(c => FN[c]);
    panel.innerHTML = `<h3>${esc(b.label || f.label)}</h3>
      <p class="small"><span class="lg lg-${st}">${esc(STATUS_TEXT[st])}</span> · ${esc(CATS[f.category] || f.category || "")}</p>
      ${f.note ? `<p class="small muted">${esc(f.note)}</p>` : ""}
      ${b.part ? `<p>Chosen: <b>${esc(b.part)}</b> <button type="button" class="outline secondary small-btn" data-act="unpick">clear</button></p>` : ""}
      <div class="row"><label class="small">Label <input data-f="label" value="${esc(b.label || "")}" placeholder="${esc(f.label)}"></label>
        <label class="small">Qty <input data-f="qty" type="number" min="1" max="99" value="${b.qty || 1}" style="width:4rem"></label></div>
      <div id="bk-parts"></div>
      ${comp.length ? `<p class="small"><b>Usually designed in with it</b></p><div class="row">${comp.map(c => `<button type="button" class="bc-chip bc-chip-sm" data-add="${c}" title="${esc(STATUS_TEXT[COUNTS[c] === null ? "ext" : COUNTS[c] ? "have" : "opp"])}">+ ${esc(FN[c].label)}</button>`).join("")}</div>` : ""}
      <div class="row"><button type="button" class="outline secondary small-btn" data-act="remove">Remove block</button>
        <select data-act="move" class="small-sel" aria-label="Move to group"><option value="">Move to…</option>${S.groups.filter(x => x !== g).map(x => `<option value="${x.id}">${esc(x.label)}</option>`).join("")}</select></div>`;
    if (st !== "ext" && COUNTS[b.fn]) {
      const box = panel.querySelector("#bk-parts");
      const draw = async q => {
        const r = await parts(b.fn, q);
        const li = p => partRow(p, true);
        box.innerHTML = `<p class="small"><b>Parts that fit</b> (${r.total}${Object.keys(S.req[b.fn] || {}).length ? " meeting the requirements" : ""})</p>
          <input type="search" placeholder="Filter parts" value="${esc(q)}" aria-label="Filter parts" data-q>` +
          (r.manufacturers.length ? r.manufacturers.map(m => `<p class="small bk-mfr"><b>${esc(m.manufacturer)}</b> · best ${m.best.length} of ${m.total}</p>
            <ul class="bk-parts">${m.best.map(li).join("")}</ul>
            ${m.total > m.best.length ? `<details><summary class="small">All ${m.total} ${esc(m.manufacturer)} parts</summary><ul class="bk-parts">${m.all.map(li).join("")}</ul></details>` : ""}`).join("")
            : `<p class="small uc-error">No part meets these requirements. Untick one, or record the gap as feedback.</p>`);
        const inp = box.querySelector("[data-q]");
        inp.oninput = () => { clearTimeout(inp._t); inp._t = setTimeout(() => draw(inp.value), 250); };
        box.querySelectorAll("[data-pick]").forEach(btn => (btn.onclick = async () => {
          const p = [...r.manufacturers.flatMap(m => [...m.best, ...m.all])].find(x => x.mpn === btn.dataset.pick);
          b.part = btn.dataset.pick;
          const notes = applyPick(b.fn, p && p.implies);
          changed();
          if (notes.length) await refreshCounts();
          showBlock(g, b);
          if (notes.length) below().querySelector(".bk-below-head").insertAdjacentHTML("beforeend", `<p class="small pt-applied">Applied from your choice of <b>${esc(b.part)}</b>: ${notes.map(esc).join(" · ")}</p>`);
        }));
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
  // Requirements above the diagram: design questions and part filters in a readable grid, collapsible so the
  // diagram stays in view. Open by default while nothing is answered yet.
  let reqOpen = null;
  const openGroups = new Set();
  // Requirements as a list, one collapsible group per function (its design questions + its part filters), then
  // the recorded system decisions. Dependencies: a filter that exists on other blocks too (automotive,
  // reinforced) offers to apply it there; a function with answers lists related blocks (companions) to check.
  function renderReqs() {
    const box = $("#bk-reqs");
    if (!box) return;
    const inDiagram = new Set(S.groups.flatMap(g => g.blocks.map(b => b.fn)));
    const fnsReq = [...inDiagram].filter(fn => (REQ[fn] || []).length);
    const qs = S.questions || [];
    if (!qs.length && !fnsReq.length) { box.innerHTML = ""; return; }
    const qByFn = {}, recorded = [];
    for (const q of qs) (q.sets && q.sets.length ? (qByFn[q.sets[0].fn] ||= []) : recorded).push(q);
    const selB = sel && sel.block && blockOf(group(sel.group), sel.block);
    const groupFns = [...new Set([...Object.keys(qByFn), ...fnsReq])];
    const nQ = Object.keys(S.qa).length, nR = Object.values(S.req).reduce((k, a) => k + Object.keys(a).length, 0);
    if (reqOpen === null) reqOpen = !nQ && !nR;
    const qRow = q => {
      const fl = filterLabel(q), set = S.qa[q.id];
      return `<li class="rq-item${set ? " rq-on" : ""}" title="${esc(q.source || "")}"><span class="rq-label">${esc(q.question)}${fl.length > 1 ? ` <small class="muted">· also filters ${esc(fl.slice(1).join(", "))}</small>` : ""}</span>
        <select data-q="${esc(q.id)}"><option value="">not decided</option>${q.choices.map(c => `<option value="${esc(c)}"${set === String(c) ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>
        ${HELP[q.id] ? `<small class="rq-help">${esc(HELP[q.id])}</small>` : ""}</li>`;
    };
    const rRow = (fn, r) => {
      const v = (S.req[fn] || {})[r.id];
      const others = v ? fnsReq.filter(f => f !== fn && (REQ[f] || []).some(x => x.id === r.id) && !(S.req[f] || {})[r.id]) : [];
      const ctl = r.choices
        ? `<select data-req="${fn}|${r.id}"><option value="">any</option>${r.choices.map(c => `<option value="${esc(c)}"${String(v ?? "") === String(c) ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>`
        : `<input type="checkbox" data-req="${fn}|${r.id}"${v ? " checked" : ""} aria-label="${esc(r.label)}">`;
      return `<li class="rq-item${v ? " rq-on" : ""}"><span class="rq-label">${esc(r.label)}${others.length ? ` <button type="button" class="link-btn" data-apply="${fn}|${r.id}" title="${esc(others.map(f => FN[f].label).join(", "))}">also for ${others.length} other block${others.length > 1 ? "s" : ""}</button>` : ""}</span>${ctl}</li>`;
    };
    const related = fn => (FN[fn].companions || []).filter(c => inDiagram.has(c) && (REQ[c] || []).length && c !== fn);
    const grp = (key, title, sub, rows, answered, extra = "") => {
      const open = (selB && key === selB.fn) || openGroups.has(key) || (!openGroups.size && !selB && answered);
      return `<details class="rq-group" data-g="${esc(key)}"${open ? " open" : ""}><summary><b>${esc(title)}</b> <span class="small muted">${sub}${answered ? ` · <span class="rq-count">${answered} set</span>` : ""}</span>${extra}</summary><ul class="rq-list">${rows}</ul></details>`;
    };
    const fnGroups = groupFns.map(fn => {
      const qsF = qByFn[fn] || [], rs = REQ[fn] || [];
      const answered = qsF.filter(q => S.qa[q.id]).length + Object.keys(S.req[fn] || {}).length;
      const rel = answered ? related(fn) : [];
      const extra = rel.length ? ` <span class="small rq-rel">→ check also: ${rel.map(c => `<a href="#" data-goto="${c}">${esc(FN[c].label)}</a>`).join(", ")}</span>` : "";
      return grp(fn, FN[fn] ? FN[fn].label : fn, `${COUNTS[fn] ?? "–"} parts fit${inDiagram.has(fn) ? "" : " · not in this diagram"}`,
        (qsF.length ? qsF.map(qRow).join("") : "") + (rs.length ? `<li class="rq-sub small muted">Part filters</li>` + rs.map(r => rRow(fn, r)).join("") : ""), answered, extra);
    }).join("");
    const recGroup = recorded.length ? grp("_recorded", "System decisions", "recorded with the design, no part filter", recorded.map(qRow).join(""), recorded.filter(q => S.qa[q.id]).length) : "";
    const head = selB
      ? `<h3>Requirements <span class="small muted">· ${esc(selB.label || fnOf(selB).label)} opened; ${COUNTS[selB.fn] ?? "–"} parts fit now (listed below)</span></h3>`
      : `<h3>Requirements</h3><p class="small muted">Answer only what the design needs; unanswered = no filter, nothing is assumed. Each group filters the parts of one block (count = parts that fit now); click a block in the diagram to focus on it.${qs.length ? ` ${nQ} of ${qs.length} design questions answered.` : ""} ${nR} part filter${nR === 1 ? "" : "s"} set.</p>`;
    box.innerHTML = `<div class="bk-reqs-box">${head}<div class="bk-reqs-body">
      ${groupFns.length + (recorded.length ? 1 : 0) < 2 ? "" : `<div class="rq-tools small"><button type="button" class="link-btn" data-all="open">expand all</button> · <button type="button" class="link-btn" data-all="close">collapse all</button></div>`}
      ${fnGroups || (selB ? `<p class="small muted">This block has no requirement questions.</p>` : "")}${recGroup}
      ${(S.sources || []).length ? `<p class="small muted">Sources: ${S.sources.map(d => `<a href="${esc(d.url)}" target="_blank" rel="noopener" title="${esc(d.title)}">${esc(d.doc)}</a>`).join(", ")}</p>` : ""}
    </div></div>`;
    const cur = selB && box.querySelector(`.rq-group[data-g="${selB.fn}"]`);
    if (cur && renderReqs.focus !== sel.block) { renderReqs.focus = sel.block; cur.scrollIntoView({behavior: "smooth", block: "start"}); }
    if (!selB) renderReqs.focus = null;
    const body = box.querySelector(".bk-reqs-body");
    if (body) { body.scrollTop = renderReqs.scroll || 0; body.onscroll = () => (renderReqs.scroll = body.scrollTop); }
    box.querySelectorAll(".rq-group").forEach(d => (d.ontoggle = () => (d.open ? openGroups.add(d.dataset.g) : openGroups.delete(d.dataset.g))));
    box.querySelectorAll("[data-all]").forEach(btn => (btn.onclick = () => {
      box.querySelectorAll(".rq-group").forEach(d => { d.open = btn.dataset.all === "open"; d.open ? openGroups.add(d.dataset.g) : openGroups.delete(d.dataset.g); });
    }));
    box.querySelectorAll("[data-goto]").forEach(a => (a.onclick = e => {
      e.preventDefault();
      const d = box.querySelector(`.rq-group[data-g="${a.dataset.goto}"]`);
      if (d) { d.open = true; openGroups.add(a.dataset.goto); d.scrollIntoView({behavior: "smooth", block: "nearest"}); d.classList.add("rq-flash"); setTimeout(() => d.classList.remove("rq-flash"), 1200); }
    }));
    box.querySelectorAll("[data-apply]").forEach(btn => (btn.onclick = async () => {
      const [fn, rid] = btn.dataset.apply.split("|"), v = S.req[fn][rid];
      for (const f of fnsReq) if (f !== fn && (REQ[f] || []).some(x => x.id === rid)) { (S.req[f] ||= {})[rid] = v; openGroups.add(f); }
      dirty = true; $("#bk-status").textContent = "Unsaved changes";
      await refreshCounts();
      if (sel && sel.block) { const g = group(sel.group), b = blockOf(g, sel.block); if (b) showBlock(g, b); }
    }));
    const again = () => { if (sel && sel.block) { const g = group(sel.group), b = blockOf(g, sel.block); if (b) showBlock(g, b); } };
    bindReq(box, again);
    bindQuestions(box, again);
  }
  $("#bk-req").onclick = () => $("#bk-reqs").scrollIntoView({behavior: "smooth", block: "start"});

  // feedback on the diagram or the selected block / group, kept for discussion
  async function showFeedback() {
    openPanel();
    const g = sel && group(sel.group), b = g && sel.block && blockOf(g, sel.block);
    const target = b ? `${g.label} / ${b.label || fnOf(b).label}` : g ? g.label : "";
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    panel.innerHTML = `<h3>Feedback</h3>
      <p class="small muted">Type or speak. It goes on the feedback to-do list (Block diagrams → Feedback) and is reviewed in batches; nothing changes until then.${target ? ` About: <b>${esc(target)}</b>.` : ""}</p>
      <textarea data-fb-msg rows="5" placeholder="What should change?"></textarea>
      <div class="row"><button type="button" class="small-btn" data-fb-save>Save</button>
        ${SR ? `<button type="button" class="outline small-btn" data-fb-mic title="Voice input uses your browser's speech recognition; some browsers (e.g. Chrome) send the audio to their speech service.">🎤 Speak</button>` : `<span class="small muted">Voice: use your keyboard's dictation key.</span>`}
        <span class="small muted" data-fb-st></span></div>`;
    const msgEl = panel.querySelector("[data-fb-msg]"), st = panel.querySelector("[data-fb-st]");
    const mic = panel.querySelector("[data-fb-mic]");
    if (mic) {
      let rec = null;
      mic.onclick = () => {
        if (rec) { rec.stop(); return; }
        rec = new SR();
        rec.lang = navigator.language || "en-US";
        rec.interimResults = false;
        rec.continuous = true;
        rec.onresult = e => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) msgEl.value = `${msgEl.value} ${e.results[i][0].transcript}`.trim(); };
        rec.onend = () => { rec = null; mic.textContent = "🎤 Speak"; st.textContent = ""; };
        rec.onerror = e => { st.textContent = `Voice input not available (${e.error})`; };
        rec.start();
        mic.textContent = "■ Stop"; st.textContent = "Listening…";
      };
    }
    panel.querySelector("[data-fb-save]").onclick = async () => {
      const msg = msgEl.value.trim();
      if (!msg) return;
      const res = await fetch("/api/blocks/feedback", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({diagram_id: configId, diagram_name: $("#bk-name").value || (tpl && tpl.name) || "", target, message: msg})});
      st.textContent = res.ok ? "Saved to the to-do list" : `Not saved (${res.status})`;
      if (res.ok) msgEl.value = "";
    };
    msgEl.focus();
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
    if (!t) { if (sel) { sel = null; root.classList.remove("panel-open"); render(); } return; }
    const g = group(t.dataset.group);
    if (t.dataset.block && sel && sel.block === t.dataset.block) { sel = null; render(); return; } // click again: deselect
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

  // ---- convert to schematic: pick what to convert, check the design rules and answer the questions, then draw
  const SCH = $("#bk-schem");
  const schem = {scope: null, check: null, out: null};
  const scopeKey = sc => sc.kind === "all" ? "all" : `${sc.kind}:${sc.group}:${sc.block || ""}`;
  const answersFor = sc => ((S.schem ||= {})[scopeKey(sc)] ||= {});
  function scopes() {
    const out = [{kind: "all", label: `Whole diagram (${S.groups.reduce((n, g) => n + g.blocks.length, 0)} blocks)`}];
    for (const g of S.groups) out.push({kind: "group", group: g.id, label: `Frame: ${g.label} (${g.blocks.length} block${g.blocks.length === 1 ? "" : "s"})`});
    for (const g of S.groups) for (const b of g.blocks) out.push({kind: "block", group: g.id, block: b.id, label: `Block: ${b.label || fnOf(b).label}${b.part ? " · " + b.part : ""} (in ${g.label})`});
    return out;
  }
  async function schemCall(drawIt) {
    const res = await fetch("/api/blocks/schematic", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({data: S, scope: schem.scope, answers: answersFor(schem.scope), draw: drawIt, title: $("#bk-name").value || "Block diagram"})});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }
  function openSchem() {
    SCH.hidden = false;
    const list = scopes();
    const cur = sel && sel.block ? list.find(x => x.block === sel.block) : sel ? list.find(x => x.kind === "group" && x.group === sel.group) : list[0];
    SCH.innerHTML = `<h2>Convert to schematic</h2>
      <p class="small muted">Choose what to convert: the whole diagram, one frame (a functional block with the blocks inside it) or a single block.
        Cross List first checks the design rules and asks what it cannot decide; nothing is drawn until you click <b>Draw schematic</b>.</p>
      <div class="row"><label class="small">Convert <select id="sch-scope" class="small-sel">${list.map((x, i) => `<option value="${i}"${x === cur ? " selected" : ""}>${esc(x.label)}</option>`).join("")}</select></label>
        <button type="button" id="sch-check" class="small-btn">Check design rules</button>
        <button type="button" id="sch-close" class="outline secondary small-btn">Close</button></div>
      <div id="sch-body"></div>`;
    SCH.querySelector("#sch-close").onclick = () => { SCH.hidden = true; };
    SCH.querySelector("#sch-check").onclick = () => { schem.scope = list[+SCH.querySelector("#sch-scope").value]; runCheck(); };
    SCH.scrollIntoView({behavior: "smooth", block: "start"});
  }
  const LEVEL = {error: "Must fix", warn: "Check", info: "Note"};
  function issuesHtml(issues) {
    if (!issues.length) return `<p class="small sch-ok">No design-rule findings.</p>`;
    return `<ul class="sch-issues">${issues.map(i => `<li class="sch-${i.level}"><b>${LEVEL[i.level]}</b> ${esc(i.text)}</li>`).join("")}</ul>`;
  }
  async function runCheck() {
    const body = SCH.querySelector("#sch-body");
    body.innerHTML = `<p class="small muted">Checking…</p>`;
    try { schem.check = await schemCall(false); } catch (e) { body.innerHTML = `<p class="small uc-error">Check failed (${esc(e.message)}). <button type="button" class="outline small-btn" id="sch-retry">Retry</button></p>`; body.querySelector("#sch-retry").onclick = runCheck; return; }
    const c = schem.check, A = answersFor(schem.scope);
    const sections = [...new Set(c.questions.map(q => q.section))];
    const val = q => A[q.id] !== undefined ? A[q.id] : q.default;
    const ctl = q => q.kind === "text"
      ? `<input type="text" data-sq="${esc(q.id)}" value="${esc(val(q))}" placeholder="e.g. 100 pF" style="max-width:14rem">`
      : q.kind === "multi"
      ? `<div class="sch-multi">${q.choices.map(([v, t]) => {
          const vq = c.questions.find(x => x.parent === q.id && x.item === v); // a value the datasheet leaves open
          return `<label class="small"><input type="checkbox" data-sq="${esc(q.id)}" value="${esc(v)}"${val(q).includes(v) ? " checked" : ""}> ${esc(t)}</label>`
            + (vq ? `<label class="small sch-val">Value <input type="text" data-sq="${esc(vq.id)}" value="${esc(val(vq))}" placeholder="not stated – e.g. 100 pF"></label>` : "");
        }).join("")}</div>`
      : `<select data-sq="${esc(q.id)}" class="small-sel">${q.choices.map(ch => `<option${String(val(q)) === String(ch) ? " selected" : ""}>${esc(ch)}</option>`).join("")}</select>`;
    body.innerHTML = `<h3>1 · Design-rule check</h3>
      <p class="small muted">${c.devices.length} device${c.devices.length === 1 ? "" : "s"}: ${c.devices.map(d => `${esc(d.ref)} ${esc(d.mpn || d.label)}${d.placeholder ? " (placeholder)" : ""}`).join(" · ")}</p>
      <div id="sch-issues">${issuesHtml(c.issues)}</div>
      <h3>2 · Questions</h3>
      ${c.questions.length ? sections.map(sec => `<details class="req-box" open><summary class="small"><b>${esc(sec)}</b></summary>${c.questions.filter(q => q.section === sec && !q.parent).map(q => `
        <div class="sch-q"><p class="small"><b>${esc(q.text)}</b>${A[q.id] !== undefined ? "" : ` <span class="lg lg-have">suggested</span>`}</p>${ctl(q)}${q.why ? `<p class="small muted">${esc(q.why)}</p>` : ""}</div>`).join("")}</details>`).join("")
        : `<p class="small muted">Nothing to decide for this selection.</p>`}
      <h3>3 · Draw</h3>
      <div class="row"><button type="button" id="sch-draw" class="small-btn"></button><span class="small muted">Answers are saved with the diagram.</span></div>
      <div id="sch-out"></div>`;
    const drawBtn = body.querySelector("#sch-draw");
    const label = n => { drawBtn.textContent = n ? `Draw anyway (${n} to fix)` : "Draw schematic"; drawBtn.classList.toggle("secondary", !!n); };
    label(c.errors);
    body.querySelectorAll("[data-sq]").forEach(el => (el.onchange = async () => {
      const q = c.questions.find(x => x.id === el.dataset.sq);
      A[q.id] = q.kind === "multi" ? [...body.querySelectorAll(`[data-sq="${CSS.escape(q.id)}"]:checked`)].map(x => x.value) : el.value;
      dirty = true; $("#bk-status").textContent = "Unsaved changes";
      try { const r = await schemCall(false); body.querySelector("#sch-issues").innerHTML = issuesHtml(r.issues); label(r.errors); } catch (e) { /* keep the last findings */ }
    }));
    drawBtn.onclick = drawSchem;
  }
  async function drawSchem() {
    const out = SCH.querySelector("#sch-out");
    out.innerHTML = `<p class="small muted">Drawing…</p>`;
    try { schem.out = await schemCall(true); } catch (e) { out.innerHTML = `<p class="small uc-error">Drawing failed (${esc(e.message)}).</p>`; return; }
    const o = schem.out;
    const fname = t => `${($("#bk-name").value || "schematic").replace(/[^\w.-]+/g, "_")}_${t.replace(/[^\w.-]+/g, "_")}.svg`;
    out.innerHTML = `${o.errors ? `<p class="small uc-error">Drawn with ${o.errors} open design-rule finding${o.errors === 1 ? "" : "s"} marked “Must fix” above.</p>` : ""}
      ${o.sheets.map((sh, i) => `<figure class="sch-sheet"><figcaption class="small"><b>Sheet ${i + 1} of ${o.sheets.length}: ${esc(sh.title)}</b>
        <button type="button" class="outline small-btn" data-dl="${i}">Download SVG</button></figcaption><div class="sch-svg">${sh.svg}</div></figure>`).join("")}
      <details class="req-box"${o.bom.length ? " open" : ""}><summary class="small"><b>External parts (${o.bom.length})</b> · from the datasheets, with the text each comes from</summary>
        ${o.bom.length ? `<div class="table-wrap"><table class="striped small"><thead><tr><th>Ref</th><th>Part</th><th>Value</th><th>At</th><th>To</th><th>Source</th></tr></thead><tbody>
        ${o.bom.map(b => `<tr><td><b>${esc(b.ref)}</b>${b.required ? "" : " <span class='muted'>rec.</span>"}</td><td>${esc(b.kind)}${b.series ? " (series)" : ""}</td><td>${esc(b.value || "per datasheet")}</td>
          <td>${esc(b.device)} ${esc(b.pin)}</td><td>${esc(b.to)}</td><td>${esc(b.doc || "")}${b.page ? `, p. ${b.page}` : ""}${b.quote ? `<br><span class="muted">“${esc(b.quote)}”</span>` : ""}${b.note ? `<br><span class="muted">${esc(b.note)}</span>` : ""}</td></tr>`).join("")}
        </tbody></table></div>` : `<p class="small muted">None: no ticked external parts, or no typical-application data for these parts yet.</p>`}</details>`;
    out.querySelectorAll("[data-dl]").forEach(btn => (btn.onclick = () => {
      const sh = o.sheets[+btn.dataset.dl];
      Object.assign(document.createElement("a"), {href: URL.createObjectURL(new Blob([sh.svg], {type: "image/svg+xml"})), download: fname(sh.title)}).click();
    }));
  }
  $("#bk-schem-open").addEventListener("click", openSchem);

  if (!design.data && tpl) dirty = true;
  if (Object.keys(S.req).length) refreshCounts(); else render();
  // requirements live above the diagram (renderReqs); the drawer is only for a clicked block or group
})();
