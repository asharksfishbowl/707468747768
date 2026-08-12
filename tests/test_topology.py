import cirq
import pytest

from app.topology import MAX_TOPOLOGY_QUBITS, build_topology
from cirq_sandbox.engine import list_virtual_processors
from conftest import real_device


class _FakeDevice(cirq.Device):
    """Minimal `cirq.Device` stub — `build_topology` only reads `.metadata`."""

    def __init__(self, metadata: cirq.GridDeviceMetadata):
        self._metadata = metadata

    @property
    def metadata(self) -> cirq.GridDeviceMetadata:
        return self._metadata


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_topology_capped_at_12_qubits_with_valid_edges(processor_id):
    topology = build_topology(real_device(processor_id))

    assert len(topology.qubits) <= MAX_TOPOLOGY_QUBITS
    qubit_set = {tuple(q) for q in topology.qubits}
    for pair in topology.pairs:
        assert len(pair) == 2
        for qubit in pair:
            assert tuple(qubit) in qubit_set


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_topology_anchor_is_lowest_row_col_qubit(processor_id):
    device = real_device(processor_id)
    topology = build_topology(device)

    expected_anchor = min(device.metadata.qubit_set)
    assert topology.qubits[0] == [expected_anchor.row, expected_anchor.col]


def test_topology_includes_all_qubits_when_device_has_fewer_than_max(): # Edge Case 13
    q0, q1, q2 = cirq.GridQubit(0, 0), cirq.GridQubit(0, 1), cirq.GridQubit(1, 0)
    gateset = cirq.Gateset(cirq.X, cirq.CNOT)
    metadata = cirq.GridDeviceMetadata(qubit_pairs=[(q0, q1), (q0, q2)], gateset=gateset)
    device = _FakeDevice(metadata)

    topology = build_topology(device)

    assert len(topology.qubits) == 3
    assert sorted(topology.qubits) == [[0, 0], [0, 1], [1, 0]]
    assert len(topology.pairs) == 2


def test_topology_stops_exactly_at_max_qubits_on_a_larger_connected_graph():
    # A 4x4 fully-connected grid (16 qubits) with more than MAX_TOPOLOGY_QUBITS.
    qubits = [cirq.GridQubit(r, c) for r in range(4) for c in range(4)]
    pairs = []
    for r in range(4):
        for c in range(4):
            if c + 1 < 4:
                pairs.append((cirq.GridQubit(r, c), cirq.GridQubit(r, c + 1)))
            if r + 1 < 4:
                pairs.append((cirq.GridQubit(r, c), cirq.GridQubit(r + 1, c)))
    gateset = cirq.Gateset(cirq.X, cirq.CNOT)
    metadata = cirq.GridDeviceMetadata(qubit_pairs=pairs, gateset=gateset, all_qubits=qubits)
    device = _FakeDevice(metadata)

    topology = build_topology(device)

    assert len(topology.qubits) == MAX_TOPOLOGY_QUBITS
    assert topology.qubits[0] == [0, 0]
