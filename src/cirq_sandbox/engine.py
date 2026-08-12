import os
from functools import lru_cache

import cirq
import cirq_google
from cirq_google.engine import virtual_engine_factory

DEFAULT_PROCESSOR_ID = "weber"

list_virtual_processors = virtual_engine_factory.list_virtual_processors


def get_sandbox_engine(processor_id: str = DEFAULT_PROCESSOR_ID, noisy: bool = True):
    """Local, credential-free Quantum Virtual Machine sandbox engine."""
    if noisy:
        return virtual_engine_factory.create_default_noisy_quantum_virtual_machine(
            processor_id=processor_id
        )
    return virtual_engine_factory.create_noiseless_virtual_engine_from_latest_templates()


@lru_cache(maxsize=None)
def get_device(processor_id: str = DEFAULT_PROCESSOR_ID, noisy: bool = True) -> cirq.Device:
    """Cached `processor_id` -> device lookup. Building the noisy virtual machine is
    expensive (~0.3s — it builds a full noise model from calibration data); the
    device for a given `(processor_id, noisy)` pair never changes at runtime, so this
    is safe to cache indefinitely rather than rebuilding it on every call (e.g. every
    `GET /processors` request in services/api/app/routes/processors.py).
    """
    engine = get_sandbox_engine(processor_id=processor_id, noisy=noisy)
    return engine.get_processor(processor_id).get_device()


def get_cloud_engine(project_id: str | None = None) -> cirq_google.Engine:
    """Real cirq_google cloud Engine. Requires GCP QCS access."""
    project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError(
            "No GCP project id given and GOOGLE_CLOUD_PROJECT is unset. "
            "Pass project_id explicitly or set the GOOGLE_CLOUD_PROJECT env var."
        )
    return cirq_google.Engine(project_id=project_id)
