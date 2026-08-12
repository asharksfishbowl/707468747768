"""GET /processors (Requirements 8-10)."""

from fastapi import APIRouter, Depends

from app.auth import require_auth
from app.circuit_builder import native_gate_names
from app.models import User
from app.topology import build_topology
from cirq_sandbox.engine import get_device, list_virtual_processors

router = APIRouter()


@router.get("/processors")
def list_processors(user: User = Depends(require_auth)) -> list[dict]:
    """Requirement 8: id, native_gates, and topology for every sandbox processor."""
    results = []
    for processor_id in list_virtual_processors():
        device = get_device(processor_id)
        topology = build_topology(device)
        gateset = device.metadata.compilation_target_gatesets[0]
        results.append(
            {
                "id": processor_id,
                "native_gates": native_gate_names(gateset),
                "topology": {"qubits": topology.qubits, "pairs": topology.pairs},
            }
        )
    return results
