import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.db import get_db
from app.main import app
from app.models import Base, User
from cirq_sandbox.engine import get_device as real_device

# Shared test env values — auth.py's required env vars (see auth.py's
# validate_required_env, called at app startup) are set for every test via the
# autouse fixture below, so any test that starts the real FastAPI app (app.main.app)
# doesn't need its own local setup. TEST_JWT_SECRET is exported since tests that
# manually create/decode JWTs (e.g. test_auth.py) need the exact value.
TEST_JWT_SECRET = "test-secret-at-least-32-bytes-long!!"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "https://api.example.com/auth/google/callback"
    )
    monkeypatch.setenv("CLIENT_BASE_URL", "https://app.example.com")


@pytest.fixture()
def db_session():
    """In-memory SQLite session shared by any test needing the ORM schema — no live
    Postgres server in this environment (see models.py's JSONB/SQLite fallback note).

    StaticPool: routes exercised via FastAPI's TestClient run on a worker thread, and
    SQLite's default `:memory:` pooling gives each thread its own empty database — a
    single shared connection (StaticPool) keeps a whole test on one DB regardless of
    which thread touches it.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def app_client(db_session):
    """TestClient wrapping the real app.main.app (not a throwaway test app), with
    get_db overridden to the isolated in-memory db_session. `app` is a module-level
    singleton shared across the whole test session, so the override is cleared after
    each test to avoid leaking one test's db_session into the next.
    """
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def user(db_session):
    """A persisted User row, for tests that need an authenticated requester."""
    u = User(google_id="test-google-id", email="test@example.com", display_name="Test User")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def auth_headers(user):
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}
