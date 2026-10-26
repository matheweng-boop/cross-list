"""Data management › Data flow: the chart of every path the data takes (data/manage/data_flow.yaml), which the owner
moves and changes on the page; saves are versions in the database and reach the daily run as a change list
(app/services/data_flow.py). Owner only (/manage is the owner's in app/auth/access.py)."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import signed_in_owner
from app.db import get_session
from app.services import data_flow as df
from app.web.routes import templates

router = APIRouter()
URL = "/manage/data-flow"
DONE = {"undone": "Undone: the chart is back to the version before.", "nothing": "Nothing to undo."}


def _owner(request: Request) -> str:
    p = signed_in_owner(request)
    if p is None:
        raise HTTPException(403, "Only the owner can change the data flow.")
    return p.name or "Owner"


def _history(session: Session) -> list[dict]:
    return [{"id": v.id, "at": f"{v.created_at:%Y-%m-%d %H:%M}", "author": v.author, "note": v.note,
             "undone": v.undone_at is not None} for v in df.history(session)]  # fmt: skip


@router.get(URL, response_class=HTMLResponse)
def data_flow_page(request: Request, done: str = "", session: Session = Depends(get_session)):
    _owner(request)
    file = df.load()
    state = df.view(session)
    v = df.current(session)
    ch = df.changes(state, file) if v else []
    data = {"lanes": file["lanes"], "file": {"nodes": file["nodes"], "edges": file["edges"]}, "state": state,
            "kinds": df.KINDS, "nodeW": df.NODE_W, "nodeH": df.NODE_H, "noteW": df.NOTE_W}  # fmt: skip
    ctx = {"data": data, "changes": ch, "history": _history(session), "saved": v is not None,
           "done_list": file["done"], "kinds": df.KINDS, "message": DONE.get(done, "")}  # fmt: skip
    return templates.TemplateResponse(request, "manage/data_flow.html", ctx)


@router.post(URL + "/save")
def data_flow_save(request: Request, payload: dict = Body(default={}), session: Session = Depends(get_session)):
    author = _owner(request)
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        return JSONResponse({"ok": False, "message": "Nothing to save: the chart was empty."}, status_code=400)
    v, ch = df.save(session, payload, author)
    session.commit()
    return {"ok": True, "version": v.id, "changes": ch, "history": _history(session),
            "message": f"Saved. {len(ch)} change{'' if len(ch) == 1 else 's'} against the file version go to "
                       "tonight's run."}  # fmt: skip


@router.post(URL + "/undo")
def data_flow_undo(request: Request, session: Session = Depends(get_session)):
    _owner(request)
    had = df.current(session) is not None
    df.undo(session)
    session.commit()
    return RedirectResponse(f"{URL}?done={'undone' if had else 'nothing'}", status_code=303)
