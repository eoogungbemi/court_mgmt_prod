"""
Analytics summary endpoint — GET /api/analytics/summary

Covers:
- Auth enforcement (requires any authenticated user; attorney is excluded)
- Empty-day response shape
- Hearing counts and completion rate
- ETA accuracy calculation (the core AI-agent metric)
- Conflict counters
"""

from datetime import datetime, timedelta, timezone
import pytest
from tests.conftest import _login


TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def attorney_user(db):
    from db.models import User
    from utils.security import hash_password
    u = User(username="testatty", password_hash=hash_password("Password1!"),
             role="attorney", is_active=True)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def hearing_set(db, courtroom, judge, lawyer):
    """
    Creates 4 hearings on today's date:
      - 2 completed (with actual_start/end + ETA estimate)
      - 1 in_progress
      - 1 scheduled
    Returns the list of Hearing objects.
    """
    from db.models import Case, Accused, Hearing, ETAEstimate

    def _case(n):
        c = Case(case_number=f"2026-JD-ATEST{n}", case_type="delinquency",
                 complexity="medium", defense_lawyer_id=lawyer.id)
        db.add(c)
        db.flush()
        db.add(Accused(name=f"Minor {n}", case_id=c.id))
        db.flush()
        return c

    base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    hearings = []

    for i, (status, actual) in enumerate([
        ("completed",   True),
        ("completed",   True),
        ("in_progress", False),
        ("scheduled",   False),
    ]):
        start = base + timedelta(hours=i)
        end   = start + timedelta(minutes=30)
        case  = _case(i)
        h = Hearing(
            case_id=case.id, courtroom_id=courtroom.id, judge_id=judge.id,
            hearing_type="review",
            scheduled_start=start, scheduled_end=end,
            estimated_duration_mins=30, status=status,
        )
        if actual:
            h.actual_start = start + timedelta(minutes=1)
            h.actual_end   = start + timedelta(minutes=28)  # 27 actual mins
        db.add(h)
        db.flush()

        if actual:
            db.add(ETAEstimate(
                hearing_id=h.id,
                estimated_start=start,
                p25_mins=25, p75_mins=35,  # p50 = 30 min
                rationale="test estimate",
                agent_name="DurationEstimatorAgent",
            ))
        hearings.append(h)

    db.flush()
    return hearings


# ── Auth guards ───────────────────────────────────────────────────────────────

def test_analytics_requires_auth(client):
    r = client.get(f"/api/analytics/summary?run_date={TODAY}")
    assert r.status_code == 401


def test_analytics_attorney_forbidden(client, attorney_user):
    """Attorney role is excluded from analytics."""
    _login(client, "testatty")
    r = client.get(f"/api/analytics/summary?run_date={TODAY}")
    assert r.status_code == 403


# ── Empty-day response ────────────────────────────────────────────────────────

def test_analytics_empty_day(client, admin_user):
    _login(client)
    r = client.get("/api/analytics/summary?run_date=2000-01-01")
    assert r.status_code == 200
    body = r.json()
    assert body["total_hearings"] == 0
    assert body["completion_rate_pct"] == 0.0
    assert body["eta_accuracy"] is None
    sb = body["status_breakdown"]
    assert all(v == 0 for v in sb.values())


# ── Hearing counts ────────────────────────────────────────────────────────────

def test_analytics_total_hearings(client, admin_user, hearing_set):
    _login(client)
    r = client.get(f"/api/analytics/summary?run_date={TODAY}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_hearings"] == 4


def test_analytics_status_breakdown(client, admin_user, hearing_set):
    _login(client)
    r    = client.get(f"/api/analytics/summary?run_date={TODAY}")
    sb   = r.json()["status_breakdown"]
    assert sb["completed"]   == 2
    assert sb["in_progress"] == 1
    assert sb["scheduled"]   == 1


def test_analytics_completion_rate(client, admin_user, hearing_set):
    """2 completed out of 4 non-cancelled = 50 %."""
    _login(client)
    r = client.get(f"/api/analytics/summary?run_date={TODAY}")
    assert r.json()["completion_rate_pct"] == 50.0


def test_analytics_by_case_type(client, admin_user, hearing_set):
    _login(client)
    r = client.get(f"/api/analytics/summary?run_date={TODAY}")
    types = {item["case_type"] for item in r.json()["by_case_type"]}
    assert "delinquency" in types


def test_analytics_by_courtroom(client, admin_user, hearing_set, courtroom):
    _login(client)
    r    = client.get(f"/api/analytics/summary?run_date={TODAY}")
    rows = r.json()["by_courtroom"]
    assert len(rows) >= 1
    room_row = next(row for row in rows if row["courtroom_id"] == courtroom.id)
    assert room_row["hearing_count"] == 4
    assert room_row["completed"] == 2


# ── ETA accuracy ──────────────────────────────────────────────────────────────

def test_analytics_eta_accuracy_calculated(client, admin_user, hearing_set):
    """
    2 completed hearings, each with p50 = 30 min and actual = 27 min.
    Expected MAE = |30 - 27| = 3.0 min.
    """
    _login(client)
    r   = client.get(f"/api/analytics/summary?run_date={TODAY}")
    eta = r.json()["eta_accuracy"]
    assert eta is not None
    assert eta["sample_size"] == 2
    assert eta["avg_estimated_mins"] == 30.0
    assert eta["avg_actual_mins"] == 27.0
    assert eta["mean_abs_error_mins"] == 3.0


def test_analytics_eta_null_when_no_completed(client, admin_user):
    """With no completed hearings there is no accuracy data."""
    _login(client)
    r = client.get("/api/analytics/summary?run_date=2000-01-01")
    assert r.json()["eta_accuracy"] is None


# ── Conflict counters ─────────────────────────────────────────────────────────

def test_analytics_conflict_counts(client, admin_user, db, courtroom, judge, lawyer):
    from db.models import Case, Accused, Hearing, LawyerConflict
    from datetime import timezone

    base = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0)

    def _case():
        c = Case(case_number=f"2026-JD-CONF{id(object())%9999}",
                 case_type="delinquency", complexity="low", defense_lawyer_id=lawyer.id)
        db.add(c); db.flush()
        db.add(Accused(name="Minor", case_id=c.id)); db.flush()
        return c

    ha = Hearing(case_id=_case().id, courtroom_id=courtroom.id, judge_id=judge.id,
                 hearing_type="arraignment", scheduled_start=base,
                 scheduled_end=base + timedelta(minutes=30),
                 estimated_duration_mins=30, status="scheduled")
    hb = Hearing(case_id=_case().id, courtroom_id=courtroom.id, judge_id=judge.id,
                 hearing_type="arraignment", scheduled_start=base + timedelta(minutes=15),
                 scheduled_end=base + timedelta(minutes=45),
                 estimated_duration_mins=30, status="scheduled")
    db.add(ha); db.add(hb); db.flush()

    conflict = LawyerConflict(
        lawyer_id=lawyer.id, hearing_a_id=ha.id, hearing_b_id=hb.id,
        overlap_start=base + timedelta(minutes=15),
        overlap_end=base + timedelta(minutes=30),
        resolved=False,
    )
    db.add(conflict); db.flush()

    _login(client)
    r    = client.get(f"/api/analytics/summary?run_date={TODAY}")
    body = r.json()
    assert body["conflicts_unresolved"] >= 1
    assert body["conflicts_detected_today"] >= 1


def test_analytics_clerk_can_access(client, clerk_user):
    _login(client, "testclerk")
    r = client.get(f"/api/analytics/summary?run_date={TODAY}")
    assert r.status_code == 200
