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

## Quick start (Docker)

The fastest way to run the whole Cirq Sandbox Studio stack (Postgres, Redis,
API, worker, Expo web client) locally:

```bash
cp .env.example .env   # fill in GOOGLE_OAUTH_*/JWT_SECRET_KEY, see below
make up                # docker compose up -d postgres redis api worker client-web
make migrate           # applies the users/circuits/runs schema
make seed               # optional: dev user + sample circuits/runs, safe to re-run
make test               # pytest (local .venv, no Docker) + client tsc --noEmit
make logs                # follow all services' logs
make down                # stop everything (keeps the postgres volume)
```

`make up` refuses to start if `.env` doesn't exist yet — copy `.env.example`
first. Migrations are never applied automatically by any service; `make
migrate` is the only way schema changes land, run it explicitly after the
stack is healthy. See `Makefile` and `docker-compose.yml` for the individual
commands each target wraps, and
[`specs/cirq-studio-tooling/cirq-studio-tooling.md`](specs/cirq-studio-tooling/cirq-studio-tooling.md)
for the full spec.

To verify the production Expo web build (not part of the default `make up`
profile): `docker compose --profile prod up client-web-prod` — serves the
static export on :8082, independent of the dev server on :8081.

The manual, non-Docker setup below remains valid and is what `make test`
itself uses for the backend (`pytest` runs against the local `.venv`, not
inside a container).

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

### `cirq-studio` operations CLI

A separately-installed terminal client for the running API — submit and
watch circuit runs without opening the web/mobile client. Installed
alongside the rest of this package (`pip install -e ".[dev]"` above also
gives you the `cirq-studio` command via `[project.scripts]`).

```bash
cirq-studio auth login                 # Google device-code flow (no browser redirect back to a local port)
cirq-studio auth whoami
cirq-studio runs create --file circuit.json --processor weber --noisy --repetitions 500
cirq-studio runs watch <run_id>        # live status + streaming histogram, plain text
cirq-studio runs list
cirq-studio auth logout
```

`cirq-studio` targets `CIRQ_STUDIO_API_URL` (default `http://localhost:8000`)
and stores its session at `~/.config/cirq-studio/credentials.json` (mode
`0600`). Every `runs` subcommand triggers the device-code flow automatically
if no valid session is stored; `auth whoami` is read-only and never does.

Signing in requires a **second** Google Cloud OAuth client, of type "TV and
Limited Input devices" (distinct from the web-application client used by the
browser flow above) — set `GOOGLE_OAUTH_DEVICE_CLIENT_ID`/
`GOOGLE_OAUTH_DEVICE_CLIENT_SECRET` in `.env` (see `.env.example`). This is a
manual step in the Google Cloud Console, same as the web OAuth client.

## Tests

```bash
pytest              # backend — src/cirq_sandbox + services/api
cd apps/studio && npx tsc --noEmit   # client type-check
```

Or, via Docker: `make test` runs both (pytest against the local `.venv`, then
the client type-check), failing if either does — see Quick start above.
