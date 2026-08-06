import argparse

import cirq

from cirq_sandbox.circuits import bell_state_circuit, select_qubit_pair
from cirq_sandbox.engine import (
    DEFAULT_PROCESSOR_ID,
    get_cloud_engine,
    get_sandbox_engine,
    list_virtual_processors,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Bell state circuit on a Cirq Google engine.")
    parser.add_argument(
        "--processor-id",
        default=DEFAULT_PROCESSOR_ID,
        choices=list_virtual_processors(),
    )
    parser.add_argument("--repetitions", type=int, default=1000)
    parser.add_argument("--noiseless", action="store_true")
    parser.add_argument("--cloud", action="store_true", help="Use the real cloud Engine instead of the sandbox.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.cloud:
        engine = get_cloud_engine()
    else:
        engine = get_sandbox_engine(processor_id=args.processor_id, noisy=not args.noiseless)

    device = engine.get_processor(args.processor_id).get_device()
    q0, q1 = select_qubit_pair(device)

    circuit = bell_state_circuit(q0, q1)
    compiled = cirq.optimize_for_target_gateset(
        circuit, gateset=device.metadata.compilation_target_gatesets[0]
    )
    sampler = engine.get_sampler(args.processor_id)
    result = sampler.run(compiled, repetitions=args.repetitions)

    print(result.histogram(key="result"))


if __name__ == "__main__":
    main()
