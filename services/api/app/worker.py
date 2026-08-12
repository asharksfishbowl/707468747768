"""Redis queue consumer -- chunked circuit execution (Requirements 27-33, Edge Cases
5-7). Runs as a standalone process (`python -m app.worker`), separate from the
FastAPI app process, consuming jobs enqueued by `routes/runs.py`'s `POST /runs`.
"""

import json
import logging
import os
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import cirq
import redis

from app.circuit_builder import build_circuit
from app.db import SessionLocal
from app.models import Run, RunStatus
from app.redis_client import JOB_QUEUE_KEY, get_redis_client, run_channel
from cirq_sandbox.engine import compile_to_device, get_device, get_sampler

logger = logging.getLogger(__name__)

CHUNK_SIZE = 100
_DEFAULT_MAX_CONCURRENT_JOBS = 4
_DEFAULT_JOB_TIMEOUT_SECONDS = 120


def _max_concurrent_jobs() -> int:
    return int(os.environ.get("MAX_CONCURRENT_JOBS", _DEFAULT_MAX_CONCURRENT_JOBS))


def _job_timeout_seconds() -> int:
    return int(os.environ.get("JOB_TIMEOUT_SECONDS", _DEFAULT_JOB_TIMEOUT_SECONDS))


def _chunk_sizes(repetitions: int) -> list[int]:
    """Requirement 29: chunks of 100 (a 1000-repetition run is 10 chunks; a run with
    repetitions < 100 is 1 chunk of that size)."""
    full_chunks, remainder = divmod(repetitions, CHUNK_SIZE)
    sizes = [CHUNK_SIZE] * full_chunks
    if remainder:
        sizes.append(remainder)
    return sizes


def _run_chunk(sampler, compiled: cirq.Circuit, chunk_size: int):
    """The actual per-chunk sampling call, isolated so tests can substitute a
    slow/controllable double instead of real (sub-second) simulation -- exercising
    the JOB_TIMEOUT_SECONDS path (Edge Case 6) doesn't need a real multi-minute sleep.
    """
    return sampler.run(compiled, repetitions=chunk_size)


def _build_and_compile(
    definition: dict, processor_id: str, noisy: bool
) -> tuple[cirq.Circuit, cirq.Circuit]:
    """Returns (circuit, compiled) -- measurement key names are read off the
    uncompiled circuit (compile_to_device only maps gates to the device's native
    gateset; MEASURE passes through unchanged, but reading keys from the same
    circuit consistently avoids depending on that being true)."""
    circuit = build_circuit(definition)
    device = get_device(processor_id, noisy=noisy)
    compiled = compile_to_device(circuit, device)
    return circuit, compiled


