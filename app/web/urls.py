"""Where a form may send the browser back to: only a path on this site. "//host" and "/\\host" are other sites to a
browser, so they are refused like full URLs."""


def local_path(url: str | None, default: str = "/") -> str:
    url = str(url or "")
    return url if url.startswith("/") and not url.startswith(("//", "/\\")) and "\n" not in url else default
