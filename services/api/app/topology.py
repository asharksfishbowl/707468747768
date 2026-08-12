"""BFS subgraph selection over a device's qubit connectivity graph.

Spec: Requirements 9-10 ("Processors and topology"). Unit-testable directly against
`list_virtual_processors()` devices from `src/cirq_sandbox/engine.py` — no HTTP layer
needed.
"""

from dataclasses import dataclass

import cirq
import networkx as nx

MAX_TOPOLOGY_QUBITS = 12


@dataclass(frozen=True)
class Topology:
    qubits: list[list[int]]
    pairs: list[list[list[int]]]


def build_topology(device: cirq.Device, max_qubits: int = MAX_TOPOLOGY_QUBITS) -> Topology:
    """Selects a fixed-size connected qubit subgraph from a device's connectivity graph.

    Anchor = the qubit with the lowest `(row, col)` tuple. BFS from the anchor,
    collecting qubits in BFS order until `max_qubits` are collected or the graph is
    exhausted (fewer than `max_qubits` if the device itself has fewer qubits total —
    spec Edge Case 13). Uses `device.metadata.nx_graph` — the connectivity graph the
    device already builds from `qubit_pairs` — rather than re-deriving adjacency by
    hand.
    """
    graph = device.metadata.nx_graph
    anchor = min(device.metadata.qubit_set)

    collected = [anchor]
    seen = {anchor}
    for _, neighbor in nx.bfs_edges(graph, anchor, sort_neighbors=sorted):
        if len(collected) >= max_qubits:
            break
        seen.add(neighbor)
        collected.append(neighbor)

    pairs = graph.subgraph(seen).edges()

    return Topology(
        qubits=[[q.row, q.col] for q in collected],
        pairs=[sorted([q.row, q.col] for q in pair) for pair in pairs],
    )
