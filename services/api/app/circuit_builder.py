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
