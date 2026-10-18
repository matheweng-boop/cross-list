"""Export a static, read-only snapshot of the app (for viewing without a server).

    uv run python -m scripts.export_preview OUT_DIR          # synthetic demo data
    uv run python -m scripts.export_preview OUT_DIR --real   # current database, one
                                                             # page per Skyworks base part

Links are rewritten to local files; search, filters and downloads are disabled
because they need the live server. Links to pages that are not exported are removed.
"""

import json
import re
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

NOTE = (
    '<p class="banner">Static preview: tap parts and expand the top-5 differences. '
    "Search, filters, the part picker and Excel/CSV downloads work in the full app.</p>"
)


# Suggestions without a server: filter an embedded part list in the browser.
OFFLINE_SUGGEST = """<script>
(() => {
  const parts = __INDEX__;
  const box = document.getElementById("global-search"), out = document.getElementById("suggestions");
  if (!box || !out) return;
  const norm = s => s.replace(/[\\s\\-_/]/g, "").toUpperCase();
  const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  box.addEventListener("input", () => {
    const q = norm(box.value);
    if (q.replace(/\\*/g, "").length < 2) { out.innerHTML = ""; return; }
    const rx = new RegExp(q.split("*").map(s => s.replace(/[.+?^${}()|[\\]\\\\]/g, "\\\\$&")).join(".*"));
    const hits = parts.filter(p => rx.test(norm(p[0])))
      .sort((a, b) => (norm(b[0]).startsWith(q) - norm(a[0]).startsWith(q)) || a[0].localeCompare(b[0])).slice(0, 60);
    out.innerHTML = hits.length ? '<ul class="suggest-list">' + hits.map(p => {
      const meta = esc(p[1]) + " · " + esc(p[2]) + " · " + esc(p[3]);
      const body = '<span class="sg-mpn">' + esc(p[0]) + '</span><span class="sg-meta">' + meta + "</span>";
      if (p[4]) return '<li><a href="part-' + p[4] + '.html">' + body + "</a></li>";
      return '<li><a aria-disabled="true">' + body + ' <span class="sg-meta">(not in preview)</span></a></li>';
    }).join("") + "</ul>" : '<p class="suggest-list muted sg-empty">No part numbers contain that.</p>';
  });
})();
</script>"""


def rewrite(html: str) -> str:
    html = re.sub(r'href="/parts/(\d+)(?:\?[^"]*)?"', r'href="part-\1.html"', html)
    html = re.sub(r'href="/compare[^".]*"', 'href="compare.html"', html)
    html = re.sub(r'href="/(lifecycle|rules)"', r'href="\1.html"', html)
    html = html.replace('href="/"', 'href="index.html"').replace('href="/static/', 'href="static/')
    html = html.replace('src="/static/', 'src="static/')
    # downloads need the server
    html = re.sub(
        r'<a href="/(?:cross|compare)[^"]*\.(?:xlsx|csv)[^"]*"[^>]*>([^<]*)</a>',
        r'<span class="muted">\1 (full app)</span>',
        html,
    )
    html = re.sub(r"<form ", '<form onsubmit="return false" ', html)
    html = html.replace('onchange="this.form.submit()"', "disabled")
    html = html.replace('<main class="container">', '<main class="container">\n  ' + NOTE, 1)
    return html


def _representatives(parts: list[dict]) -> list[dict]:
    """One Skyworks part per base part, preferring wide-body default-low parts."""
    best: dict[str, dict] = {}
    for p in parts:
        if p["role"] != "reference":
            continue
        m = re.match(r"^(SI86(?:S\d{3}|S[A-Z]\d{2}|P\d{3}|\d{2}))", p["mpn"])
        key = m.group(1) if m else p["mpn"]
        rank = (p["package"] != "SOIC-16W", "-A" in p["mpn"], len(p["mpn"]), p["mpn"])
        if key not in best or rank < best[key][0]:
            best[key] = (rank, p)
    return [v[1] for v in best.values()]


def main(out: Path, real: bool = False) -> None:
    out = out.resolve()
    if out == Path.cwd().resolve() or (out / "pyproject.toml").exists():
        raise SystemExit(f"Refusing to export into {out}: choose an empty output folder")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):  # previous export in this folder only
        old.unlink()
    tmp = out / "_preview.db"
    tmp.unlink(missing_ok=True)
    if real:
        client = TestClient(create_app(seed_synthetic=False))
        parts = _representatives(client.get("/api/parts?role=reference&limit=5000").json())
        pages = {"index.html": "/?q=", "rules.html": "/rules", "lifecycle.html": "/lifecycle"}
        by_mpn = {p["mpn"]: p["id"] for p in client.get("/api/parts?limit=5000").json()}
        pick = [by_mpn[m] for m in ("SI8641BD-IS", "ISO7741DWR", "NSI8241W0-DSWR", "ISO6741DWR") if m in by_mpn]
        if pick:
            pages["compare.html"] = f"/compare?ids={','.join(map(str, pick))}&baseline={pick[0]}"
    else:
        client = TestClient(create_app(f"sqlite:///{tmp}", seed_synthetic=True))
        parts = client.get("/api/parts").json()
        ids = {p["mpn"]: p["id"] for p in parts}
        pages = {"index.html": "/", "lifecycle.html": "/lifecycle", "rules.html": "/rules"}
        pick = ",".join(str(ids[m]) for m in ["SR8641", "SA7741", "SB8441", "SC141", "SD8641A"])
        pages["compare.html"] = f"/compare?ids={pick}&baseline={ids['SR8641']}"
    pages.update({f"part-{p['id']}.html": f"/parts/{p['id']}" for p in parts})
    exported = {p["id"] for p in parts}
    everything = client.get("/api/parts?limit=5000").json()
    index = [
        [p["mpn"], p["manufacturer"], p["package"], p["lifecycle"]["status"], p["id"] if p["id"] in exported else 0]
        for p in everything
    ]
    for name, url in pages.items():
        html = rewrite(client.get(url).text)
        html = html.replace('hx-get="/suggest"', "data-static-suggest")
        html = html.replace("</body>", OFFLINE_SUGGEST.replace("__INDEX__", json.dumps(index)) + "</body>")
        # Drop links to part pages that are not part of this export.
        html = re.sub(
            r'<a href="part-(\d+)\.html"[^>]*>(.*?)</a>',
            lambda m: m.group(0) if int(m.group(1)) in exported else m.group(2),
            html,
            flags=re.S,
        )
        if name == "index.html":  # the artifact host supplies the document skeleton for the main page
            head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
            head = re.sub(r"<meta[^>]*>\s*", "", head)
            body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
            html = head.strip() + "\n" + body
        (out / name).write_text(html)
    static = Path(__file__).resolve().parent.parent / "app" / "web" / "static"
    shutil.copytree(static, out / "static", dirs_exist_ok=True)
    tmp.unlink(missing_ok=True)
    print(f"{len(pages)} pages written to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), real="--real" in sys.argv)
