import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Circuit, Run, RunStatus, User


def _session():
    # In-memory SQLite: no live Postgres server in this environment. The JSONB
    # columns fall back to generic JSON on this dialect (see models.py), so this
    # still exercises the real schema shape, just not the Postgres-specific type.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_user_circuit_run_round_trip():
    with _session() as session:
        user = User(
            google_id="g-123", email="a@example.com", display_name="Ada"
        )
        session.add(user)
        session.flush()

        circuit = Circuit(
            owner_id=user.id,
            name="My Bell Circuit",
            definition={"processor_id": "weber", "moments": []},
            processor_id="weber",
            is_public=True,
        )
        session.add(circuit)
        session.flush()

        run = Run(
            owner_id=user.id,
            circuit_id=circuit.id,
            definition=circuit.definition,
            processor_id="weber",
            noisy=True,
            repetitions=1000,
            status=RunStatus.QUEUED,
        )
        session.add(run)
        session.commit()

        assert isinstance(user.id, uuid.UUID)
        assert circuit.owner_id == user.id
        assert circuit.is_public is True
        assert run.circuit_id == circuit.id
        assert run.status == RunStatus.QUEUED
        assert run.result is None
        assert run.error_message is None


def test_run_without_a_saved_circuit_is_allowed():
    with _session() as session:
        user = User(google_id="g-456", email="b@example.com", display_name="Bo")
        session.add(user)
        session.flush()

        run = Run(
            owner_id=user.id,
            circuit_id=None,
            definition={"processor_id": "weber", "moments": []},
            processor_id="weber",
            noisy=False,
            repetitions=500,
            status=RunStatus.DONE,
            result={"00": 250, "11": 250},
        )
        session.add(run)
        session.commit()

        assert run.circuit_id is None
        assert run.result == {"00": 250, "11": 250}


def test_google_id_is_unique():
    from sqlalchemy.exc import IntegrityError

    with _session() as session:
        session.add(User(google_id="dup", email="a@example.com", display_name="A"))
        session.commit()

        session.add(User(google_id="dup", email="b@example.com", display_name="B"))
        try:
            session.commit()
            raise AssertionError("expected IntegrityError for duplicate google_id")
        except IntegrityError:
            session.rollback()
