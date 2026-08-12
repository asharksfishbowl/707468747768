"""Schema validation for circuit JSON definitions (spec Requirement 25, first clause
only: unknown `gate` values, missing gate-specific required fields, malformed
`qubits` values). Used by `POST`/`PUT /circuits` (this phase) and, per Requirement
25's own wording, also by `POST /runs` (Phase 4) — write it once here, reuse it there.

Semantic/connectivity validation (Requirement 25's remaining clauses (a)-(e): repetition
bounds, MEASURE presence, topology membership, connectivity, duplicate MEASURE keys) is
`POST /runs`-specific and belongs to Phase 4 — deliberately not duplicated here.
"""

from typing import Any

from app.circuit_builder import _PARAMETERIZED_GATES, _SINGLE_QUBIT_GATES, _TWO_QUBIT_GATES

# Derived from circuit_builder.py's gate-name -> cirq.Gate maps (the same maps
# build_circuit and native_gate_names use), not re-listed by hand, so this can't
# silently drift from what build_circuit actually supports.
_VALID_GATES = (
    _SINGLE_QUBIT_GATES.keys() | _TWO_QUBIT_GATES.keys() | _PARAMETERIZED_GATES.keys()
    | {"MEASURE"}
)

# Expected qubit count per gate; a gate absent here (MEASURE) is unconstrained.
_EXPECTED_QUBIT_COUNT: dict[str, int] = {
    **{name: 1 for name in _SINGLE_QUBIT_GATES},
    **{name: 1 for name in _PARAMETERIZED_GATES},
    **{name: 2 for name in _TWO_QUBIT_GATES},
}


def validate_circuit_definition(definition: Any) -> None:
    """Raises `ValueError`, with a message naming the specific violation, on the
    first schema problem found.
    """
    if not isinstance(definition, dict) or not isinstance(definition.get("moments"), list):
        raise ValueError("definition must be an object with a 'moments' list")

    for moment_index, moment in enumerate(definition["moments"]):
        if not isinstance(moment, list):
            raise ValueError(f"moment {moment_index} must be a list of gate placements")
        for placement in moment:
            _validate_placement(placement, moment_index)


def _validate_placement(placement: Any, moment_index: int) -> None:
    if not isinstance(placement, dict):
        raise ValueError(f"moment {moment_index}: placement must be an object")

    gate = placement.get("gate")
    if gate not in _VALID_GATES:
        raise ValueError(f"moment {moment_index}: unsupported gate {gate!r}")

    qubits = placement.get("qubits")
    if not isinstance(qubits, list) or not qubits:
        raise ValueError(f"moment {moment_index}: {gate} placement has malformed qubits")
    for qubit in qubits:
        if not (
            isinstance(qubit, list)
            and len(qubit) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in qubit)
        ):
            raise ValueError(
                f"moment {moment_index}: {gate} placement has a malformed qubit {qubit!r}"
            )

    expected_count = _EXPECTED_QUBIT_COUNT.get(gate)
    if expected_count is not None and len(qubits) != expected_count:
        raise ValueError(
            f"moment {moment_index}: {gate} requires exactly {expected_count} "
            f"qubit(s), got {len(qubits)}"
        )

    if gate in _PARAMETERIZED_GATES:
        angle = placement.get("angle_radians")
        if not isinstance(angle, (int, float)) or isinstance(angle, bool):
            raise ValueError(
                f"moment {moment_index}: {gate} requires a numeric angle_radians"
            )

    if gate == "MEASURE":
        key = placement.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError(
                f"moment {moment_index}: MEASURE requires a non-empty string key"
            )
