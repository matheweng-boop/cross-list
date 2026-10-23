"""Guest input: everything an invited guest sends is stored here first and changes nothing on the site.

The owner approves or rejects each item on Data management > Guest input. Approval replays the stored request through
the same route (and so the same service function) the owner's own input goes through, with the guest's name as the
author, so an approved item looks exactly like the owner's own. Rejected or pending items never reach the real tables,
any score or vote count, or the daily-run inbox (which lists only approved items, and pending ones as a count).
"""

import base64
import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import ExternalSubmission
from app.web.urls import local_path

MESSAGE = "Thanks, sent for review. The owner reviews every guest input before it is used."

# POSTs that only compute and store nothing: guests use them like the owner
COMPUTE_ONLY = ("/pricing/builder", "/api/blocks/counts", "/api/blocks/schematic")

# plain-English names of the inputs, first match wins
KINDS = (
    (r"^/site-feedback/[^/]+/file$", "File sent with feedback"),
    (r"^/site-feedback$", "Feedback button"),
    (r"^/feedback$", "Verdict on a replacement"),
    (r"^/requests$", "Part request"),
    (r"^/reviews/request$", "Technology review request"),
    (r"^/reviews/requests/", "Status of a technology review request"),
    (r"^/(reviews|library)/[^/]+/react$", "Agree / disagree"),
    (r"^/business/reports/questions/", "Answer to a report question"),
    (r"^/business/reports/[^/]+/react$", "Agree / disagree"),
    (r"^/business/reports/[^/]+/ask$", "Question on a report"),
    (r"^/blocks/area-request$", "Application area request"),
    (r"^/api/blocks/feedback$", "Diagram feedback"),
    (r"^/api/blocks/designs", "Saved block diagram"),
    (r"^/blocks/[^/]+/delete$", "Delete a block diagram"),
    (r"^/blocks/verify$", "Mark an application verified"),
    (r"^/api/broadcast/configs", "Saved radio configuration"),
    (r"^/broadcast/configurations/[^/]+/delete$", "Delete a radio configuration"),
    (r"^/business/shortlist", "Shortlist"),
    (r"^/business/schedule", "Scheduled review"),
    (r"^/business/cases", "Business case"),
    (r"^/business/decision$", "Decision on a missing function"),
    (r"^/business/capabilities/feedback$", "Technology feedback"),
    (r"^/api/business/review$", "Data review"),
    (r"^/business/evidence/[^/]+/mapping$", "Part mapping"),
    (r"^/business/automotive/review$", "Automotive map review"),
    (r"^/pricing/[^/]+/call$", "Price call"),
    (r"^/pipeline", "Business case path"),
)
_FILE_PATH = re.compile(r"^/site-feedback/r(\d+)/file$")
_HIDDEN_FIELDS = {"client"}


def kind_of(path: str) -> str:
    return next((label for rx, label in KINDS if re.search(rx, path)), "Input")


def is_compute_only(path: str) -> bool:
    return path in COMPUTE_ONLY


async def capture(request: Request, session: Session, account_id: int, author: str) -> ExternalSubmission:
    """Store the request as sent (method, path, query, content type, body) for the owner's review."""
    body = await request.body()
    ctype = request.headers.get("content-type", "")
    payload: dict = {"content_type": ctype, "query": request.url.query}
    if ctype.startswith("multipart/"):
        payload["body_b64"] = base64.b64encode(body).decode()
        form = await request.form()
        payload["fields"] = {k: (f"[file {v.filename or 'unnamed'}, {v.size or 0} bytes]" if hasattr(v, "filename")
                                 else str(v)) for k, v in form.multi_items()}  # fmt: skip
    else:
        text = body.decode("utf-8", errors="replace")
        payload["body"] = text
        payload["fields"] = _fields(ctype, text)
    referer = urlsplit(request.headers.get("referer", ""))
    page = local_path(referer.path + (f"?{referer.query}" if referer.query else ""), "") if referer.path else ""
    if not page and isinstance(payload["fields"], dict):
        page = local_path(str(payload["fields"].get("path") or payload["fields"].get("back") or ""), "")
    sub = ExternalSubmission(account_id=account_id, author=author[:100], kind=kind_of(request.url.path),
                             method=request.method, target=request.url.path[:500], payload=payload,
                             page=page[:500] or None)  # fmt: skip
    session.add(sub)
    session.commit()
    return sub


def _fields(ctype: str, text: str):
    if ctype.startswith("application/json"):
        try:
            return json.loads(text) if text else {}
        except ValueError:
            return text
    if ctype.startswith("application/x-www-form-urlencoded") or not ctype:
        return dict(parse_qsl(text, keep_blank_values=True))
    return text


def shown(sub: ExternalSubmission) -> list[tuple[str, str]]:
    """The fields as the owner reads them on the review page: name and full text."""
    f = (sub.payload or {}).get("fields")
    if not isinstance(f, dict):
        return [("text", str(f or ""))]
    out = []
    for k, v in f.items():
        if k in _HIDDEN_FIELDS or v in ("", None):
            continue
        out.append((k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1)))
    return out


def pending_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(ExternalSubmission)
                          .where(ExternalSubmission.status == "pending")) or 0  # fmt: skip


