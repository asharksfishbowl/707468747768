import cirq


def bell_state_circuit(q0: cirq.Qid, q1: cirq.Qid) -> cirq.Circuit:
    return cirq.Circuit(
        cirq.H(q0),
        cirq.CNOT(q0, q1),
        cirq.measure(q0, q1, key="result"),
    )


def select_qubit_pair(device: cirq.Device) -> tuple[cirq.Qid, cirq.Qid]:
    """Pick a connectivity-valid 2-qubit pair from the device's metadata."""
    q0, q1 = next(iter(device.metadata.qubit_pairs))
    return q0, q1
