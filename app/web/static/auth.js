// Sign-in helpers: the browser check (proof of work), passkeys (WebAuthn) and the copy / confirm buttons on the
// People & invites and My passkeys pages. Plain JS, no outside scripts.
(() => {
  const $ = s => document.querySelector(s);
  const msg = t => { const m = $("#auth-msg"); if (m) m.textContent = t; };

  // base64url <-> ArrayBuffer
  const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unb64u = s => { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer; };

  // Proof of work: find a nonce so that SHA-256(challenge:nonce) starts with `bits` zero bits (well under a second).
  const zeros = h => { let n = 0; for (const b of h) { if (b === 0) { n += 8; continue; } return n + Math.clz32(b) - 24; } return n; };
  async function solve() {
    const r = await fetch("/login/pow", {cache: "no-store"});
    const {challenge, bits} = await r.json();
    const enc = new TextEncoder();
    for (let start = 0; ; start += 256) {
      const tries = [];
      for (let n = start; n < start + 256; n++) tries.push(crypto.subtle.digest("SHA-256", enc.encode(`${challenge}:${n}`)).then(d => [n, d]));
      for (const [n, d] of await Promise.all(tries)) if (zeros(new Uint8Array(d)) >= bits) return {pow_challenge: challenge, pow_nonce: String(n)};
    }
  }
  let ready = null;
  const nextPow = () => (ready = solve());
  const takePow = async () => { const p = await (ready || nextPow()); ready = null; return p; };

  async function post(url, body) {
    const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || `The site answered ${r.status}`);
    return j;
  }

  const credJSON = c => {
    const out = {id: c.id, rawId: b64u(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {}, response: {clientDataJSON: b64u(c.response.clientDataJSON)}};
    if (c.authenticatorAttachment) out.authenticatorAttachment = c.authenticatorAttachment;
    const r = c.response;
    if (r.attestationObject) { out.response.attestationObject = b64u(r.attestationObject); if (r.getTransports) out.response.transports = r.getTransports(); }
    if (r.authenticatorData) out.response.authenticatorData = b64u(r.authenticatorData);
    if (r.signature) out.response.signature = b64u(r.signature);
    if (r.userHandle) out.response.userHandle = b64u(r.userHandle);
    return out;
  };
  const createOpts = o => ({...o, challenge: unb64u(o.challenge), user: {...o.user, id: unb64u(o.user.id)},
    excludeCredentials: (o.excludeCredentials || []).map(c => ({...c, id: unb64u(c.id)}))});
  const failText = e => e && e.name === "NotAllowedError" ? "Cancelled, or the device did not answer. Try again." : (e && e.message) || "Something went wrong.";
  const noPasskeys = () => !window.PublicKeyCredential && (msg("This browser cannot use passkeys. Use an up-to-date browser on your phone or computer."), true);

  // sign-in page: password form waits for the browser check
  const pw = $("#pw-form");
  if (pw) {
    nextPow();
    pw.addEventListener("submit", async e => {
      if (pw.dataset.done) return;
      e.preventDefault();
      msg("Checking your browser…");
      try {
        const p = await takePow();
        pw.pow_challenge.value = p.pow_challenge; pw.pow_nonce.value = p.pow_nonce;
        pw.dataset.done = "1"; pw.submit();
      } catch (err) { msg("The browser check failed. Reload the page and try again."); }
    });
  }
  const login = $("#passkey-login");
  if (login) login.addEventListener("click", async () => {
    if (noPasskeys()) return;
    login.disabled = true; msg("Checking your browser…");
    try {
      const o = await post("/passkey/login/options", await takePow());
      nextPow();
      msg("Follow your device's prompt…");
      const c = await navigator.credentials.get({publicKey: {...o, challenge: unb64u(o.challenge), allowCredentials: []}});
      const r = await post("/passkey/login/verify", {credential: credJSON(c), next: login.dataset.next || "/"});
      location.href = r.next || "/";
    } catch (err) { msg(failText(err)); nextPow(); }
    login.disabled = false;
  });

  // invite page: the guest's first passkey
  const inv = $("#invite-create");
  if (inv) {
    nextPow();
    inv.addEventListener("click", async () => {
      if (noPasskeys()) return;
      inv.disabled = true; msg("Checking your browser…");
      const base = `/invite/${inv.dataset.token}`;
      try {
        const o = await post(`${base}/options`, await takePow());
        msg("Follow your device's prompt…");
        const c = await navigator.credentials.create({publicKey: createOpts(o)});
        const r = await post(`${base}/verify`, {credential: credJSON(c)});
        msg("Your passkey is ready. Opening BizDev…");
        location.href = r.next || "/";
      } catch (err) { msg(failText(err)); nextPow(); inv.disabled = false; }
    });
  }

  // My passkeys (owner)
  const add = $("#owner-add-passkey");
  if (add) add.addEventListener("click", async () => {
    if (noPasskeys()) return;
    add.disabled = true;
    try {
      const o = await post("/owner/passkeys/options");
      msg("Follow your device's prompt…");
      const c = await navigator.credentials.create({publicKey: createOpts(o)});
      const r = await post("/owner/passkeys/verify", {credential: credJSON(c)});
      location.href = r.next;
    } catch (err) { msg(failText(err)); add.disabled = false; }
  });

  // copy an invite link; confirm before a remove
  document.addEventListener("click", async e => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    const input = $(b.dataset.copy), out = $("[data-copy-msg]");
    try { await navigator.clipboard.writeText(input.value); if (out) out.textContent = "Copied."; }
    catch (err) { input.select(); if (out) out.textContent = "Select the link and copy it."; }
  });
  document.addEventListener("submit", e => {
    const f = e.target;
    if (f.dataset && f.dataset.confirm && !confirm(f.dataset.confirm)) e.preventDefault();
  });
})();