def _run_with_timeout(fn, timeout_seconds: float, *args):
    """Runs `fn(*args)` with a hard wall-clock deadline (Requirement 31). A plain
    Python thread can't be forcibly killed once started, so on timeout the call is
    abandoned (not interrupted) -- `executor.shutdown(wait=False)` means this
    function returns immediately on timeout rather than blocking until the abandoned
    call finishes; there is no interruption primitive for a blocking `sampler.run()`
    call, so "stop waiting and report timed-out" is what "hard timeout" can mean here.
    Raises `concurrent.futures.TimeoutError` if `fn` doesn't finish in time.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fn, *args)
        return future.result(timeout=max(timeout_seconds, 0))
    finally:
        executor.shutdown(wait=False)


def _histogram_to_json(totals: dict[str, Counter]) -> dict[str, dict[str, int]]:
    return {key: {str(k): v for k, v in counter.items()} for key, counter in totals.items()}


def _publish(redis_conn: redis.Redis, run_id: str, payload: dict) -> None:
    redis_conn.publish(run_channel(run_id), json.dumps(payload))


def _finish_error(db, redis_conn: redis.Redis, run: Run, error_message: str) -> None:
    run.status = RunStatus.ERROR
    run.error_message = error_message
    db.commit()
    _publish(
        redis_conn,
        str(run.id),
        {"run_id": str(run.id), "status": "error", "error_message": error_message},
    )


def _finish_timeout(db, redis_conn: redis.Redis, run: Run, timeout_seconds: float) -> None:
    # Edge Case 6: completed chunks are discarded, not partially saved as the result.
    _finish_error(db, redis_conn, run, f"timed out after {timeout_seconds}s")


def _finish_done(db, redis_conn: redis.Redis, run: Run, result: dict) -> None:
    run.status = RunStatus.DONE
    run.result = result
    db.commit()
    _publish(redis_conn, str(run.id), {"run_id": str(run.id), "status": "done", "result": result})


def process_job(
    job: dict,
    redis_conn: redis.Redis,
    db_session_factory=SessionLocal,
    run_chunk=_run_chunk,
    timeout_seconds: float | None = None,
) -> None:
    """Processes one run job end-to-end (Requirements 28-33). `run_chunk` and
    `timeout_seconds` are injectable, for tests (see `_run_chunk`'s docstring and
    Edge Case 6's timeout test).

    The wall-clock deadline (Requirement 31) covers build/compile as well as every
    chunk -- including the (very common, repetitions <= 100) single-chunk case, which
    a naive "check the deadline only between chunks" design would never actually
    enforce, since there'd be no second chunk boundary to check at.
    """
    run_id = job["run_id"]
    timeout_seconds = (
        timeout_seconds if timeout_seconds is not None else _job_timeout_seconds()
    )
    deadline = time.monotonic() + timeout_seconds
    db = db_session_factory()
    try:
        run = db.get(Run, uuid.UUID(run_id))
        if run is None:
            logger.error("Run %s not found in DB -- dropping job", run_id)
            return

        run.status = RunStatus.RUNNING
        db.commit()
        chunks = _chunk_sizes(job["repetitions"])
        _publish(
            redis_conn,
            run_id,
            {
                "run_id": run_id,
                "status": "running",
                "partial_histogram": {},
                "chunks_done": 0,
                "chunks_total": len(chunks),
            },
        )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _finish_timeout(db, redis_conn, run, timeout_seconds)
            return
        try:
            circuit, compiled = _run_with_timeout(
                _build_and_compile, remaining, job["definition"], job["processor_id"], job["noisy"]
            )
        except FutureTimeoutError:
            _finish_timeout(db, redis_conn, run, timeout_seconds)
            return
        except Exception as e:  # Requirement 33, Edge Case 7: surfaced verbatim.
            _finish_error(db, redis_conn, run, str(e))
            return

        key_names = cirq.measurement_key_names(circuit)
        sampler = get_sampler(job["processor_id"], noisy=job["noisy"])
        totals: dict[str, Counter] = {key: Counter() for key in key_names}

        for chunk_index, chunk_size in enumerate(chunks, start=1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _finish_timeout(db, redis_conn, run, timeout_seconds)
                return
            try:
                result = _run_with_timeout(run_chunk, remaining, sampler, compiled, chunk_size)
            except FutureTimeoutError:
                _finish_timeout(db, redis_conn, run, timeout_seconds)
                return
            except Exception as e:
                _finish_error(db, redis_conn, run, str(e))
                return

            for key in key_names:
                totals[key].update(result.histogram(key=key))

            _publish(
                redis_conn,
                run_id,
                {
                    "run_id": run_id,
                    "status": "running",
                    "partial_histogram": _histogram_to_json(totals),
                    "chunks_done": chunk_index,
                    "chunks_total": len(chunks),
                },
            )

        _finish_done(db, redis_conn, run, _histogram_to_json(totals))
    finally:
        db.close()


def run_worker_loop(
    redis_conn: redis.Redis | None = None,
    max_concurrent: int | None = None,
    stop_event: threading.Event | None = None,
    db_session_factory=SessionLocal,
) -> None:
    """Consumes jobs from the Redis queue (Requirement 27), `max_concurrent` at a
    time: `max_concurrent` plain threads, each independently blocking on the same
    Redis list. New jobs stay queued in Redis (Edge Case 5) for free -- a thread only
    dequeues its next job once it's done with the last one, so nothing pulls ahead of
    capacity; no separate semaphore/executor pairing needed to get that property.
    Blocks until `stop_event` is set, then waits for in-flight jobs to finish.
    `db_session_factory` is forwarded to `process_job` (defaults to the real
    `SessionLocal`) so tests can exercise the loop itself against an isolated DB.
    """
    redis_conn = redis_conn or get_redis_client()
    max_concurrent = (
        max_concurrent if max_concurrent is not None else _max_concurrent_jobs()
    )
    stop_event = stop_event or threading.Event()

    def _worker() -> None:
        while not stop_event.is_set():
            popped = redis_conn.blpop(JOB_QUEUE_KEY, timeout=1)
            if popped is None:
                continue
            _, raw_job = popped
            job = json.loads(raw_job)
            try:
                process_job(job, redis_conn, db_session_factory=db_session_factory)
            except Exception:
                logger.exception("Unhandled error processing job %s", job.get("run_id"))

    threads = [threading.Thread(target=_worker) for _ in range(max_concurrent)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker_loop()
