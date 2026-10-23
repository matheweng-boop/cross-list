// Block-diagram generator. A diagram is groups (dotted frames on a grid) holding blocks; each block is a
// system function that a Skyworks part in BizDev may fill. State (saved as JSON):
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
  // a saved design without its groups list (old or broken data) opens like a new one instead of a blank editor
  let S = Array.isArray(design.data?.groups) ? design.data : fromTemplate(tpl) || {groups: [], links: []};
  S.req ||= {}; // requirement answers per function: {fn: {reqId: value}}; unanswered = no filter
  S.qa ||= {}; // answers to the template's design questions: {questionId: choice}; unanswered = nothing assumed
  let sel = null; // {group} or {group, block}
  const DIM = new Set(["ext"]); // statuses greyed out in the diagram (legend buttons toggle them); gaps show by default
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
  const STATUS_TEXT = {part: "Part chosen", have: "Skyworks / Qorvo parts fit", opp: "Gap: no Skyworks or Qorvo part in BizDev yet", ext: "Customer part"};

  // ---- layout
  const CELL = 250, GAP_X = 56, GAP_Y = 52, BW = 112, BH = 46, BG = 8, HEAD = 26, PAD = 9;
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
    return {rects, W, H: Math.max(260, y), rowY, rowH, rows: rowsSorted};
  }

  // ---- connections, schematic style: right angles only, never through a frame.
  //   same row, nothing in between: side to side (straight when the ports line up)
  //   same row with frames in between: down into the gap below the row, along it, back up
  //   neighbouring rows: bottom to top through the gap between the rows
  //   rows further apart: through the gap next to each end and a free column gap between them
  // Several connections on one side get spread-out ports; connections in the same gap get their own lane.
  function routes(L) {
    const R = id => L.rects[id], rowIdx = Object.fromEntries(L.rows.map((r, i) => [r, i]));
    const gapBelow = r => [L.rowY[r] + L.rowH[r], L.rowY[r] + L.rowH[r] + GAP_Y];
    const gapAbove = r => [Math.max(2, L.rowY[r] - GAP_Y), L.rowY[r]];
    const maxCol = Math.max(0, ...S.groups.map(g => g.col + (g.w || 1)));
    const colGaps = [6, ...Array.from({length: maxCol + 1}, (_, k) => 20 + (k + 1) * (CELL + GAP_X) - GAP_X / 2)];
    const items = [];
    S.links.forEach(([a, b, label], i) => {
      const ga = group(a), gb = group(b), ra = R(a), rb = R(b);
      if (!ra || !rb || a === b) return;
      const it = {i, a, b, label, ra, rb};
      if (ga.row === gb.row) {
        const [x0, x1] = ra.x < rb.x ? [ra.x + ra.w, rb.x] : [rb.x + rb.w, ra.x];
        const between = S.groups.some(g => g !== ga && g !== gb && g.row === ga.row && R(g.id).x < x1 && R(g.id).x + R(g.id).w > x0);
        if (!between) { it.kind = "H"; const right = rb.x > ra.x; it.sa = right ? "r" : "l"; it.sb = right ? "l" : "r"; }
        else { it.kind = "U"; it.sa = it.sb = "b"; it.gap = gapBelow(ga.row); }
      } else {
        const down = gb.row > ga.row;
        it.sa = down ? "b" : "t"; it.sb = down ? "t" : "b";
        const ia = rowIdx[ga.row], ib = rowIdx[gb.row];
        if (Math.abs(ia - ib) === 1) { it.kind = "V"; it.gap = down ? gapBelow(ga.row) : gapAbove(ga.row); }
        else {
          it.kind = "V5";
          it.gapA = down ? gapBelow(ga.row) : gapAbove(ga.row);
          it.gapB = down ? gapAbove(gb.row) : gapBelow(gb.row);
          const lo = Math.min(ia, ib), hi = Math.max(ia, ib);
          const blockers = S.groups.filter(g => rowIdx[g.row] > lo && rowIdx[g.row] < hi).map(g => R(g.id));
          const free = colGaps.filter(x => !blockers.some(f => x >= f.x - 4 && x <= f.x + f.w + 4));
          const mid = (ra.x + ra.w / 2 + rb.x + rb.w / 2) / 2;
          it.gx = free.length ? free.reduce((best, x) => Math.abs(x - mid) < Math.abs(best - mid) ? x : best) : 6;
        }
      }
      items.push(it);
    });
    // ports, spread along each side in the order of where the other end is
    const sides = {};
    for (const it of items) {
      (sides[`${it.a}|${it.sa}`] ||= []).push({it, end: "a", other: it.rb});
      (sides[`${it.b}|${it.sb}`] ||= []).push({it, end: "b", other: it.ra});
    }
    for (const [key, list] of Object.entries(sides)) {
      const side = key.split("|")[1], r = list[0].end === "a" ? list[0].it.ra : list[0].it.rb;
      const vert = side === "l" || side === "r";
      list.sort((p, q) => vert ? (p.other.y + p.other.h / 2) - (q.other.y + q.other.h / 2) : (p.other.x + p.other.w / 2) - (q.other.x + q.other.w / 2));
      list.forEach((p, k) => {
        const f = (k + 1) / (list.length + 1);
        p.it[p.end === "a" ? "pa" : "pb"] = vert ? {x: side === "r" ? r.x + r.w : r.x, y: r.y + HEAD + (r.h - HEAD) * f}
          : {x: r.x + r.w * (0.1 + 0.8 * f), y: side === "b" ? r.y + r.h : r.y};
      });
    }
    // lanes in shared gaps
    const lanes = {}, lane = (key, it, slot) => (lanes[key] ||= []).push([it, slot]);
    for (const it of items) {
      if (it.kind === "H") lane(`h${Math.round(Math.min(it.pa.x, it.pb.x))}`, it, "mx");
      else if (it.kind === "V" || it.kind === "U") lane(`g${it.gap[0]}`, it, "my");
      else { lane(`g${it.gapA[0]}`, it, "ya"); lane(`g${it.gapB[0]}`, it, "yb"); lane(`c${it.gx}`, it, "cx"); }
    }
    for (const [key, list] of Object.entries(lanes)) list.forEach(([it, slot], k) => {
      const f = (k + 1) / (list.length + 1);
      if (slot === "mx") { const x0 = Math.min(it.pa.x, it.pb.x), x1 = Math.max(it.pa.x, it.pb.x); it.mx = x0 + (x1 - x0) * f; }
      else if (slot === "cx") it.cx = it.gx + (k - (list.length - 1) / 2) * 7;
      else { const g = slot === "my" ? it.gap : slot === "ya" ? it.gapA : it.gapB; it[slot] = g[0] + (g[1] - g[0]) * f; }
    });
    for (const it of items) {
      const {pa, pb} = it;
      if (it.kind === "H") {
        it.d = Math.abs(pa.y - pb.y) < 1 ? `M${pa.x} ${pa.y}H${pb.x}` : `M${pa.x} ${pa.y}H${it.mx}V${pb.y}H${pb.x}`;
        it.lx = (pa.x + pb.x) / 2; it.ly = Math.min(pa.y, pb.y) - 5;
      } else if (it.kind === "V" || it.kind === "U") {
        it.d = Math.abs(pa.x - pb.x) < 1 && it.kind === "V" ? `M${pa.x} ${pa.y}V${pb.y}` : `M${pa.x} ${pa.y}V${it.my}H${pb.x}V${pb.y}`;
        it.lx = (pa.x + pb.x) / 2; it.ly = it.my - 4;
      } else {
        it.d = `M${pa.x} ${pa.y}V${it.ya}H${it.cx}V${it.yb}H${pb.x}V${pb.y}`;
        it.lx = it.cx + 4; it.ly = (it.ya + it.yb) / 2; it.lanchor = "start";
      }
    }
    return items;
  }

  function render() {
    const L = layout(), parts = [];
    parts.push(`<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#3a3f47"/></marker></defs>`);
    const R = routes(L);
    for (const it of R) parts.push(`<path class="link" d="${it.d}"/>`);
    for (const it of R) if (it.label) parts.push(`<text class="link-label" x="${it.lx}" y="${it.ly}" text-anchor="${it.lanchor || "middle"}">${esc(it.label)}</text>`);
    for (const g of S.groups) {
      const r = L.rects[g.id];
      parts.push(`<g class="grp${sel && sel.group === g.id && !sel.block ? " sel" : ""}" data-gid="${g.id}"><rect class="frame" data-drag-group="${g.id}" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="4"><title>Drag to move this frame</title></rect>` +
        `<text class="grp-title" data-group="${g.id}" x="${r.x + 8}" y="${r.y + 17}" tabindex="0" role="button">${esc(g.label)}</text>` +
        `<g class="grp-add" data-add-to="${g.id}" tabindex="0" role="button" aria-label="Add a block to ${esc(g.label)}"><title>Add a block to this frame</title>` +
        `<rect x="${r.x + r.w - 26}" y="${r.y + 4}" width="20" height="18" rx="4"/><text x="${r.x + r.w - 16}" y="${r.y + 17.5}" text-anchor="middle">+</text></g>`);
      g.blocks.forEach((b, i) => {
        const cx = r.x + PAD + (i % r.cols) * (BW + BG), cy = r.y + HEAD + Math.floor(i / r.cols) * (BH + BG);
        const st = status(b), f = fnOf(b);
        const label = b.label || f.label;
        const sub = b.part || (st === "have" ? `${COUNTS[b.fn]} parts` : st === "opp" ? "gap" : st === "ext" ? "customer part" : "");
        parts.push(`<g class="blk st-${st}${DIM.has(st) ? " dim" : ""}${sel && sel.block === b.id ? " sel" : ""}" data-group="${g.id}" data-block="${b.id}" tabindex="0" role="button" aria-label="${esc(label)}">` +
          `<rect x="${cx}" y="${cy}" width="${BW}" height="${BH}"/>` +
          wrap(label, 16).slice(0, 2).map((t, k) => `<text class="b-label" x="${cx + BW / 2}" y="${cy + 15 + k * 13}" text-anchor="middle">${esc(t)}</text>`).join("") +
          `<text class="b-sub" x="${cx + BW / 2}" y="${cy + BH - 5}" text-anchor="middle">${esc(sub.slice(0, 19))}${b.qty > 1 ? ` ×${b.qty}` : ""}</text></g>`);
      });
      parts.push(`</g>`);
    }
    if (!S.groups.length) parts.push(`<text x="40" y="80" fill="#888" font-size="14">Add a frame with + Frame, then add blocks to it.</text>`);
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
      if (!view || e.target.closest("[data-block], [data-group], [data-drag-group], [data-add-to]")) return;
      drag = {x: e.clientX, y: e.clientY, v: {...view}, s: view.w / svg.clientWidth};
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", e => { if (drag) { view = {...drag.v, x: drag.v.x - (e.clientX - drag.x) * drag.s, y: drag.v.y - (e.clientY - drag.y) * drag.s}; applyView(); } });
    svg.addEventListener("pointerup", () => (drag = null));
  })();
  // the side panel is a drawer that opens on a selection
  const openPanel = () => root.classList.add("panel-open");
  $("#bk-close").onclick = () => { root.classList.remove("panel-open"); sel = null; render(); };

  // ---- summary: Skyworks content vs gaps
  function renderSummary() {
    const all = S.groups.flatMap(g => g.blocks);
    const by = {part: 0, have: 0, opp: 0, ext: 0};
    all.forEach(b => (by[status(b)] += b.qty || 1));
    const opp = {}, chosen = [];
    all.forEach(b => { if (status(b) === "opp") opp[fnOf(b).label] = (opp[fnOf(b).label] || 0) + (b.qty || 1); if (b.part) chosen.push(`${b.part}${b.qty > 1 ? ` ×${b.qty}` : ""}`); });
    // covered = a part chosen or Skyworks / Qorvo parts available; choosing a part never lowers it
    const total = by.part + by.have + by.opp, covered = by.part + by.have;
    const progress = `Covered <b>${covered}</b> of ${total} blocks <span class="muted">(chosen ${by.part} · options available ${by.have})</span> · <b>${by.opp}</b> gap${by.opp === 1 ? "" : "s"} · ${by.ext} customer part${by.ext === 1 ? "" : "s"}`;
    $("#bk-headline").innerHTML = progress + (by.opp ? ` · <a href="#bk-summary">see the gaps</a>` : "");
    $("#bk-summary").innerHTML = `<p class="bk-progress">${progress}</p>` +
      (chosen.length ? `<p><b>Skyworks bill of materials:</b> ${esc(chosen.join(", "))}</p>` : "") +
      (Object.keys(opp).length ? `<p><b>Gaps</b> (no Skyworks or Qorvo part in BizDev yet): ${Object.entries(opp).map(([k, n]) => `${esc(k)}${n > 1 ? ` ×${n}` : ""}`).join(" · ")}</p>` : "");
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
  const partRow = (p, pick, chosen) => `<li class="pt-row${chosen ? " pt-chosen" : ""}"><div class="pt-main"><a class="pt-mpn" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.mpn)}</a>${p.pins ? `<span class="pt-chip k-sch" title="Pin list in BizDev: can be drawn as a schematic">schematic</span>` : ""}${pick ? (chosen ? `<span class="pt-picked">✓ chosen</span>` : `<button type="button" class="outline small-btn" data-pick="${esc(p.mpn)}">use</button>`) : ""}</div>
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
    if (!fns.length) { box.innerHTML = `<h3>Suggested parts</h3><p class="small muted">No block in this diagram has Skyworks or Qorvo parts in BizDev yet.</p>`; return; }
    const open = renderBelow.open || (renderBelow.open = new Set());
    const unpicked = S.groups.flatMap(g => g.blocks).filter(b => status(b) === "have").length;
    box.innerHTML = `<h3>Suggested parts <span class="small muted">· open a block for its most likely parts per manufacturer; “use” puts the part in the diagram</span></h3>
      <div class="row bk-pick-bar"><button type="button" class="small-btn" id="bk-pick-all"${unpicked ? "" : " disabled"}>Pick the best match for ${unpicked ? `${unpicked} block${unpicked === 1 ? "" : "s"}` : "every block"}</button>
        <label class="small"><input type="checkbox" id="bk-pick-pins"${renderBelow.pins === false ? "" : " checked"}> prefer parts that can be drawn as a schematic</label>
        <button type="button" class="outline secondary small-btn" id="bk-pick-clear"${S.groups.some(g => g.blocks.some(b => b.part)) ? "" : " disabled"}>Clear all picks</button></div>
      ${renderBelow.note ? `<p class="small pt-applied">${renderBelow.note}</p>` : ""}
      <div class="bk-sugg">${fns.map(fn => `<details class="bk-sugg-fn" data-fn="${fn}"${open.has(fn) ? " open" : ""}><summary class="small"><b>${esc(FN[fn].label)}</b> <span class="muted">· ${COUNTS[fn] ?? "–"} fit${Object.keys(S.req[fn] || {}).length ? " the requirements" : ""}</span></summary><div class="bk-sugg-body"></div></details>`).join("")}</div>`;
    box.querySelectorAll(".bk-sugg-fn").forEach(d => {
      // "use": the part goes into every block of this function
      const bindPicks = (el, r) => el.querySelectorAll("[data-pick]").forEach(btn => (btn.onclick = async () => {
        const p = r.manufacturers.flatMap(m => [...m.best, ...m.all]).find(x => x.mpn === btn.dataset.pick);
        S.groups.flatMap(g => g.blocks).filter(b => b.fn === d.dataset.fn).forEach(b => (b.part = btn.dataset.pick));
        const notes = applyPick(d.dataset.fn, p && p.implies);
        renderBelow.note = `${esc(btn.dataset.pick)} → ${esc(FN[d.dataset.fn].label)}${notes.length ? ` · applied: ${notes.map(esc).join(" · ")}` : ""}`;
        d.querySelector(".bk-sugg-body").dataset.loaded = "";
        changed();
        if (notes.length) await refreshCounts();
      }));
      const load = async () => {
        const body = d.querySelector(".bk-sugg-body");
        if (body.dataset.loaded === JSON.stringify(S.req[d.dataset.fn] || {})) return;
        body.innerHTML = `<p class="small muted" aria-live="polite">Loading…</p>`;
        let r;
        try { r = await parts(d.dataset.fn, "", true); } catch (e) { body.innerHTML = `<p class="small uc-error">Could not load the parts. <button type="button" class="link-btn" data-retry>Try again</button></p>`; body.querySelector("[data-retry]").onclick = () => { body.dataset.loaded = ""; load(); }; return; }
        body.dataset.loaded = JSON.stringify(S.req[d.dataset.fn] || {});
        const fnBlocks = S.groups.flatMap(g => g.blocks).filter(b => b.fn === d.dataset.fn);
        const li = p => partRow(p, true, fnBlocks.length && fnBlocks.every(b => b.part === p.mpn));
        body.innerHTML = r.manufacturers.map(m => `<p class="small bk-mfr">${esc(m.manufacturer)}</p><ul class="bk-parts">${m.best.map(li).join("")}</ul>
          ${m.total > m.best.length ? `<details class="bk-more"><summary class="small">More ${esc(m.manufacturer)} (${m.total - m.best.length})</summary><ul class="bk-parts"><li class="small muted">Loading…</li></ul></details>` : ""}`).join("") || `<p class="small uc-error">None meets the requirements.</p>`;
        body.querySelectorAll(".bk-more").forEach((more, i) => more.addEventListener("toggle", async () => {
          if (!more.open || more.dataset.loaded) return;
          more.dataset.loaded = "1";
          const full = await parts(d.dataset.fn), m = full.manufacturers[i];
          more.querySelector("ul").innerHTML = m ? m.all.slice(m.best.length, 60).map(li).join("") : "";
          bindPicks(more, full);
        }));
        bindPicks(body, r);
      };
      d.addEventListener("toggle", () => { d.open ? (open.add(d.dataset.fn), load()) : open.delete(d.dataset.fn); });
      if (d.open) load();
    });
    box.querySelector("#bk-pick-pins").onchange = e => { renderBelow.pins = e.target.checked; };
    box.querySelector("#bk-pick-all").onclick = pickAll;
    box.querySelector("#bk-pick-clear").onclick = () => {
      if (!confirm("Remove the chosen part from every block?")) return;
      S.groups.forEach(g => g.blocks.forEach(b => (b.part = null)));
      renderBelow.note = "All picks cleared.";
      changed();
    };
  }
  // quick run-down: the best-ranked part for every block that has candidates and no part yet
  async function pickAll() {
    const btn = $("#bk-pick-all");
    btn.disabled = true; btn.textContent = "Picking…";
    const pins = renderBelow.pins !== false;
    const todo = S.groups.flatMap(g => g.blocks).filter(b => status(b) === "have");
    const fns = [...new Set(todo.map(b => b.fn))];
    const picked = [], none = [];
    let applied = [];
    for (const fn of fns) {
      let r;
      try { r = await parts(fn, "", true); } catch (e) { none.push(FN[fn].label); continue; }
      const ranked = r.manufacturers.flatMap(m => m.best);
      const best = (pins && ranked.find(p => p.pins)) || r.manufacturers[0]?.best[0];
      if (!best) { none.push(FN[fn].label); continue; }
      todo.filter(b => b.fn === fn).forEach(b => (b.part = best.mpn));
      applied = applied.concat(applyPick(fn, best.implies));
      picked.push(`${FN[fn].label}: ${best.mpn}${best.pins ? "" : " (no pin list)"}`);
    }
    renderBelow.note = `Picked ${picked.length} part${picked.length === 1 ? "" : "s"}: ${picked.map(esc).join(" · ")}` +
      (none.length ? `<br>No part meets the requirements: ${none.map(esc).join(", ")}` : "") +
      (applied.length ? `<br>Applied: ${applied.map(esc).join(" · ")}` : "") + `<br><span class="muted">Change any pick by opening its block below or clicking it in the diagram.</span>`;
    changed();
    if (applied.length) await refreshCounts();
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
      panel.querySelector("#bk-parts").innerHTML = `<p class="small">No Skyworks part for this function is in BizDev. This can be a gap in the portfolio or a product family not imported yet (full portfolio import is on the backlog).
        <a href="/requests">Add a request</a> if a specific part should be crossed.</p>`;
    }
    bindReq(panel, () => showBlock(g, b));
    panel.querySelectorAll("[data-f]").forEach(el => (el.onchange = () => { b[el.dataset.f] = el.dataset.f === "qty" ? Math.max(1, +el.value || 1) : el.value; changed(); }));
    panel.querySelector('[data-act="remove"]').onclick = () => { g.blocks = g.blocks.filter(x => x !== b); sel = {group: g.id}; changed(); showGroup(g); };
    panel.querySelector('[data-act="unpick"]')?.addEventListener("click", () => { b.part = null; changed(); showBlock(g, b); });
    panel.querySelector('[data-act="move"]').onchange = e => { const to = group(e.target.value); if (!to) return; g.blocks = g.blocks.filter(x => x !== b); to.blocks.push(b); sel = {group: to.id, block: b.id}; changed(); showBlock(to, b); };
    panel.querySelectorAll("[data-add]").forEach(btn => (btn.onclick = () => addFunction(btn.dataset.add, g)));
  }

  // the functions of the catalogue as grouped options (the same list as the toolbar picker)
  const fnOptions = () => Object.entries(CATS).map(([ck, cl]) => `<optgroup label="${esc(cl)}">${Object.entries(FN).filter(([, f]) => f.category === ck)
    .map(([k, f]) => `<option value="${k}">${esc(f.label)}${COUNTS[k] === null ? " (customer)" : COUNTS[k] ? ` · ${COUNTS[k]} parts` : " · gap"}</option>`).join("")}</optgroup>`).join("");
  function showGroup(g, focusAdd) {
    openPanel();
    const others = S.groups.filter(x => x !== g);
    const links = S.links.map((l, i) => [l, i]).filter(([l]) => l[0] === g.id || l[1] === g.id);
    panel.innerHTML = `<h3>${esc(g.label)}</h3>
      <label class="small bk-addfn">Add a block to this frame <select data-addfn class="small-sel"><option value="">choose a function…</option>${fnOptions()}</select></label>
      <p class="small muted">${g.blocks.length} block${g.blocks.length === 1 ? "" : "s"} in this frame · drag a block here from another frame to move it.</p>
      <div class="row"><label class="small">Name <input data-g="label" value="${esc(g.label)}"></label></div>
      <div class="row small">Move <button type="button" class="outline small-btn" data-mv="-1,0" aria-label="Left">←</button><button type="button" class="outline small-btn" data-mv="1,0" aria-label="Right">→</button>
        <button type="button" class="outline small-btn" data-mv="0,-1" aria-label="Up">↑</button><button type="button" class="outline small-btn" data-mv="0,1" aria-label="Down">↓</button>
        Width <button type="button" class="outline small-btn" data-w="-1" aria-label="Narrower">−</button><button type="button" class="outline small-btn" data-w="1" aria-label="Wider">+</button></div>
      <p class="small"><b>Connections</b></p>
      <ul>${links.map(([l, i]) => `<li class="small">${esc(group(l[0])?.label)} → ${esc(group(l[1])?.label)} ${l[2] ? `(${esc(l[2])})` : ""} <button type="button" class="outline secondary small-btn" data-unlink="${i}">×</button></li>`).join("") || `<li class="small muted">none</li>`}</ul>
      <div class="row"><select data-link class="small-sel" aria-label="Connect to group"><option value="">Connect to…</option>${others.map(x => `<option value="${x.id}">${esc(x.label)}</option>`).join("")}</select>
        <input data-link-label placeholder="label, e.g. SPI" style="width:8rem"></div>
      <div class="row"><button type="button" class="outline secondary small-btn" data-act="delgroup">Delete group</button></div>`;
    panel.querySelector('[data-g="label"]').onchange = e => { g.label = e.target.value || g.label; changed(); };
    const addSel = panel.querySelector("[data-addfn]");
    addSel.onchange = () => { if (addSel.value) addFunction(addSel.value, g); };
    if (focusAdd) addSel.focus();
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
      <p class="small muted">From the reference documents below. <span class="lg lg-have">narrows</span> = the answer filters parts; <span class="lg lg-ext">recorded</span> = kept with the design (no matching parameter in BizDev yet).</p>
      ${qs.map(q => {
        const fl = filterLabel(q);
        return `<label class="small req-row" title="${esc(q.source || "")}">${esc(q.question)}
          <select data-q="${esc(q.id)}"><option value="">not decided</option>${q.choices.map(c => `<option value="${esc(c)}"${S.qa[q.id] === String(c) ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>
          <span class="lg ${fl.length ? "lg-have" : "lg-ext"}" title="${esc(fl.length ? "Narrows: " + fl.join(", ") : "Recorded only")}">${fl.length ? "narrows" : "recorded"}</span></label>`;
      }).join("")}
      ${(S.sources || []).length ? `<p class="small muted">Sources: ${S.sources.map(d => `<a href="${esc(d.url)}" target="_blank" rel="noopener" title="${esc(d.title)}">${esc(d.doc)}</a>`).join(", ")} (public)</p>` : ""}
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
        : `<p class="small muted">No block in this diagram has requirement questions yet (they come with functions that have parts in BizDev).</p>`);
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
      <p class="small muted">Type or speak. It goes on the review list (Data management → Site data) and is reviewed in batches; nothing changes until then.${target ? ` About: <b>${esc(target)}</b>.` : ""}</p>
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
      const out = res.ok ? await res.json().catch(() => ({})) : {};
      st.textContent = res.ok ? (out.review ? out.message : "Saved to the to-do list") : `Not saved (${res.status})`;
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

  // ---- drag and drop: frames snap to the grid (others in that row move aside); blocks move to the frame they are
  // dropped on, at the drop position. A press without movement stays a click (select).
  let dnd = null, dragged = false;
  const svgPt = e => { const svg = $("#bk-svg"), pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
  const frameAt = (pt, skip) => S.groups.find(g => { const r = lastL.rects[g.id]; return g.id !== skip && r && pt.x >= r.x && pt.x <= r.x + r.w && pt.y >= r.y && pt.y <= r.y + r.h; });
  let undoLayout = null;
  const snapshot = () => JSON.stringify(S.groups.map(g => ({id: g.id, col: g.col, row: g.row, w: g.w, blocks: g.blocks.map(b => b.id)})));
  function restore(snap) {
    const all = Object.fromEntries(S.groups.flatMap(g => g.blocks).map(b => [b.id, b]));
    for (const x of JSON.parse(snap)) { const g = group(x.id); if (!g) continue; Object.assign(g, {col: x.col, row: x.row, w: x.w}); g.blocks = x.blocks.map(id => all[id]).filter(Boolean); }
  }
  const svgEl = $("#bk-svg");
  svgEl.addEventListener("pointerdown", e => {
    if (e.button !== 0 || !lastL) return;
    const blk = e.target.closest("[data-block]");
    const frm = !blk && e.target.closest("[data-drag-group], .grp-title");
    if (!blk && !frm) return;
    const gid = blk ? blk.dataset.group : (frm.dataset.dragGroup || frm.dataset.group);
    const el = blk || svgEl.querySelector(`g.grp[data-gid="${CSS.escape(gid)}"]`);
    dnd = {kind: blk ? "block" : "group", gid, bid: blk && blk.dataset.block, start: svgPt(e), el, moved: false, id: e.pointerId};
  });
  svgEl.addEventListener("pointermove", e => {
    if (!dnd) return;
    const p = svgPt(e), dx = p.x - dnd.start.x, dy = p.y - dnd.start.y;
    if (!dnd.moved && Math.hypot(dx, dy) < 6) return;
    if (!dnd.moved) { dnd.moved = true; svgEl.setPointerCapture(dnd.id); dnd.el.classList.add("dragging"); dnd.before = snapshot(); }
    dnd.el.setAttribute("transform", `translate(${dx},${dy})`);
    svgEl.querySelectorAll(".grp.drop").forEach(x => x.classList.remove("drop"));
    if (dnd.kind === "block") { const t = frameAt(p); if (t) svgEl.querySelector(`g.grp[data-gid="${CSS.escape(t.id)}"]`)?.classList.add("drop"); }
  });
  svgEl.addEventListener("pointerup", e => {
    if (!dnd) return;
    const d = dnd; dnd = null;
    if (!d.moved) return;
    dragged = true; // the click that follows a drag does not select
    const p = svgPt(e), L = lastL;
    if (d.kind === "group") {
      const g = group(d.gid), r = L.rects[g.id];
      const x = r.x + (p.x - d.start.x), y = r.y + (p.y - d.start.y);
      const col = Math.max(0, Math.round((x - 20) / (CELL + GAP_X)));
      let row = L.rows.reduce((best, k) => Math.abs(L.rowY[k] - y) < Math.abs(L.rowY[best] - y) ? k : best, L.rows[0] ?? 0);
      const last = L.rows[L.rows.length - 1];
      if (last !== undefined && y > L.rowY[last] + L.rowH[last]) row = last + 1;
      if (y < 0 && L.rows.length) row = L.rows[0] - 1;
      const w = g.w || 1;
      // make room: frames in the target row that overlap the new place move right
      const others = S.groups.filter(o => o !== g && o.row === row).sort((a, b) => a.col - b.col);
      let edgeCol = col + w;
      for (const o of others) if (o.col + (o.w || 1) > col && o.col < edgeCol) { o.col = edgeCol; edgeCol = o.col + (o.w || 1); }
      Object.assign(g, {col, row});
      if (Math.min(...S.groups.map(o => o.row)) < 0) S.groups.forEach(o => (o.row += 1));
    } else {
      const from = group(d.gid), b = blockOf(from, d.bid), to = frameAt(p) || from;
      const r = L.rects[to.id];
      const c = Math.max(0, Math.min(r.cols - 1, Math.floor((p.x - r.x - PAD) / (BW + BG))));
      const rr = Math.max(0, Math.floor((p.y - r.y - HEAD) / (BH + BG)));
      from.blocks = from.blocks.filter(x => x !== b);
      const idx = Math.min(to.blocks.length, rr * r.cols + c);
      to.blocks.splice(idx, 0, b);
      if (sel && sel.block === b.id) sel = {group: to.id, block: b.id};
    }
    undoLayout = d.before;
    changed();
    updateUndo();
  });
  const updateUndo = () => { const u = $("#bk-undo"); if (u) u.disabled = !undoLayout; };
  // arrange: frames top to bottom in signal order (each frame one row below the frames that feed it), side by side
  // within a row in the order of what feeds them; frames without connections go to the last row
  function arrange() {
    const before = snapshot();
    const ids = S.groups.map(g => g.id), into = Object.fromEntries(ids.map(id => [id, []]));
    for (const [a, b] of S.links) if (into[b] && into[a] && a !== b) into[b].push(a);
    const linked = new Set(S.links.flatMap(([a, b]) => [a, b]));
    const rank = {}, visiting = new Set();
    const rk = id => {
      if (rank[id] !== undefined) return rank[id];
      if (visiting.has(id)) return 0; // a loop: break it here
      visiting.add(id);
      const r = into[id].length ? 1 + Math.max(...into[id].map(rk)) : 0;
      visiting.delete(id);
      return (rank[id] = r);
    };
    ids.forEach(rk);
    const MAXW = 4; // columns per row before wrapping
    const rows = [];
    const byRank = {};
    for (const g of S.groups) (byRank[linked.has(g.id) ? rank[g.id] : 1e6] ||= []).push(g);
    const pos = {};
    for (const k of Object.keys(byRank).map(Number).sort((a, b) => a - b)) {
      const list = byRank[k].sort((a, b) => {
        const bc = g => { const f = into[g.id].map(id => pos[id]).filter(v => v !== undefined); return f.length ? f.reduce((s, v) => s + v, 0) / f.length : 1e3; };
        return bc(a) - bc(b) || a.col - b.col;
      });
      let row = [], width = 0;
      for (const g of list) {
        const w = Math.min(g.w || 1, MAXW);
        if (width + w > MAXW && row.length) { rows.push(row); row = []; width = 0; }
        row.push(g); width += w;
      }
      if (row.length) rows.push(row);
    }
    rows.forEach((row, r) => { let c = 0; for (const g of row) { g.row = r; g.col = c; pos[g.id] = c + (g.w || 1) / 2; c += g.w || 1; } });
    undoLayout = before;
    view = null;
    changed();
    updateUndo();
  }

  // ---- events
  $("#bk-svg").addEventListener("click", e => {
    if (dragged) { dragged = false; return; }
    const add = e.target.closest("[data-add-to]");
    if (add) { const g = group(add.dataset.addTo); sel = {group: g.id}; render(); showGroup(g, true); return; }
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
    const name = prompt("Frame name (e.g. Power rail, Timing, Networking)");
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
  $("#bk-name").addEventListener("input", () => {
    dirty = true; $("#bk-status").textContent = "Unsaved changes";
    $("#bk-title").textContent = $("#bk-name").value || "New block diagram";
  });
  $("#bk-help-btn").onclick = () => {
    const t = $("#bk-help-text");
    t.hidden = !t.hidden;
    $("#bk-help-btn").setAttribute("aria-expanded", String(!t.hidden));
  };
  $("#bk-save").addEventListener("click", async () => {
    const res = await fetch(configId ? `/api/blocks/designs/${configId}` : "/api/blocks/designs",
      {method: configId ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: $("#bk-name").value, data: S})});
    if (!res.ok) { $("#bk-status").textContent = `Not saved (${res.status})`; return; }
    const out = await res.json();
    if (out.review) { dirty = false; $("#bk-status").textContent = out.message; return; }
    if (!configId) { configId = out.id; history.replaceState(null, "", `/blocks/${configId}${new URLSearchParams(location.search).get("bare") ? "?bare=1" : ""}`); }
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
  const scopeKey = sc => (sc.kind === "all" ? "all" : `${sc.kind}:${sc.group}:${sc.block || ""}`) + (sc.drawable ? ":d" : "");
  const answersFor = sc => ((S.schem ||= {})[scopeKey(sc)] ||= {});
  // with "only blocks we can draw", blocks without a chosen part are not offered (the server also leaves out parts
  // without a pin list and names them)
  function scopes(drawable) {
    const has = b => !drawable || b.part;
    const n = S.groups.reduce((k, g) => k + g.blocks.filter(has).length, 0);
    const out = [{kind: "all", label: drawable ? `Blocks with a part (${n})` : `Whole diagram (${n})`}];
    for (const g of S.groups) { const k = g.blocks.filter(has).length; if (k) out.push({kind: "group", group: g.id, label: `Frame: ${g.label} (${k} block${k === 1 ? "" : "s"})`}); }
    for (const g of S.groups) for (const b of g.blocks.filter(has)) out.push({kind: "block", group: g.id, block: b.id, label: `Block: ${b.label || fnOf(b).label}${b.part ? " · " + b.part : ""} (in ${g.label})`});
    return out.map(x => ({...x, drawable}));
  }
  async function schemCall(drawIt) {
    const res = await fetch("/api/blocks/schematic", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({data: S, scope: schem.scope, answers: answersFor(schem.scope), draw: drawIt, title: $("#bk-name").value || "Block diagram"})});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }
  function openSchem() {
    SCH.hidden = false;
    const drawable = openSchem.drawable !== false;
    const list = scopes(drawable);
    const cur = (sel && sel.block ? list.find(x => x.block === sel.block) : sel ? list.find(x => x.kind === "group" && x.group === sel.group) : null) || list[0];
    SCH.innerHTML = `<h2>Convert to schematic</h2>
      <p class="small muted">Choose what to convert: the whole diagram, one frame (a functional block with the blocks inside it) or a single block.
        BizDev first checks the design rules and asks what it cannot decide; nothing is drawn until you click <b>Draw schematic</b>.</p>
      <div class="row"><label class="small">Convert <select id="sch-scope" class="small-sel">${list.map((x, i) => `<option value="${i}"${x === cur ? " selected" : ""}>${esc(x.label)}</option>`).join("")}</select></label>
        <label class="small"><input type="checkbox" id="sch-drawable"${drawable ? " checked" : ""}> only blocks we can draw (a chosen part with a pin list)</label>
        <button type="button" id="sch-check" class="small-btn">Check design rules</button>
        <button type="button" id="sch-close" class="outline secondary small-btn">Close</button></div>
      <div id="sch-body"></div>`;
    SCH.querySelector("#sch-close").onclick = () => { SCH.hidden = true; };
    SCH.querySelector("#sch-drawable").onchange = e => { openSchem.drawable = e.target.checked; openSchem(); };
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
      ${(c.skipped || []).length ? `<details class="small"><summary>Left out: ${c.skipped.length} block${c.skipped.length === 1 ? "" : "s"} without a part we can draw</summary><p class="muted">${c.skipped.map(esc).join(" · ")}</p></details>` : ""}
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
  $("#bk-arrange").addEventListener("click", arrange);
  $("#bk-undo").addEventListener("click", () => { if (!undoLayout) return; restore(undoLayout); undoLayout = null; changed(); updateUndo(); });

  if (!design.data && tpl) dirty = true;
  // opened with a part placed in it (walk-through "Add to an application"): unsaved until Save is pressed
  if (design.prefill) { dirty = true; $("#bk-status").textContent = design.prefill; }
  if (Object.keys(S.req).length) refreshCounts(); else render();
  // requirements live above the diagram (renderReqs); the drawer is only for a clicked block or group
})();

// "Own window": the same diagram in a separate browser window with only the toolbar and canvas (?bare=1).
document.getElementById("bk-window")?.addEventListener("click", () => {
  const u = new URL(location.href);
  u.searchParams.set("bare", "1");
  u.hash = "";
  window.open(u.toString(), "_blank", `popup,width=${Math.min(screen.availWidth, 1600)},height=${Math.min(screen.availHeight, 1000)}`);
});
