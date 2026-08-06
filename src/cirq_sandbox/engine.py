import os

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


def get_cloud_engine(project_id: str | None = None) -> cirq_google.Engine:
    """Real cirq_google cloud Engine. Requires GCP QCS access."""
    project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError(
            "No GCP project id given and GOOGLE_CLOUD_PROJECT is unset. "
            "Pass project_id explicitly or set the GOOGLE_CLOUD_PROJECT env var."
        )
    return cirq_google.Engine(project_id=project_id)
