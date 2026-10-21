// Case from a part (/pipeline/<id>): the application description narrows the design list as it is typed (top 10
// from /pipeline/apps.json), "+" adds another customer or market, and the prelim case goes to the review queue.
(() => {
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  // 1. application description -> the top 10 designs
  const desc = document.getElementById("pl-desc");
  const list = document.getElementById("pl-found");
  if (desc && list && !desc.dataset.bound) {
    desc.dataset.bound = "1";
    const action = list.closest("section").querySelector("form.pl-new").getAttribute("action");
    const note = document.getElementById("pl-found-note");
    const fn = desc.dataset.fn || "";
    const fnLabel = (note.textContent.match(/Designs with an? (.*) · top 10/) || [])[1] || "";
    const sync = () => document.querySelectorAll('input[type="hidden"][name="description"]').forEach(i => (i.value = desc.value));
    let timer = null, seq = 0;
    const row = t => `<form method="post" action="${esc(action)}" class="pl-row">${t.kind === "template"
        ? `<input type="hidden" name="act" value="template"><input type="hidden" name="i" value="${t.i}">`
        : `<input type="hidden" name="act" value="saved"><input type="hidden" name="id" value="${t.id}">`}<input type="hidden" name="description" value="${esc(desc.value)}">
      <span><b>${esc(t.name)}</b> <small class="muted">${t.blocks} functions${t.kind === "saved" ? " · your diagram" : ""}${t.has && fnLabel ? ` · has a ${esc(fnLabel)}` : ""}${t.tags.length ? ` · ${esc(t.tags.join(", "))}` : ""}</small></span><button type="submit" class="outline small-btn">Use this design</button></form>`;
    const search = async () => {
      const n = ++seq;
      const r = await fetch(`/pipeline/apps.json?q=${encodeURIComponent(desc.value)}&fn=${encodeURIComponent(fn)}`);
      if (!r.ok || n !== seq) return;
      const rows = await r.json();
      list.innerHTML = rows.length ? rows.map(row).join("")
        : `<p class="small muted">No design matches yet. Try a general word (HVAC, BMS, motor drive, solar) or start a new diagram below.</p>`;
      note.textContent = desc.value.trim() ? `Best matches for your description · top 10 · ${rows.length} shown` : `Designs with the part's function · top 10`;
    };
    desc.addEventListener("input", () => { sync(); clearTimeout(timer); timer = setTimeout(search, 200); });
  }

  // 2. "+" adds another customer / market field
  document.querySelectorAll(".pl-add").forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const rows = btn.parentElement.querySelectorAll(".pl-multi-row");
      const last = rows[rows.length - 1];
      const copy = last.cloneNode(true);
      const input = copy.querySelector("input");
      input.value = "";
      btn.before(copy);
      input.focus();
    });
  });

  // 3. the prelim case goes to the review queue by itself the first time the page opens
  const send = document.getElementById("pl-send");
  if (send && send.dataset.autosend === "1") {
    send.dataset.autosend = "";
    send.submit();
  }
})();
