import json
import threading
import time

import fakeredis

from app.models import Run, RunStatus
from app.redis_client import JOB_QUEUE_KEY
from app.worker import _chunk_sizes, process_job, run_worker_loop

_BELL_DEFINITION = {
    "processor_id": "weber",
    "moments": [
        [{"gate": "H", "qubits": [[0, 5]]}],
        [{"gate": "CNOT", "qubits": [[0, 5], [0, 6]]}],
        [{"gate": "MEASURE", "qubits": [[0, 5], [0, 6]], "key": "result"}],
    ],
}


def _create_run(db_session, user, *, repetitions=200, definition=None, noisy=False):
    run = Run(
        owner_id=user.id,
        circuit_id=None,
        definition=definition or _BELL_DEFINITION,
        processor_id="weber",
        noisy=noisy,
        repetitions=repetitions,
        status=RunStatus.QUEUED,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _job_for(run: Run) -> dict:
    return {
        "run_id": str(run.id),
        "definition": run.definition,
        "processor_id": run.processor_id,
        "noisy": run.noisy,
        "repetitions": run.repetitions,
    }


def test_chunk_sizes():
    assert _chunk_sizes(1000) == [100] * 10
    assert _chunk_sizes(50) == [50]
    assert _chunk_sizes(150) == [100, 50]


def test_process_job_persists_done_with_correct_total_count(
    db_session, user, worker_session_factory
):
    run = _create_run(db_session, user, repetitions=200)
    redis_conn = fakeredis.FakeStrictRedis()

    process_job(_job_for(run), redis_conn, db_session_factory=worker_session_factory)

    db_session.refresh(run)
    assert run.status == RunStatus.DONE
    assert run.error_message is None
    total = sum(run.result["result"].values())
    assert total == 200


def test_process_job_publishes_running_then_done(db_session, user, worker_session_factory):
    run = _create_run(db_session, user, repetitions=150)  # 2 chunks: 100, 50
    redis_conn = fakeredis.FakeStrictRedis()
    pubsub = redis_conn.pubsub()
    pubsub.subscribe(f"run:{run.id}")
    pubsub.get_message(timeout=1)  # subscribe confirmation

    process_job(_job_for(run), redis_conn, db_session_factory=worker_session_factory)

    messages = []
    while True:
        msg = pubsub.get_message(timeout=0.5)
        if msg is None:
            break
        if msg["type"] == "message":
            messages.append(json.loads(msg["data"]))

    statuses = [m["status"] for m in messages]
    # Initial "running" (0 chunks), then one "running" per chunk (2), then "done".
    assert statuses == ["running", "running", "running", "done"]
    assert messages[1]["chunks_done"] == 1
    assert messages[1]["chunks_total"] == 2
    assert sum(messages[1]["partial_histogram"]["result"].values()) == 100
    assert messages[-1]["status"] == "done"
    assert sum(messages[-1]["result"]["result"].values()) == 150


def test_process_job_bell_state_shows_00_11_dominant_correlation(
    db_session, user, worker_session_factory
):
    run = _create_run(db_session, user, repetitions=1000, noisy=False)
    redis_conn = fakeredis.FakeStrictRedis()

    process_job(_job_for(run), redis_conn, db_session_factory=worker_session_factory)

    db_session.refresh(run)
    histogram = run.result["result"]
    dominant = histogram.get("0", 0) + histogram.get("3", 0)
    rare = histogram.get("1", 0) + histogram.get("2", 0)
    assert dominant > rare


def test_process_job_sampler_exception_sets_error_status_verbatim(
    db_session, user, worker_session_factory
):
    # Edge Case 7: an exception from run_chunk (standing in for optimize_for_target_
    # gateset/sampler.run) surfaces verbatim in error_message, no retry, no generic
    # "something went wrong" swallow.
    run = _create_run(db_session, user, repetitions=100)
    redis_conn = fakeredis.FakeStrictRedis()

    def _failing_chunk(sampler, compiled, chunk_size):
        raise RuntimeError("sampler exploded")

    process_job(
        _job_for(run),
        redis_conn,
        db_session_factory=worker_session_factory,
        run_chunk=_failing_chunk,
    )

    db_session.refresh(run)
    assert run.status == RunStatus.ERROR
    assert run.error_message == "sampler exploded"


def test_process_job_timeout_discards_completed_chunks(
    db_session, user, worker_session_factory
):
    run = _create_run(db_session, user, repetitions=200)  # 2 chunks
    redis_conn = fakeredis.FakeStrictRedis()

    call_count = 0

    def _chunk_runner(sampler, compiled, chunk_size):
        nonlocal call_count
        call_count += 1
        return sampler.run(compiled, repetitions=chunk_size)

    # timeout_seconds=0 means the very first deadline check (before chunk 1) already
    # fails -- exercises the "abort remaining chunks, don't partially persist
    # completed ones" path (Edge Case 6) deterministically, no real sleep needed.
    process_job(
        _job_for(run),
        redis_conn,
        db_session_factory=worker_session_factory,
        run_chunk=_chunk_runner,
        timeout_seconds=0,
    )

    db_session.refresh(run)
    assert run.status == RunStatus.ERROR
    assert run.error_message == "timed out after 0s"
    assert run.result is None
    assert call_count == 0  # no chunk was ever run


def test_process_job_timeout_fires_mid_single_chunk(db_session, user, worker_session_factory):
    # Regression test for the simplify-pass altitude finding: a naive "check the
    # deadline only between chunks" design never enforces a timeout on a single-chunk
    # job (repetitions <= 100, the common case) since there's no second chunk
    # boundary to check at. Uses a real sleep to prove the deadline is enforced
    # *during* the one chunk's execution, not just via the before-any-chunk pre-check
    # the timeout_seconds=0 test above already covers.
    run = _create_run(db_session, user, repetitions=50)  # 1 chunk

    def _slow_chunk(sampler, compiled, chunk_size):
        time.sleep(0.3)
        return sampler.run(compiled, repetitions=chunk_size)

    process_job(
        _job_for(run),
        fakeredis.FakeStrictRedis(),
        db_session_factory=worker_session_factory,
        run_chunk=_slow_chunk,
        timeout_seconds=0.05,
    )

    db_session.refresh(run)
    assert run.status == RunStatus.ERROR
    assert run.error_message == "timed out after 0.05s"
    assert run.result is None


def test_run_worker_loop_dequeues_and_processes_a_job(db_session, user, worker_session_factory):
    run = _create_run(db_session, user, repetitions=100)
    redis_conn = fakeredis.FakeStrictRedis()
    redis_conn.rpush(JOB_QUEUE_KEY, json.dumps(_job_for(run)))

    stop_event = threading.Event()
    loop_thread = threading.Thread(
        target=run_worker_loop,
        kwargs={
            "redis_conn": redis_conn,
            "max_concurrent": 2,
            "stop_event": stop_event,
            "db_session_factory": worker_session_factory,
        },
    )
    loop_thread.start()

    # blpop's own 1s poll interval bounds how long a single iteration can take; give
    # it a few iterations' worth of margin rather than a tight race.
    for _ in range(30):
        db_session.expire_all()
        if db_session.get(Run, run.id).status != RunStatus.QUEUED:
            break
        threading.Event().wait(0.1)

    stop_event.set()
    loop_thread.join(timeout=5)

    db_session.expire_all()
    finished = db_session.get(Run, run.id)
    assert finished.status == RunStatus.DONE
    assert sum(finished.result["result"].values()) == 100
