import pytest

from app.circuit_builder import build_circuit
from app.topology import build_topology
from cirq_sandbox.engine import list_virtual_processors
from cirq_sandbox.preset_circuits import (
    bell_state_preset,
    ghz_state_preset,
    superposition_preset,
)
from conftest import real_device

_VALID_GATES = {
    "H",
    "X",
    "Y",
    "Z",
    "S",
    "T",
    "CNOT",
    "CZ",
    "SWAP",
    "RX",
    "RY",
    "RZ",
    "MEASURE",
}


def _topology(processor_id):
    return build_topology(real_device(processor_id))


def _assert_schema_valid(definition, processor_id):
    assert definition["processor_id"] == processor_id
    for moment in definition["moments"]:
        for placement in moment:
            assert placement["gate"] in _VALID_GATES
            for qubit in placement["qubits"]:
                assert len(qubit) == 2


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_bell_state_preset_is_schema_valid_and_buildable(processor_id):
    topology = _topology(processor_id)
    definition = bell_state_preset(topology, processor_id)

    _assert_schema_valid(definition, processor_id)
    build_circuit(definition)  # doesn't raise

    gates = [p["gate"] for moment in definition["moments"] for p in moment]
    assert gates == ["H", "CNOT", "MEASURE"]


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_ghz_state_preset_covers_min_4_qubits_and_respects_connectivity(processor_id):
    topology = _topology(processor_id)
    definition = ghz_state_preset(topology, processor_id)

    _assert_schema_valid(definition, processor_id)
    build_circuit(definition)  # doesn't raise

    expected_count = min(4, len(topology.qubits))
    measure_moment = definition["moments"][-1][0]
    assert measure_moment["gate"] == "MEASURE"
    assert len(measure_moment["qubits"]) == expected_count

    # Every CNOT's pair must be a real edge in the topology (Requirement 13).
    topology_pairs = {frozenset(map(tuple, pair)) for pair in topology.pairs}
    cnot_moments = [m for m in definition["moments"] if m[0]["gate"] == "CNOT"]
    assert len(cnot_moments) == expected_count - 1
    for moment in cnot_moments:
        pair = frozenset(map(tuple, moment[0]["qubits"]))
        assert pair in topology_pairs


def test_ghz_state_preset_caps_at_4_even_with_more_available_qubits():
    processor_id = list_virtual_processors()[0]
    topology = _topology(processor_id)
    assert len(topology.qubits) > 4  # all 3 sandbox processors have >=12

    definition = ghz_state_preset(topology, processor_id)
    measure_moment = definition["moments"][-1][0]
    assert len(measure_moment["qubits"]) == 4


@pytest.mark.parametrize("processor_id", list_virtual_processors())
def test_superposition_preset_covers_every_topology_qubit(processor_id):
    topology = _topology(processor_id)
    definition = superposition_preset(topology, processor_id)

    _assert_schema_valid(definition, processor_id)
    build_circuit(definition)  # doesn't raise

    h_moment = definition["moments"][0]
    assert len(h_moment) == len(topology.qubits)
    assert {tuple(p["qubits"][0]) for p in h_moment} == {tuple(q) for q in topology.qubits}

    measure_moment = definition["moments"][-1][0]
    assert len(measure_moment["qubits"]) == len(topology.qubits)
