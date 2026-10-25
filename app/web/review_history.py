"""The small collapsible "History (n)" under a review box: up to five earlier answers to the item, one line each
(date, verdict, comment cut with "more", author). Templates call ``review_history(request, dataset, key)``; one query
per dataset and request (app/services/review_history.py)."""

from markupsafe import Markup
from sqlalchemy.orm import Session

from app.auth.session import principal
from app.db import get_engine
from app.services import review_history as rh

CUT = 70  # characters of a comment shown before "more"


def _guest(request) -> bool:
    try:
        p = principal(request)
    except Exception:  # noqa: BLE001 - a page rendered outside a request (PDF packs): show the guest version
        return True
    return bool(p and p.is_guest)


def rows(request, dataset: str, key: str, skip: int = 1) -> list[dict]:
    """Up to five answers before the ``skip`` newest ones (those the box already shows), newest first."""
    cache = getattr(request.state, "review_history", None) if request is not None else None
    if cache is None:
        cache = {}
        if request is not None:
            request.state.review_history = cache
    if dataset not in cache:
        with Session(get_engine()) as s:
            cache[dataset] = rh.by_dataset(s, dataset, n=rh.N + 1)
    found = cache[dataset].get(str(key)[:120], [])[skip : skip + rh.N]
    return rh.for_viewer(found, dataset, request is None or _guest(request))


def _comment(text: str) -> Markup:
    text = " ".join(text.split())
    if len(text) <= CUT:
        return Markup(' <span class="rh-c">{}</span>').format(text)
    return Markup(' <span class="rh-c">{}…</span><details class="rh-more"><summary>more</summary>{}</details>').format(
        text[:CUT].rstrip(), text
    )


def render(request, dataset: str, key: str, skip: int = 1) -> Markup:
    found = rows(request, dataset, key, skip)
    if not found:
        return Markup("")
    items = []
    for r in found:
        d = r["date"]
        v = r["verdict"]
        cls = "correct" if v in ("correct", "ok", "answered") else "wrong" if v == "wrong" else "unsure"
        line = Markup('<li><time>{}</time> <span class="rh-v v-{}">{}</span>').format(
            f"{d.day} {d:%b %Y}" if d else "", cls, r["label"]
        )
        if r["comment"]:
            line += _comment(r["comment"])
        if r["author"]:
            line += Markup(' <span class="muted">· {}</span>').format(r["author"])
        items.append(line + Markup("</li>"))
    title = "Earlier answers" if skip else "Latest answers"
    return Markup('<details class="rv-hist" title="{}"><summary>History ({})</summary><ul>{}</ul></details>').format(
        title, len(found), Markup("").join(items)
    )


def register(env) -> None:
    env.globals["review_history"] = render
    env.globals["review_history_rows"] = rows
