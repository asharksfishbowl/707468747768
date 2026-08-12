"""POST /runs, GET /runs/{id}, GET /runs (Requirements 24-26, 35-36, Edge Cases 1-4,
12).
"""

import json
import uuid
from typing import Any

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.circuit_builder import _TWO_QUBIT_GATES
from app.db import get_db
from app.models import Run, RunStatus, User
from app.redis_client import JOB_QUEUE_KEY, get_redis_client
from app.routes.circuits import _DEFAULT_PAGE_SIZE, _get_visible_or_404
from app.schema_validation import validate_circuit_definition
from app.topology import build_topology
from cirq_sandbox.engine import get_device, list_virtual_processors

router = APIRouter()


class RunCreate(BaseModel):
    circuit_id: uuid.UUID | None = None
    definition: dict[str, Any] | None = None
    processor_id: str
    noisy: bool
    repetitions: int


def _run_summary(run: Run) -> dict:
    return {
        "id": str(run.id),
        "status": run.status.value,
        "processor_id": run.processor_id,
        "noisy": run.noisy,
        "repetitions": run.repetitions,
        # Requirement 39's immutable snapshot, surfaced so Run History (Requirement
        # 44: "view its stored result and the circuit that produced it") has
        # something to render -- without this the client has no way to reconstruct
        # what was actually run.
        "definition": run.definition,
        "result": run.result,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
    }


def _validate_run_semantics(definition: dict, repetitions: int) -> None:
    """Requirement 25(a)-(e) minus the schema clause (done separately, first, by
    schema_validation.py). Checked in this exact order, first-failure-wins -- each
    check is a full pass over every placement before the next check starts (not
    interleaved per-placement), so e.g. a topology-membership violation (c) earlier
    in the circuit is always reported ahead of a connectivity violation (d) later in
    it, matching "in this order... on the first failure found" literally rather than
    just by coincidence for definitions with only one violation type.
    """
    if not (1 <= repetitions <= 1000):
        raise ValueError(f"repetitions must be between 1 and 1000, got {repetitions}")

    placements = [placement for moment in definition["moments"] for placement in moment]
    if not any(p["gate"] == "MEASURE" for p in placements):
        raise ValueError("circuit must contain at least one MEASURE gate")

    # Not part of the spec's a-e list -- a defensive addition so a garbage
    # processor_id fails with a 400 here instead of an unhandled 500 out of
    # get_device()/build_topology() below.
    processor_id = definition["processor_id"]
    if processor_id not in list_virtual_processors():
        raise ValueError(f"unknown processor_id {processor_id!r}")
    topology = build_topology(get_device(processor_id))
    topology_qubits = {tuple(q) for q in topology.qubits}
    topology_pairs = {frozenset(map(tuple, pair)) for pair in topology.pairs}

    # (c): every qubit referenced anywhere must be in topology.qubits.
    for placement in placements:
        for qubit in placement["qubits"]:
            if tuple(qubit) not in topology_qubits:
                raise ValueError(
                    f"qubit {qubit} is not part of {processor_id}'s topology"
                )

    # (d): every two-qubit gate's pair must be in topology.pairs.
    for placement in placements:
        if placement["gate"] in _TWO_QUBIT_GATES:
            pair = frozenset(map(tuple, placement["qubits"]))
            if pair not in topology_pairs:
                raise ValueError(
                    f"{placement['gate']} on {placement['qubits']} is not a "
                    f"connected pair on {processor_id}"
                )

    # (e): no two MEASURE placements share the same key.
    seen_measure_keys: set[str] = set()
    for placement in placements:
        if placement["gate"] == "MEASURE":
            key = placement["key"]
            if key in seen_measure_keys:
                raise ValueError(f"duplicate MEASURE key {key!r}")
            seen_measure_keys.add(key)


@router.post("/runs", status_code=202)
def create_run(
    body: RunCreate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    redis_conn: redis.Redis = Depends(get_redis_client),
) -> dict:
    """Requirement 24: exactly one of circuit_id/definition. Requirement 25/26:
    validates (schema, then semantics a-e, in order, first-failure-wins), then
    creates a `queued` runs row and enqueues the job -- doesn't block on execution.
    """
    if (body.circuit_id is None) == (body.definition is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of circuit_id or definition must be provided",
        )

    if body.circuit_id is not None:
        circuit = _get_visible_or_404(db, body.circuit_id, user)
        definition = circuit.definition
    else:
        definition = body.definition

    try:
        validate_circuit_definition(definition)
        if definition.get("processor_id") != body.processor_id:
            raise ValueError(
                "processor_id must match definition.processor_id"
            )
        _validate_run_semantics(definition, body.repetitions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    run = Run(
        owner_id=user.id,
        circuit_id=body.circuit_id,
        definition=definition,
        processor_id=body.processor_id,
        noisy=body.noisy,
        repetitions=body.repetitions,
        status=RunStatus.QUEUED,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    job = {
        "run_id": str(run.id),
        "definition": definition,
        "processor_id": body.processor_id,
        "noisy": body.noisy,
        "repetitions": body.repetitions,
    }
    redis_conn.rpush(JOB_QUEUE_KEY, json.dumps(job))

    return {"run_id": str(run.id), "status": "queued"}


@router.get("/runs")
def list_my_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Requirement 36: the authenticated user's own run history, newest first."""
    runs = (
        db.query(Run)
        .filter(Run.owner_id == user.id)
        .order_by(desc(Run.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_run_summary(r) for r in runs]


def _get_owned_run(db: Session, run_id: uuid.UUID, user: User) -> Run | None:
    """Owner-only lookup (runs have no `is_public` concept, unlike circuits) -- `None`
    if the run doesn't exist or isn't the user's own. Shared by this route and
    ws.py's `WS /runs/{id}/stream`, which each translate `None` into their own
    transport's "not found" response (404 here, close code 4404 there) -- matching
    circuits.py's `_get_owned_or_404`/`_get_visible_or_404` pattern of keeping the
    ownership check itself in one place.
    """
    run = db.get(Run, run_id)
    if run is None or run.owner_id != user.id:
        return None
    return run


@router.get("/runs/{run_id}")
def get_run(
    run_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 35: polling alternative to the WS stream."""
    run = _get_owned_run(db, run_id, user)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_summary(run)
