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
def _cached_engine(processor_id: str, noisy: bool):
    """Building the noisy virtual machine is expensive (~0.3s — it builds a full
    noise model from calibration data); it's the same engine object regardless of
    whether the caller wants the device, the sampler, or both, so `get_device` and
    `get_sampler` both route through this one cache instead of each independently
    calling `get_sandbox_engine` (which would build the noise model twice per job).
    """
    return get_sandbox_engine(processor_id=processor_id, noisy=noisy)


def get_device(processor_id: str = DEFAULT_PROCESSOR_ID, noisy: bool = True) -> cirq.Device:
    """Cached `processor_id` -> device lookup — see `_cached_engine`."""
    return _cached_engine(processor_id, noisy).get_processor(processor_id).get_device()


def get_sampler(processor_id: str = DEFAULT_PROCESSOR_ID, noisy: bool = True):
    """Cached `processor_id` -> sampler lookup — see `_cached_engine`."""
    return _cached_engine(processor_id, noisy).get_sampler(processor_id)


def compile_to_device(circuit: cirq.Circuit, device: cirq.Device) -> cirq.Circuit:
    """Compiles `circuit` to `device`'s native gateset. The same call already
    verified working in `src/cirq_sandbox/main.py` (single source of truth for this
    one line, reused by `services/api/app/worker.py` instead of re-typing it).
    """
    return cirq.optimize_for_target_gateset(
        circuit, gateset=device.metadata.compilation_target_gatesets[0]
    )


def get_cloud_engine(project_id: str | None = None) -> cirq_google.Engine:
    """Real cirq_google cloud Engine. Requires GCP QCS access."""
    project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError(
            "No GCP project id given and GOOGLE_CLOUD_PROJECT is unset. "
            "Pass project_id explicitly or set the GOOGLE_CLOUD_PROJECT env var."
        )
    return cirq_google.Engine(project_id=project_id)
