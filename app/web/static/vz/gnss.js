// Interactive GNSS visuals (owner, 28 Oct 2026: "how it works, how the bands are divided up ... cool visualizations of
// how positioning works"). Four visuals that register with the visuals engine in visuals.js (window.VZ_ADD):
//   gnssbands  the band plan of every constellation with the interferers around it
//   gnsstri    pseudoranges, the receiver clock error and why one more satellite than dimensions is needed
//   gnssdop    satellite geometry and dilution of precision
//   gnssiono   the ionospheric delay against frequency and the dual-frequency correction
// The maths sits in window.VZ_GNSS (plain functions, no page) so the tests can check it. Simplified 2-D geometry is
// marked est on the page. Frequencies: ESA Navipedia signal plans and the RF bands chart.
(() => {
  const C0 = 299792458;
  const F = {L1: 1575.42, L2: 1227.6, L5: 1176.45, E5b: 1207.14, E6: 1278.75, B1I: 1561.098, B3I: 1268.52, G1: 1602, G2: 1246};
  // code delay in metres for a slant TEC in TECU at f MHz (Navipedia, Ionospheric Delay: 40.3e16 / f^2 per TECU)
  const ionoDelay = (tec, fMHz) => (40.3e16 * tec) / (fMHz * 1e6) ** 2;
  // ionosphere-free combination of two code ranges and how much it amplifies (uncorrelated) noise
  function ionoFree(p1, p2, f1 = F.L1, f2 = F.L5) {
    const g1 = f1 ** 2 / (f1 ** 2 - f2 ** 2), g2 = -(f2 ** 2) / (f1 ** 2 - f2 ** 2);
    return {range: g1 * p1 + g2 * p2, a: g1, b: g2, noise: Math.hypot(g1, g2)};
  }
  // 3x3 and 2x2 helpers
  const inv3 = m => {
    const [a, b, c] = m[0], [d, e, f] = m[1], [g, h, i] = m[2];
    const A = e * i - f * h, B = -(d * i - f * g), Cc = d * h - e * g, det = a * A + b * B + c * Cc;
    if (Math.abs(det) < 1e-12) return null;
    return [[A, -(b * i - c * h), b * f - c * e], [B, a * i - c * g, -(a * f - c * d)], [Cc, -(a * h - b * g), a * e - b * d]].map(r => r.map(x => x / det));
  };
  // 2-D DOP for satellites at the given azimuths (degrees), all seen at the same elevation (est: planar model);
  // unknowns east, north and the receiver clock
  function dop(az) {
    if (az.length < 3) return null;
    const G = az.map(a => [-Math.sin((a * Math.PI) / 180), -Math.cos((a * Math.PI) / 180), 1]);
    const N = [0, 1, 2].map(i => [0, 1, 2].map(j => G.reduce((s, r) => s + r[i] * r[j], 0)));
    const Q = inv3(N);
    if (!Q) return null;
    return {hdop: Math.sqrt(Q[0][0] + Q[1][1]), tdop: Math.sqrt(Q[2][2]), gdop: Math.sqrt(Q[0][0] + Q[1][1] + Q[2][2]), Q};
  }
  // least-squares position from pseudoranges in 2-D; solveClock: also estimate the common clock range offset
  function solve(sats, pr, solveClock, start = [50, 40]) {
    let x = start[0], y = start[1], b = 0;
    for (let it = 0; it < 30; it++) {
      const rows = sats.map(([sx, sy], k) => {
        const r = Math.hypot(x - sx, y - sy) || 1e-9;
        return {g: [(x - sx) / r, (y - sy) / r, 1], res: pr[k] - (r + b)};
      });
      const n = solveClock ? 3 : 2;
      const N = [...Array(n)].map((_, i) => [...Array(n)].map((_, j) => rows.reduce((s, r) => s + r.g[i] * r.g[j], 0)));
      const u = [...Array(n)].map((_, i) => rows.reduce((s, r) => s + r.g[i] * r.res, 0));
      let d;
      if (n === 3) { const Q = inv3(N); if (!Q) break; d = Q.map(r => r[0] * u[0] + r[1] * u[1] + r[2] * u[2]); }
      else { const det = N[0][0] * N[1][1] - N[0][1] * N[1][0]; if (Math.abs(det) < 1e-12) break; d = [(N[1][1] * u[0] - N[0][1] * u[1]) / det, (N[0][0] * u[1] - N[1][0] * u[0]) / det]; }
      x += d[0]; y += d[1]; if (n === 3) b += d[2];
      if (Math.hypot(...d) < 1e-6) break;
    }
    return {x, y, b};
  }
  window.VZ_GNSS = {F, ionoDelay, ionoFree, dop, solve};

  (window.VZ_ADD = window.VZ_ADD || []).push(({V, C, num, esc, range}) => {
    const est = '<span class="kn-est" title="BizDev\'s own reasoning or simplification, not from a source">est</span>';
    const links = `<p class="small">More: <a href="/engineering/gnss_how_it_works">GNSS: how satellite positioning works</a> · <a href="/reviews/how/gnss">Part knowledge: GNSS front-end parts</a> · <a href="/library/gnss_frontend">Systems library: automotive GNSS front ends</a></p>`;
    const svgOpen = (w, h, label) => `<svg viewBox="0 0 ${w} ${h}" class="gn-svg" role="img" aria-label="${esc(label)}" style="width:100%;height:auto;max-width:${w}px;display:block" font-size="12">`;

    // ---------------------------------------------------------------- 1 · band plan
    const SYS = {GPS: C.blue, Galileo: C.teal, BeiDou: C.red, GLONASS: C.purple, "QZSS / NavIC": C.orange};
    const GBANDS = [
      ["L5 / E5a / B2a", 1164, 1189, ["GPS", "Galileo", "BeiDou", "QZSS / NavIC"]], ["E5b / B2b", 1197, 1217, ["Galileo", "BeiDou"]],
      ["L2", 1217, 1238, ["GPS", "QZSS / NavIC"]], ["G2", 1242, 1249, ["GLONASS"]], ["E6 / B3 / L6", 1258, 1299, ["Galileo", "BeiDou", "QZSS / NavIC"]],
      ["B1I", 1559, 1563, ["BeiDou"]], ["L1 / E1 / B1C", 1563, 1588, ["GPS", "Galileo", "BeiDou", "QZSS / NavIC"]], ["G1", 1598, 1606, ["GLONASS"]],
      ["NavIC S", 2483.5, 2500, ["QZSS / NavIC"]]];
    const NEAR = [["L-band LTE / 5G downlink (B11/21/32, n75)", 1427, 1517], ["MSS / NTN downlink (Inmarsat)", 1525, 1559], ["B13/B14 2nd harmonic", 1554, 1596],
      ["Iridium", 1616, 1626.5], ["NTN / MSS uplink", 1626.5, 1660.5], ["LTE B3 uplink", 1710, 1785]];
    const WIDE = [["LTE low band (incl. B13/B14 uplink 777-798)", 699, 960], ["LTE / 5G mid band", 1710, 2200], ["Wi-Fi 2.4 GHz", 2400, 2483.5],
      ["5G n77 / n78", 3300, 4200], ["Wi-Fi 5 GHz", 5150, 5850], ["V2X 5.9 GHz", 5855, 5925], ["Wi-Fi 6E / 7", 5925, 7125]];
    function bandsSvg(v) {
      const wide = v.view === "wide", W = 720, H = wide ? 300 : 330, x0 = 20, x1 = W - 20;
      const lo = wide ? 600 : 1140, hi = wide ? 7200 : 1680;
      const X = f => (wide ? x0 + ((Math.log10(f) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (x1 - x0) : x0 + ((f - lo) / (hi - lo)) * (x1 - x0));
      let s = svgOpen(W, H, "GNSS band plan with nearby interferers");
      const axisY = H - 40;
      s += `<line x1="${x0}" y1="${axisY}" x2="${x1}" y2="${axisY}" stroke="currentColor"/>`;
      const ticks = wide ? [700, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 7000] : [1150, 1200, 1250, 1300, 1350, 1400, 1450, 1500, 1550, 1600, 1650];
      for (const t of ticks) s += `<line x1="${X(t)}" y1="${axisY}" x2="${X(t)}" y2="${axisY + 5}" stroke="currentColor"/><text x="${X(t)}" y="${axisY + 18}" text-anchor="middle" fill="currentColor">${t}</text>`;
      s += `<text x="${x1}" y="${axisY + 34}" text-anchor="end" fill="currentColor" opacity=".7">MHz${wide ? " (log scale)" : ""}</text>`;
      const sysList = Object.keys(SYS);
      GBANDS.filter(b => b[2] < hi && b[1] > lo).forEach((b, i) => {
        const on = v.sys === "all" || b[3].includes(v.sys);
        const xa = X(Math.max(b[1], lo)), xb = X(Math.min(b[2], hi)), w = Math.max(3, xb - xa);
        b[3].forEach(sy => {
          const row = sysList.indexOf(sy), y = 30 + row * 26;
          s += `<rect x="${xa}" y="${y}" width="${w}" height="20" rx="3" fill="${SYS[sy]}" opacity="${on ? 0.85 : 0.15}"><title>${esc(b[0])} · ${esc(sy)} · ${b[1]}-${b[2]} MHz</title></rect>`;
        });
        if (!wide || i % 1 === 0) s += `<text x="${(xa + xb) / 2}" y="${30 + sysList.length * 26 + 4}" text-anchor="middle" fill="currentColor" font-size="10" transform="rotate(-35 ${(xa + xb) / 2} ${30 + sysList.length * 26 + 4})" opacity="${on ? 1 : 0.4}">${esc(b[0])}</text>`;
      });
      sysList.forEach((sy, row) => { s += `<text x="${x0 + 2}" y="${30 + row * 26 + 14}" fill="currentColor" font-size="11" font-weight="600" opacity=".9">${esc(sy)}</text>`; });
      const intf = (wide ? [...WIDE, ["NTN / MSS (L-band)", 1525, 1660.5]] : NEAR).filter(b => b[2] > lo && b[1] < hi);
      intf.forEach((b, i) => {
        const xa = X(Math.max(b[1], lo)), xb = X(Math.min(b[2], hi)), y = axisY - 26 - (i % 3) * 14;
        s += `<rect x="${xa}" y="${y}" width="${Math.max(3, xb - xa)}" height="10" fill="${C.orange}" opacity="${v.intf === "on" ? 0.45 : 0}"><title>${esc(b[0])}: ${b[1]}-${b[2]} MHz</title></rect>`;
        if (v.intf === "on") s += `<text x="${Math.min(xb + 3, x1 - 2)}" y="${y + 9}" fill="currentColor" font-size="9.5" text-anchor="${xb + 120 > x1 ? "end" : "start"}">${esc(b[0])}</text>`;
      });
      return s + "</svg>";
    }
    V.push({
      id: "gnssbands", group: "GNSS", title: "GNSS band plan and the interferers around it",
      explains: [["GNSS front-end parts", "/reviews/how/gnss"], ["Systems library: automotive GNSS", "/library/gnss_frontend"]],
      lead: "Every constellation transmits in a few L-band slots; several share the same centre frequency so one antenna serves them all. Strong transmitters sit right next to these weak signals.",
      controls: [
        {k: "view", label: "View", type: "select", options: [["gnss", "GNSS bands, 1.14-1.68 GHz"], ["wide", "Wide view, 0.6-7.2 GHz (car radios)"]], value: "gnss"},
        {k: "sys", label: "Highlight", type: "select", options: [["all", "All constellations"], ...Object.keys(SYS).map(k => [k, k])], value: "all"},
        {k: "intf", label: "Interferers", type: "select", options: [["on", "Show"], ["off", "Hide"]], value: "on"},
      ],
      compute(v) {
        const n = GBANDS.filter(b => v.sys === "all" || b[3].includes(v.sys)).length;
        return {
          nochart: true,
          outputs: [["L1 / E1 / B1C centre", `${F.L1} MHz`], ["L5 / E5a / B2a centre", `${F.L5} MHz`], ["Bands of the highlighted system", String(n)],
            ["B13/B14 uplink × 2", "1554-1596 MHz: on L1", "bad"]],
          eq: "f<sub>harmonic</sub> = 2 × f<sub>uplink</sub>: 2 × 777-798 MHz = 1554-1596 MHz",
          eqn: "Shared centres: GPS L1 = Galileo E1 = BeiDou B1C = 1575.42 MHz · GPS L5 = Galileo E5a = BeiDou B2a = 1176.45 MHz",
          html: bandsSvg(v) + `<p class="small">Coloured bars: the bands each system uses (hover for the edges). Orange: transmitters and signals next to or inside the GNSS bands. 1559-1610 MHz and 1164-1214 MHz are also protected for aviation; L2 and E6 share their band with ground radars.</p>${links}`,
          note: "Band edges rounded to the published signal bandwidths; GLONASS G1 / G2 are spread over several channels (FDMA).",
        };
      },
      related: [["RF bands chart", "/rf-bands"], ["Cascaded noise figure", "#nf"], ["Band-pass filter", "#filter"]],
    });

    // ---------------------------------------------------------------- 2 · pseudoranges and the clock
    const SATS = [[8, 92], [50, 98], [93, 90], [28, 96]];
    const RX = [55, 32];
    const NOISE = [0.6, -0.8, 0.4, -0.3];
    function triSvg(v, sol) {
      const n = +v.n, W = 420, H = 300, sx = W / 100, sy = H / 110;
      const P = ([x, y]) => [x * sx, H - y * sy];
      const cb = +v.clk;
      let s = svgOpen(W, H, "Satellites with pseudorange circles and the receiver position");
      s += `<rect x="0" y="${H - 18 * sy}" width="${W}" height="${18 * sy}" fill="${C.green}" opacity=".08"/>`;
      SATS.slice(0, n).forEach((sat, k) => {
        const tr = Math.hypot(RX[0] - sat[0], RX[1] - sat[1]), pr = tr + cb + v.noise * NOISE[k];
        const [cx, cy] = P(sat);
        s += `<circle cx="${cx}" cy="${cy}" r="${pr * sx}" fill="none" stroke="${C.orange}" stroke-width="1.5" stroke-dasharray="5 4" opacity=".9"/>`;
        if (v.fix === "on" && sol) s += `<circle cx="${cx}" cy="${cy}" r="${Math.max(0, pr - sol.b) * sx}" fill="none" stroke="${C.blue}" stroke-width="1.5" opacity=".8"/>`;
        s += `<circle cx="${cx}" cy="${cy}" r="7" fill="${C.purple}"/><text x="${cx}" y="${cy + 20}" text-anchor="middle" fill="currentColor" font-size="11">sat ${k + 1}</text>`;
      });
      const [rx, ry] = P(RX);
      s += `<circle cx="${rx}" cy="${ry}" r="6" fill="${C.green}"/><text x="${rx + 9}" y="${ry + 4}" fill="currentColor" font-size="11">true position</text>`;
      if (sol && isFinite(sol.x)) {
        const [ex, ey] = P([sol.x, sol.y]);
        s += `<path d="M${ex - 7} ${ey - 7}L${ex + 7} ${ey + 7}M${ex - 7} ${ey + 7}L${ex + 7} ${ey - 7}" stroke="${C.red}" stroke-width="2.5"/><text x="${ex + 9}" y="${ey - 6}" fill="currentColor" font-size="11">estimate</text>`;
      }
      return s + "</svg>";
    }
    V.push({
      id: "gnsstri", group: "GNSS", title: "Pseudoranges: why the receiver clock needs one more satellite",
      explains: [["GNSS: how positioning works", "/engineering/gnss_how_it_works"]],
      lead: "Each satellite gives a range circle. The receiver's cheap clock adds the same error to every range, so the circles do not meet. With one more satellite than dimensions the receiver solves for the clock error too.",
      controls: [
        {k: "clk", label: "Receiver clock error, as a range (1 ns = 0.3 m)", min: -15, max: 15, step: 0.5, value: 6, unit: "units"},
        {k: "n", label: "Satellites used", type: "select", options: [["2", "2 (position only, clock not solved)"], ["3", "3 (position + clock, 2-D)"], ["4", "4 (more than needed: least squares)"]], value: "3"},
        {k: "noise", label: "Range noise (multipath, atmosphere)", min: 0, max: 4, step: 0.1, value: 0, unit: "units"},
        {k: "fix", label: "Show circles corrected by the solved clock", type: "select", options: [["on", "Yes"], ["off", "No"]], value: "on"},
      ],
      compute(v) {
        const n = +v.n, sats = SATS.slice(0, n);
        const pr = sats.map((sat, k) => Math.hypot(RX[0] - sat[0], RX[1] - sat[1]) + v.clk + v.noise * NOISE[k]);
        const sol = solve(sats, pr, n >= 3, [45, 35]);
        const err = Math.hypot(sol.x - RX[0], sol.y - RX[1]);
        return {
          nochart: true,
          outputs: [["Unknowns", n >= 3 ? "x, y and clock" : "x, y only"], ["Clock error put in", `${num(v.clk)} units`],
            ["Clock error solved", n >= 3 ? `${num(sol.b)} units` : "not solved"], ["Position error", `${num(err)} units`, err < 1 ? "ok" : err < 4 ? "warn" : "bad"]],
          eq: "ρ<sub>i</sub> = |s<sub>i</sub> − r| + c·δt + ε<sub>i</sub> &nbsp;·&nbsp; unknowns: r (2-D here, 3-D in reality) and c·δt → 3 satellites in 2-D, 4 in 3-D",
          eqn: `${n} ranges, ${n >= 3 ? 3 : 2} unknowns · solved c·δt = ${n >= 3 ? num(sol.b) : "–"} · position error ${num(err)}`,
          html: triSvg(v, n >= 3 ? sol : {...sol, b: 0}) + `<p class="small">Orange dashed: the measured pseudoranges. Blue: the same circles after subtracting the solved clock error; they meet at the estimate (red cross). With 2 satellites the clock cannot be solved and the estimate moves with the clock error. A flat 2-D picture ${est}; in 3-D the same logic needs 4 satellites.</p>${links}`,
          note: "Units are arbitrary distance units; real ranges are about 20 000 km and 1 µs of clock error equals 300 m.",
        };
      },
      related: [["Satellite geometry (DOP)", "#gnssdop"], ["GNSS band plan", "#gnssbands"]],
    });

    // ---------------------------------------------------------------- 3 · DOP
    function dopSvg(az, ell, sigma) {
      const W = 360, H = 360, cx = 180, cy = 180, R = 150;
      let s = svgOpen(W, H, "Sky plot with satellites and the position error ellipse");
      s += `<circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="currentColor" opacity=".5"/><circle cx="${cx}" cy="${cy}" r="${R / 2}" fill="none" stroke="currentColor" opacity=".25"/>`;
      for (const [t, a] of [["N", 0], ["E", 90], ["S", 180], ["W", 270]]) {
        const x = cx + (R + 12) * Math.sin((a * Math.PI) / 180), y = cy - (R + 12) * Math.cos((a * Math.PI) / 180);
        s += `<text x="${x}" y="${y + 4}" text-anchor="middle" fill="currentColor" font-size="12">${t}</text>`;
      }
      az.forEach(a => {
        const x = cx + R * 0.75 * Math.sin((a * Math.PI) / 180), y = cy - R * 0.75 * Math.cos((a * Math.PI) / 180);
        s += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${C.grey}" stroke-dasharray="3 3"/><circle cx="${x}" cy="${y}" r="8" fill="${C.purple}"/>`;
      });
      if (ell) {
        const k = 12 * sigma;  // px per unit of 1-sigma error (est scale)
        s += `<ellipse cx="${cx}" cy="${cy}" rx="${Math.min(R, ell.a * k)}" ry="${Math.min(R, ell.b * k)}" transform="rotate(${-ell.ang} ${cx} ${cy})" fill="${C.orange}" opacity=".35" stroke="${C.orange}"/>`;
      }
      return s + `<circle cx="${cx}" cy="${cy}" r="4" fill="${C.green}"/></svg>`;
    }
    V.push({
      id: "gnssdop", group: "GNSS", title: "Satellite geometry: dilution of precision (DOP)",
      explains: [["GNSS: how positioning works", "/engineering/gnss_how_it_works"]],
      lead: "The same range error gives a small or a large position error depending on where the satellites are. Spread them over the sky and the error ellipse shrinks; bunch them together (a street canyon) and it stretches.",
      controls: [
        {k: "n", label: "Satellites", min: 3, max: 10, step: 1, value: 6, unit: ""},
        {k: "span", label: "Spread across the sky (azimuth span)", min: 20, max: 360, step: 5, value: 300, unit: "°"},
        {k: "dir", label: "Direction of the open sky", min: 0, max: 355, step: 5, value: 0, unit: "°"},
        {k: "sigma", label: "Range error (1 σ)", min: 0.5, max: 10, step: 0.5, value: 3, unit: "m"},
      ],
      compute(v) {
        const n = Math.round(v.n), span = Math.min(360, v.span);
        const az = Array.from({length: n}, (_, i) => (v.dir - span / 2 + (span === 360 ? (360 * i) / n : (span * i) / (n - 1)) + 720) % 360);
        const d = dop(az);
        let ell = null;
        if (d) {
          const [[a, b], [, c]] = [d.Q[0].slice(0, 2), d.Q[1].slice(0, 2)];
          const tr = a + c, det = a * c - b * b, l1 = tr / 2 + Math.sqrt(Math.max(0, tr * tr / 4 - det)), l2 = tr / 2 - Math.sqrt(Math.max(0, tr * tr / 4 - det));
          const ang = (Math.atan2(l1 - a, b || 1e-9) * 180) / Math.PI;
          ell = {a: Math.sqrt(Math.max(l1, 0)), b: Math.sqrt(Math.max(l2, 0)), ang};  // ang: from east towards north
        }
        const h = d ? d.hdop : NaN;
        return {
          nochart: true,
          outputs: [["HDOP (horizontal)", d ? num(h) : "no fix"], ["Horizontal error (1 σ) ≈ HDOP × σ", d ? `${num(h * v.sigma)} m` : "–", !d ? "bad" : h < 2 ? "ok" : h < 5 ? "warn" : "bad"],
            ["Geometry", !d ? "too few or in a line" : h < 2 ? "good" : h < 5 ? "fair" : "poor"], ["Satellites", String(n)]],
          eq: "position error ≈ DOP × range error &nbsp;·&nbsp; DOP = √(trace of (GᵀG)⁻¹) over the position terms, G = unit vectors to the satellites plus a clock column",
          eqn: d ? `HDOP = ${num(h)} · ${num(h)} × ${num(v.sigma)} m = ${num(h * v.sigma)} m` : "GᵀG cannot be inverted: no position",
          html: dopSvg(az, ell, v.sigma / 3) + `<p class="small">Sky plot from above: north up, satellites in purple, the orange ellipse shows the 1-σ horizontal error (scaled). Narrow the spread or point the open sky down a street and watch the ellipse stretch across the street. Planar model with all satellites at one elevation ${est}.</p>${links}`,
          note: "Real receivers use 3-D geometry with elevation; vertical DOP is usually worse than horizontal because no satellite is below the horizon.",
        };
      },
      related: [["Pseudoranges and the clock", "#gnsstri"], ["Dual-frequency ionosphere correction", "#gnssiono"]],
    });

    // ---------------------------------------------------------------- 4 · ionosphere
    V.push({
      id: "gnssiono", group: "GNSS", title: "Ionosphere: why dual frequency (L1 + L5) removes the delay",
      explains: [["GNSS front-end parts (L1 + L5)", "/reviews/how/gnss"], ["GNSS: how positioning works", "/engineering/gnss_how_it_works"]],
      lead: "The ionosphere slows the signal by an amount that falls with the square of the frequency. Measure the same range on L1 and L5 and the difference reveals the delay, which can then be removed.",
      controls: [
        {k: "tec", label: "Slant electron content (TECU)", min: 1, max: 150, value: 30, unit: "TECU", log: true},
        {k: "sig", label: "Code noise per frequency (1 σ)", min: 0.1, max: 3, step: 0.1, value: 0.5, unit: "m"},
        {k: "pair", label: "Frequency pair", type: "select", options: [["L5", "L1 + L5 (1575.42 / 1176.45 MHz)"], ["L2", "L1 + L2 (1575.42 / 1227.60 MHz)"], ["E5b", "L1 + E5b (1575.42 / 1207.14 MHz)"]], value: "L5"},
      ],
      compute(v) {
        const f2 = F[v.pair], d1 = ionoDelay(v.tec, F.L1), d2 = ionoDelay(v.tec, f2), IF = ionoFree(0, 0, F.L1, f2);
        const fs = range(1100, 1650, 80);
        return {
          outputs: [["Delay on L1", `${num(d1)} m`], [`Delay on ${v.pair}`, `${num(d2)} m`], ["Left after the dual-frequency combination", "≈ 0 m (first order)", "ok"],
            ["Noise after combining", `${num(IF.noise * v.sig)} m (× ${num(IF.noise)})`, IF.noise < 3 ? "warn" : "bad"]],
          eq: "I<sub>f</sub> = 40.3 · TEC / f² &nbsp;·&nbsp; ρ<sub>IF</sub> = (f<sub>1</sub>² ρ<sub>1</sub> − f<sub>2</sub>² ρ<sub>2</sub>) / (f<sub>1</sub>² − f<sub>2</sub>²)",
          eqn: `I<sub>L1</sub> = 40.3 × ${num(v.tec)}·10¹⁶ / (${F.L1} MHz)² = ${num(d1)} m · I<sub>${v.pair}</sub> = ${num(d2)} m · weights ${num(IF.a)} and ${num(IF.b)} → noise × ${num(IF.noise)}`,
          chart: {x: {min: 1100, max: 1650, label: "Frequency (MHz)"}, y: {min: 0, max: Math.max(5, ionoDelay(v.tec, 1100) * 1.1), label: "Ionospheric code delay (m)"},
            series: [{pts: fs.map(f => [f, ionoDelay(v.tec, f)]), width: 3, label: "delay ∝ 1/f²"}],
            vlines: [{x: F.L5, label: "L5", color: C.blue}, {x: F.L2, label: "L2", row: 1}, {x: F.E5b, label: "E5b", row: 2}, {x: F.L1, label: "L1", color: C.blue}],
            marks: [{x: F.L1, y: d1, label: `${num(d1)} m`}, {x: f2, y: d2, label: `${num(d2)} m`}]},
          html: `<p class="small">One TECU (10¹⁶ electrons per m²) delays L1 by about 0.16 m. Daytime values of tens of TECU, and over 100 in solar storms, give metres to tens of metres. Single-frequency receivers use a broadcast model that removes only part of it ${est}. The wider apart the two frequencies, the smaller the noise penalty: L1 + L5 gives about × 2.6, L1 + L2 about × 3.0.</p>${links}`,
          note: "First-order ionosphere only (more than 99.9 % of the effect, Navipedia); higher-order terms and code biases between frequencies remain. Noise assumed equal and independent on both frequencies.",
        };
      },
      related: [["GNSS band plan", "#gnssbands"], ["Pseudoranges and the clock", "#gnsstri"]],
    });
  });
})();
