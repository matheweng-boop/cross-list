// Presentation preview (owner, 25 Oct 2026): one slide at a time; Previous / Next, arrow keys, swipe, thumbnails,
// slide counter, full screen (Fullscreen API; on iPhone / older iPad Safari a fixed full-window view instead).
(() => {
  const stage = document.getElementById("pv-stage");
  if (!stage) return;
  const slides = [...document.querySelectorAll(".pv-slide")];
  const counter = document.getElementById("pv-counter");
  const prev = document.getElementById("pv-prev");
  const next = document.getElementById("pv-next");
  const full = document.getElementById("pv-full");
  const thumbs = document.getElementById("pv-thumbs");
  document.documentElement.classList.add("pv-js");
  let cur = Math.min(Math.max(parseInt((location.hash.match(/^#(\d+)$/) || [])[1] || "1", 10), 1), slides.length) - 1;

  // thumbnails: a copy of each slide, scaled by the slide's own width-relative sizes
  slides.forEach((s, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pv-thumb";
    b.setAttribute("aria-label", "Slide " + (i + 1));
    const copy = s.cloneNode(true);
    copy.removeAttribute("id");
    copy.classList.add("pv-copy");
    copy.removeAttribute("aria-label");
    copy.setAttribute("aria-hidden", "true");
    b.append(copy);
    b.addEventListener("click", () => go(i));
    thumbs.append(b);
  });

  function go(i) {
    cur = Math.min(Math.max(i, 0), slides.length - 1);
    slides.forEach((s, k) => s.classList.toggle("pv-on", k === cur));
    [...thumbs.children].forEach((t, k) => t.setAttribute("aria-current", k === cur ? "true" : "false"));
    counter.textContent = cur + 1 + " / " + slides.length;
    prev.disabled = cur === 0;
    next.disabled = cur === slides.length - 1;
    history.replaceState(null, "", "#" + (cur + 1));
    const t = thumbs.children[cur];
    if (t && t.scrollIntoView) t.scrollIntoView({block: "nearest", inline: "nearest"});
  }

  prev.addEventListener("click", () => go(cur - 1));
  next.addEventListener("click", () => go(cur + 1));
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, select, textarea") || e.altKey || e.ctrlKey || e.metaKey) return;
    if (["ArrowRight", "PageDown", " "].includes(e.key)) { e.preventDefault(); go(cur + 1); }
    else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); go(cur - 1); }
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(slides.length - 1);
    else if (e.key === "f" || e.key === "F") toggleFull();
    else if (e.key === "Escape" && stage.classList.contains("pv-full")) exitFull();
  });

  // swipe on touch screens
  let x0 = null, y0 = null;
  stage.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, {passive: true});
  stage.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) go(cur + (dx < 0 ? 1 : -1));
    x0 = null;
  });
  // a tap on the right or left third of the slide in full screen moves on or back
  stage.querySelector(".pv-deck").addEventListener("click", (e) => {
    if (!stage.classList.contains("pv-full")) return;
    const r = e.currentTarget.getBoundingClientRect();
    go(cur + (e.clientX - r.left > r.width / 3 ? 1 : -1));
  });

  const api = stage.requestFullscreen || stage.webkitRequestFullscreen;
  const fsEl = () => document.fullscreenElement || document.webkitFullscreenElement;
  function enterFull() {
    stage.classList.add("pv-full");
    full.textContent = "Exit full screen";
    if (api) {
      try {
        const p = api.call(stage);
        if (p && p.catch) p.catch(() => {});
      } catch (err) { /* the fixed full-window view stays */ }
    }
    stage.focus();
  }
  function exitFull() {
    stage.classList.remove("pv-full");
    full.textContent = "Full screen";
    if (fsEl()) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
  }
  function toggleFull() { stage.classList.contains("pv-full") ? exitFull() : enterFull(); }
  full.addEventListener("click", toggleFull);
  ["fullscreenchange", "webkitfullscreenchange"].forEach((ev) => document.addEventListener(ev, () => {
    if (!fsEl() && stage.classList.contains("pv-full") && api) { stage.classList.remove("pv-full"); full.textContent = "Full screen"; }
  }));

  go(cur);
})();
