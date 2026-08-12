"""Circuit CRUD, gallery, presets, and clone (Requirements 16-23, Edge Cases 9, 14).

Existence-hiding 404 policy (Edge Case 9): every one of `GET`/`PUT`/`DELETE
/circuits/{id}` and `POST /circuits/{id}/clone` returns 404 (never 403) for a
circuit the requester doesn't own (and, for `GET`/clone, isn't public either) — so a
non-owner can't distinguish "exists but not yours" from "doesn't exist".

Route registration order matters: every static path below (`/circuits/gallery`,
`/circuits/presets`) is declared above the dynamic `/circuits/{circuit_id}` pattern,
so it matches first — otherwise e.g. "gallery" would be swallowed as a `circuit_id`
value. `GET /circuits/presets` lives here (not in routes/processors.py, despite being
about processors/presets) specifically so this ordering guarantee is local to one
file's decorator order, not a cross-router `include_router()` sequence in main.py
that a later, unrelated change could quietly break.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.auth import require_auth
from app.db import get_db
from app.models import Circuit, User
from app.schema_validation import validate_circuit_definition
from app.topology import build_topology
from cirq_sandbox.engine import get_device, list_virtual_processors
from cirq_sandbox.preset_circuits import (
    bell_state_preset,
    ghz_state_preset,
    hello_qubit_preset,
    superposition_preset,
)

router = APIRouter()

_DEFAULT_PAGE_SIZE = 20

# Hello Qubit first, matching Cirq's own recommended learning progression
# (Requirement 16's explicit order).
_PRESET_GENERATORS = (
    hello_qubit_preset,
    bell_state_preset,
    ghz_state_preset,
    superposition_preset,
)


class CircuitCreate(BaseModel):
    name: str
    definition: dict[str, Any]
    is_public: bool = False


class CircuitUpdate(BaseModel):
    name: str | None = None
    definition: dict[str, Any] | None = None
    is_public: bool | None = None


def _circuit_summary(circuit: Circuit) -> dict:
    return {
        "id": str(circuit.id),
        "name": circuit.name,
        "processor_id": circuit.processor_id,
        "is_public": circuit.is_public,
        "created_at": circuit.created_at.isoformat(),
        "updated_at": circuit.updated_at.isoformat(),
    }


def _circuit_full(circuit: Circuit) -> dict:
    return {**_circuit_summary(circuit), "definition": circuit.definition}


def _is_visible(circuit: Circuit | None, user: User) -> bool:
    return circuit is not None and (circuit.owner_id == user.id or circuit.is_public)


def _get_visible_or_404(db: Session, circuit_id: uuid.UUID, user: User) -> Circuit:
    """Owner-or-public lookup with existence-hiding 404 — used by GET/clone."""
    circuit = db.get(Circuit, circuit_id)
    if not _is_visible(circuit, user):
        raise HTTPException(status_code=404, detail="circuit not found")
    return circuit


def _get_owned_or_404(db: Session, circuit_id: uuid.UUID, user: User) -> Circuit:
    """Owner-only lookup with existence-hiding 404 — used by PUT/DELETE, which never
    allow a non-owner regardless of `is_public`.
    """
    circuit = db.get(Circuit, circuit_id)
    if circuit is None or circuit.owner_id != user.id:
        raise HTTPException(status_code=404, detail="circuit not found")
    return circuit


def _validate_definition_or_400(definition: dict) -> None:
    try:
        validate_circuit_definition(definition)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not isinstance(definition.get("processor_id"), str) or not definition["processor_id"]:
        raise HTTPException(status_code=400, detail="definition.processor_id is required")


@router.post("/circuits", status_code=201)
def create_circuit(
    body: CircuitCreate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 17."""
    _validate_definition_or_400(body.definition)

    circuit = Circuit(
        owner_id=user.id,
        name=body.name,
        definition=body.definition,
        processor_id=body.definition["processor_id"],
        is_public=body.is_public,
    )
    db.add(circuit)
    db.commit()
    db.refresh(circuit)
    return _circuit_full(circuit)


@router.get("/circuits")
def list_my_circuits(
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Requirement 18: the authenticated user's own circuits, newest first."""
    circuits = (
        db.query(Circuit)
        .filter(Circuit.owner_id == user.id)
        .order_by(desc(Circuit.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_circuit_summary(c) for c in circuits]


@router.get("/circuits/gallery")
def gallery(
    page: int = Query(1, ge=1),
    page_size: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Requirement 22: all public circuits, newest first, with the owner's display
    name. Eager-loads `owner` (`joinedload`) to avoid an N+1 query per row.
    """
    circuits = (
        db.query(Circuit)
        .options(joinedload(Circuit.owner))
        .filter(Circuit.is_public.is_(True))
        .order_by(desc(Circuit.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        {**_circuit_summary(c), "owner_display_name": c.owner.display_name}
        for c in circuits
    ]


@router.get("/circuits/presets")
def get_presets(
    processor_id: str = Query(...),
    user: User = Depends(require_auth),
) -> list[dict]:
    """Requirement 16: all four presets against `processor_id`'s topology, in the
    hello_qubit -> bell_state -> ghz_state -> superposition order.
    """
    if processor_id not in list_virtual_processors():
        raise HTTPException(status_code=404, detail="unknown processor_id")

    topology = build_topology(get_device(processor_id))
    return [generator(topology, processor_id) for generator in _PRESET_GENERATORS]


@router.get("/circuits/{circuit_id}")
def get_circuit(
    circuit_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 19: owner or public, else 404 (Edge Case 9)."""
    return _circuit_full(_get_visible_or_404(db, circuit_id, user))


@router.put("/circuits/{circuit_id}")
def update_circuit(
    circuit_id: uuid.UUID,
    body: CircuitUpdate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 20: owner-only, 404 for anyone else (existence-hiding). Any subset
    of name/definition/is_public may be provided (`exclude_unset` distinguishes "not
    sent" from an explicit value). `updated_at` isn't set explicitly here — the
    model's `onupdate` fires automatically whenever a tracked column actually changes.
    """
    circuit = _get_owned_or_404(db, circuit_id, user)

    updates = body.model_dump(exclude_unset=True)
    if "definition" in updates:
        _validate_definition_or_400(updates["definition"])
        circuit.definition = updates["definition"]
        circuit.processor_id = updates["definition"]["processor_id"]
    if "name" in updates:
        circuit.name = updates["name"]
    if "is_public" in updates:
        circuit.is_public = updates["is_public"]

    db.commit()
    db.refresh(circuit)
    return _circuit_full(circuit)


@router.delete("/circuits/{circuit_id}", status_code=204)
def delete_circuit(
    circuit_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> None:
    """Requirement 21: owner-only, same 404 policy as PUT."""
    circuit = _get_owned_or_404(db, circuit_id, user)
    db.delete(circuit)
    db.commit()


@router.post("/circuits/{circuit_id}/clone")
def clone_circuit(
    circuit_id: uuid.UUID,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Requirement 23: target must be public or owned by the requester; creates a new
    independent row (Edge Case 14: cloning your own public circuit is allowed, not a
    no-op).
    """
    original = _get_visible_or_404(db, circuit_id, user)

    clone = Circuit(
        owner_id=user.id,
        name=f"{original.name} (copy)",
        definition=original.definition,
        processor_id=original.processor_id,
        is_public=False,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return _circuit_full(clone)
