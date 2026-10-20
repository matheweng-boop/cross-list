// Case pages: open an item's react form in a dialog instead of inline. Without the script the <details> opens inline.
(() => {
  const dlg = document.getElementById("pc-dialog");
  if (!dlg || !dlg.showModal) return;
  const title = dlg.querySelector("#pc-dialog-title"), body = dlg.querySelector(".pc-dialog-body");
  let home = null;  // the <details> whose content is in the dialog
  const restore = () => {
    if (!home) return;
    while (body.firstChild) home.append(body.firstChild);
    home = null;
  };
  document.addEventListener("click", e => {
    const sum = e.target.closest(".pc-react > summary");
    if (!sum) return;
    e.preventDefault();
    restore();
    home = sum.parentElement;
    title.textContent = home.dataset.title || "Your reaction";
    [...home.children].filter(c => c !== sum).forEach(c => body.append(c));
    dlg.showModal();
    body.querySelector("textarea")?.focus();
  });
  dlg.addEventListener("close", restore);
  dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });  // click outside the article
})();
