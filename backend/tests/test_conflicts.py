"""
Conflict detection endpoints — GET/PATCH /api/conflicts

Covers:
- Auth enforcement (clerk/admin only)
- Enriched ConflictDetail shape (lawyer_name, hearing_a/b with case_number + courtroom)
- resolved filter
- Resolve (PATCH) toggles resolved flag
- GET /{id} returns flat ConflictOut
"""

from datetime import datetime, timedelta, timezone
import pytest
from tests.conftest import _login


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def attorney_user(db):
    from db.models import User
    from utils.security import hash_password
    u = User(username="conflictatty", password_hash=hash_password("Password1!"),
             role="attorney", is_active=True)
    db.add(u); db.flush()
    return u


@pytest.fixture
def conflict(db, courtroom, judge, lawyer):
    """
    A LawyerConflict between two overlapping hearings for the same lawyer,
    fully eager-loaded-compatible (all FK rows present).
    """
    from db.models import Case, Accused, Hearing, LawyerConflict

    def _case(n):
        c = Case(case_number=f"2026-JD-CTEST{n}", case_type="delinquency",
                 complexity="low", defense_lawyer_id=lawyer.id)
        db.add(c); db.flush()
        db.add(Accused(name=f"Minor {n}", case_id=c.id)); db.flush()
        return c

    base = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    ca, cb = _case(1), _case(2)

    ha = Hearing(case_id=ca.id, courtroom_id=courtroom.id, judge_id=judge.id,
                 hearing_type="detention", scheduled_start=base,
                 scheduled_end=base + timedelta(minutes=45),
                 estimated_duration_mins=45, status="scheduled")
    hb = Hearing(case_id=cb.id, courtroom_id=courtroom.id, judge_id=judge.id,
                 hearing_type="detention", scheduled_start=base + timedelta(minutes=20),
                 scheduled_end=base + timedelta(minutes=60),
                 estimated_duration_mins=40, status="scheduled")
    db.add(ha); db.add(hb); db.flush()

    c = LawyerConflict(
        lawyer_id=lawyer.id, hearing_a_id=ha.id, hearing_b_id=hb.id,
        overlap_start=base + timedelta(minutes=20),
        overlap_end=base + timedelta(minutes=45),
        resolved=False,
    )
    db.add(c); db.flush()
    return c


@pytest.fixture
def resolved_conflict(db, courtroom, judge, lawyer):
    from db.models import Case, Accused, Hearing, LawyerConflict

    def _case(n):
        c = Case(case_number=f"2026-JD-RTEST{n}", case_type="dependency",
                 complexity="low", defense_lawyer_id=lawyer.id)
        db.add(c); db.flush()
        db.add(Accused(name=f"Minor R{n}", case_id=c.id)); db.flush()
        return c

    base = datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)
    ca, cb = _case(1), _case(2)

    ha = Hearing(case_id=ca.id, courtroom_id=courtroom.id, judge_id=judge.id,
                 hearing_type="review", scheduled_start=base,
                 scheduled_end=base + timedelta(minutes=30),
                 estimated_duration_mins=30, status="completed")
    hb = Hearing(case_id=cb.id, courtroom_id=courtroom.id, judge_id=judge.id,
                 hearing_type="review", scheduled_start=base + timedelta(minutes=10),
                 scheduled_end=base + timedelta(minutes=40),
                 estimated_duration_mins=30, status="completed")
    db.add(ha); db.add(hb); db.flush()

    c = LawyerConflict(
        lawyer_id=lawyer.id, hearing_a_id=ha.id, hearing_b_id=hb.id,
        overlap_start=base + timedelta(minutes=10),
        overlap_end=base + timedelta(minutes=30),
        resolved=True,
    )
    db.add(c); db.flush()
    return c


# ── Auth guards ───────────────────────────────────────────────────────────────

def test_list_conflicts_requires_auth(client):
    r = client.get("/api/conflicts")
    assert r.status_code == 401


