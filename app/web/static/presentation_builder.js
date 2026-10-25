// Shareable > Presentation builder (owner, 25 Oct 2026): ticks -> sections; the "Your presentation" list orders them;
// the address (?s=a,b,c) and the Preview link always hold the current selection and order.
(() => {
  const pick = document.getElementById("pb-pick");
  const list = document.getElementById("pb-list");
  if (!pick || !list) return;
  const hidden = document.getElementById("pb-s");
  const preview = document.getElementById("pb-preview");
  const count = document.getElementById("pb-count");
  const empty = document.querySelector(".pb-empty");
  const owner = !!document.querySelector(".pb-own");
  const deck = pick.querySelector("input[name=deck]");
  let ids = (hidden.value || "").split(",").filter(Boolean);

  const boxes = (sid) => [...pick.querySelectorAll("input[name=s]")].filter((b) => b.value === sid);
  const titleOf = (sid) => { const b = boxes(sid)[0]; return b ? b.dataset.title : sid; };

  function render() {
    const typed = {};
    list.querySelectorAll("input.pb-title").forEach((i) => { typed[i.name.slice(2)] = i.value; });
    list.textContent = "";
    ids.forEach((sid) => {
      const li = document.createElement("li");
      li.dataset.sid = sid;
      const name = document.createElement("span");
      name.className = "pb-name";
      name.textContent = titleOf(sid);
      const tools = document.createElement("span");
      tools.className = "pb-tools";
      [["↑", "Move up", "-1"], ["↓", "Move down", "1"], ["✕", "Remove", ""]].forEach(([t, label, mv]) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "pb-mini" + (mv ? "" : " pb-del");
        b.textContent = t;
        b.setAttribute("aria-label", label);
        if (mv) b.dataset.move = mv; else b.dataset.remove = "";
        tools.append(b);
      });
      li.append(name, tools);
      if (owner) {
        const inp = document.createElement("input");
        inp.className = "pb-title";
        inp.name = "t." + sid;
        inp.maxLength = 90;
        inp.value = typed[sid] ?? titleOf(sid);
        inp.setAttribute("aria-label", "Slide title");
        li.append(inp);
      }
      list.append(li);
    });
    const s = ids.join(",");
    hidden.value = s;
    const q = "s=" + s + (deck ? "&deck=" + encodeURIComponent(deck.value) : "");
    preview.href = pick.action.replace(/\/$/, "") + "/preview?" + q;
    count.textContent = ids.length + (ids.length === 1 ? " section" : " sections");
    if (empty) empty.hidden = ids.length > 0;
    history.replaceState(null, "", location.pathname + (ids.length || deck ? "?" + q : ""));
  }

  function setChecked(sid, on) {
    boxes(sid).forEach((b) => { b.checked = on; });
    if (on && !ids.includes(sid)) ids.push(sid);
    if (!on) ids = ids.filter((x) => x !== sid);
  }

  pick.addEventListener("change", (e) => {
    const el = e.target;
    if (el.classList.contains("pb-tcheck")) {
      const topic = el.closest(".pb-topic");
      const items = topic.querySelector(".pb-items");
      items.hidden = !el.checked;
      topic.classList.toggle("pb-open", el.checked);
      if (!el.checked) {
        // take this topic's sections out; a note stays when another open topic offers it too
        items.querySelectorAll("input[name=s]").forEach((b) => {
          const elsewhere = boxes(b.value).some((o) => o !== b && !o.closest(".pb-items").hidden);
          if (!elsewhere) setChecked(b.value, false);
        });
      }
      render();
      return;
    }
    if (el.name === "s") { setChecked(el.value, el.checked); render(); }
  });
  pick.addEventListener("submit", (e) => { e.preventDefault(); render(); });

  list.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const sid = b.closest("li").dataset.sid;
    const i = ids.indexOf(sid);
    if (b.dataset.move) {
      const j = i + Number(b.dataset.move);
      if (j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      render();
      const again = list.querySelector(`li[data-sid="${CSS.escape(sid)}"] button[data-move="${b.dataset.move}"]`);
      if (again) again.focus();
    } else if ("remove" in b.dataset) {
      setChecked(sid, false);
      render();
    }
  });

  document.querySelectorAll("button[data-confirm]").forEach((b) => b.addEventListener("click", (e) => {
    if (!confirm(b.dataset.confirm)) e.preventDefault();
  }));
  render();
})();
