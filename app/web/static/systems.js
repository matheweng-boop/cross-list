// Systems library and Block diagram library (owner, 2 Nov 2026): each system is one <details> line that opens and
// closes; all start closed. A link to a system (#sys-automotive, #area-automotive) or to anything inside one
// (#card-…, #sub-car-radio, #diagrams-…) opens it and scrolls to it, also when that hash is already in the address
// bar (a system button tapped twice). Without JS the lines still open and close; only the hash opening needs this.
(() => {
  const hash = () => { try { return decodeURIComponent(location.hash.slice(1)); } catch { return ""; } };
  const target = id => {
    if (!id) return null;
    const el = document.getElementById(id);
    if (el || !id.startsWith("sub-")) return el;
    // a sub-system whose diagrams are not listed on this page: its card
    return document.querySelector(`.sys-sub[data-sub="${CSS.escape(id.slice(4))}"]`);
  };
  const show = id => {
    const el = target(id);
    if (!el) return;
    for (let d = el; d; d = d.parentElement) if (d.tagName === "DETAILS") d.open = true;
    el.scrollIntoView({block: "start"});
  };
  window.addEventListener("hashchange", () => show(hash()));
  document.addEventListener("click", e => {  // the same hash again: no hashchange, so open it here
    const a = e.target.closest('a[href^="#"]');
    if (a && a.getAttribute("href").slice(1) === hash() && hash()) { e.preventDefault(); show(hash()); }
  });
  if (location.hash) show(hash());
})();
