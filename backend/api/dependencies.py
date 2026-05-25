from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from config import SECRET_KEY, ALGORITHM
from db.database import get_db
from db.models import Case, User


def get_current_user(
    access_token: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Malformed token")

    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    return user


def get_optional_user(
    access_token: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
) -> User | None:
    """Returns the authenticated user, or None for unauthenticated requests.
    Use on public endpoints that serve different content based on auth state."""
    if not access_token:
        return None
    try:
        return get_current_user(access_token, db)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Factory that returns a FastAPI dependency enforcing one of the given roles."""
    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {' or '.join(roles)}",
            )
        return current_user
    return _check


# ── Sealed-case access guard ──────────────────────────────────────────────────
_PRIVILEGED_ROLES = {"admin", "clerk", "judge"}


def check_case_access(case: Case, user: User | None) -> None:
    """
    Raise 403 if the requesting user must not see a sealed (confidential) case.

    Who can see sealed cases:
    - admin, clerk, judge — always
    - attorney — only their own client's case
    - unauthenticated / public — never
    """
    if not case.is_confidential:
        return
    if user is None:
        raise HTTPException(status_code=403, detail="Case is sealed")
    if user.role in _PRIVILEGED_ROLES:
        return
    if user.role == "attorney" and user.lawyer_id == case.defense_lawyer_id:
        return
    raise HTTPException(status_code=403, detail="Case is sealed")


def can_see_case(case: Case, user: User | None) -> bool:
    """Non-raising variant — used for filtering in list/queue views."""
    if not case.is_confidential:
        return True
    if user is None:
        return False
    if user.role in _PRIVILEGED_ROLES:
        return True
    if user.role == "attorney" and user.lawyer_id == case.defense_lawyer_id:
        return True
    return False


# ── Convenience aliases ───────────────────────────────────────────────────────
AnyAuthenticated = Depends(get_current_user)
OptionalUser     = Depends(get_optional_user)
ClerkOrAdmin     = Depends(require_role("clerk", "admin"))
AdminOnly        = Depends(require_role("admin"))
JudgeOrAbove     = Depends(require_role("judge", "clerk", "admin"))