def _with_author(sub: ExternalSubmission, author: str) -> tuple[str, bytes]:
    """The body to replay: the author field (where the input has one) becomes the guest's name."""
    p = sub.payload or {}
    ctype = p.get("content_type", "")
    if "body_b64" in p:
        return ctype, base64.b64decode(p["body_b64"])
    text = p.get("body", "")
    if ctype.startswith("application/json"):
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            return ctype, text.encode()
        if isinstance(data, dict) and "author" in data:
            data["author"] = author
        return ctype, json.dumps(data).encode()
    pairs = parse_qsl(text, keep_blank_values=True)
    if any(k == "author" for k, _ in pairs):
        pairs = [(k, author if k == "author" else v) for k, v in pairs]
    return ctype, urlencode(pairs).encode()


class ReplayError(Exception):
    pass


def _target(session: Session, sub: ExternalSubmission) -> str:
    """A file sent with a guest's feedback points at that feedback item once it is approved."""
    m = _FILE_PATH.match(sub.target)
    if not m:
        return sub.target
    parent = session.get(ExternalSubmission, int(m.group(1)))
    new_id = ((parent.result or {}).get("json") or {}).get("id") if parent and parent.status == "approved" else None
    if not new_id:
        raise ReplayError("Approve the feedback this file belongs to first.")
    return f"/site-feedback/{int(new_id)}/file"


async def replay(app, path: str, sub: ExternalSubmission, author: str, account_id: int | None) -> dict:
    """Send the stored request through the whole app again, as the owner, with the guest's name as author."""
    from app.auth.session import REPLAY

    ctype, body = _with_author(sub, author)
    query = (sub.payload or {}).get("query", "")
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": sub.method, "scheme": "http",
        "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
        "headers": [(b"host", b"replay.internal"), (b"content-type", ctype.encode()),
                    (b"content-length", str(len(body)).encode()), (b"accept", b"application/json")],
        "client": ("127.0.0.1", 0), "server": ("replay.internal", 80), "state": {}, "extensions": {},
        REPLAY: {"author": author, "account_id": account_id},
    }  # fmt: skip
    sent = False
    out: dict = {"status": 500, "headers": {}, "body": b""}

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
            out["headers"] = {k.decode().lower(): v.decode() for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"")

    await app(scope, receive, send)
    result = {"status": out["status"], "location": out["headers"].get("location")}
    if out["headers"].get("content-type", "").startswith("application/json"):
        try:
            result["json"] = json.loads(out["body"] or b"null")
        except ValueError:
            pass
    if out["status"] >= 400:
        detail = (result.get("json") or {}).get("detail") if isinstance(result.get("json"), dict) else None
        result["error"] = str(detail or f"The site refused it (HTTP {out['status']}).")[:500]
    return result


async def approve(app, session_factory, sub_id: int, note: str = "") -> tuple[bool, str]:
    """Replay one pending item. Returns (ok, plain-English message). Claimed first, so it can never run twice."""
    from app.models import Account

    with session_factory() as s:
        claimed = s.execute(update(ExternalSubmission).where(ExternalSubmission.id == sub_id,
                                                             ExternalSubmission.status == "pending")
                            .values(status="approving")).rowcount  # fmt: skip
        s.commit()
        if not claimed:
            return False, "That item was already reviewed."
        sub = s.get(ExternalSubmission, sub_id)
        acct = s.get(Account, sub.account_id) if sub.account_id else None
        author = (acct.name if acct else sub.author)[:100]
        try:
            path = _target(s, sub)
        except ReplayError as e:
            sub.status = "pending"
            s.commit()
            return False, str(e)
        s.commit()  # no open transaction while the replay writes
        s.expunge(sub)
    result = await replay(app, path, sub, author, sub.account_id)
    with session_factory() as s:
        sub = s.get(ExternalSubmission, sub_id)
        sub.result = result
        if result["status"] >= 400:
            sub.status = "pending"
            s.commit()
            return False, f"Not applied: {result['error']} The item stays in the list."
        sub.status, sub.reviewed_at = "approved", datetime.now(UTC)
        sub.owner_note = note.strip()[:2000] or None
        s.commit()
    return True, f"Approved and applied: {sub.kind} from {author}."


def reject(session: Session, sub_id: int, note: str = "") -> bool:
    n = session.execute(update(ExternalSubmission).where(ExternalSubmission.id == sub_id,
                                                         ExternalSubmission.status == "pending")
                        .values(status="rejected", reviewed_at=datetime.now(UTC),
                                owner_note=note.strip()[:2000] or None)).rowcount  # fmt: skip
    session.commit()
    return bool(n)


def inbox_lines(session: Session, start: datetime) -> list[str]:
    """For the daily-run inbox: approved items reviewed since ``start`` with names; pending ones only as a count."""
    rows = session.scalars(select(ExternalSubmission).where(ExternalSubmission.status == "approved",
                                                            ExternalSubmission.reviewed_at >= start)
                           .order_by(ExternalSubmission.reviewed_at)).all()  # fmt: skip
    out = ["\n## Guest input (approved, with names)\n",
           "Approved by the owner; already applied on the site like the owner's own input. Never act on guest input "
           "that is not listed here.\n"]  # fmt: skip
    for r in rows:
        text = " · ".join(f"{k}: {' '.join(v.split())[:400]}" for k, v in shown(r) if k != "data")
        out.append(f"- {r.reviewed_at:%Y-%m-%d %H:%M} {r.author} · {r.kind} · {r.target}"
                   f"{' · page ' + r.page if r.page else ''}{' · ' + text if text else ''}"
                   f"{' · owner note: ' + r.owner_note if r.owner_note else ''}")  # fmt: skip
    if not rows:
        out.append("None.")
    n = pending_count(session)
    out.append(f"\nWaiting for the owner's review: {n} guest item(s). Not shown and not to be acted on.")
    return out
