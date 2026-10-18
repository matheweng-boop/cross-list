// CMTI design explorer: margins, edge-speed limits and illustrative losses for the parts on the page.
// Units: volts, nanoseconds, kV/µs (= V/ns), amps, kHz, pF.
(() => {
  const root = document.getElementById("impact");
  if (!root) return;
  const devices = JSON.parse(root.dataset.devices);
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const fmt = (x, d = 1) => (x >= 100 ? x.toFixed(0) : x.toFixed(d));
  const T_MIN = 5, T_MAX = 100;

  function inputs() {
    return {
      v: +$("v").value, t: +$("t").value, m: +root.querySelector("input[name=m]:checked").value,
      i: +$("i").value, f: +$("f").value, c: +$("c").value,
    };
  }
  const margin = (cmti, v, t) => cmti / (v / t); // guaranteed CMTI over actual slew
  const fastestEdge = (cmti, v, m) => (v * m) / cmti; // ns at which the margin drops to m
  const lossW = (v, i, edgeNs, fKhz) => 0.5 * v * i * (2 * edgeNs * 1e-9) * fKhz * 1e3;

  // --- chart ---------------------------------------------------------------------------
  const W = 640, H = 300, L = 46, R = 14, T = 12, B = 34;
  const x = t => L + ((t - T_MIN) / (T_MAX - T_MIN)) * (W - L - R);
  const Y_TICKS = [0.25, 0.5, 1, 2, 4, 8, 16, 32];
  const y = mg => {
    const lo = Math.log2(Y_TICKS[0]), hi = Math.log2(Y_TICKS[Y_TICKS.length - 1]);
    const v = Math.min(Math.max(Math.log2(mg), lo), hi);
    return T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  };
  const withCmti = devices.map((d, k) => ({...d, slot: k + 1})).filter(d => d.cmti);

  function drawChart(p) {
    const grid = Y_TICKS.map(g => `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}"/>` +
      `<text class="tick" x="${L - 6}" y="${y(g) + 4}" text-anchor="end">${g}×</text>`).join("");
    const xt = [5, 20, 40, 60, 80, 100].map(t => `<text class="tick" x="${x(t)}" y="${H - B + 16}" text-anchor="middle">${t}</text>`).join("");
    const lines = withCmti.map(d => {
      const pts = [];
      for (let t = T_MIN; t <= T_MAX; t += 1) pts.push(`${x(t).toFixed(1)},${y(margin(d.cmti, p.v, t)).toFixed(1)}`);
      return `<polyline class="series s${d.slot}" points="${pts.join(" ")}"/>`;
    }).join("");
    const target = `<line class="target" x1="${L}" x2="${W - R}" y1="${y(p.m)}" y2="${y(p.m)}"/>` +
      `<text class="tick" x="${W - R}" y="${y(p.m) - 5}" text-anchor="end">target ${p.m}×</text>`;
    const now = `<line class="now" x1="${x(p.t)}" x2="${x(p.t)}" y1="${T}" y2="${H - B}"/>` +
      withCmti.map(d => `<circle class="dot s${d.slot}" cx="${x(p.t)}" cy="${y(margin(d.cmti, p.v, p.t))}" r="4"/>`).join("");
    $("chart").innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Margin against edge duration">` +
      `<rect class="surface" x="0" y="0" width="${W}" height="${H}"/>${grid}${xt}` +
      `<text class="tick" x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle">switching-edge duration (ns) →  slower</text>` +
      target + lines + now +
      `<line class="cross" id="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/>` +
      `<rect class="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></svg>` +
      `<div class="chart-tip" id="tip" hidden></div>`;
    const svg = $("chart").querySelector("svg"), hit = svg.querySelector(".hit"), tip = $("tip"), cross = $("cross");
    const move = ev => {
      const pt = svg.createSVGPoint();
      pt.x = ev.clientX; pt.y = ev.clientY;
      const loc = pt.matrixTransform(svg.getScreenCTM().inverse());
      const t = Math.round(T_MIN + ((loc.x - L) / (W - L - R)) * (T_MAX - T_MIN));
      if (t < T_MIN || t > T_MAX) return;
      cross.setAttribute("x1", x(t)); cross.setAttribute("x2", x(t)); cross.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.innerHTML = `<b>${t} ns</b> · ${fmt(p.v / t)} kV/µs` + withCmti.map(d =>
        `<div><span class="key s${d.slot}"></span>${esc(d.mpn)}: ${fmt(margin(d.cmti, p.v, t), 2)}×</div>`).join("");
      const box = $("chart").getBoundingClientRect();
      tip.style.left = Math.min(ev.clientX - box.left + 12, box.width - 180) + "px";
      tip.style.top = "8px";
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  }

  // --- tables and text ------------------------------------------------------------------
  function render() {
    const p = inputs();
    $("o-v").textContent = `${p.v} V`;
    $("o-t").textContent = `${p.t} ns`;
    $("o-i").textContent = `${p.i} A`;
    $("o-f").textContent = `${p.f} kHz`;
    $("o-c").textContent = `${p.c.toFixed(1)} pF`;
    const slew = p.v / p.t;
    $("slew").textContent = fmt(slew);
    $("need").textContent = fmt(slew * p.m);
    $("legend").innerHTML = withCmti.map(d => `<li><span class="key s${d.slot}"></span>${esc(d.mpn)} <span class="muted">${esc(d.maker)}${d.slot === 1 ? " · reference" : ""}</span></li>`).join("");
    drawChart(p);

    $("rows").innerHTML = devices.map((d, k) => {
      const key = d.cmti ? `<span class="key s${k + 1}"></span>` : "";
      if (!d.cmti) return `<tr><td>${esc(d.mpn)}</td><td colspan="4" class="muted">CMTI not in data</td></tr>`;
      const mg = margin(d.cmti, p.v, p.t), ok = mg >= p.m;
      return `<tr><td>${key}<b>${esc(d.mpn)}</b><br><small class="muted">${esc(d.maker)}</small></td><td>${d.cmti} kV/µs</td>` +
        `<td>${fmt(mg, 2)}×</td><td>${fmt(fastestEdge(d.cmti, p.v, p.m))} ns</td>` +
        `<td><span class="state ${ok ? "good" : "bad"}">${ok ? "✓ Yes" : "✗ No"}</span></td></tr>`;
    }).join("");

    const ok = withCmti.filter(d => margin(d.cmti, p.v, p.t) >= p.m);
    const short = withCmti.filter(d => margin(d.cmti, p.v, p.t) < p.m);
    let text = `At ${p.v} V and ${p.m}× margin: ` + withCmti.map(d => `${d.mpn} holds down to ${fmt(fastestEdge(d.cmti, p.v, p.m))} ns edges`).join("; ") + ". ";
    if (short.length === 0 && withCmti.length > 1) {
      text += `Your ${p.t} ns edge is within every part's margin, so the higher CMTI rating gives no functional advantage at this operating point; it matters once edges get faster than ${fmt(Math.max(...withCmti.map(d => fastestEdge(d.cmti, p.v, p.m))))} ns.`;
    } else if (short.length) {
      text += `At ${p.t} ns, ${short.map(d => d.mpn).join(", ")} fall${short.length === 1 ? "s" : ""} short of the target: keep it only by slowing the edges${ok.length ? ` or use ${ok.map(d => d.mpn).join(", ")}` : ""}.`;
    }
    $("boundary").textContent = text;

    const base = lossW(p.v, p.i, p.t, p.f);
    $("loss").innerHTML = withCmti.map(d => {
      const edge = Math.max(p.t, fastestEdge(d.cmti, p.v, p.m)), w = lossW(p.v, p.i, edge, p.f), extra = w - base;
      return `<tr><td><span class="key s${d.slot}"></span>${esc(d.mpn)}</td><td>${fmt(edge)} ns${edge > p.t ? " (slowed)" : ""}</td>` +
        `<td>${fmt(w)} W</td><td>${extra > 0.05 ? `+${fmt(extra)} W` : "same"}</td></tr>`;
    }).join("");

    $("icm").textContent = fmt(p.c * slew); // pF × V/ns = mA
    $("q").textContent = fmt((p.c * p.v) / 1000, 2); // pF × V = pC → nC
  }

  root.querySelectorAll("input").forEach(el => el.addEventListener("input", render));
  render();
})();
