"""Idempotent dev-data seeding (cirq-studio-tooling.md Requirements 16-17, Edge
Case 3)."""

from app.models import Circuit, Run, RunStatus, User
from app.seed import SEED_GOOGLE_ID, seed


def test_seed_creates_dev_user_three_circuits_and_one_run(db_session, worker_session_factory):
    seed(db_session_factory=worker_session_factory)
    db_session.expire_all()

    users = db_session.query(User).all()
    assert [u.google_id for u in users] == [SEED_GOOGLE_ID]
    assert users[0].email == "dev@localhost"

    circuits = db_session.query(Circuit).filter_by(owner_id=users[0].id).all()
    assert {c.name for c in circuits} == {"Bell State", "GHZ State", "Superposition"}
    assert all(c.is_public for c in circuits)

    runs = db_session.query(Run).filter_by(owner_id=users[0].id).all()
    assert len(runs) == 1
    assert runs[0].status == RunStatus.DONE
    bell = next(c for c in circuits if c.name == "Bell State")
    assert runs[0].circuit_id == bell.id


def test_seed_run_twice_leaves_exactly_one_of_each_no_duplicates(db_session, worker_session_factory):
    seed(db_session_factory=worker_session_factory)
    seed(db_session_factory=worker_session_factory)
    db_session.expire_all()

    assert db_session.query(User).count() == 1
    assert db_session.query(Circuit).count() == 3
    assert db_session.query(Run).count() == 1
