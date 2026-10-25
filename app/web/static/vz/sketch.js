// Small plotting helpers shared by the broadcast-radio visuals (signal flow, RDS): a spectrum or time-domain sketch
// with plausible axes, drawn as an inline SVG string. No libraries. window.VZ_SKETCH, loaded before flow.js / rds.js.
(() => {
  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
  const lin = (a, b, n) => Array.from({length: n}, (_, i) => a + ((b - a) * i) / (n - 1));
  const rnd = seed => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const gauss = r => Math.sqrt(-2 * Math.log(Math.max(1e-9, r()))) * Math.cos(2 * Math.PI * r());
  const pw = d => 10 ** (d / 10), toDb = p => 10 * Math.log10(Math.max(p, 1e-30));
  const sumDb = (...d) => toDb(d.reduce((a, x) => a + pw(x), 0));  // power sum of levels in dB
  const brick = (f, c, half, lev, n = 10) => lev + toDb(1 / (1 + ((f - c) / half) ** (2 * n)));  // flat-topped block (OFDM)
  const bell = (f, c, w, lev) => lev - 12 * ((f - c) / w) ** 2;  // a rounded station, 12 dB down at c ± w
  const spec = (x0, x1, fn, n = 260) => lin(x0, x1, n).map(f => [f, fn(f)]);

  // o: {label, x: [x0, x1], y: [y0, y1], xt: [[v, text]], yt: [[v, text]], xlab, ylab, series: [{pts, color, fill,
  //     dots, stems, dash, width}], areas: [{pts: [[x, lo, hi]], color}], bands: [[x0, x1, text, color]],
  //     vlines: [[x, text, color]], note}
  function plot(o) {
    const W = o.w || 300, H = o.h || 132, L = 36, R = 8, T = 16, B = 28;
    const [x0, x1] = o.x, [y0, y1] = o.y;
    const X = v => L + ((v - x0) / (x1 - x0)) * (W - L - R);
    const Y = v => T + (1 - (Math.max(y0, Math.min(y1, v)) - y0) / (y1 - y0)) * (H - T - B);
    const P = ([a, b]) => `${X(a).toFixed(1)},${Y(b).toFixed(1)}`;
    let s = `<svg viewBox="0 0 ${W} ${H}" class="sk-svg" role="img" aria-label="${esc(o.label)}">`
      + `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="#fcfcfd" stroke="#e3e6ea"/>`;
    for (const [a, b, t, c] of o.bands || []) {
      s += `<rect x="${X(a).toFixed(1)}" y="${T}" width="${Math.max(1, X(b) - X(a)).toFixed(1)}" height="${H - T - B}" fill="${c || "#8a94a3"}" opacity=".13"/>`;
      if (t) s += `<text x="${((X(a) + X(b)) / 2).toFixed(1)}" y="${T + 9}" text-anchor="middle" class="sk-t" fill="${c || "#3a4450"}">${esc(t)}</text>`;
    }
    for (const a of o.areas || []) {
      const up = a.pts.map(([x, , hi]) => P([x, hi])), lo = a.pts.slice().reverse().map(([x, l]) => P([x, l]));
      s += `<polygon points="${up.concat(lo).join(" ")}" fill="${a.color}" opacity="${a.opacity || 0.55}"/>`;
    }
    for (const sr of o.series || []) {
      const c = sr.color || "#1f5fa8";
      if (sr.fill) s += `<polygon points="${X(sr.pts[0][0]).toFixed(1)},${Y(y0)} ${sr.pts.map(P).join(" ")} ${X(sr.pts[sr.pts.length - 1][0]).toFixed(1)},${Y(y0)}" fill="${c}" opacity=".18"/>`;
      if (sr.stems) s += sr.pts.map(p => `<line x1="${X(p[0]).toFixed(1)}" x2="${X(p[0]).toFixed(1)}" y1="${Y(sr.base ?? 0).toFixed(1)}" y2="${Y(p[1]).toFixed(1)}" stroke="${c}" stroke-width="${sr.width || 1}"/>`).join("");
      if (sr.dots) s += sr.pts.map(p => `<circle cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="${sr.r || 1.8}" fill="${c}"/>`).join("");
      if (!sr.dots && !sr.stems) s += `<polyline fill="none" stroke="${c}" stroke-width="${sr.width || 1.5}"${sr.dash ? ` stroke-dasharray="${sr.dash}"` : ""} points="${sr.pts.map(P).join(" ")}"/>`;
      if (sr.label) { const p = sr.pts[sr.at ?? Math.floor(sr.pts.length * 0.75)]; s += `<text x="${X(p[0]).toFixed(1)}" y="${(Y(p[1]) - 4).toFixed(1)}" text-anchor="middle" class="sk-t" fill="${c}">${esc(sr.label)}</text>`; }
    }
    for (const [v, t, c] of o.vlines || []) {
      s += `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${T}" y2="${H - B}" stroke="${c || "#b42318"}" stroke-dasharray="3 3"/>`;
      if (t) s += `<text x="${(X(v) + 3).toFixed(1)}" y="${T + 19}" class="sk-t" fill="${c || "#b42318"}">${esc(t)}</text>`;
    }
    for (const [v, t] of o.xt || []) s += `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${H - B}" y2="${H - B + 3}" stroke="#8a94a3"/><text x="${X(v).toFixed(1)}" y="${H - B + 12}" text-anchor="middle" class="sk-t">${esc(t)}</text>`;
    for (const [v, t] of o.yt || []) s += `<text x="${L - 3}" y="${(Y(v) + 3).toFixed(1)}" text-anchor="end" class="sk-t">${esc(t)}</text>`;
    s += `<text x="${(L + W - R) / 2}" y="${H - 3}" text-anchor="middle" class="sk-t sk-ax">${esc(o.xlab || "")}</text>`
      + `<text x="${L + 3}" y="${T - 5}" class="sk-t sk-ax">${esc(o.ylab || "")}</text>`;
    if (o.note) s += `<text x="${W - R}" y="${T - 5}" text-anchor="end" class="sk-t" fill="#6b7280">${esc(o.note)}</text>`;
    return s + "</svg>";
  }
  window.VZ_SKETCH = {esc, lin, rnd, gauss, pw, toDb, sumDb, brick, bell, spec, plot};
})();
