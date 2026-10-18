"""Current-user dependency.

Today this returns the single local user. When passkey (WebAuthn) login is added,
only this function changes: it will read the session cookie and load the user.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.services.seed import ensure_local_user


def get_current_user(session: Session = Depends(get_session)) -> User:
    user = ensure_local_user(session)
    session.commit()
    return user
