"""Data management > Uploads: pictures / PDFs checked by content, explanations without a file, edit and delete."""

import pytest

from app.services import uploads as up

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"x" * 64


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(up, "upload_dir", lambda: d)
    return d


def test_sniff_accepts_only_raster_images_and_pdf():
    assert up.sniff(PNG[:16]) == ("image/png", ".png")
    assert up.sniff(PDF[:16])[0] == "application/pdf"
    assert up.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ")[0] == "image/webp"
    assert up.sniff(b"<svg xmlns=") is None and up.sniff(b"<html>") is None


def test_upload_view_edit_delete(client, tmp_uploads):
    r = client.post("/manage/uploads", data={"title": "Small cell front end", "kind": "block_diagram",
                                             "explanation": "PA, LNA and switch per chain", "topic": "Small cell"},
                    files={"file": ("figure.png", PNG, "image/png")}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    url = r.headers["location"]
    page = client.get(url)
    assert page.status_code == 200 and "Small cell front end" in page.text and "PA, LNA and switch" in page.text
    f = client.get(url + "/file")
    assert (
        f.content == PNG
        and f.headers["content-type"] == "image/png"
        and f.headers["x-content-type-options"] == "nosniff"
    )
    assert "Small cell front end" in client.get("/manage/uploads?kind=block_diagram").text
    client.post(url, data={"title": "Renamed", "kind": "block_diagram", "status": "used", "note": "template 160"})
    assert "Renamed" in client.get(url).text
    assert len(list(tmp_uploads.iterdir())) == 1
    client.post(url + "/delete")
    assert client.get(url).status_code == 404 and not list(tmp_uploads.iterdir())


def test_explanation_without_file_and_refused_types(client, tmp_uploads):
    r = client.post("/manage/uploads", data={"kind": "explanation", "explanation": "Why GNSS LNAs need a pre-filter"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and client.get(r.headers["location"]).status_code == 200
    svg = {"file": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")}
    bad = client.post("/manage/uploads", data={"title": "x"}, files=svg, follow_redirects=False)
    assert "error=" in bad.headers["location"] and not list(tmp_uploads.iterdir())
    empty = client.post("/manage/uploads", data={"title": "nothing"}, follow_redirects=False)
    assert "error=" in empty.headers["location"]
