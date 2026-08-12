# cirq-sandbox

Builds and runs quantum circuits against Google Cirq's Quantum Virtual Machine
(QVM) — a local, credential-free stand-in for the real Quantum Computing
Service (QCS) — with an opt-in path to the real `cirq_google.Engine` cloud
service once you have GCP/QCS access.

This repo has two parts:

- **The CLI** (`src/cirq_sandbox/`) — a standalone script that runs a single
  hardcoded circuit against the sandbox or the real cloud engine. See
  [CLI](#cli) below.
- **Cirq Sandbox Studio** (`services/api/`) — a multi-user web/mobile product
  being built on top of the same sandbox engine: sign in with Google, build
  circuits visually, run them, save and share them. See
  [Cirq Sandbox Studio](#cirq-sandbox-studio) below. Full spec:
  [`specs/cirq-sandbox-studio/cirq-sandbox-studio.md`](specs/cirq-sandbox-studio/cirq-sandbox-studio.md).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests

```bash
pytest
```

## CLI

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

Copy `.env.example` to `.env` and fill in the relevant variables (see below).

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

## Cirq Sandbox Studio

A new HTTP/WebSocket API (`services/api/`) in front of the sandbox engine,
plus an Expo client (`apps/studio/`, not yet built) providing a visual
drag-and-drop circuit builder, live run results, and per-user saved circuits
with optional public sharing. Full spec, requirements, edge cases, and
acceptance criteria: `specs/cirq-sandbox-studio/cirq-sandbox-studio.md`.

### Build status

| Piece | Status |
|---|---|
| Data model (`users`/`circuits`/`runs`, Alembic migration) | ✅ Built |
| Qubit topology selection (BFS subgraph, ≤12 qubits) | ✅ Built |
| Circuit builder (JSON definition → `cirq.Circuit`, 14 gate types incl. `SQRT_X`) | ✅ Built |
| Presets (Hello Qubit, Bell state, GHZ state, Superposition) | ✅ Built |
| Google OAuth + JWT auth, WS token auth | ✅ Built |
| REST API (`GET /processors`, circuits CRUD, gallery, clone) | ✅ Built |
| Runs (queueing, Redis worker, chunked execution, `WS /runs/{id}/stream`) | Not yet built |
| Expo client (`apps/studio/`) | Not yet built |

The pieces marked "Built" are implemented under `services/api/app/` with a
full test suite (`pytest` covers all of them — see Tests above). The FastAPI
app (`services/api/app/main.py`) is wired up and runnable
(`uvicorn app.main:app`) but only serves the auth, processors, and circuits
routes so far — runs and the WebSocket stream are Phase 4.

### Environment variables

Copy `.env.example` to `.env` and fill in what you need:

- `DATABASE_URL` — Postgres connection string for `services/api`. Falls back
  to a local dev default (see `services/api/app/db.py`) if unset.
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
  `GOOGLE_OAUTH_REDIRECT_URI` — Google OAuth client config for
  `services/api/app/auth.py`'s login/callback routes.
- `JWT_SECRET_KEY` — signs the 24h access tokens `auth.py` issues.
- `CLIENT_BASE_URL` — the client app's base URL; the OAuth callback redirects
  here on success/failure.

### Database migrations

```bash
cd services/api
alembic upgrade head
```

`services/api/alembic/env.py` reads `DATABASE_URL` from the environment
(falling back to `alembic.ini`'s own default) — see `.env.example`.
