// Business case inputs: when a box gets focus, show what BizDev already knows for that field (rendered with the
// page as JSON in #sg-data) with "Use" (put it in the box) and "Copy" buttons. On a wide screen the panel sits in the
// right column; on a phone it moves right below the box.
(function () {
  const data = JSON.parse((document.getElementById("sg-data") || {}).textContent || "{}");
  const panel = document.getElementById("sg-panel"), slot = document.getElementById("sg-slot");
  const list = document.getElementById("sg-list"), name = document.getElementById("sg-field");
  const form = document.querySelector(".case-form");
  if (!panel || !form) return;
  const narrow = window.matchMedia("(max-width: 900px)");
  let box = null;

  form.querySelectorAll("label[data-field]").forEach((lab) => {
    const n = (data[lab.dataset.field] || []).length;
    if (!n) return;
    const chip = document.createElement("span");
    chip.className = "sg-chip";
    chip.textContent = n + (n === 1 ? " hint" : " hints");
    lab.insertBefore(chip, lab.querySelector("input, textarea, select"));
  });

  function put(text) {
    if (!box) return;
    const cur = box.value.trim();
    if (box.tagName === "INPUT") box.value = text.split("\n")[0];
    else box.value = cur && !cur.includes(text) ? cur + "\n" + text : text;
    box.dispatchEvent(new Event("input", { bubbles: true }));
    box.focus();
  }

  function show(field, label) {
    const items = data[field] || [];
    name.textContent = (label.childNodes[0].textContent || field).trim();
    list.replaceChildren();
    if (!items.length) {
      const p = document.createElement("p");
      p.className = "small muted";
      p.textContent = "Nothing yet for this box.";
      list.append(p);
    }
    items.forEach((it) => {
      const card = document.createElement("div");
      card.className = "sg-item";
      const src = document.createElement("small");
      src.className = "muted";
      src.textContent = it.src;
      const txt = document.createElement("p");
      txt.className = "sg-text";
      txt.textContent = it.text;
      const use = document.createElement("button");
      use.type = "button";
      use.className = "small-btn";
      use.textContent = "Use";
      use.title = "Put this text in the box";
      use.onmousedown = (e) => e.preventDefault();
      use.onclick = () => put(it.text);
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "small-btn outline";
      copy.textContent = "Copy";
      copy.onmousedown = (e) => e.preventDefault();
      copy.onclick = async () => {
        try { await navigator.clipboard.writeText(it.text); copy.textContent = "Copied"; }
        catch (e) { copy.textContent = "Select and copy"; }
      };
      const row = document.createElement("span");
      row.className = "sg-btns";
      row.append(use, copy);
      card.append(src, txt, row);
      list.append(card);
    });
    if (narrow.matches) label.after(panel); else slot.append(panel);
    panel.hidden = false;
  }

  form.addEventListener("focusin", (e) => {
    const el = e.target, label = el.closest("label[data-field]");
    if (!label || !el.matches("input, textarea")) return;
    box = el;
    show(label.dataset.field, label);
  });
})();
