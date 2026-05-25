import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.limiter import limiter

from config import (
    SECRET_KEY, ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    ENVIRONMENT,
)
from db.database import get_db
from db.models import User, RefreshToken
from schemas.auth import (
    ChangePasswordRequest, LoginRequest, MeResponse, TokenResponse,
)
from schemas.common import MessageResponse
from api.dependencies import get_current_user
from utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_SECURE_COOKIE = ENVIRONMENT == "production"
_COOKIE_OPTS   = dict(httponly=True, secure=_SECURE_COOKIE, samesite="lax")

# ── Brute-force lockout ───────────────────────────────────────────────────────
# Simple in-process counter.  For multi-replica deployments, replace with Redis.
_MAX_ATTEMPTS    = 10
_LOCKOUT_MINUTES = 15

# {username: (attempts, locked_until | None)}
_login_attempts: dict[str, tuple[int, datetime | None]] = {}


def _check_lockout(username: str) -> None:
    """Raise 429 if the account is currently locked out."""
    attempts, locked_until = _login_attempts.get(username, (0, None))
    if locked_until and datetime.now(timezone.utc) < locked_until:
        secs = int((locked_until - datetime.now(timezone.utc)).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {secs} seconds.",
        )


def _record_failure(username: str) -> None:
    attempts, locked_until = _login_attempts.get(username, (0, None))
    # Reset counter if previous lockout has expired
    if locked_until and datetime.now(timezone.utc) >= locked_until:
        attempts = 0
    attempts += 1
    new_lockout = (
        datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
        if attempts >= _MAX_ATTEMPTS else None
    )
    _login_attempts[username] = (attempts, new_lockout)
    if new_lockout:
        logger.warning("Account locked out: username=%s", username)


def _clear_failure(username: str) -> None:
    _login_attempts.pop(username, None)


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {
            "sub":       str(user.id),
            "username":  user.username,
            "role":      user.role,
            "lawyer_id": user.lawyer_id,
            "judge_id":  user.judge_id,
            "exp":       expire,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _issue_refresh_token(user_id: int, db: Session) -> str:
    """Create a new refresh token, persist its SHA-256 hash, return the raw value."""
    raw        = secrets.token_hex(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires    = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires))
    db.commit()
    return raw


def _set_auth_cookies(response: Response, user: User, db: Session) -> dict:
    access  = create_access_token(user)
    refresh = _issue_refresh_token(user.id, db)
    response.set_cookie(
        "access_token", access,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, **_COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token", refresh,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400, **_COOKIE_OPTS,
    )
    return {"role": user.role, "username": user.username}


def _revoke_all_tokens(user_id: int, db: Session) -> None:
    """Revoke every active refresh token for a user (e.g. after password change)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
        .values(revoked=True)
    )
    db.commit()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    _check_lockout(body.username)

    user = db.execute(
        select(User).where(User.username == body.username)
    ).scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        _record_failure(body.username)
        # Deliberate vague message — don't reveal whether username exists
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled — contact admin")

    _clear_failure(body.username)
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    logger.info("login: user_id=%s role=%s", user.id, user.role)
    return _set_auth_cookies(response, user, db)


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
):
    # Revoke the specific refresh token if present
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        record = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()
        if record:
            record.revoked = True
            db.commit()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    record = db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked    == False,
        )
    ).scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=401, detail="Refresh token invalid")
    if record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired — please log in again")

    # Rotate: revoke old token, issue new pair
    record.revoked = True
    db.commit()

    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    return _set_auth_cookies(response, user, db)


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    return {
        "id":        current_user.id,
        "username":  current_user.username,
        "role":      current_user.role,
        "lawyer_id": current_user.lawyer_id,
        "judge_id":  current_user.judge_id,
    }


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user = db.get(User, current_user.id)
    user.password_hash = hash_password(body.new_password)

    # Revoke all existing refresh tokens so other sessions are terminated
    _revoke_all_tokens(current_user.id, db)
    db.commit()

    # Clear the caller's own cookies — they must log in again
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    logger.info("password changed: user_id=%s", current_user.id)
    return {"message": "Password updated. Please log in again."}
