"""JSON circuit definition (spec Requirement 11) -> `cirq.Circuit` (Requirement 14).

Assumes a well-formed definition. Schema/semantic validation (Requirement 25) belongs
to the `POST`/`PUT /circuits` and `POST /runs` routes (Phases 3-4), not this module —
this module only converts.

Note: the spec text describes the qubit type as "cirq_google.GridQubit", but
`cirq_google` has no such attribute — the real device qubits returned by
`src/cirq_sandbox/engine.py` (`device.metadata.qubit_set`) are `cirq.GridQubit`
instances, so that's what's used here to match what the sandbox engine actually
produces.
"""

from typing import Any

import cirq

_SINGLE_QUBIT_GATES: dict[str, cirq.Gate] = {
    "H": cirq.H,
    "X": cirq.X,
    "Y": cirq.Y,
    "Z": cirq.Z,
    "S": cirq.S,
    "T": cirq.T,
    "SQRT_X": cirq.X**0.5,
}

_TWO_QUBIT_GATES: dict[str, cirq.Gate] = {
    "CNOT": cirq.CNOT,
    "CZ": cirq.CZ,
    "SWAP": cirq.SWAP,
}

_PARAMETERIZED_GATES = {
    "RX": cirq.rx,
    "RY": cirq.ry,
    "RZ": cirq.rz,
}


def build_circuit(definition: dict[str, Any]) -> cirq.Circuit:
    """Converts a Requirement-11-shaped circuit JSON definition into a `cirq.Circuit`."""
    moments = [
        cirq.Moment(_build_operation(placement) for placement in moment)
        for moment in definition["moments"]
    ]
    return cirq.Circuit(moments)


def _build_operation(placement: dict[str, Any]) -> cirq.Operation:
    gate_name = placement["gate"]
    qubits = [_qubit(q) for q in placement["qubits"]]

    if gate_name == "MEASURE":
        return cirq.measure(*qubits, key=placement["key"])
    if gate_name in _SINGLE_QUBIT_GATES:
        return _SINGLE_QUBIT_GATES[gate_name].on(*qubits)
    if gate_name in _TWO_QUBIT_GATES:
        return _TWO_QUBIT_GATES[gate_name].on(*qubits)
    if gate_name in _PARAMETERIZED_GATES:
        return _PARAMETERIZED_GATES[gate_name](placement["angle_radians"]).on(*qubits)
    raise ValueError(f"Unsupported gate: {gate_name!r}")


def _qubit(row_col: list[int]) -> cirq.GridQubit:
    row, col = row_col
    return cirq.GridQubit(row, col)


def native_gate_names(gateset: cirq.Gateset) -> list[str]:
    """Returns which of this module's supported gate names (Requirement 12) `gateset`
    accepts natively, for `GET /processors`'s `native_gates` field (Requirement 8,
    Phase 3). Reuses the same gate-name -> `cirq.Gate` maps `build_circuit` uses, so
    the two never drift apart. Gateset membership is checked per-operation (not per
    bare gate), so placeholder qubits are used — their identity doesn't affect
    gate-type membership. RX/RY/RZ are probed at one arbitrary angle (0.3), assuming
    gateset membership for them is angle-independent (a type-based GateFamily match,
    not an instance-based one) — true for all 3 sandbox processors today; would need
    revisiting if a future gateset restricts these to specific angles.
    """
    q0, q1 = cirq.GridQubit(0, 0), cirq.GridQubit(0, 1)
    sample_ops = {
        **{name: gate.on(q0) for name, gate in _SINGLE_QUBIT_GATES.items()},
        **{name: gate.on(q0, q1) for name, gate in _TWO_QUBIT_GATES.items()},
        **{
            name: factory(0.3).on(q0) for name, factory in _PARAMETERIZED_GATES.items()
        },
        "MEASURE": cirq.measure(q0, key="native_gates_probe"),
    }
    return [name for name, op in sample_ops.items() if op in gateset]
