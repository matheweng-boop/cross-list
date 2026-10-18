// Quick calculators for the engineering notes. Each <div data-calc="name"> gets a row per part
// (reference first) from the JSON in #note-devices; inputs inside the div recalculate live.
(() => {
  const data = document.getElementById("note-devices");
  if (!data) return;
  const devices = JSON.parse(data.textContent);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const num = v => (Array.isArray(v) ? v.map(Number) : v == null ? null : Number(v));
  const fmt = (x, d = 1) => (x == null || isNaN(x) ? "–" : x >= 100 ? x.toFixed(0) : x.toFixed(d));
  const ok = good => `<span class="state ${good ? "good" : "bad"}">${good ? "✓ Yes" : "✗ No"}</span>`;

  // name -> (inputs) => {head: [...], row: device => [...cells]}
  const CALCS = {
    working_voltage: ({v}) => ({
      head: ["Part", "VIORM", "Margin at your voltage", "Covers it?"],
      row: d => {
        const viorm = num(d.values.viorm_vpk);
        return viorm == null ? ["–", "not in data", "–"] : [`${viorm} Vpk`, `${fmt(viorm / v, 2)}×`, ok(viorm >= v)];
      },
    }),
    spi: ({tco, tsu}) => ({
      head: ["Part", "tPD (max)", "Max SCLK through the isolator"],
      row: d => {
        const tpd = num(d.values.prop_delay_ns);
        // half a clock period must cover SCLK out, slave clock-to-out, MISO back and master setup
        return tpd == null ? ["not in data", "–"] : [`${tpd} ns`, `${fmt(1000 / (2 * (2 * tpd + tco + tsu)))} MHz`];
      },
    }),
    gate_charge: ({qg}) => ({
      head: ["Part", "Peak source / sink", "Turn-on ≈ Qg/I", "Turn-off ≈ Qg/I"],
      row: d => {
        const src = num(d.values.peak_source_a), snk = num(d.values.peak_sink_a);
        return [`${src ?? "–"} A / ${snk ?? "–"} A`, src ? `${fmt(qg / src)} ns` : "–", snk ? `${fmt(qg / snk)} ns` : "–"];
      },
    }),
    supply: ({rail}) => ({
      head: ["Part", "Supply range", "Your rail inside it?"],
      row: d => {
        const r = num(d.values.vdd_range_v ?? d.values.supply_v ?? d.values.vdd1_range_v);
        return r == null ? ["not in data", "–"] : [`${r[0]} to ${r[1]} V`, ok(rail >= Math.min(...r) && rail <= Math.max(...r))];
      },
    }),
    data_rate: ({rate}) => ({
      head: ["Part", "Max data rate", "Headroom", "Enough?"],
      row: d => {
        const max = num(d.values.data_rate_mbps);
        return max == null ? ["not in data", "–", "–"] : [`${max} Mbps`, `${fmt(max / rate, 2)}×`, ok(max >= rate)];
      },
    }),
    temperature: ({tmax}) => ({
      head: ["Part", "Operating range", "Covers your maximum?"],
      row: d => {
        const r = num(d.values.temp_range_c);
        return r == null ? ["not in data", "–"] : [`${r[0]} to ${r[1]} °C`, ok(tmax <= Math.max(...r))];
      },
    }),
  };

  document.querySelectorAll("[data-calc]").forEach(box => {
    const calc = CALCS[box.dataset.calc];
    const out = box.querySelector("tbody"), head = box.querySelector("thead");
    const render = () => {
      const inputs = {};
      box.querySelectorAll("input").forEach(el => {
        inputs[el.name] = +el.value;
        const o = box.querySelector(`output[for=${el.id}]`);
        if (o) o.textContent = `${el.value} ${el.dataset.unit || ""}`;
      });
      const c = calc(inputs);
      head.innerHTML = "<tr>" + c.head.map(h => `<th>${h}</th>`).join("") + "</tr>";
      out.innerHTML = devices.length
        ? devices.map((d, k) => `<tr><td><b>${esc(d.mpn)}</b><br><small class="muted">${esc(d.maker)}${k === 0 ? " · reference" : ""}</small></td>` +
            c.row(d).map(x => `<td>${x}</td>`).join("") + "</tr>").join("")
        : `<tr><td colspan="${c.head.length}" class="muted">Open this note from a cross to fill in the parts.</td></tr>`;
    };
    box.querySelectorAll("input").forEach(el => el.addEventListener("input", render));
    render();
  });
})();
