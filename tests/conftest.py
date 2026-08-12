import fakeredis
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.db import get_db
from app.main import app
from app.models import Base, User
from app.redis_client import get_async_redis_client, get_redis_client
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
def worker_session_factory(db_session):
    """A sessionmaker bound to db_session's own connection, for handing to
    process_job/run_worker_loop (which open and close their own session per job --
    the real worker gives every job a fresh one). Since db_session's engine uses
    StaticPool, this is genuinely the same underlying SQLite connection, so writes
    made through a session from this factory are visible back through db_session
    afterward -- same as production's shared database, just one process instead of
    two.
    """
    return sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)


@pytest.fixture()
def redis_pair():
    """A shared fakeredis backend (no live Redis server in this environment),
    exposed as both a sync and an async client -- worker.py/routes/runs.py use the
    sync client (enqueue, consume, publish), ws.py uses the async client (subscribe,
    so a blocking pub/sub read doesn't stall its event loop) -- both need to observe
    the same fake state, which is what sharing one `FakeServer` gives us.
    """
    server = fakeredis.FakeServer()
    sync_client = fakeredis.FakeStrictRedis(server=server)
    async_client = fakeredis.aioredis.FakeRedis(server=server)
    return sync_client, async_client


@pytest.fixture()
def app_client(db_session, redis_pair):
    """TestClient wrapping the real app.main.app (not a throwaway test app), with
    get_db and the Redis clients overridden to the isolated test doubles. `app` is a
    module-level singleton shared across the whole test session, so overrides are
    cleared after each test to avoid leaking one test's state into the next.
    """
    sync_redis, async_redis = redis_pair
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis_client] = lambda: sync_redis
    app.dependency_overrides[get_async_redis_client] = lambda: async_redis
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


@pytest.fixture()
def other_user(db_session):
    """A second persisted User row, for tests exercising cross-user access (the
    404-not-403 existence-hiding policy, gallery/clone, etc.)."""
    u = User(google_id="other-google-id", email="bo@example.com", display_name="Bo")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def other_auth_headers(other_user):
    return {"Authorization": f"Bearer {create_access_token(other_user)}"}
