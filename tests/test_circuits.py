import cirq

from cirq_sandbox.circuits import bell_state_circuit


def test_bell_state_circuit_structure():
    q0, q1 = cirq.LineQubit.range(2)
    circuit = bell_state_circuit(q0, q1)

    expected = cirq.Circuit(
        cirq.H(q0),
        cirq.CNOT(q0, q1),
        cirq.measure(q0, q1, key="result"),
    )
    cirq.testing.assert_same_circuits(circuit, expected)
