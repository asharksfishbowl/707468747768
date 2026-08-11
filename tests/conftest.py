from functools import lru_cache

import cirq

from cirq_sandbox.engine import get_sandbox_engine


@lru_cache(maxsize=None)
def real_device(processor_id: str) -> cirq.Device:
    """Cached sandbox device lookup, shared across test modules.

    Building the noisy virtual machine is expensive (~0.3s — it builds a full noise
    model from calibration data), and topology/preset tests are parametrized per
    processor, so each processor's device is built once and reused instead of once
    per test case.
    """
    engine = get_sandbox_engine(processor_id=processor_id, noisy=True)
    return engine.get_processor(processor_id).get_device()
