import math

import cirq
import pytest

from app.circuit_builder import build_circuit


def _q(row, col):
    return cirq.GridQubit(row, col)


@pytest.mark.parametrize(
    "gate_name,expected",
    [
        ("H", cirq.H(_q(0, 0))),
        ("X", cirq.X(_q(0, 0))),
        ("Y", cirq.Y(_q(0, 0))),
        ("Z", cirq.Z(_q(0, 0))),
        ("S", cirq.S(_q(0, 0))),
        ("T", cirq.T(_q(0, 0))),
        ("SQRT_X", (cirq.X**0.5)(_q(0, 0))),
    ],
)
def test_single_qubit_gates(gate_name, expected):
    definition = {"moments": [[{"gate": gate_name, "qubits": [[0, 0]]}]]}
    circuit = build_circuit(definition)
    cirq.testing.assert_same_circuits(circuit, cirq.Circuit(expected))


@pytest.mark.parametrize(
    "gate_name,expected",
    [
        ("CNOT", cirq.CNOT(_q(0, 0), _q(0, 1))),
        ("CZ", cirq.CZ(_q(0, 0), _q(0, 1))),
        ("SWAP", cirq.SWAP(_q(0, 0), _q(0, 1))),
    ],
)
def test_two_qubit_gates(gate_name, expected):
    definition = {"moments": [[{"gate": gate_name, "qubits": [[0, 0], [0, 1]]}]]}
    circuit = build_circuit(definition)
    cirq.testing.assert_same_circuits(circuit, cirq.Circuit(expected))


@pytest.mark.parametrize(
    "gate_name,cirq_factory",
    [("RX", cirq.rx), ("RY", cirq.ry), ("RZ", cirq.rz)],
)
def test_parameterized_gates(gate_name, cirq_factory):
    angle = math.pi / 3
    definition = {
        "moments": [[{"gate": gate_name, "qubits": [[0, 0]], "angle_radians": angle}]]
    }
    circuit = build_circuit(definition)
    expected = cirq.Circuit(cirq_factory(angle).on(_q(0, 0)))
    cirq.testing.assert_same_circuits(circuit, expected)


def test_measure_gate_with_key():
    definition = {
        "moments": [[{"gate": "MEASURE", "qubits": [[0, 0], [0, 1]], "key": "result"}]]
    }
    circuit = build_circuit(definition)
    expected = cirq.Circuit(cirq.measure(_q(0, 0), _q(0, 1), key="result"))
    cirq.testing.assert_same_circuits(circuit, expected)


def test_multi_moment_circuit_preserves_moment_boundaries():
    definition = {
        "moments": [
            [{"gate": "H", "qubits": [[0, 0]]}],
            [{"gate": "CNOT", "qubits": [[0, 0], [0, 1]]}],
            [{"gate": "MEASURE", "qubits": [[0, 0], [0, 1]], "key": "result"}],
        ]
    }
    circuit = build_circuit(definition)
    expected = cirq.Circuit(
        cirq.H(_q(0, 0)),
        cirq.CNOT(_q(0, 0), _q(0, 1)),
        cirq.measure(_q(0, 0), _q(0, 1), key="result"),
    )
    cirq.testing.assert_same_circuits(circuit, expected)


def test_unsupported_gate_raises():
    definition = {"moments": [[{"gate": "TOFFOLI", "qubits": [[0, 0]]}]]}
    with pytest.raises(ValueError, match="Unsupported gate"):
        build_circuit(definition)
