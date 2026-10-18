(() => {
  const SHARDS = window.CL_SHARDS, view = document.getElementById("cross-view");
  const byId = {};  // filled on first render: parts.js loads after this script
  const loaded = {};
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const cls = t => (t.match(/, (better|worse|different|unknown)\)$/) || [])[1] || "";
  const NAMES = {fff: "FFF – form, fit & function", upgrade: "Upgrade", p2p: "Pin-to-pin", downgrade: "Downgrade"};
  const FFF = {auto: ["ok", "FFF"], accepted: ["ok", "FFF – accepted"], review: ["warn", "FFF – needs review"], rejected: ["bad", "FFF – rejected"]};
  const link = p => p[4] ? "part-" + p[4] + ".html" : "cross.html#" + p[5];
  window.CL_SHARD = (n, d) => { loaded[n] = d; render(); };
  function render() {
    if (!Object.keys(byId).length) (window.CL_PARTS || []).forEach(p => (byId[p[5]] = p));
    const id = parseInt(location.hash.slice(1), 10), p = byId[id];
    if (!p) { view.innerHTML = '<p>Part not found. Use the search above.</p>'; return; }
    const n = id % SHARDS;
    if (!loaded[n]) {
      if (!document.getElementById("shard-" + n)) {
        const s = document.createElement("script"); s.id = "shard-" + n; s.src = "static/preview/x" + n + ".js";
        document.body.appendChild(s);
      }
      view.innerHTML = '<h1>' + esc(p[0]) + '</h1><p class="muted">Loading crosses…</p>'; return;
    }
    const rec = loaded[n][id] || {}, competitor = p[1] !== "Skyworks";
    let h = '<h1>' + esc(p[0]) + '</h1><p class="subtitle muted">' + esc(p[1]) + " · " + esc(p[2]) + " · " + esc(p[3]) + "</p>";
    if (p[4]) h += '<p><a href="part-' + p[4] + '.html">Open the full page with difference tables</a></p>';
    h += "<h2>" + (competitor ? "Suitable Skyworks parts" : "Competitor crosses") + "</h2>";
    h += '<nav class="catnav">' + Object.keys(NAMES).map(c => '<a class="badge cat" href="#' + id + '" data-jump="sec-' + c + '">'
      + NAMES[c] + " (" + ((rec[c] || [[], 0])[1]) + ")</a>").join("") + "</nav>";
    for (const c of Object.keys(NAMES)) {
      const [rows, total] = rec[c] || [[], 0];
      h += '<h3 id="sec-' + c + '">' + NAMES[c] + ' <small class="muted">(' + total + ")</small></h3>";
      if (!rows.length) { h += '<p class="muted">No parts in this category.</p>'; continue; }
      for (const [cid, fs, top, p3] of rows) {
        const q = byId[cid] || ["?", "", "", ""];
        const badge = FFF[fs] ? '<span class="badge ' + FFF[fs][0] + '">' + FFF[fs][1] + "</span>" : "";
        h += '<article class="cross"><header><a href="' + link(q) + '"><strong>' + esc(q[1] + " " + q[0]) + "</strong></a> "
          + '<span class="badge muted">' + esc(q[2]) + '</span> <span class="badge muted">' + esc(q[3]) + "</span> " + badge + "</header>"
          + "<strong>Top 5 differences</strong>" + (top.length ? '<ol class="top5">' + top.map(t => '<li class="' + cls(t) + '">' + esc(t) + "</li>").join("") + "</ol>" : '<p class="muted">No differences found.</p>')
          + (p3.length ? '<p class="p3-notes">Also note (priority 3): ' + p3.map(t => '<span class="worse">' + esc(t) + "</span>").join("; ") + "</p>" : "")
          + "</article>";
      }
      if (total > rows.length) h += '<p class="muted">Showing the best ' + rows.length + " of " + total + ". The full app lists all of them.</p>";
    }
    view.innerHTML = h;
    view.querySelectorAll("[data-jump]").forEach(a => a.addEventListener("click", e => {
      e.preventDefault(); document.getElementById(a.dataset.jump).scrollIntoView({behavior: "smooth"});
    }));
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", render);
  window.addEventListener("load", render);
})();
