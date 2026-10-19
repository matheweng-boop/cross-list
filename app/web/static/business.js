// Review widgets on the business pages: ✓ / ✗ / ? per data item, posted to /api/business/review.
(() => {
  const NAME = "bo-reviewer";
  const who = () => { try { return localStorage.getItem(NAME) || ""; } catch (e) { return ""; } };
  document.addEventListener("click", async e => {
    const b = e.target.closest(".rv-b");
    if (!b) return;
    const box = b.closest(".rv"), v = b.dataset.v;
    let comment = "";
    if (v !== "correct") {
      comment = prompt(v === "wrong" ? "What is wrong, and what is right? (a public source helps)" : "What should be checked?") ;
      if (comment === null) return;
    }
    let author = who();
    if (!author) { author = prompt("Your name (optional, remembered on this device)") || ""; try { localStorage.setItem(NAME, author); } catch (err) {} }
    const res = await fetch("/api/business/review", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({dataset: box.dataset.ds, key: box.dataset.key, verdict: v, comment, author})});
    if (!res.ok) { alert(`Not saved (${res.status})`); return; }
    const r = await res.json(), st = box.querySelector(".rv-st");
    st.className = `rv-st rv-${r.state}`;
    st.textContent = {verified: "reviewed ✓", disputed: "disputed", unverified: "not reviewed"}[r.state] || r.state;
    st.title = `Reviewed by people: ${r.correct} correct, ${r.wrong} wrong, ${r.unsure} unsure`;
    box.classList.add("rv-done");
  });
})();
