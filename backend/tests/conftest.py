"""
Test fixtures.

Uses a separate PostgreSQL database (court_mgmt_test).
SQLAlchemy creates tables directly from models — no Alembic needed in tests.
Each test function gets a transaction that is rolled back after the test,
keeping tests isolated without truncation overhead.

Required env var (or defaults):
    TEST_DATABASE_URL=postgresql://court:court@localhost:5432/court_mgmt_test
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

from db.models import Base
from db.database import get_db
from api.main import app
from utils.security import hash_password

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://court:court@localhost:5432/court_mgmt_test",
)

_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
_Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Create schema once per test session; drop after all tests finish."""
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)


@pytest.fixture
def db():
    """
    Yield a database session wrapped in a SAVEPOINT so each test is fully
    isolated and no data persists between tests.
    """
    connection  = _engine.connect()
    transaction = connection.begin()
    session     = _Session(bind=connection)

    # Nested transaction so the test body can call session.commit() freely
    nested = connection.begin_nested()

    @sa_event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        nonlocal nested
        if not trans.nested:
            return
        nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    """TestClient with the db dependency overridden to use the test session."""
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Seed helpers ──────────────────────────────────────────────────────────────

@pytest.fixture
def admin_user(db):
    from db.models import User
    u = User(
        username="testadmin",
        password_hash=hash_password("Password1!"),
        role="admin",
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def clerk_user(db):
    from db.models import User
    u = User(
        username="testclerk",
        password_hash=hash_password("Password1!"),
        role="clerk",
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def lawyer(db):
    from db.models import Lawyer
    l = Lawyer(name="Jane Doe", bar_number="PA-TEST01", phone=None, email=None)
    db.add(l)
    db.flush()
    return l


@pytest.fixture
def courtroom(db):
    from db.models import Courtroom
    cr = Courtroom(name="Juvenile Court - Room 1", floor=2)
    db.add(cr)
    db.flush()
    return cr


@pytest.fixture
def judge(db, courtroom):
    from db.models import Judge
    j = Judge(name="Hon. Smith", courtroom_id=courtroom.id)
    db.add(j)
    db.flush()
    return j


def _login(client, username="testadmin", password="Password1!"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r
