// Walk-through step 2 "Sell around it": the application cards narrow as you type a general word (HVAC, BMS,
// traction inverter...). Same rules as app/services/blocks.py search_all: a category phrase matches a card in that
// category or with the phrase in its text; any other word must start a word in the card's text.
(() => {
  const box = document.getElementById("walk-cards");
  const input = document.getElementById("walk-q");
  if (!box || !input) return;
  const {phrases, stop} = JSON.parse(document.getElementById("walk-search-data").textContent);
  const STOP = new Set(stop);
  const cards = [...box.querySelectorAll(".walk-card")];
  const first = +box.dataset.first || 9;
  const more = document.getElementById("walk-more");
  const count = document.getElementById("walk-count");
  const none = document.getElementById("walk-none");
  const chips = [...document.querySelectorAll(".walk-cat")];
  let all = false;
  const reEsc = s => s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  const wordRe = w => new RegExp(`(?<![a-z0-9])${reEsc(w)}${w.length <= 3 ? "(?![a-z0-9])" : ""}`);
  const words = q => (q.toLowerCase().match(/[a-z0-9][a-z0-9/+.\-]*/g) || []).filter(w => !STOP.has(w));

  function units(q) {
    let rest = ` ${words(q).join(" ")} `;
    const out = [];
    for (const [w, keys] of phrases) {
      if (rest.includes(` ${w} `)) { out.push([w, keys]); rest = rest.split(` ${w} `).join(" "); }
    }
    return out.concat(rest.split(" ").filter(Boolean).map(w => [w, []]));
  }

  function apply() {
    const q = input.value.trim();
    const us = units(q);
    let n = 0, shown = 0;
    cards.forEach(c => {
      const tags = (c.dataset.tags || "").split(" ");
      const text = c.dataset.text || "";
      const ok = us.every(([w, keys]) => keys.some(k => tags.includes(k)) || wordRe(w).test(text));
      if (ok) n++;
      const show = ok && (q || all || n <= first);
      c.hidden = !show;
      if (show) shown++;
    });
    if (more) more.hidden = !!q || all;
    if (none) none.hidden = n > 0;
    count.textContent = q ? `${n} of ${cards.length} applications match “${q}”` : `${shown} of ${cards.length} applications`;
    chips.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.q === q.toLowerCase())));
  }

  let timer = null;
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(apply, 120); });
  input.form.addEventListener("submit", e => { e.preventDefault(); apply(); });
  chips.forEach(b => b.addEventListener("click", () => {
    input.value = input.value.trim().toLowerCase() === b.dataset.q ? "" : b.dataset.q;
    apply();
  }));
  more?.addEventListener("click", () => { all = true; apply(); });
  apply();
})();
