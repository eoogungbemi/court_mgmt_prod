"""Case CRUD, bulk upload, and sealed-case enforcement."""

import io
import pytest
from tests.conftest import _login


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_case(client, lawyer_id: int, sealed: bool = False) -> dict:
    r = client.post("/api/cases", json={
        "case_type":         "delinquency",
        "complexity":        "medium",
        "defense_lawyer_id": lawyer_id,
        "is_confidential":   sealed,
        "respondents": [{"name": "Jane Minor"}],
    })
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_create_case(client, admin_user, lawyer):
    _login(client)
    case = _create_case(client, lawyer.id)
    assert case["case_number"].startswith(str(__import__("datetime").datetime.utcnow().year))
    assert case["case_type"] == "delinquency"
    assert len(case["respondents"]) == 1


def test_create_case_unknown_lawyer(client, admin_user):
    _login(client)
    r = client.post("/api/cases", json={
        "case_type": "dependency", "complexity": "low",
        "defense_lawyer_id": 99999,
        "respondents": [{"name": "Test"}],
    })
    assert r.status_code == 400


def test_get_case(client, admin_user, lawyer):
    _login(client)
    case = _create_case(client, lawyer.id)
    r    = client.get(f"/api/cases/{case['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == case["id"]


def test_update_case(client, admin_user, lawyer):
    _login(client)
    case = _create_case(client, lawyer.id)
    r    = client.patch(f"/api/cases/{case['id']}", json={"complexity": "high"})
    assert r.status_code == 200
    assert r.json()["complexity"] == "high"


def test_seal_case(client, admin_user, lawyer):
    _login(client)
    case = _create_case(client, lawyer.id)
    r    = client.post(f"/api/cases/{case['id']}/seal")
    assert r.status_code == 200
    r2   = client.get(f"/api/cases/{case['id']}")
    assert r2.json()["is_confidential"] is True


# ── Sealed case enforcement ───────────────────────────────────────────────────

def test_sealed_case_hidden_from_attorney(client, db, lawyer):
    """An attorney cannot access a sealed case that is not theirs."""
    from db.models import User
    from utils.security import hash_password

    # Admin creates a sealed case belonging to lawyer
    admin = __import__("db.models", fromlist=["User"]).User(
        username="adm2", password_hash=hash_password("Pass1!"), role="admin", is_active=True,
    )
    db.add(admin)
    db.flush()

    other_atty = User(
        username="otheratty",
        password_hash=hash_password("Pass1!"),
        role="attorney",
        lawyer_id=None,   # linked to a different lawyer (or none)
        is_active=True,
    )
    db.add(other_atty)
    db.flush()

    _login(client, "adm2", "Pass1!")
    case = _create_case(client, lawyer.id, sealed=True)

    # Switch to attorney who has no access
    _login(client, "otheratty", "Pass1!")
    r = client.get(f"/api/cases/{case['id']}")
    assert r.status_code == 403


def test_sealed_case_visible_to_admin(client, admin_user, lawyer):
    _login(client)
    case = _create_case(client, lawyer.id, sealed=True)
    r    = client.get(f"/api/cases/{case['id']}")
    assert r.status_code == 200


def test_sealed_case_not_in_search_results_for_attorney(client, db, lawyer):
    """search_cases must filter out sealed cases for attorney role."""
    from db.models import User
    from utils.security import hash_password

    # Create a sealed case via direct DB (no HTTP)
    from db.models import Case, Accused
    sealed = Case(
        case_number="2026-JD-99999", case_type="delinquency",
        complexity="low", is_confidential=True, defense_lawyer_id=lawyer.id,
    )
    db.add(sealed)
    db.flush()
    db.add(Accused(name="Secret Minor", case_id=sealed.id))
    db.flush()

    # Create an attorney user with a *different* lawyer_id
    atty = User(
        username="atty99", password_hash=hash_password("Pass1!"),
        role="attorney", lawyer_id=None, is_active=True,
    )
    db.add(atty)
    db.flush()

    _login(client, "atty99", "Pass1!")
    r = client.get("/api/cases")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert sealed.id not in ids


# ── Bulk upload ───────────────────────────────────────────────────────────────

def test_bulk_upload_csv(client, admin_user, lawyer):
    _login(client)
    csv_content = (
        "case_type,respondent_name,defense_lawyer_id,complexity\n"
        f"delinquency,Minor A,{lawyer.id},low\n"
        f"dependency,Minor B,{lawyer.id},medium\n"
        "status_offense,Minor C,99999,low\n"   # bad lawyer_id → skipped
    )
    r = client.post(
        "/api/cases/bulk-upload",
        files={"file": ("cases.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 2
    assert body["skipped"] == 1
    assert len(body["errors"]) == 1
