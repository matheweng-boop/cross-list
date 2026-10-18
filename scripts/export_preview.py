"""Export a static, read-only snapshot of the app (for viewing without a server).

    uv run python -m scripts.export_preview OUT_DIR

Uses the synthetic demo data. Links are rewritten to local files; search, filters
and downloads are disabled because they need the live server.
"""

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


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_preview.db"
    tmp.unlink(missing_ok=True)
    client = TestClient(create_app(f"sqlite:///{tmp}", seed_synthetic=True))
    parts = client.get("/api/parts").json()
    ids = {p["mpn"]: p["id"] for p in parts}
    pages = {"index.html": "/", "lifecycle.html": "/lifecycle", "rules.html": "/rules"}
    pick = ",".join(str(ids[m]) for m in ["SR8641", "SA7741", "SB8441", "SC141", "SD8641A"])
    pages["compare.html"] = f"/compare?ids={pick}&baseline={ids['SR8641']}"
    pages.update({f"part-{p['id']}.html": f"/parts/{p['id']}" for p in parts})
    for name, url in pages.items():
        html = rewrite(client.get(url).text)
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
    main(Path(sys.argv[1]))
