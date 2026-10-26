// Shareable previews open in a lightbox over the current page instead of leaving it (owner, 25 Oct 2026).
// Links with data-lightbox open their address in a framed window with Open in a new tab and Close (Esc). No print
// button (owner, 26 Oct 2026): Create PDF and Create PowerPoint on /shareable make the files. Pages shown inside call
// window.parent.postMessage("lightbox:close").
(() => {
  let box, frame, newTab;
  function build() {
    box = document.createElement("dialog");
    box.className = "lb";
    box.setAttribute("aria-label", "Preview");
    box.innerHTML = '<div class="lb-bar"><b class="lb-title">Preview</b><span class="lb-tools">'
      + '<a class="lb-new" target="_blank" rel="noopener">Open in a new tab</a>'
      + '<button type="button" class="lb-close outline" aria-label="Close preview">Close</button></span></div>'
      + '<iframe class="lb-frame" title="Preview" allow="fullscreen" allowfullscreen></iframe>';
    document.body.appendChild(box);
    frame = box.querySelector(".lb-frame");
    newTab = box.querySelector(".lb-new");
    box.querySelector(".lb-close").addEventListener("click", close);
    box.addEventListener("click", e => { if (e.target === box) close(); });  // a click on the backdrop
    box.addEventListener("close", () => { frame.src = "about:blank"; document.documentElement.classList.remove("lb-open"); });
  }
  function close() { if (box && box.open) box.close(); }
  function open(url, title) {
    if (!box) build();
    box.querySelector(".lb-title").textContent = title || "Preview";
    // inside the window only the report shows (?embed=1); "Open in a new tab" keeps the full page
    const path = new URL(url, location.href).pathname;
    frame.src = path.startsWith("/shareable/") ? url + (url.includes("?") ? "&" : "?") + "embed=1" : url;
    newTab.href = url;
    document.documentElement.classList.add("lb-open");
    if (typeof box.showModal === "function") box.showModal(); else box.setAttribute("open", "");
  }
  window.shareableLightbox = open;
  document.addEventListener("click", e => {
    const a = e.target.closest("a[data-lightbox]");
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    open(a.href, a.dataset.lightbox || a.textContent.trim());
  });
  window.addEventListener("message", e => { if (e.origin === location.origin && e.data === "lightbox:close") close(); });
})();
