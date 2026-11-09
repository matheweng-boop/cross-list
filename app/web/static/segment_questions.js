// Questions to ask per segment (owner, 9 Nov 2026): three tabs (Customer · Developers · Business unit) over the
// question groups of library/_segment_questions.html. Without JavaScript the tab bar stays hidden and every group
// shows. A link to one question or answer (#i-<id>, #ans-<id>, after saving) opens its section and its tab.
(() => {
  document.querySelectorAll("[data-sq-scope]").forEach((scope) => {
    const bar = scope.querySelector(".sq-tabs");
    const panels = [...scope.querySelectorAll(".sq-panel[data-sq]")];
    if (!bar || !panels.length) return;
    const buttons = [...bar.querySelectorAll("button[data-sq]")];
    const pick = (key) => {
      buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sq === key)));
      panels.forEach((p) => { p.hidden = p.dataset.sq !== key; });
    };
    buttons.forEach((b) => b.addEventListener("click", () => pick(b.dataset.sq)));
    bar.hidden = false;
    scope.classList.add("sq-on");
    const show = () => {
      const id = decodeURIComponent((location.hash || "").slice(1));
      const target = id ? document.getElementById(id) : null;
      const panel = target && scope.contains(target) ? target.closest(".sq-panel") : null;
      if (panel) {
        const sec = scope.closest("details");
        if (sec) sec.open = true;
        pick(panel.dataset.sq);
        target.scrollIntoView({ block: "start" });
        return true;
      }
      return false;
    };
    if (!show()) pick(panels[0].dataset.sq);
    window.addEventListener("hashchange", show);
  });
})();
