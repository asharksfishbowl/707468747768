# cirq-sandbox

Builds and runs quantum circuits against Google Cirq's Quantum Virtual Machine
(QVM) — a local, credential-free stand-in for the real Quantum Computing
Service (QCS) — with an opt-in path to the real `cirq_google.Engine` cloud
service once you have GCP/QCS access.

## Run modes

**Sandbox (default)** — runs entirely locally via `cirq_google`'s virtual
engine factory. No credentials, no GCP project, no network access required.
Supports a noisy mode (calibration-based noise for a given processor) and a
noiseless mode.

**Cloud (opt-in, `--cloud` flag)** — runs against the real Quantum Engine
service via `cirq_google.Engine`. Requires:

1. A GCP project with the Quantum Engine API enabled and QCS access granted
   (request access and enable the API in the GCP console — this is a manual
   step, not something this scaffold can do for you).
2. Authentication via `gcloud auth application-default login`, or a
   service-account key referenced by `GOOGLE_APPLICATION_CREDENTIALS`.
3. `GOOGLE_CLOUD_PROJECT` set to your project id (or pass it explicitly to
   `get_cloud_engine(project_id=...)`).

Copy `.env.example` to `.env` and fill in the two variables to configure the
cloud path.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# Sandbox, noisy (default), Bell state circuit on the "weber" processor
python -m cirq_sandbox.main

# Sandbox, noiseless
python -m cirq_sandbox.main --noiseless

# Choose a different virtual processor
python -m cirq_sandbox.main --processor-id rainbow

# Real cloud engine (requires GCP/QCS access, see above)
python -m cirq_sandbox.main --cloud
```

## Tests

```bash
pytest
```

## Note on how this was built

This project was scaffolded in a container with no Python interpreter, pip,
or package manager access available, so the code has **not** been executed
or tested in-container — only written against verified Cirq API signatures.
Before relying on it, run the Setup and Tests steps above locally to verify.