def test_list_conflicts_attorney_forbidden(client, attorney_user):
    _login(client, "conflictatty")
    r = client.get("/api/conflicts")
    assert r.status_code == 403


# ── List (enriched) ───────────────────────────────────────────────────────────

def test_list_conflicts_empty(client, admin_user):
    _login(client)
    r = client.get("/api/conflicts")
    assert r.status_code == 200
    assert r.json() == []


def test_list_conflicts_returns_detail_shape(client, admin_user, conflict, lawyer, courtroom):
    _login(client)
    r    = client.get("/api/conflicts")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1

    item = next(c for c in body if c["id"] == conflict.id)

    # Lawyer enrichment
    assert item["lawyer_name"] == lawyer.name
    assert item["lawyer_id"]   == lawyer.id

    # hearing_a enrichment
    ha = item["hearing_a"]
    assert "id"              in ha
    assert "scheduled_start" in ha
    assert "courtroom_name"  in ha
    assert "case_number"     in ha
    assert ha["courtroom_name"] == courtroom.name
    assert "JD-CTEST1" in ha["case_number"]

    # hearing_b enrichment
    hb = item["hearing_b"]
    assert "JD-CTEST2" in hb["case_number"]

    # Overlap window
    assert item["resolved"] is False
    assert item["overlap_start"] is not None
    assert item["overlap_end"]   is not None


def test_list_conflicts_filter_unresolved(client, admin_user, conflict, resolved_conflict):
    _login(client)
    r    = client.get("/api/conflicts?resolved=false")
    ids  = [c["id"] for c in r.json()]
    assert conflict.id          in ids
    assert resolved_conflict.id not in ids


def test_list_conflicts_filter_resolved(client, admin_user, conflict, resolved_conflict):
    _login(client)
    r    = client.get("/api/conflicts?resolved=true")
    ids  = [c["id"] for c in r.json()]
    assert resolved_conflict.id in ids
    assert conflict.id          not in ids


def test_list_conflicts_filter_by_lawyer(client, admin_user, conflict, db, lawyer):
    _login(client)
    # Filter by the actual lawyer — should see the conflict
    r = client.get(f"/api/conflicts?lawyer_id={lawyer.id}")
    assert r.status_code == 200
    assert any(c["id"] == conflict.id for c in r.json())

    # Filter by a non-existent lawyer — should see nothing
    r2 = client.get("/api/conflicts?lawyer_id=99999")
    assert r2.json() == []


# ── Get single ────────────────────────────────────────────────────────────────

def test_get_conflict_by_id(client, admin_user, conflict):
    _login(client)
    r = client.get(f"/api/conflicts/{conflict.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"]       == conflict.id
    assert body["resolved"] is False


def test_get_conflict_not_found(client, admin_user):
    _login(client)
    r = client.get("/api/conflicts/99999")
    assert r.status_code == 404


# ── Resolve (PATCH) ───────────────────────────────────────────────────────────

def test_resolve_conflict(client, admin_user, conflict):
    _login(client)
    r = client.patch(f"/api/conflicts/{conflict.id}", json={"resolved": True})
    assert r.status_code == 200
    assert r.json()["resolved"] is True


def test_unresolve_conflict(client, admin_user, resolved_conflict):
    _login(client)
    r = client.patch(f"/api/conflicts/{resolved_conflict.id}", json={"resolved": False})
    assert r.status_code == 200
    assert r.json()["resolved"] is False


def test_resolve_conflict_not_found(client, admin_user):
    _login(client)
    r = client.patch("/api/conflicts/99999", json={"resolved": True})
    assert r.status_code == 404


def test_resolve_requires_auth(client, conflict):
    r = client.patch(f"/api/conflicts/{conflict.id}", json={"resolved": True})
    assert r.status_code == 401


def test_clerk_can_resolve(client, clerk_user, conflict):
    _login(client, "testclerk")
    r = client.patch(f"/api/conflicts/{conflict.id}", json={"resolved": True})
    assert r.status_code == 200
