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
    if (!r.ok) throw Object.assign(new Error(j.detail || `it answered ${r.status}`), {name: "SiteError"});
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
  const getOpts = o => ({...o, challenge: unb64u(o.challenge),
    allowCredentials: (o.allowCredentials || []).map(a => ({...a, id: unb64u(a.id)}))});

  // Plain-English text for every way a passkey step can fail: never fail silently.
  const failText = (e, creating) => {
    const n = e && e.name;
    if (n === "NotAllowedError") return "The passkey prompt was cancelled, timed out or blocked by the browser. Tap the button again.";
    if (n === "InvalidStateError") return creating ? "This device already has a passkey for this site. Use it to sign in, or remove it in the device's password settings first." : "The passkey could not be used on this device. Try again.";
    if (n === "SecurityError") return "The browser refused passkeys for this address. Open the site at its usual https address and try again.";
    if (n === "AbortError") return "The passkey step was interrupted. Tap the button again.";
    if (n === "NotSupportedError") return "This device or browser cannot make this kind of passkey. Try an up-to-date phone or computer.";
    if (n === "SiteError") return `The site said: ${e.message}`;
    if (n === "TypeError") return "Could not reach the site. Check the connection and try again.";
    return e && e.message ? `Something went wrong: ${e.message}` : "Something went wrong. Try again.";
  };
  const noPasskeys = () => !window.PublicKeyCredential && (msg("This browser cannot use passkeys. Use an up-to-date browser on your phone or computer."), true);

  // Options are fetched BEFORE the tap. Safari (WebKit) shows the passkey prompt only when navigator.credentials is
  // called directly inside the tap; after an awaited network request the tap no longer counts. So the options (and, to
  // sign in, the browser check) are prepared on page load, again every 4 minutes (the server's challenge lives 5 minutes
  // and works once) and after every failure, and each click handler calls navigator.credentials first.
  const FRESH = 240e3;
  function prepared(fetchOpts, build) {
    const st = {opts: null, at: 0, busy: null, err: null, timer: 0};
    const load = () => {
      if (st.busy) return st.busy;
      clearTimeout(st.timer);
      st.opts = null; st.err = null;
      st.busy = fetchOpts()
        .then(o => { st.opts = build(o); st.at = Date.now(); },
              e => { st.err = e; msg(`${failText(e)} Tap the button to try again.`); })
        .finally(() => { st.busy = null; if (!st.err) st.timer = setTimeout(() => { if (!document.hidden) load(); }, FRESH); });
      return st.busy;
    };
    const stale = () => !st.opts || Date.now() - st.at > FRESH;
    document.addEventListener("visibilitychange", () => { if (!document.hidden && !st.busy && !st.err && stale()) load(); });
    addEventListener("pageshow", e => { if (e.persisted) load(); });
    load();
    return {
      load,
      // the prepared options, used once; null (and a fresh fetch) when they are missing or too old
      take() {
        const o = st.opts;
        if (!o || Date.now() - st.at > FRESH + 30e3) {
          if (!st.busy) load();
          msg("Preparing… tap again in a moment.");
          return null;
        }
        st.opts = null;
        return o;
      },
    };
  }
  // navigator.credentials as a promise, also when it throws at once
  const call = f => { try { return Promise.resolve(f()); } catch (e) { return Promise.reject(e); } };

  // After navigator.credentials was called inside the tap: send the result, then go on or explain the failure.
  function finish(btn, prep, pending, send, creating) {
    msg("Follow your device's prompt…");
    btn.disabled = true;
    pending
      .then(c => {
        if (!c) throw Object.assign(new Error("no passkey"), {name: "NotAllowedError"});
        msg("Checking…");
        return send(credJSON(c));
      })
      .then(r => { msg(creating ? "Your passkey is ready. Opening BizDev…" : "Confirmed. Opening BizDev…"); location.href = r.next || "/"; })
      .catch(err => { msg(failText(err, creating)); btn.disabled = false; prep.load(); });
  }

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

  // One passkey button: its options are prepared ahead, and the tap calls navigator.credentials before anything else.
  const login = $("#passkey-login");
  if (login && window.PublicKeyCredential) {
    // sign in: its own browser check and options, both ready before the tap
    const prep = prepared(async () => post("/passkey/login/options", await solve()), o => ({...getOpts(o), allowCredentials: []}));
    login.addEventListener("click", () => {
      const o = prep.take();
      if (!o) return;
      const pending = call(() => navigator.credentials.get({publicKey: o}));
      finish(login, prep, pending, cred => post("/passkey/login/verify", {credential: cred, next: login.dataset.next || "/"}), false);
    });
  } else if (login) login.addEventListener("click", noPasskeys);

  // invite page: the guest's first passkey
  const inv = $("#invite-create");
  if (inv && window.PublicKeyCredential) {
    const base = `/invite/${inv.dataset.token}`;
    const prep = prepared(async () => post(`${base}/options`, await solve()), createOpts);
    inv.addEventListener("click", () => {
      const o = prep.take();
      if (!o) return;
      const pending = call(() => navigator.credentials.create({publicKey: o}));
      finish(inv, prep, pending, cred => post(`${base}/verify`, {credential: cred}), true);
    });
  } else if (inv) inv.addEventListener("click", noPasskeys);

  // My passkeys (owner)
  const add = $("#owner-add-passkey");
  if (add && window.PublicKeyCredential) {
    const prep = prepared(() => post("/owner/passkeys/options"), createOpts);
    add.addEventListener("click", () => {
      const o = prep.take();
      if (!o) return;
      const pending = call(() => navigator.credentials.create({publicKey: o}));
      finish(add, prep, pending, cred => post("/owner/passkeys/verify", {credential: cred}), true);
    });
  } else if (add) add.addEventListener("click", noPasskeys);

  // owner confirmation (step-up) with one of the owner's passkeys
  const conf = $("#owner-confirm-passkey");
  if (conf && window.PublicKeyCredential) {
    const prep = prepared(() => post("/owner/confirm/options"), getOpts);
    conf.addEventListener("click", () => {
      const o = prep.take();
      if (!o) return;
      const pending = call(() => navigator.credentials.get({publicKey: o}));
      const next = conf.dataset.next || "/manage/people";
      finish(conf, prep, pending, cred => post("/owner/confirm/verify", {credential: cred, next}).then(r => ({next: r.next || next})), false);
    });
  } else if (conf) conf.addEventListener("click", noPasskeys);

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
