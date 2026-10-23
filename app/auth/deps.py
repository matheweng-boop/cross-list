"""Current-user dependency: the older `User` row that cross verdicts are stored under.

The owner (password or passkey) is the single local user. When the owner approves a guest's item, the replayed request
is stored under a `User` row named after that guest, so it reads exactly like the owner's own input with the guest's
name. Guests never write directly (the gate stores their input for review).
"""

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.session import REPLAY
from app.db import get_session
from app.models import User
from app.services.seed import ensure_local_user


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    replay = request.scope.get(REPLAY)
    if replay and replay.get("account_id"):
        email = f"guest-{int(replay['account_id'])}@crosslist.invalid"
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            local = ensure_local_user(session)
            user = User(email=email, display_name=str(replay.get("author") or "Guest")[:200],
                        organization_id=local.organization_id)  # fmt: skip
            session.add(user)
        session.commit()
        return user
    user = ensure_local_user(session)
    session.commit()
    return user
