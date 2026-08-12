"""Database session management, shared by every route module.

`DATABASE_URL` (see .env.example) selects the target database; falls back to
`_DEFAULT_DATABASE_URL` below when unset. That default is the same connection string
as services/api/alembic.ini's `sqlalchemy.url` and .env.example's own
`DATABASE_URL=` placeholder — three copies with no shared source (a Python constant
can't be read from a `.ini` file's static config), so a change to the dev DB URL has
to be applied in all three by hand.
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_DATABASE_URL = "postgresql://cirq_sandbox:cirq_sandbox@localhost:5432/cirq_sandbox"

engine = create_engine(os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency — yields a session, closes it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
