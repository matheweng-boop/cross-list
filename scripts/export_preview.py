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
from app.services.mechanical import load_mechanical

NOTE = (
    '<p class="banner">Static preview: tap parts and expand the top-5 differences. '
    "Search, filters, the part picker and Excel/CSV downloads work in the full app.</p>"
)


# Suggestions without a server: filter an embedded part list in the browser.
# Enter opens the exact match (or the only match); parts without a full page open cross.html.
HERE = Path(__file__).resolve().parent
OFFLINE_SUGGEST = (
    '<script src="static/preview/parts.js"></script>\n<script>\n'
    + (HERE / "preview" / "search.js").read_text()
    + "</script>"
)


SHARDS = 32  # cross data files, loaded on demand
PER_CATEGORY = 8

# Lightweight part page for parts without a full exported page: renders the crosses from static/preview/x*.js.
CROSS_VIEW = (
    '\n<div id="cross-view"><p class="muted">Loading…</p></div>\n'
    f"<script>window.CL_SHARDS = {SHARDS};</script>\n<script>\n"
    + (HERE / "preview" / "cross.js").read_text()
    + "</script>\n"
)


def _overlay_file(a: int, b: int, lp: int = 0) -> str:
    return f"overlay-{a}-{b}" + (f"-lp{lp}" if lp else "") + ".html"


def rewrite(html: str, package: dict[int, int] | None = None) -> str:
    html = re.sub(
        r'href="/packages/(\d+)/overlay/(\d+)\?lp=(\d+)"',
        lambda m: f'href="{_overlay_file(int(m.group(1)), int(m.group(2)), int(m.group(3)))}"',
        html,
    )
    if package:  # cross details on full part pages link to the package-pair drawing
        html = re.sub(
            r'href="/overlay/(\d+)/(\d+)"',
            lambda m: f'href="{_overlay_file(package[int(m.group(1))], package[int(m.group(2))])}"',
            html,
        )
    html = re.sub(r'href="/parts/(\d+)(?:\?[^"]*)?"', r'href="part-\1.html"', html)
    html = re.sub(r'href="/compare[^".]*"', 'href="compare.html"', html)
    html = re.sub(r'href="/(lifecycle|rules|parts)"', r'href="\1.html"', html)
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


def _write_cross_data(client: TestClient, everything: list[dict], data: Path) -> set[tuple[int, int]]:
    """Best crosses per category for every part, split into shards loaded on demand by cross.html.

    A competitor part is crossed against Skyworks parts only, like the app does by default.
    """
    shards: list[dict] = [{} for _ in range(SHARDS)]
    package = {p["id"]: p["package_id"] for p in everything}
    pairs = set()
    for p in everything:
        crosses = client.get(f"/api/parts/{p['id']}/crosses").json()
        rec = {}
        for cat in ("fff", "upgrade", "p2p", "downgrade"):
            rows = []
            for r in crosses[cat][:PER_CATEGORY]:
                top = r["top_differences"]
                p3 = [
                    f"{d['label']} {d['candidate']} vs {d['reference']}"
                    for d in r["differences"]
                    if d["priority"] == 3
                    and d["status"] in ("worse", "different")
                    and not any(t.startswith(d["label"] + ":") for t in top)
                ]
                rows.append([r["candidate"]["id"], r["fff_status"] if cat == "fff" else "", top, p3])
                pairs.add((package[p["id"]], package[r["candidate"]["id"]]))
            rec[cat] = [rows, len(crosses[cat])]
        shards[p["id"] % SHARDS][p["id"]] = rec
    for n, shard in enumerate(shards):
        (data / f"x{n}.js").write_text(f"CL_SHARD({n}," + json.dumps(shard, separators=(",", ":")) + ");\n")
    return pairs


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
        pages = {"index.html": "/", "parts.html": "/parts", "rules.html": "/rules", "lifecycle.html": "/lifecycle"}
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
    if real:
        # Add the best TI / Novosense candidate per company for each exported Skyworks
        # part, so competitor pages (Skyworks replacements) can be tried too.
        extra: dict[int, dict] = {}
        for p in parts:
            crosses = client.get(f"/api/parts/{p['id']}/crosses").json()
            seen = set()
            for cat in ("fff", "upgrade", "p2p", "downgrade"):
                for r in crosses[cat]:
                    mfr = r["candidate"]["label"].split()[0]
                    if mfr not in seen:
                        seen.add(mfr)
                        extra.setdefault(r["candidate"]["id"], {"id": r["candidate"]["id"]})
        parts = parts + list(extra.values())[:60]
    pages.update({f"part-{p['id']}.html": f"/parts/{p['id']}" for p in parts})
    exported = {p["id"] for p in parts}
    everything = client.get("/api/parts?limit=5000").json()
    index = [
        [
            p["mpn"],
            p["manufacturer"],
            p["package"],
            p["lifecycle"]["status"],
            p["id"] * (p["id"] in exported),
            p["id"],
            p["package_id"],
        ]
        for p in everything
    ]
    data = out / "static" / "preview"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    (data / "parts.js").write_text("window.CL_PARTS=" + json.dumps(index, separators=(",", ":")) + ";\n")
    if real:
        pages["cross.html"] = "/rules"  # page frame only; the body is replaced below
        for a, b in sorted(_write_cross_data(client, everything, data)):
            lands = load_mechanical().get(next(p["package"] for p in everything if p["package_id"] == a))
            for lp in range(max(1, len(lands.land_patterns) if lands else 1)):
                pages[_overlay_file(a, b, lp)] = f"/packages/{a}/overlay/{b}?lp={lp}"
    for name, url in pages.items():
        html = rewrite(client.get(url).text, {p["id"]: p["package_id"] for p in everything})
        if name == "cross.html":
            main = re.compile(r'(<main class="container">).*</main>', re.S)
            html = main.sub(lambda m: m.group(1) + CROSS_VIEW + "</main>", html)
            html = re.sub(r"<title>[^<]*</title>", "<title>Part crosses · Cross List</title>", html)
        html = html.replace('hx-get="/suggest"', "data-static-suggest")
        html = html.replace("</body>", OFFLINE_SUGGEST + "</body>")
        # Parts without a full page open the light crosses view (real data) or lose the link.
        html = re.sub(
            r'<a href="part-(\d+)\.html"([^>]*)>(.*?)</a>',
            lambda m: (
                m.group(0)
                if int(m.group(1)) in exported
                else (f'<a href="cross.html#{m.group(1)}"{m.group(2)}>{m.group(3)}</a>' if real else m.group(3))
            ),
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
