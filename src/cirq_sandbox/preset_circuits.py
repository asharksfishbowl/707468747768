"""Preset circuit generators (spec Requirement 15).

Each preset takes a `topology` (the shape produced by
`services/api/app/topology.py`'s `Topology` — `qubits`/`pairs` attributes; duck-typed
here rather than imported, since `src/` is the lower-level package and `services/api`
is its consumer, not the reverse) and returns a circuit JSON definition (Requirement
11's shape) built from qubits in that topology.
"""

from typing import Protocol


class TopologyLike(Protocol):
    qubits: list[list[int]]
    pairs: list[list[list[int]]]


def hello_qubit_preset(topology: TopologyLike, processor_id: str) -> dict:
    """SQRT_X + measure on a single qubit — Cirq's own canonical "Hello Qubit" first
    example (https://quantumai.google/cirq/start/start), adapted to this app's JSON
    shape. The simplest possible preset: one qubit, no connectivity requirement.
    """
    q0 = topology.qubits[0]
    return {
        "processor_id": processor_id,
        "moments": [
            [{"gate": "SQRT_X", "qubits": [q0]}],
            [{"gate": "MEASURE", "qubits": [q0], "key": "result"}],
        ],
    }


def bell_state_preset(topology: TopologyLike, processor_id: str) -> dict:
    """H + CNOT + measure on the first connected pair.

    Same H+CNOT+measure("result") structure as `cirq_sandbox.circuits.bell_state_circuit`,
    emitted as a JSON definition instead of a `cirq.Circuit` — not a direct call, since
    that function builds a `cirq.Circuit` and this returns JSON; there's no existing
    circuit-to-JSON serializer in the codebase to bridge the two return types.
    """
    q0, q1 = topology.pairs[0]
    return {
        "processor_id": processor_id,
        "moments": [
            [{"gate": "H", "qubits": [q0]}],
            [{"gate": "CNOT", "qubits": [q0, q1]}],
            [{"gate": "MEASURE", "qubits": [q0, q1], "key": "result"}],
        ],
    }


def ghz_state_preset(topology: TopologyLike, processor_id: str) -> dict:
    """H on the anchor qubit, then a CNOT chain outward along `topology.pairs`
    covering `min(4, len(topology.qubits))` total qubits, then measure all of them.
    """
    target_count = min(4, len(topology.qubits))
    chain = _walk_chain(topology, target_count)

    moments = [[{"gate": "H", "qubits": [chain[0]]}]]
    for a, b in zip(chain, chain[1:]):
        moments.append([{"gate": "CNOT", "qubits": [a, b]}])
    moments.append([{"gate": "MEASURE", "qubits": chain, "key": "result"}])

    return {"processor_id": processor_id, "moments": moments}


def superposition_preset(topology: TopologyLike, processor_id: str) -> dict:
    """H on every qubit in the topology, then measure all."""
    qubits = topology.qubits
    return {
        "processor_id": processor_id,
        "moments": [
            [{"gate": "H", "qubits": [q]} for q in qubits],
            [{"gate": "MEASURE", "qubits": qubits, "key": "result"}],
        ],
    }


def _walk_chain(topology: TopologyLike, target_count: int) -> list[list[int]]:
    """Greedy connectivity-respecting walk from `topology.qubits[0]`, collecting
    `target_count` qubits where each consecutive pair is a real edge in
    `topology.pairs` (required so the resulting CNOT chain only uses gate placements
    the processor's connectivity actually supports).

    Plain greedy, no backtracking: `topology` is always a `build_topology()` output —
    a dense, BFS-connected subgraph of a real device capped at 12 qubits — and
    `target_count` is at most 4, so a greedy walk never dead-ends on any of the
    sandbox's processors. Backtracking search is more machinery than that input shape
    needs; add it back if a future topology genuinely requires it.
    """
    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {
        tuple(q): [] for q in topology.qubits
    }
    for a, b in topology.pairs:
        ta, tb = tuple(a), tuple(b)
        adjacency[ta].append(tb)
        adjacency[tb].append(ta)

    anchor = tuple(topology.qubits[0])
    chain = [anchor]
    visited = {anchor}
    current = anchor
    while len(chain) < target_count:
        neighbor = next(
            (n for n in sorted(adjacency[current]) if n not in visited), None
        )
        if neighbor is None:
            break
        chain.append(neighbor)
        visited.add(neighbor)
        current = neighbor

    return [list(q) for q in chain]
