// Floating feedback button: knows the page it is on (path, heading, selected text) and shows the answers to what
// this browser sent before. The browser keeps only a random id and the name typed in; nothing else is stored.
(() => {
  const root = document.getElementById("fb");
  if (!root) return;
  const panel = root.querySelector(".fb-panel"), form = root.querySelector("form"), msg = root.querySelector(".fb-msg");
  const store = {
    get: k => { try { return localStorage.getItem(k) || ""; } catch { return ""; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private window: fine */ } },
  };
  let client = store.get("fb-client");
  if (!client) { client = Math.random().toString(36).slice(2) + Date.now().toString(36); store.set("fb-client", client); }
  let selection = "";
  const heading = () => (document.querySelector("main h1")?.textContent || "").trim();
  const path = () => location.pathname + location.search;

  async function showContext() {
    const sel = (window.getSelection()?.toString() || "").trim();
    if (sel) selection = sel.slice(0, 1000);
    root.querySelector(".fb-where").textContent = "…";
    try {
      const r = await fetch(`/site-feedback/context?path=${encodeURIComponent(path())}&heading=${encodeURIComponent(heading())}`);
      root.querySelector(".fb-where").textContent = (await r.json()).page;
    } catch { root.querySelector(".fb-where").textContent = path(); }
    const box = root.querySelector(".fb-sel");
    box.hidden = !selection;
    box.querySelector("span").textContent = selection.length > 90 ? selection.slice(0, 90) + "…" : selection;
    loadMine();
  }
  async function loadMine() {
    const list = root.querySelector(".fb-mine ul");
    try {
      const rows = await (await fetch(`/site-feedback/mine?client=${client}`)).json();
      list.innerHTML = "";
      rows.filter(r => r.response || r.status !== "New").slice(0, 4).forEach(r => {
        const li = document.createElement("li");
        li.innerHTML = `<b></b> <span class="muted"></span><br><i></i>`;
        li.querySelector("b").textContent = r.status;
        li.querySelector("span").textContent = `${r.date} · ${r.text.slice(0, 60)}`;
        li.querySelector("i").textContent = r.response || "";
        list.append(li);
      });
      root.querySelector(".fb-mine").hidden = !list.children.length;
    } catch { /* offline: the form still works */ }
  }
  root.querySelector(".fb-open").addEventListener("mousedown", () => {
    selection = (window.getSelection()?.toString() || "").trim().slice(0, 1000);
  });
  root.querySelector(".fb-open").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    root.querySelector(".fb-open").setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) { msg.textContent = ""; form.hidden = false; showContext(); form.text.focus(); }
  });
  root.querySelector(".fb-close").addEventListener("click", () => { panel.hidden = true; });
  document.addEventListener("keydown", e => { if (e.key === "Escape") panel.hidden = true; });
  form.author.value = store.get("fb-author");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const body = {
      text: form.text.value, kind: form.kind.value, author: form.author.value, client, path: path(), heading: heading(),
      selection: form.withsel?.checked ? selection : "",
    };
    store.set("fb-author", form.author.value);
    const file = form.file?.files?.[0];
    if (file && file.size > 10 * 1024 * 1024) { msg.textContent = "The file is larger than 10 MB. Pick a smaller one or remove it."; return; }
    const detail = async r => { const j = await r.json().catch(() => ({})); return typeof j.detail === "string" ? j.detail : r.statusText; };
    let sent = false;
    try {
      const r = await fetch("/site-feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await detail(r));
      sent = true;
      const { id } = await r.json();
      let note = "";
      if (file) {  // the file goes with the item, stored like the Uploads page does
        msg.textContent = "Sending the file…";
        const fd = new FormData();
        fd.append("client", client); fd.append("file", file);
        const f = await fetch(`/site-feedback/${id}/file`, { method: "POST", body: fd });
        note = f.ok ? " The file is attached." : ` Your text was sent, but the file was not: ${await detail(f)}.`;
      }
      form.text.value = ""; form.file.value = ""; selection = "";
      msg.textContent = "Thank you. It is in today's feedback digest; the answer will appear here." + note;
      form.hidden = true;
      setTimeout(loadMine, 300);
    } catch (err) {
      msg.textContent = sent ? "Your text was sent, but the file was not: " + err.message + "."
        : "Not sent: " + err.message + ". Your text is still in the box.";
    }
  });
})();
