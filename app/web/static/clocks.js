// Clock planner (Products > Clock planner): add / remove output rows, save and share the plan shown.
(() => {
  const $ = s => document.querySelector(s);
  const rows = $("#cp-rows");
  if (rows) {
    const blank = () => {
      const last = rows.querySelector(".cp-row:last-of-type");
      const row = last.cloneNode(true);
      row.querySelectorAll("input").forEach(i => { i.value = i.name === "n" ? "1" : ""; });
      row.querySelectorAll("select").forEach(s => { s.selectedIndex = s.name === "fmt" ? s.selectedIndex : 0; });
      return row;
    };
    $("#cp-add").addEventListener("click", () => {
      if (rows.querySelectorAll(".cp-row:not(.cp-row-head)").length >= 16) return;
      const row = blank();
      rows.append(row);
      row.querySelector("input").focus();
    });
    rows.addEventListener("click", e => {
      const del = e.target.closest(".cp-del");
      if (!del) return;
      const row = del.closest(".cp-row");
      if (rows.querySelectorAll(".cp-row:not(.cp-row-head)").length > 1) row.remove();
      else row.querySelectorAll("input").forEach(i => { i.value = i.name === "n" ? "1" : ""; });
    });
  }

  const save = $("#cp-save-btn");
  if (!save) return;
  const data = JSON.parse($("#cp-data").textContent);
  let planId = JSON.parse($("#cp-plan-id").textContent);
  const status = $("#cp-status"), copy = $("#cp-copy");
  const link = () => `${location.origin}/clocks/plans/${planId}`;
  save.addEventListener("click", async () => {
    const name = $("#cp-name").value.trim();
    const res = await fetch(planId ? `/api/clocks/plans/${planId}` : "/api/clocks/plans", {
      method: planId ? "PUT" : "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, data}),
    });
    if (!res.ok) { status.textContent = `Not saved (${res.status})`; return; }
    const out = await res.json();
    if (out.review) { status.textContent = out.message; return; }
    planId = out.id;
    $("#cp-name").value = out.name;
    history.replaceState(null, "", out.url);
    status.innerHTML = "";
    status.append("Saved. Link: ", Object.assign(document.createElement("a"), {href: out.url, textContent: link()}));
    save.textContent = "Save changes";
    copy.hidden = false;
  });
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(link()); copy.textContent = "Link copied"; }
    catch { prompt("Copy this link", link()); }
  });
})();
