// Shareable previews open in a lightbox over the current page instead of leaving it (owner, 25 Oct 2026).
// Links with data-lightbox, and the "Build a PDF" form, open their address in a framed window with Print / Save as
// PDF, Open in a new tab and Close (Esc). Pages shown inside call window.parent.postMessage("lightbox:close").
(() => {
  let box, frame, newTab;
  function build() {
    box = document.createElement("dialog");
    box.className = "lb";
    box.setAttribute("aria-label", "Preview");
    box.innerHTML = '<div class="lb-bar"><b class="lb-title">Preview</b><span class="lb-tools">'
      + '<button type="button" class="lb-print">Print / Save as PDF</button>'
      + '<a class="lb-new" target="_blank" rel="noopener">Open in a new tab</a>'
      + '<button type="button" class="lb-close outline" aria-label="Close preview">Close</button></span></div>'
      + '<iframe class="lb-frame" title="Preview" allow="fullscreen" allowfullscreen></iframe>';
    document.body.appendChild(box);
    frame = box.querySelector(".lb-frame");
    newTab = box.querySelector(".lb-new");
    box.querySelector(".lb-close").addEventListener("click", close);
    box.querySelector(".lb-print").addEventListener("click", () => { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { window.open(frame.src, "_blank"); } });
    box.addEventListener("click", e => { if (e.target === box) close(); });  // a click on the backdrop
    box.addEventListener("close", () => { frame.src = "about:blank"; document.documentElement.classList.remove("lb-open"); });
  }
  function close() { if (box && box.open) box.close(); }
  function open(url, title) {
    if (!box) build();
    box.querySelector(".lb-title").textContent = title || "Preview";
    frame.src = url;
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
