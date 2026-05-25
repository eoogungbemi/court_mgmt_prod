"""
Hearing scheduling, reschedule, courtrooms/{id}, password strength, health check.

Covers:
- POST /api/hearings — create a hearing (clerk/admin only)
- POST /api/hearings/{id}/reschedule — time shift with audit trail
- GET /api/courtrooms/{id} — single-room endpoint returning judge_id
- Password strength validator (via POST /api/users with weak passwords)
- GET /health — deep check returns expected shape
"""

from datetime import datetime, timedelta, timezone
import pytest
from tests.conftest import _login


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def case(db, lawyer):
    from db.models import Case, Accused
    c = Case(case_number="2026-JD-HTEST01", case_type="delinquency",
             complexity="medium", defense_lawyer_id=lawyer.id)
    db.add(c); db.flush()
    db.add(Accused(name="Test Minor", case_id=c.id)); db.flush()
    return c


@pytest.fixture
def hearing(db, case, courtroom, judge):
    from db.models import Hearing
    base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    h = Hearing(
        case_id=case.id, courtroom_id=courtroom.id, judge_id=judge.id,
        hearing_type="detention",
        scheduled_start=base, scheduled_end=base + timedelta(minutes=30),
        estimated_duration_mins=30, status="scheduled",
    )
    db.add(h); db.flush()
    return h


def _iso(h: int, m: int = 0) -> str:
    dt = datetime.now(timezone.utc).replace(hour=h, minute=m, second=0, microsecond=0)
    return dt.isoformat()


# ── Create hearing ────────────────────────────────────────────────────────────

