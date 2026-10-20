// "☆ Shortlist" buttons: add the item without leaving the page, confirm it in place and update the count on the
// Business cases tab. Without the script the form posts and returns to the page as before.
(() => {
  if (window.shortlistBound) return;
  window.shortlistBound = true;
  const tab = () => document.querySelector('nav a[href="/business/shortlist"]');
  const badge = n => {
    const a = tab();
    if (!a) return;
    let b = a.querySelector(".nav-count");
    if (!b) a.append(Object.assign(document.createElement("span"), {className: "nav-count"}));
    b = a.querySelector(".nav-count");
    b.textContent = n;
    b.title = `${n} on the shortlist`;
    b.hidden = !n;
  };
  document.addEventListener("submit", async e => {
    const f = e.target;
    if (!f.matches || !f.matches("form.push-form") || !f.querySelector(".push-btn")) return;
    e.preventDefault();
    const btn = f.querySelector(".push-btn");
    btn.disabled = true;
    try {
      const res = await fetch(f.action, {method: "POST", body: new FormData(f), headers: {Accept: "application/json"}});
      if (!res.ok) throw new Error(res.status);
      const {count} = await res.json();
      f.outerHTML = `<span class="pushed small" role="status">★ Added · <a href="/business/shortlist">view shortlist</a></span>`;
      badge(count);
    } catch (err) {
      btn.disabled = false;
      f.submit();
    }
  });
  document.addEventListener("DOMContentLoaded", async () => {
    if (!tab()) return;
    try { const r = await fetch("/api/shortlist/count"); if (r.ok) badge((await r.json()).count); } catch (err) { /* no badge */ }
  });
})();
