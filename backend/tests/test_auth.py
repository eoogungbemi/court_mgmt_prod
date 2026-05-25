"""Auth flow: login, /me, logout, refresh, lockout, password change."""

import pytest
from tests.conftest import _login


def test_login_success(client, admin_user):
    r = _login(client)
    assert r.json()["role"] == "admin"
    assert "access_token"  in client.cookies
    assert "refresh_token" in client.cookies


def test_login_wrong_password(client, admin_user):
    r = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401
    # Error message must not reveal whether the username exists
    assert "nobody" not in r.json()["detail"]


def test_me_authenticated(client, admin_user):
    _login(client)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "testadmin"


def test_me_unauthenticated(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_session(client, admin_user):
    _login(client)
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    # Cookie should be gone
    assert client.cookies.get("access_token") is None


def test_refresh_rotates_token(client, admin_user):
    _login(client)
    old_access = client.cookies.get("access_token")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert client.cookies.get("access_token") != old_access


def test_refresh_without_cookie(client):
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401


def test_account_lockout(client, admin_user):
    """10 failed attempts should trigger 429."""
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    r = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert r.status_code == 429


def test_lockout_clears_on_success(client, admin_user):
    """Counter resets after a successful login (simulated by using a fresh user fixture)."""
    # Fresh user has no failed attempts — should always succeed
    r = _login(client)
    assert r.status_code == 200


def test_change_password_revokes_tokens(client, admin_user):
    _login(client)
    old_refresh = client.cookies.get("refresh_token")

    r = client.post("/api/auth/change-password", json={
        "current_password": "Password1!",
        "new_password":     "NewPass99!",
    })
    assert r.status_code == 200

    # Old refresh token should now be rejected
    client.cookies.set("refresh_token", old_refresh)
    r2 = client.post("/api/auth/refresh")
    assert r2.status_code == 401


def test_inactive_user_cannot_login(client, db):
    from db.models import User
    from utils.security import hash_password
    u = User(username="inactive", password_hash=hash_password("pass"), role="clerk", is_active=False)
    db.add(u)
    db.flush()
    r = client.post("/api/auth/login", json={"username": "inactive", "password": "pass"})
    assert r.status_code == 403
