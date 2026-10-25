// Interactive visual "Hex, binary and registers" (owner, 24 Oct 2026: "Can you add a HEX decoding table, HEX to
// Binary. What else would be useful for binary?"). Registers with the visuals engine in visuals.js (window.VZ_ADD).
// The number maths sits in window.VZ_HEX, plain functions without the page, so the tests can check it directly.
(() => {
  // ------------------------------------------------------------------ number maths (w = word size: 8, 16 or 32 bits)
  const u = (x, w) => (w >= 32 ? x >>> 0 : (x >>> 0) % 2 ** w);  // unsigned value of the low w bits
  const signed = (x, w) => { const v = u(x, w); return v >= 2 ** (w - 1) ? v - 2 ** w : v; };  // two's complement
  const hex = (x, w) => "0x" + u(x, w).toString(16).toUpperCase().padStart(w / 4, "0");
  const bin = (x, w) => u(x, w).toString(2).padStart(w, "0");
  const group4 = s => s.replace(/(.{4})(?=.)/g, "$1 ");
  const oct = (x, w) => "0o" + u(x, w).toString(8);
  // text typed in one base -> unsigned w-bit value, or {error}; kind: 16, 2, 8, "u" (decimal) or "s" (signed decimal)
  function parse(text, kind, w) {
    let t = String(text).trim().replace(/[\s_]/g, "");
    if (!t) return {error: "Type a number."};
    const neg = kind === "s" && t.startsWith("-");
    if (neg) t = t.slice(1);
    t = t.replace(kind === 16 ? /^0x/i : kind === 2 ? /^0b/i : kind === 8 ? /^0o/i : /^$/, "");
    const ok = {16: /^[0-9a-f]+$/i, 2: /^[01]+$/, 8: /^[0-7]+$/, u: /^\d+$/, s: /^\d+$/}[kind];
    if (!t || !ok.test(t)) return {error: {16: "Hex uses 0–9 and A–F.", 2: "Binary uses only 0 and 1.", 8: "Octal uses 0–7.", u: "Decimal uses 0–9.", s: "Decimal uses 0–9 and a leading minus."}[kind]};
    const n = parseInt(t, typeof kind === "number" ? kind : 10) * (neg ? -1 : 1);
    const lo = kind === "s" ? -(2 ** (w - 1)) : 0, hi = kind === "s" ? 2 ** (w - 1) - 1 : 2 ** w - 1;
    if (!(n >= lo && n <= hi)) return {error: `Does not fit in ${w} bits (${kind === "s" ? `${lo} to ${hi}` : `0 to ${hi}`}): choose a larger word.`};
    return {value: n < 0 ? n + 2 ** w : n};
  }
  const bytes = (x, w) => Array.from({length: w / 8}, (_, i) => (u(x, w) >>> (8 * (w / 8 - 1 - i))) & 255);  // big endian
  const swap = (x, w) => bytes(x, w).reverse().reduce((a, b) => a * 256 + b, 0);  // the other byte order
  const fieldValue = (x, hi, lo) => (hi - lo + 1 >= 32 ? x >>> 0 : ((x >>> lo) & (2 ** (hi - lo + 1) - 1)) >>> 0);
  // "[7:4] MODE, [3] EN" -> [{hi, lo, name}]; fields outside the word or overlapping an earlier one are dropped
  function fields(text, w) {
    const out = [], used = new Set();
    for (const m of String(text).matchAll(/\[\s*(\d+)\s*(?::\s*(\d+)\s*)?\]\s*([A-Za-z_][\w-]*)/g)) {
      let hi = +m[1], lo = m[2] == null ? hi : +m[2];
      if (lo > hi) [hi, lo] = [lo, hi];
      if (hi >= w) continue;
      const bits = Array.from({length: hi - lo + 1}, (_, i) => lo + i);
      if (bits.some(b => used.has(b))) continue;
      bits.forEach(b => used.add(b));
      out.push({hi, lo, name: m[3]});
    }
    return out;
  }
  const bcd = n => String(n).split("").map(d => (+d).toString(2).padStart(4, "0")).join(" ");  // each decimal digit in 4 bits
  const fromBcd = (x, w) => { const h = u(x, w).toString(16); return /^[0-9]+$/.test(h) ? +h : null; };  // null: a nibble above 9
  const gray = x => (x ^ (x >>> 1)) >>> 0;
  const fromGray = g => { let x = g >>> 0; for (let s = 1; s < 32; s <<= 1) x = (x ^ (x >>> s)) >>> 0; return x; };
  const CTRL = ["NUL", "SOH", "STX", "ETX", "EOT", "ENQ", "ACK", "BEL", "BS (backspace)", "TAB", "LF (new line)", "VT", "FF", "CR (carriage return)", "SO", "SI",
    "DLE", "DC1 (XON)", "DC2", "DC3 (XOFF)", "DC4", "NAK", "SYN", "ETB", "CAN", "EM", "SUB", "ESC", "FS", "GS", "RS", "US"];
  const ascii = b => (b < 32 ? CTRL[b] : b === 32 ? "space" : b < 127 ? String.fromCharCode(b) : b === 127 ? "DEL" : "not ASCII (above 127)");
  const ones = x => bin(x, 32).split("").filter(c => c === "1").length;
  window.VZ_HEX = {u, signed, hex, bin, oct, parse, bytes, swap, fieldValue, fields, bcd, fromBcd, gray, fromGray, ascii, ones};

  // ------------------------------------------------------------------ the visual
  (window.VZ_ADD = window.VZ_ADD || []).push(({V, esc}) => {
    const S = {val: 0xB5, w: 8, fields: "[7:4] MODE, [3] EN, [2:0] DIV"};
    let sync = () => {};
    const code = s => `<code>${esc(s)}</code>`;
    const KINDS = [[16, "Hex"], [2, "Binary"], ["u", "Decimal (unsigned)"], ["s", "Decimal (signed, two's complement)"], [8, "Octal"]];
    const show = (kind, x, w) => (kind === 16 ? hex(x, w) : kind === 2 ? group4(bin(x, w)) : kind === 8 ? oct(x, w) : kind === "s" ? String(signed(x, w)) : String(u(x, w)));
    const MASKS = [["15", "0x0F: low nibble (bits 3–0)"], ["240", "0xF0: high nibble (bits 7–4)"], ["1", "0x01: bit 0"], ["128", "0x80: bit 7"], ["85", "0x55: every other bit"], ["65280", "0xFF00: high byte (16-bit)"]];

    V.push({
      id: "hex", group: "Digital basics", title: "Hex, binary and registers",
      lead: "Chips are set up by writing numbers into registers. Binary is how the chip stores them (one bit per switch), hex is the short way to write them: one hex digit is exactly four bits. Type a number in any box, click the bits of the register, and see masks, byte order, BCD, Gray code and ASCII for the same value.",
      explains: [["Clocks and oscillators (Si5xx)", "/knowledge#p-timing"], ["Broadcast radio tuners (Si47xx / Si46xx)", "/knowledge#p-tuners"]],
      controls: [
        {k: "w", label: "Word size", type: "select", options: [["8", "8-bit (one byte)"], ["16", "16-bit"], ["32", "32-bit"]], value: "8"},
        {k: "bit", label: "Bit for the set / clear example", min: 0, max: 31, step: 1, value: 3, unit: ""},
        {k: "sh", label: "Shift by", min: 0, max: 8, step: 1, value: 1, unit: "bits"},
        {k: "mk", label: "Mask for AND / OR / XOR", type: "select", options: MASKS, value: "15"},
      ],
      setup(el, rerender) {
        Object.assign(S, {val: 0xB5, w: 8, fields: "[7:4] MODE, [3] EN, [2:0] DIV"});
        el.innerHTML = `<div class="hx-conv">${KINDS.map(([k, l]) => `<label><span>${esc(l)}</span><input type="text" data-hx="${k}" spellcheck="false" autocomplete="off" autocapitalize="off" inputmode="${k === 16 ? "text" : k === "s" ? "text" : "numeric"}" aria-label="${esc(l)}"></label>`).join("")}
          <label class="hx-wide"><span>Register fields: [high bit:low bit] NAME, separated by commas</span><input type="text" class="hx-fields" spellcheck="false" autocomplete="off" value="${esc(S.fields)}" aria-label="Register fields"></label></div>
          <p class="hx-msg small" aria-live="polite"></p>`;
        const msg = el.querySelector(".hx-msg");
        sync = () => el.querySelectorAll("[data-hx]").forEach(inp => {
          if (inp === document.activeElement) return;  // leave the box being typed in alone
          const k = inp.dataset.hx;
          inp.value = show(isNaN(+k) ? k : +k, S.val, S.w);
          inp.removeAttribute("aria-invalid");
        });
        el.querySelectorAll("[data-hx]").forEach(inp => inp.addEventListener("input", () => {
          const k = isNaN(+inp.dataset.hx) ? inp.dataset.hx : +inp.dataset.hx, r = parse(inp.value, k, S.w);
          if (r.error) { inp.setAttribute("aria-invalid", "true"); msg.textContent = r.error; return; }
          inp.removeAttribute("aria-invalid"); msg.textContent = "";
          S.val = r.value; rerender();
        }));
        el.querySelectorAll("[data-hx]").forEach(inp => inp.addEventListener("blur", () => { msg.textContent = ""; sync(); }));
        el.querySelector(".hx-fields").addEventListener("input", e => { S.fields = e.target.value; rerender(); });
        // the register bits are drawn in the panel's "more" area on every render: one listener for all of them
        el.parentElement.querySelector(".vz-more").addEventListener("click", e => {
          const b = e.target.closest("[data-bit]");
          if (!b) return;
          S.val = (S.val ^ 2 ** +b.dataset.bit) >>> 0;
          rerender();
          const again = el.parentElement.querySelector(`[data-bit="${b.dataset.bit}"]`);
          if (again) again.focus();
        });
      },
      compute(v) {
        const w = +v.w;
        if (w !== S.w) { S.w = w; S.val = u(S.val, w); }
        sync();
        const x = S.val, bit = Math.min(Math.round(v.bit), w - 1), sh = Math.round(v.sh), m = u(+v.mk, w), one = u(2 ** bit, w);
        const fs = fields(S.fields, w), fieldOf = b => fs.findIndex(f => b >= f.lo && b <= f.hi);
        const H = hex(x, w).slice(2), B = bin(x, w);
        // register view: one row per byte, most significant first; click a bit to flip it
        const rows = Array.from({length: w / 8}, (_, r) => {
          const top = w - 1 - 8 * r;
          const cells = Array.from({length: 8}, (_, i) => {
            const b = top - i, on = B[w - 1 - b] === "1", fi = fieldOf(b);
            return `<button type="button" class="hx-bit${on ? " on" : ""}${fi >= 0 ? ` hx-f${fi % 6}` : ""}${i === 3 ? " hx-gap" : ""}" data-bit="${b}" aria-pressed="${on}" aria-label="Bit ${b}${fi >= 0 ? ", " + esc(fs[fi].name) : ""}: ${on ? 1 : 0}"><small>${b}</small>${on ? 1 : 0}</button>`;
          }).join("");
          return `<div class="hx-row"><span class="hx-rl small muted">${w > 8 ? `byte ${w / 8 - 1 - r}` : "bits"}<br>${hex(u(x >>> (8 * (w / 8 - 1 - r)), 8), 8)}</span>${cells}</div>`;
        }).join("");
        const ftab = fs.length ? `<table class="hx-t"><thead><tr><th>Field</th><th>Bits</th><th>Binary</th><th class="n">Value</th></tr></thead><tbody>${fs.map((f, i) => {
          const fv = fieldValue(x, f.hi, f.lo), n = f.hi - f.lo + 1;
          return `<tr><td><span class="hx-sw hx-f${i % 6}"></span>${esc(f.name)}</td><td>[${f.hi}${n > 1 ? ":" + f.lo : ""}]</td><td>${code(fv.toString(2).padStart(n, "0"))}</td><td class="n">${fv} = 0x${fv.toString(16).toUpperCase()}</td></tr>`;
        }).join("")}</tbody></table>` : '<p class="small muted">No fields: type them above, for example [7:4] MODE, [3] EN.</p>';
        // nibble table 0-F in two halves
        const nib = i => `<td class="hx-h${H.includes(i.toString(16).toUpperCase()) ? " in" : ""}">${i.toString(16).toUpperCase()}</td><td>${code(i.toString(2).padStart(4, "0"))}</td><td class="n">${i}</td>`;
        const ntab = `<table class="hx-t hx-nib"><thead><tr><th>Hex</th><th>Binary</th><th class="n">Dec</th><th>Hex</th><th>Binary</th><th class="n">Dec</th></tr></thead><tbody>${Array.from({length: 8}, (_, i) => `<tr>${nib(i)}${nib(i + 8)}</tr>`).join("")}</tbody></table>`;
        // masks and shifts
        const line = (label, val, how) => `<tr><td>${label}</td><td>${code(group4(bin(val, w)))}</td><td>${code(hex(val, w))}</td><td class="small">${how}</td></tr>`;
        const ops = `<table class="hx-t hx-ops"><thead><tr><th>Operation</th><th>Binary</th><th>Hex</th><th>What it does</th></tr></thead><tbody>
          ${line("value", x, "your number")}${line("mask", m, "the bits you care about")}
          ${line("value AND mask", x & m, "keeps only the mask's bits: read a field")}${line("value OR mask", (x | m) >>> 0, "forces the mask's bits to 1: switch on")}
          ${line("value XOR mask", (x ^ m) >>> 0, "flips the mask's bits")}${line("NOT value", ~x >>> 0, "flips every bit")}
          ${line(`value &lt;&lt; ${sh}`, (x << sh) >>> 0, `moves bits left: × ${2 ** sh}, bits pushed out on the left are lost`)}${line(`value &gt;&gt; ${sh}`, u(x, w) >>> sh, `moves bits right: ÷ ${2 ** sh}, rounded down`)}</tbody></table>`;
        const setv = (x | one) >>> 0, clr = (x & ~one) >>> 0, isSet = (x & one) !== 0;
        const worked = `<p class="small"><b>Worked example, bit ${bit}.</b> The mask for bit ${bit} is 1 &lt;&lt; ${bit} = ${code(hex(one, w))}.
          Set it: value OR mask = ${code(hex(x, w))} | ${code(hex(one, w))} = ${code(hex(setv, w))}.
          Clear it: value AND (NOT mask) = ${code(hex(x, w))} &amp; ${code(hex(~one >>> 0, w))} = ${code(hex(clr, w))}.
          Test it: value AND mask = ${code(hex(x & one, w))}, so bit ${bit} is <b>${isSet ? "1 (set)" : "0 (clear)"}</b>.
          This is read-modify-write: read the register, change only your bit, write it back, so the other settings stay.</p>`;
        // byte order
        const endian = [16, 32].map(n => {
          const val = u(x, n), be = bytes(val, n).map(b => hex(b, 8).slice(2)).join(" "), le = bytes(val, n).reverse().map(b => hex(b, 8).slice(2)).join(" ");
          return `<tr><td>${n}-bit ${code(hex(val, n))}</td><td>${code(be)}</td><td>${code(le)}</td><td>${code(hex(swap(val, n), n))}</td></tr>`;
        }).join("");
        const etab = `<table class="hx-t"><thead><tr><th>Value</th><th>Big endian (bytes in order)</th><th>Little endian</th><th>Read with the wrong order</th></tr></thead><tbody>${endian}</tbody></table>`;
        // BCD, Gray, ASCII, parity
        const dec = u(x, w), fb = fromBcd(x, w), g = gray(u(x, w)), lowByte = u(x, 8);
        const chars = bytes(x, w).map(b => (b >= 32 && b < 127 ? String.fromCharCode(b) : "·")).join("");
        const p = ones(u(x, w));
        const grayRows = Array.from({length: 8}, (_, i) => `<td>${i}</td><td>${code(bin(i, 8).slice(5))}</td><td>${code(bin(gray(i), 8).slice(5))}</td>`);
        const gtab = `<table class="hx-t hx-gray"><thead><tr><th class="n">n</th><th>Binary</th><th>Gray</th><th class="n">n</th><th>Binary</th><th>Gray</th></tr></thead><tbody>${[0, 1, 2, 3].map(i => `<tr>${grayRows[i]}${grayRows[i + 4]}</tr>`).join("")}</tbody></table>`;
        return {
          outputs: [["Hex", hex(x, w)], ["Binary", group4(B)], ["Unsigned decimal", String(dec)], [`Signed (int${w}, two's complement)`, String(signed(x, w))]],
          eq: "value = Σ bit<sub>n</sub> · 2<sup>n</sup> &nbsp;·&nbsp; one hex digit = 4 bits (a nibble) &nbsp;·&nbsp; signed: if the top bit is 1, value − 2<sup>w</sup>",
          eqn: `${hex(x, w)} = ${H.split("").map((d, i) => `${parseInt(d, 16)}·16<sup>${H.length - 1 - i}</sup>`).join(" + ")} = ${dec}${signed(x, w) < 0 ? ` &nbsp;·&nbsp; top bit 1, so signed = ${dec} − 2<sup>${w}</sup> = ${signed(x, w)}` : ""}`,
          html: `<div class="hx">
            <h3>Register: click a bit to flip it</h3><div class="hx-reg" role="group" aria-label="Register bits">${rows}</div>${ftab}
            <p class="small">A register is a row of switches inside the chip. The data sheet's register map names groups of bits, like ${code("[7:4] MODE")}: bits 7 down to 4 together hold the mode (0–15). Writing the whole byte changes every field in it, which is why masks matter.</p>
            <div class="hx-cols"><div><h3>Hex to binary: the 16 nibbles</h3>${ntab}<p class="small">Every hex digit is four bits, so you convert digit by digit: ${code(hex(x, w))} = ${code(group4(B))}. The digits in your number are highlighted.</p></div>
            <div><h3>Masks and shifts</h3><div class="hx-scroll">${ops}</div>${worked}</div></div>
            <h3>Byte order (endianness)</h3><div class="hx-scroll">${etab}</div>
            <p class="small">A 16- or 32-bit number travels as bytes. Big endian sends the most significant byte first (most I²C and SPI register maps, network protocols); little endian sends the least significant first (Arm and x86 memory, USB). Read the bytes in the wrong order and ${code(hex(u(x, 16), 16))} becomes ${code(hex(swap(u(x, 16), 16), 16))}.</p>
            <div class="hx-cols"><div><h3>BCD and Gray code</h3>
              <p class="small"><b>BCD</b> (binary-coded decimal) stores each decimal digit in its own four bits, so the hex looks like the decimal number: ${dec} in BCD is ${code(bcd(dec))}. Real-time clocks keep the time this way (59 seconds = 0x59). Your value read as BCD: ${fb == null ? "not valid BCD, a nibble is above 9" : `<b>${fb}</b>`}.</p>
              <p class="small"><b>Gray code</b> changes only one bit between neighbouring numbers, so a reading taken mid-change is never far off: rotary encoders, position sensors, FIFO pointers crossing clock domains. Your value in Gray: ${code(group4(bin(g, w)))} (${code(hex(g, w))}); decoded back: ${fromGray(g)}.</p>${gtab}</div>
            <div><h3>ASCII: a byte as a character</h3>
              <p class="small">The low byte ${code(hex(lowByte, 8))} = ${lowByte} is <b>${esc(ascii(lowByte))}</b> in ASCII. All bytes of the value as text: ${code(chars)} (· = not printable). Letters start at 0x41 (A) and 0x61 (a), digits at 0x30 (0); 0x20 is a space.</p>
              <h3>Parity and CRC (optional)</h3>
              <p class="small">Your value has ${p} one${p === 1 ? "" : "s"}, so an even-parity bit would be ${p % 2} (it makes the count of ones even). Parity catches one flipped bit. A CRC is a stronger check made by shifting and XOR-ing the data; links such as SPI with CRC, CAN and SENT add one to each frame so a corrupted register write is rejected instead of applied.</p></div></div>
            <h3>Why it matters for our parts</h3>
            <ul class="small hx-why">
              <li><b>Si5xx clocks and jitter attenuators</b> (Si534x, Si539x, Si5332): set up over I²C or SPI with hundreds of registers. ClockBuilder Pro exports the setup as address / value pairs in hex; on the larger parts a 16-bit address is a page (high byte, written to the page register) plus a register (low byte). A customer who flashes the list in the wrong byte order gets a clock that does not lock.</li>
              <li><b>Si47xx / Si46xx radios</b>: the host sends a command byte and argument bytes, and sets properties by number. Example from the Si47xx programming guide (AN332): FM_TUNE_FREQ is command 0x20 and takes the frequency in 10 kHz steps, high byte first; 98.1 MHz = 9810 = ${code("0x2652")}, sent as ${code("0x26 0x52")}. Status replies are bit fields read with AND masks (for example "seek/tune complete").</li>
              <li><b>Isolators and gate drivers</b>: most digital isolators are set by pins and part number (default output high or low, channel direction), not registers. Drivers and isolated converters with a digital interface report faults as a status byte where each bit is one flag (undervoltage, desaturation, over-temperature: an example layout, est); the firmware reads it with a mask and clears it by writing the bit back.</li>
              <li><b>In support questions</b>: a customer's register dump, I²C trace or logic-analyser capture is hex. Converting it here tells you which field is set before you forward it to an applications engineer.</li>
            </ul></div>`,
          note: "Word size sets how many bits the number has: the same bits read as signed or unsigned give different decimals (0xFF is 255 unsigned, −1 as a signed byte). Prefixes: 0x hex, 0b binary, 0o octal; spaces and underscores in the boxes are ignored.",
          nochart: true,
        };
      },
      related: [["Clock tree and jitter visual", "#jitter"], ["Si47xx tuners", "/find?q=Si47"], ["Si5xx clocks", "/find?q=Si53"]],
    });
  });
})();
