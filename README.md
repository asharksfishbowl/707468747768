# cirq-sandbox

Builds and runs quantum circuits against Google Cirq's Quantum Virtual Machine
(QVM) — a local, credential-free stand-in for the real Quantum Computing
Service (QCS) — with an opt-in path to the real `cirq_google.Engine` cloud
service once you have GCP/QCS access.

This repo has two things in it:

1. **`cirq_sandbox`** (`src/`) — the original Python CLI, a minimal script that
   runs a hardcoded Bell-state circuit against the sandbox.
2. **Cirq Sandbox Studio** (`services/api/` + `apps/studio/`) — a public,
   multi-user web/iOS/Android product built on top of the same sandbox
   engine: sign in, build circuits visually against a real device's qubit
   topology, run them, and watch results stream in live. Full spec:
   [`specs/cirq-sandbox-studio/cirq-sandbox-studio.md`](specs/cirq-sandbox-studio/cirq-sandbox-studio.md)
   (implementation) and
   [`specs/cirq-sandbox-studio/design-cirq-sandbox-studio.md`](specs/cirq-sandbox-studio/design-cirq-sandbox-studio.md)
   (visual/interaction design).

## `cirq_sandbox` CLI

### Run modes

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

### Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Usage

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

### Backend (`services/api/`)

FastAPI service exposing the sandbox engine over HTTP + WebSocket: Google
OAuth/JWT auth, `GET /processors` (device topology + native gateset), circuit
CRUD + public gallery + clone, `POST /runs` (validated, queued to Redis,
chunked execution against the sandbox, live progress via
`WS /runs/{id}/stream`).

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in the variables below

alembic -c services/api/alembic.ini upgrade head   # apply the users/circuits/runs schema
uvicorn app.main:app --app-dir services/api --reload   # API on :8000
python -m app.worker --app-dir services/api            # run queue worker (separate process)
```

Requires a running Postgres and Redis. Environment variables (see
`.env.example`):

- `DATABASE_URL` — Postgres connection string. Falls back to a local dev
  default (see `services/api/app/db.py`) if unset.
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
  `GOOGLE_OAUTH_REDIRECT_URI` — Google OAuth client config for
  `services/api/app/auth.py`'s login/callback routes.
- `JWT_SECRET_KEY` — signs the 24h access tokens `auth.py` issues.
- `CLIENT_BASE_URL` — the client app's base URL; the OAuth callback redirects
  here on success/failure.
- `REDIS_URL` — run queue backing store (`services/api/app/redis_client.py`,
  `worker.py`). Tests use `fakeredis` instead, so `pytest` doesn't need a
  real Redis server.
- `MAX_CONCURRENT_JOBS`, `JOB_TIMEOUT_SECONDS` — abuse-limit knobs for the
  run worker (defaults: 4, 120).

### Client (`apps/studio/`)

Expo (React Native Web) app — one codebase for web, iOS, and Android. Screens:
Login, Builder (qubit-grid circuit builder + run panel with live-streaming
results), My Circuits, Run History, Gallery.

```bash
cd apps/studio
npm install
npm run web      # or: npm run ios / npm run android
```

Point it at a running backend via `apps/studio/src/config.ts` (defaults to
`http://localhost:8000`).

## Tests

```bash
pytest              # backend — src/cirq_sandbox + services/api
cd apps/studio && npx tsc --noEmit   # client type-check
```
