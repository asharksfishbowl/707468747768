import json
import uuid

from app.models import Run
from app.redis_client import JOB_QUEUE_KEY
from app.worker import process_job

_VALID_DEFINITION = {
    "processor_id": "weber",
    "moments": [
        [{"gate": "H", "qubits": [[0, 5]]}],
        [{"gate": "CNOT", "qubits": [[0, 5], [0, 6]]}],
        [{"gate": "MEASURE", "qubits": [[0, 5], [0, 6]], "key": "result"}],
    ],
}


def _run_body(**overrides):
    body = {
        "definition": _VALID_DEFINITION,
        "processor_id": "weber",
        "noisy": False,
        "repetitions": 100,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# POST /runs (Requirement 24, 26)
# ---------------------------------------------------------------------------


def test_create_run_requires_auth(app_client):
    response = app_client.post("/runs", json=_run_body())
    assert response.status_code == 401


def test_create_run_requires_exactly_one_of_circuit_id_or_definition(
    app_client, auth_headers
):
    neither = app_client.post(
        "/runs",
        headers=auth_headers,
        json={"processor_id": "weber", "noisy": False, "repetitions": 100},
    )
    assert neither.status_code == 400

    both = app_client.post(
        "/runs",
        headers=auth_headers,
        json=_run_body(circuit_id="00000000-0000-0000-0000-000000000000"),
    )
    assert both.status_code == 400


def test_create_run_returns_202_and_creates_queued_row(app_client, auth_headers, db_session):
    response = app_client.post("/runs", headers=auth_headers, json=_run_body())

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run = db_session.get(Run, uuid.UUID(body["run_id"]))
    assert run.status.value == "queued"
    assert run.definition == _VALID_DEFINITION


def test_create_run_enqueues_job_on_redis(app_client, auth_headers, redis_pair):
    sync_redis, _ = redis_pair
    response = app_client.post("/runs", headers=auth_headers, json=_run_body())

    raw_job = sync_redis.lpop(JOB_QUEUE_KEY)
    job = json.loads(raw_job)
    assert job["run_id"] == response.json()["run_id"]
    assert job["repetitions"] == 100


def test_create_run_with_repetitions_out_of_bounds_returns_400(
    app_client, auth_headers, db_session
):
    for bad_repetitions in (0, -5, 1500):
        response = app_client.post(
            "/runs", headers=auth_headers, json=_run_body(repetitions=bad_repetitions)
        )
        assert response.status_code == 400
    assert db_session.query(Run).count() == 0


def test_create_run_with_zero_measure_gates_returns_400(app_client, auth_headers, db_session):
    definition = {
        "processor_id": "weber",
        "moments": [[{"gate": "H", "qubits": [[0, 5]]}]],
    }
    response = app_client.post(
        "/runs", headers=auth_headers, json=_run_body(definition=definition)
    )
    assert response.status_code == 400
    assert db_session.query(Run).count() == 0


def test_create_run_with_13_distinct_qubits_returns_400(app_client, auth_headers, db_session):
    definition = {
        "processor_id": "weber",
        "moments": [
            [{"gate": "H", "qubits": [[0, i]]} for i in range(13)],
            [{"gate": "MEASURE", "qubits": [[0, 0]], "key": "result"}],
        ],
    }
    response = app_client.post(
        "/runs", headers=auth_headers, json=_run_body(definition=definition)
    )
    assert response.status_code == 400
    assert db_session.query(Run).count() == 0


def test_create_run_two_qubit_gate_on_non_adjacent_pair_returns_400(
    app_client, auth_headers, db_session
):
    # [0,5] and [0,7] are both real weber qubits individually, but not a connected
    # pair (their neighbor is [0,6], not each other) -- Edge Case 1.
    definition = {
        "processor_id": "weber",
        "moments": [
            [{"gate": "CNOT", "qubits": [[0, 5], [0, 7]]}],
            [{"gate": "MEASURE", "qubits": [[0, 5], [0, 7]], "key": "result"}],
        ],
    }
    response = app_client.post(
        "/runs", headers=auth_headers, json=_run_body(definition=definition)
    )
    assert response.status_code == 400
    assert db_session.query(Run).count() == 0


def test_create_run_duplicate_measure_keys_returns_400(app_client, auth_headers, db_session):
    definition = {
        "processor_id": "weber",
        "moments": [
            [{"gate": "MEASURE", "qubits": [[0, 5]], "key": "result"}],
            [{"gate": "MEASURE", "qubits": [[0, 6]], "key": "result"}],
        ],
    }
    response = app_client.post(
        "/runs", headers=auth_headers, json=_run_body(definition=definition)
    )
    assert response.status_code == 400
    assert db_session.query(Run).count() == 0


def test_create_run_with_unknown_processor_id_returns_400(app_client, auth_headers, db_session):
    definition = dict(_VALID_DEFINITION, processor_id="not-a-real-processor")
    response = app_client.post(
        "/runs",
        headers=auth_headers,
        json=_run_body(definition=definition, processor_id="not-a-real-processor"),
    )
    assert response.status_code == 400
    assert db_session.query(Run).count() == 0


def test_create_run_reports_earliest_violation_when_multiple_exist(
    app_client, auth_headers, db_session
):
    # Regression test for the simplify-pass altitude finding: checks (c)/(d)/(e) must
    # run as full passes over the whole definition, in order -- not interleaved
    # per-placement -- so a topology-membership violation (c) earlier in the circuit
    # is reported ahead of a connectivity violation (d) later in it, even though the
    # connectivity-violating placement comes first in circuit order.
    definition = {
        "processor_id": "weber",
        "moments": [
            # (d) violation: both real weber qubits, but not a connected pair.
            [{"gate": "CNOT", "qubits": [[0, 5], [1, 4]]}],
            # (c) violation: not a weber qubit at all.
            [{"gate": "MEASURE", "qubits": [[9, 9]], "key": "result"}],
        ],
    }
    response = app_client.post(
        "/runs", headers=auth_headers, json=_run_body(definition=definition)
    )
    assert response.status_code == 400
    assert "[9, 9]" in response.json()["detail"]  # (c)'s violation, not (d)'s
    assert db_session.query(Run).count() == 0


def test_create_run_from_saved_circuit_uses_its_definition(app_client, auth_headers):
    created = app_client.post(
        "/circuits",
        headers=auth_headers,
        json={"name": "Saved", "definition": _VALID_DEFINITION, "is_public": False},
    ).json()

    response = app_client.post(
        "/runs",
        headers=auth_headers,
        json={
            "circuit_id": created["id"],
            "processor_id": "weber",
            "noisy": False,
            "repetitions": 100,
        },
    )
    assert response.status_code == 202


def test_create_run_from_invisible_circuit_returns_404(
    app_client, auth_headers, other_auth_headers
):
    other = app_client.post(
        "/circuits",
        headers=other_auth_headers,
        json={"name": "Private", "definition": _VALID_DEFINITION, "is_public": False},
    ).json()

    response = app_client.post(
        "/runs",
        headers=auth_headers,
        json={
            "circuit_id": other["id"],
            "processor_id": "weber",
            "noisy": False,
            "repetitions": 100,
        },
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{id} (Requirement 35), GET /runs (Requirement 36)
# ---------------------------------------------------------------------------


def test_get_run_by_non_owner_returns_404(app_client, auth_headers, other_auth_headers):
    created = app_client.post("/runs", headers=auth_headers, json=_run_body()).json()
    response = app_client.get(f"/runs/{created['run_id']}", headers=other_auth_headers)
    assert response.status_code == 404


def test_get_run_includes_definition_snapshot(app_client, auth_headers):
    """Requirement 39/44: Run History needs the immutable circuit snapshot to
    render "the circuit that produced" a run, not just its result."""
    created = app_client.post("/runs", headers=auth_headers, json=_run_body()).json()
    response = app_client.get(f"/runs/{created['run_id']}", headers=auth_headers)
    assert response.json()["definition"] == _VALID_DEFINITION


def test_list_my_runs_returns_only_own_newest_first(
    app_client, auth_headers, other_auth_headers
):
    app_client.post("/runs", headers=other_auth_headers, json=_run_body())
    mine = app_client.post("/runs", headers=auth_headers, json=_run_body()).json()

    response = app_client.get("/runs", headers=auth_headers)
    body = response.json()
    assert [r["id"] for r in body] == [mine["run_id"]]


# ---------------------------------------------------------------------------
# End-to-end: POST /runs -> worker -> GET /runs/{id} (spec Acceptance Criteria item 5)
# ---------------------------------------------------------------------------


def test_full_run_lifecycle_reaches_done_with_correct_histogram_total(
    app_client, auth_headers, redis_pair, db_session, worker_session_factory
):
    sync_redis, _ = redis_pair
    created = app_client.post(
        "/runs", headers=auth_headers, json=_run_body(repetitions=1000)
    ).json()
    run_id = created["run_id"]

    raw_job = sync_redis.lpop(JOB_QUEUE_KEY)
    process_job(json.loads(raw_job), sync_redis, db_session_factory=worker_session_factory)

    # app_client's get_db override hands every request the *same* db_session object
    # (a test simplification -- production's get_db opens a fresh session per
    # request). process_job just wrote through a separate session sharing the same
    # underlying connection, so db_session's identity-map cache of this Run row is
    # now stale; expire it so the next query re-fetches instead of returning the
    # cached pre-process_job (queued) state.
    db_session.expire_all()
    response = app_client.get(f"/runs/{run_id}", headers=auth_headers)
    body = response.json()
    assert body["status"] == "done"
    assert sum(body["result"]["result"].values()) == 1000
