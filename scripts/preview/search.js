(() => {
  const parts = window.CL_PARTS || [];
  const out = document.getElementById("suggestions");
  if (!out) return;
  const norm = s => s.replace(/[\s\-_/]/g, "").toUpperCase();
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const href = p => p[4] ? "part-" + p[4] + ".html" : "cross.html#" + p[5];
  const search = value => {
    const q = norm(value);
    if (q.replace(/\*/g, "").length < 2) return null;
    const rx = new RegExp(q.split("*").map(s => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*"));
    return parts.filter(p => rx.test(norm(p[0])))
      .sort((a, b) => (norm(b[0]).startsWith(q) - norm(a[0]).startsWith(q)) || a[0].localeCompare(b[0]));
  };
  document.querySelectorAll("input[data-static-suggest]").forEach(box => {
    box.addEventListener("input", () => {
      const hits = search(box.value);
      if (!hits) { out.innerHTML = ""; return; }
      const shown = hits.slice(0, 60);
      out.innerHTML = shown.length ? '<ul class="suggest-list">' + shown.map(p => {
        const meta = esc(p[1]) + " · " + esc(p[2]) + " · " + esc(p[3]);
        return '<li><a href="' + href(p) + '"><span class="sg-mpn">' + esc(p[0]) + '</span><span class="sg-meta">' + meta + "</span></a></li>";
      }).join("") + (hits.length > 60 ? '<li class="sg-more muted">' + hits.length + " matches, showing 60. Type more to narrow.</li>" : "")
        + "</ul>" : '<p class="suggest-list muted sg-empty">No part numbers contain that.</p>';
    });
    const go = e => {
      e.preventDefault();
      const hits = search(box.value) || [];
      const exact = hits.find(p => norm(p[0]) === norm(box.value));
      if (exact || hits.length === 1) location.href = href(exact || hits[0]);
      else box.dispatchEvent(new Event("input"));
    };
    if (box.form) box.form.addEventListener("submit", go);
    box.addEventListener("keydown", e => { if (e.key === "Enter") go(e); });
  });
})();
