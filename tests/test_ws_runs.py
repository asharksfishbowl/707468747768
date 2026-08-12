import threading
import uuid

import pytest
from fastapi.websockets import WebSocketDisconnect

from app.models import Run, RunStatus
from app.worker import process_job

_BELL_DEFINITION = {
    "processor_id": "weber",
    "moments": [
        [{"gate": "H", "qubits": [[0, 5]]}],
        [{"gate": "CNOT", "qubits": [[0, 5], [0, 6]]}],
        [{"gate": "MEASURE", "qubits": [[0, 5], [0, 6]], "key": "result"}],
    ],
}


def _create_run(db_session, user, *, repetitions=150, status=RunStatus.QUEUED):
    run = Run(
        owner_id=user.id,
        circuit_id=None,
        definition=_BELL_DEFINITION,
        processor_id="weber",
        noisy=False,
        repetitions=repetitions,
        status=status,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _token(auth_headers) -> str:
    return auth_headers["Authorization"].removeprefix("Bearer ")


def test_ws_stream_without_valid_token_closes_4401(app_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect(f"/runs/{uuid.uuid4()}/stream"):
            pass
    assert exc_info.value.code == 4401


def test_ws_stream_for_nonexistent_run_closes_4404(app_client, auth_headers):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect(
            f"/runs/{uuid.uuid4()}/stream?token={_token(auth_headers)}"
        ):
            pass
    assert exc_info.value.code == 4404


def test_ws_stream_for_another_users_run_closes_4404(
    app_client, auth_headers, db_session, other_user
):
    run = _create_run(db_session, other_user)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect(
            f"/runs/{run.id}/stream?token={_token(auth_headers)}"
        ):
            pass
    assert exc_info.value.code == 4404


def test_ws_stream_sends_current_state_first(app_client, auth_headers, db_session, user):
    # Edge Case 8: a client connecting mid-run (or after completion) sees the current
    # persisted state immediately, not just future pub/sub messages.
    run = _create_run(db_session, user, status=RunStatus.DONE)
    run.result = {"result": {"0": 500, "3": 500}}
    db_session.commit()

    with app_client.websocket_connect(
        f"/runs/{run.id}/stream?token={_token(auth_headers)}"
    ) as ws:
        first = ws.receive_json()

    assert first["run_id"] == str(run.id)
    assert first["status"] == "done"
    assert first["result"] == {"result": {"0": 500, "3": 500}}


def test_ws_stream_relays_running_then_done_from_worker(
    app_client, auth_headers, db_session, user, redis_pair, worker_session_factory
):
    # Spec Acceptance Criteria item 9: receives >=1 "running" message with a
    # non-empty partial_histogram before the final "done" message.
    sync_redis, _ = redis_pair
    run = _create_run(db_session, user, repetitions=150)  # 2 chunks: 100, 50
    job = {
        "run_id": str(run.id),
        "definition": run.definition,
        "processor_id": run.processor_id,
        "noisy": run.noisy,
        "repetitions": run.repetitions,
    }

    with app_client.websocket_connect(
        f"/runs/{run.id}/stream?token={_token(auth_headers)}"
    ) as ws:
        initial = ws.receive_json()
        assert initial["status"] == "queued"

        worker_thread = threading.Thread(
            target=process_job,
            args=(job, sync_redis),
            kwargs={"db_session_factory": worker_session_factory},
        )
        worker_thread.start()

        seen_running_with_data = False
        seen_done = False
        for _ in range(20):
            message = ws.receive_json()
            if message["status"] == "running" and message.get("partial_histogram"):
                seen_running_with_data = True
            if message["status"] == "done":
                seen_done = True
                break

        worker_thread.join(timeout=5)

    assert seen_running_with_data
    assert seen_done