def test_create_hearing(client, admin_user, case, courtroom, judge):
    _login(client)
    r = client.post("/api/hearings", json={
        "case_id":                case.id,
        "courtroom_id":           courtroom.id,
        "judge_id":               judge.id,
        "hearing_type":           "adjudicatory",
        "scheduled_start":        _iso(10),
        "scheduled_end":          _iso(11),
        "estimated_duration_mins": 60,
        "interpreter_required":   False,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["hearing_type"] == "adjudicatory"
    assert body["status"]       == "scheduled"
    assert body["case_id"]      == case.id


def test_create_hearing_invalid_type(client, admin_user, case, courtroom, judge):
    _login(client)
    r = client.post("/api/hearings", json={
        "case_id": case.id, "courtroom_id": courtroom.id, "judge_id": judge.id,
        "hearing_type": "INVALID",
        "scheduled_start": _iso(10), "scheduled_end": _iso(11),
        "estimated_duration_mins": 60,
    })
    assert r.status_code == 400


def test_create_hearing_bad_time_order(client, admin_user, case, courtroom, judge):
    _login(client)
    r = client.post("/api/hearings", json={
        "case_id": case.id, "courtroom_id": courtroom.id, "judge_id": judge.id,
        "hearing_type": "adjudicatory",
        "scheduled_start": _iso(11), "scheduled_end": _iso(10),  # reversed
        "estimated_duration_mins": 60,
    })
    assert r.status_code == 400


def test_create_hearing_unknown_case(client, admin_user, courtroom, judge):
    _login(client)
    r = client.post("/api/hearings", json={
        "case_id": 99999, "courtroom_id": courtroom.id, "judge_id": judge.id,
        "hearing_type": "adjudicatory",
        "scheduled_start": _iso(10), "scheduled_end": _iso(11),
        "estimated_duration_mins": 30,
    })
    assert r.status_code == 400


def test_create_hearing_requires_clerk(client, db):
    from db.models import User
    from utils.security import hash_password
    judge_user = User(username="testjudge2", password_hash=hash_password("Password1!"),
                      role="judge", is_active=True)
    db.add(judge_user); db.flush()
    _login(client, "testjudge2")
    r = client.post("/api/hearings", json={
        "case_id": 1, "courtroom_id": 1, "judge_id": 1,
        "hearing_type": "adjudicatory",
        "scheduled_start": _iso(10), "scheduled_end": _iso(11),
        "estimated_duration_mins": 30,
    })
    assert r.status_code == 403


# ── Reschedule ────────────────────────────────────────────────────────────────

def test_reschedule_hearing(client, admin_user, hearing):
    _login(client)
    new_start = _iso(14)
    new_end   = _iso(15)
    r = client.post(f"/api/hearings/{hearing.id}/reschedule", json={
        "scheduled_start":        new_start,
        "scheduled_end":          new_end,
        "estimated_duration_mins": 60,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "scheduled"
    assert body["estimated_duration_mins"] == 60
    # Start time should be updated
    assert new_start[:16] in body["scheduled_start"]


def test_reschedule_bad_time_order(client, admin_user, hearing):
    _login(client)
    r = client.post(f"/api/hearings/{hearing.id}/reschedule", json={
        "scheduled_start": _iso(15),
        "scheduled_end":   _iso(14),
    })
    assert r.status_code == 400


def test_reschedule_not_found(client, admin_user):
    _login(client)
    r = client.post("/api/hearings/99999/reschedule", json={
        "scheduled_start": _iso(10),
        "scheduled_end":   _iso(11),
    })
    assert r.status_code == 404


def test_reschedule_resets_status_to_scheduled(client, admin_user, db, hearing):
    """A delayed hearing that is rescheduled should revert to 'scheduled'."""
    hearing.status = "delayed"
    db.flush()
    _login(client)
    r = client.post(f"/api/hearings/{hearing.id}/reschedule", json={
        "scheduled_start": _iso(14),
        "scheduled_end":   _iso(15),
    })
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"


# ── GET /api/courtrooms/{id} ──────────────────────────────────────────────────

def test_get_courtroom_by_id(client, admin_user, courtroom, judge):
    _login(client)
    r = client.get(f"/api/courtrooms/{courtroom.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"]    == courtroom.id
    assert body["name"]  == courtroom.name
    assert body["floor"] == courtroom.floor
    assert body["judge_id"] == judge.id


def test_get_courtroom_no_judge(client, admin_user, db):
    from db.models import Courtroom
    cr = Courtroom(name="Empty Room", floor=3)
    db.add(cr); db.flush()
    _login(client)
    r = client.get(f"/api/courtrooms/{cr.id}")
    assert r.status_code == 200
    assert r.json()["judge_id"] is None


def test_get_courtroom_not_found(client, admin_user):
    _login(client)
    r = client.get("/api/courtrooms/99999")
    assert r.status_code == 404


def test_get_courtroom_requires_auth(client, courtroom):
    r = client.get(f"/api/courtrooms/{courtroom.id}")
    assert r.status_code == 401


# ── Password strength validator ───────────────────────────────────────────────

def test_password_too_short_rejected(client, admin_user, lawyer):
    _login(client)
    r = client.post("/api/users", json={
        "username": "newuser1", "password": "Short1",
        "role": "clerk",
    })
    assert r.status_code == 422
    assert "10 characters" in r.text or "10" in r.text


def test_password_no_uppercase_rejected(client, admin_user, lawyer):
    _login(client)
    r = client.post("/api/users", json={
        "username": "newuser2", "password": "allowercase1",
        "role": "clerk",
    })
    assert r.status_code == 422
    assert "uppercase" in r.text.lower()


def test_password_no_digit_rejected(client, admin_user, lawyer):
    _login(client)
    r = client.post("/api/users", json={
        "username": "newuser3", "password": "NoDigitsHere",
        "role": "clerk",
    })
    assert r.status_code == 422
    assert "digit" in r.text.lower()


def test_password_valid_accepted(client, admin_user, lawyer):
    _login(client)
    r = client.post("/api/users", json={
        "username": "newuser4", "password": "ValidPass1",
        "role": "clerk",
    })
    assert r.status_code == 201


def test_reset_password_weak_rejected(client, admin_user, db):
    """Admin resetting another user's password must also satisfy strength rules."""
    from db.models import User
    from utils.security import hash_password
    target = User(username="resetme", password_hash=hash_password("OldPass99"),
                  role="clerk", is_active=True)
    db.add(target); db.flush()

    _login(client)
    r = client.post(f"/api/users/{target.id}/reset-password",
                    json={"new_password": "weak"})
    assert r.status_code == 422


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_returns_ok_shape(client):
    r = client.get("/health")
    # Should be 200 (DB up in test environment; Redis may be unavailable → still 200)
    assert r.status_code in (200, 503)
    body = r.json()
    assert "status"      in body
    assert "service"     in body
    assert "checks"      in body
    assert "db"    in body["checks"]
    assert "redis" in body["checks"]


def test_health_db_ok(client):
    r    = client.get("/health")
    body = r.json()
    assert body["checks"]["db"] == "ok"
