// Letter tabs (owner, 2 Nov 2026: "5 tabs pre-filtering the labels, so we don't show all of them at once"), used by
// the Automotive map's By application view and the Car explorer's area lists. Each [data-lv-scope] holds a hidden tab bar
// (.lv-tabs, one button per letter), letter rows (.am-row[data-lv]) and cards ([data-lv-card]) with a "none" line
// (.lv-empty). Without JavaScript the bar stays hidden and every letter shows. The default is A (Sell now); where
// there is no A, the first letter that has functions.
(() => {
  document.querySelectorAll("[data-lv-scope]").forEach((scope) => {
    const tabs = scope.querySelector(".lv-tabs");
    if (!tabs) return;
    const buttons = [...tabs.querySelectorAll("button[data-lv]")];
    const pick = (lv) => {
      buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lv === lv)));
      scope.querySelectorAll(".am-row[data-lv]").forEach((r) => { r.hidden = r.dataset.lv !== lv; });
      scope.querySelectorAll("[data-lv-card]").forEach((c) => {
        const none = c.querySelector(".lv-empty");
        if (none) none.hidden = !!c.querySelector(`.am-row[data-lv="${lv}"]`);
      });
    };
    buttons.forEach((b) => b.addEventListener("click", () => pick(b.dataset.lv)));
    const first = buttons.find((b) => b.dataset.lv === "A" && !b.disabled) || buttons.find((b) => !b.disabled);
    if (!first) return;
    scope.classList.add("lv-on");
    tabs.hidden = false;
    pick(first.dataset.lv);
  });
})();
