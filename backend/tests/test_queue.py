"""
Public queue and check-in flow.
Verifies sealed-case masking and party check-in.
"""

from datetime import datetime, timezone, timedelta
import pytest
from tests.conftest import _login


def _seed_hearing(db, case_id, courtroom_id, judge_id, start_offset_hours=1):
    from db.models import Hearing
    start = datetime.now(timezone.utc) + timedelta(hours=start_offset_hours)
    h = Hearing(
        case_id=case_id,
        courtroom_id=courtroom_id,
        judge_id=judge_id,
        hearing_type="adjudicatory",
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=1),
        estimated_duration_mins=60,
    )
    db.add(h)
    db.flush()
    return h


def _seed_case(db, lawyer_id, sealed=False):
    from db.models import Case, Accused
    import random
    cn = f"2026-JD-{random.randint(10000, 99999)}"
    c = Case(
        case_number=cn, case_type="delinquency",
        complexity="medium", is_confidential=sealed,
        defense_lawyer_id=lawyer_id,
    )
    db.add(c)
    db.flush()
    db.add(Accused(name="Test Minor", case_id=c.id))
    db.flush()
    return c


# ── Overview ──────────────────────────────────────────────────────────────────

def test_overview_unauthenticated(client, courtroom):
    """Overview is public — no auth required."""
    r = client.get("/api/courtrooms/overview")
    assert r.status_code == 200
    names = [cr["name"] for cr in r.json()]
    assert courtroom.name in names


# ── Queue masking ─────────────────────────────────────────────────────────────

def test_queue_masks_sealed_case_for_public(client, db, courtroom, judge, lawyer):
    """Unauthenticated request must receive 'Confidential' for sealed case fields."""
    sealed_case = _seed_case(db, lawyer.id, sealed=True)
    _seed_hearing(db, sealed_case.id, courtroom.id, judge.id)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r     = client.get(f"/api/courtrooms/{courtroom.id}/queue?run_date={today}")
    assert r.status_code == 200

    sealed_items = [i for i in r.json() if i["respondent_name"] == "Confidential"]
    assert len(sealed_items) >= 1
    assert sealed_items[0]["case_number"] == "Confidential"
    assert sealed_items[0]["attorney_name"] == "Confidential"


def test_queue_shows_sealed_case_to_clerk(client, db, courtroom, judge, lawyer, clerk_user):
    """Clerk must see full data even for sealed cases."""
    _login(client, "testclerk")
    sealed_case = _seed_case(db, lawyer.id, sealed=True)
    _seed_hearing(db, sealed_case.id, courtroom.id, judge.id)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r     = client.get(f"/api/courtrooms/{courtroom.id}/queue?run_date={today}")
    assert r.status_code == 200

    visible = [i for i in r.json() if i["respondent_name"] == "Test Minor"]
    assert len(visible) >= 1


# ── Check-in flow ─────────────────────────────────────────────────────────────

def test_checkin_attorney(client, db, courtroom, judge, lawyer, clerk_user):
    _login(client, "testclerk")
    case    = _seed_case(db, lawyer.id)
    hearing = _seed_hearing(db, case.id, courtroom.id, judge.id)

    r = client.post(f"/api/hearings/{hearing.id}/checkin", json={"party": "attorney"})
    assert r.status_code == 200
    assert r.json()["lawyer_checked_in"] is True
    assert r.json()["accused_checked_in"] is False


def test_checkin_juvenile(client, db, courtroom, judge, lawyer, clerk_user):
    _login(client, "testclerk")
    case    = _seed_case(db, lawyer.id)
    hearing = _seed_hearing(db, case.id, courtroom.id, judge.id)

    client.post(f"/api/hearings/{hearing.id}/checkin", json={"party": "attorney"})
    r = client.post(f"/api/hearings/{hearing.id}/checkin", json={"party": "juvenile"})
    assert r.status_code == 200
    assert r.json()["lawyer_checked_in"] is True
    assert r.json()["accused_checked_in"] is True


def test_checkin_requires_auth(client, db, courtroom, judge, lawyer):
    case    = _seed_case(db, lawyer.id)
    hearing = _seed_hearing(db, case.id, courtroom.id, judge.id)
    r       = client.post(f"/api/hearings/{hearing.id}/checkin", json={"party": "attorney"})
    assert r.status_code == 401


# ── ETA fallback ──────────────────────────────────────────────────────────────

def test_rule_based_eta_fallback():
    """Rule-based estimator returns sensible output without any API call."""
    from agents.duration_estimator_agent import _rule_estimate

    result = _rule_estimate("delinquency", "adjudicatory", "high")
    assert result["p25_mins"] > 0
    assert result["p75_mins"] > result["p25_mins"]
    assert "rule-based" in result["rationale"].lower()

    result_low = _rule_estimate("dependency", "review", "low")
    # Low complexity should produce shorter estimates than high
    assert result_low["p75_mins"] < result["p75_mins"]
