"""Idempotent dev-data seeding (spec Requirements 16-17, Edge Case 3).

Run via `make seed` (`docker compose exec api python -m app.seed`), never wired into
any automatic startup path. Safe to run more than once: checks for the dev user by a
fixed, well-known `google_id` before inserting anything — that `google_id` value can
never collide with a real Google-issued numeric id, so no environment guard is needed
beyond the idempotency check itself.
"""

import logging

from app.db import SessionLocal
from app.models import Circuit, Run, RunStatus, User
from app.topology import build_topology
from cirq_sandbox.engine import get_device
from cirq_sandbox.preset_circuits import bell_state_preset, ghz_state_preset, superposition_preset

logger = logging.getLogger(__name__)

SEED_GOOGLE_ID = "cirq-studio-dev-seed-user"
SEED_PROCESSOR_ID = "weber"

# Bell state ideally collapses to only the |00> and |11> outcomes (result keys "0"
# and "3" under cirq's default int-fold histogram encoding — see worker.py's
# _histogram_to_json) -- a plausible-looking result so Run History isn't empty on a
# fresh environment, not a real sampled run.
_SEED_RUN_REPETITIONS = 100
_SEED_RUN_RESULT = {"result": {"0": 52, "3": 48}}


def seed(db_session_factory=SessionLocal) -> None:
    """`db_session_factory` is injectable (defaults to the real `SessionLocal`, same
    pattern as `worker.py`'s `process_job`), so tests can point this at an isolated
    session instead of the real Postgres connection.
    """
    db = db_session_factory()
    try:
        existing = db.query(User).filter_by(google_id=SEED_GOOGLE_ID).one_or_none()
        if existing is not None:
            logger.info("Seed data already present (user %s) — nothing to do.", existing.id)
            return

        user = User(google_id=SEED_GOOGLE_ID, email="dev@localhost", display_name="Dev User")
        db.add(user)
        db.flush()  # assigns user.id for the circuits/run below without a full commit yet

        topology = build_topology(get_device(SEED_PROCESSOR_ID))

        circuits = [
            Circuit(
                owner_id=user.id,
                name=name,
                definition=preset_fn(topology, SEED_PROCESSOR_ID),
                processor_id=SEED_PROCESSOR_ID,
                is_public=True,
            )
            for name, preset_fn in (
                ("Bell State", bell_state_preset),
                ("GHZ State", ghz_state_preset),
                ("Superposition", superposition_preset),
            )
        ]
        bell = circuits[0]
        db.add_all(circuits)
        db.flush()  # assigns bell.id for the run row below

        db.add(
            Run(
                owner_id=user.id,
                circuit_id=bell.id,
                definition=bell.definition,
                processor_id=SEED_PROCESSOR_ID,
                noisy=True,
                repetitions=_SEED_RUN_REPETITIONS,
                status=RunStatus.DONE,
                result=_SEED_RUN_RESULT,
            )
        )

        db.commit()
        logger.info("Seeded dev user %s with 3 circuits and 1 run.", user.id)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
