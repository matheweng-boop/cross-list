"""Polite HTTP fetching shared by the manufacturer sources."""

import time
import urllib.request

USER_AGENT = "Mozilla/5.0 (CrossList datasheet importer)"


def get(
    url: str, data: bytes | None = None, content_type: str | None = None, pause: float = 1.0, retries: int = 4
) -> bytes:
    """GET (or POST when ``data`` is given), pausing between requests and backing off
    when the site answers with an empty body or an error."""
    headers = {"User-Agent": USER_AGENT}
    if content_type:
        headers["Content-Type"] = content_type
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
        except OSError:
            body = b""
        time.sleep(pause)
        if body.strip():
            return body
        time.sleep(pause * 2 ** (attempt + 1))
    raise RuntimeError(f"No response from {url} after {retries} attempts")
