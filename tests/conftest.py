from functools import lru_cache

import cirq
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from cirq_sandbox.engine import get_sandbox_engine


@lru_cache(maxsize=None)
def real_device(processor_id: str) -> cirq.Device:
    """Cached sandbox device lookup, shared across test modules.

    Building the noisy virtual machine is expensive (~0.3s — it builds a full noise
    model from calibration data), and topology/preset tests are parametrized per
    processor, so each processor's device is built once and reused instead of once
    per test case.
    """
    engine = get_sandbox_engine(processor_id=processor_id, noisy=True)
    return engine.get_processor(processor_id).get_device()


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
