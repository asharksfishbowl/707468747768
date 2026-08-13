# Spec: Cirq Studio Tooling (dev CLI, docker-compose, operations CLI)

## Overview

Adds developer/operator tooling on top of the already-shipped Cirq Sandbox
Studio (`services/api/`, `apps/studio/`): a `Makefile` that wraps the
multi-step manual setup from the README into single commands, a
`docker-compose.yml` stack running the full system (Postgres, Redis, API,
worker, and the Expo web client), and a separately-installed `cirq-studio`
Python CLI that acts as a terminal client for the running API (submit and
watch circuit runs from the command line, authenticating via a Google
device-code flow).

## Goals

- `docker compose up` brings up a fully working local stack: Postgres,
  Redis, the API, the worker, and the Expo web client.
- `make migrate` / `make seed` / `make test` / `make logs` / `make down`
  cover the rest of the dev lifecycle without hand-typing alembic/npm/pytest
  invocations across two runtimes.
- `cirq-studio` lets a user submit a circuit run and watch it complete
  (live status + streaming histogram) entirely from a terminal, without
  opening the web/mobile client, authenticating via Google without a
  browser redirect back to a local port.

## Non-Goals

- `processors`/`circuits` subcommand groups on `cirq-studio` — v1 ships
  `runs` (create/get/watch/list) and a minimal `auth` group (login/logout/
  whoami, Requirements 22-24) for managing the CLI session explicitly.
- Containerizing iOS/Android — the Expo compose service only serves the web
  target; mobile development continues via `npm run ios` / `npm run android`
  on the host, unaffected by compose.
- A production/deployment topology (this is dev/local tooling — no
  orchestration beyond `docker-compose.yml`, no CI pipeline changes).
- Automatic migrations on container startup — `migrate` stays an explicit
  step (see Requirement 8).
- Any change to `apps/studio/` (the existing mobile/web client) or to the
  existing web OAuth redirect flow (Requirements 1-2 of
  `specs/cirq-sandbox-studio/cirq-sandbox-studio.md`) — those are unchanged;
  this spec only *adds* a second, CLI-specific auth path.

## Requirements

### Docker Compose

1. `docker-compose.yml` at the repo root defines five services: `postgres`,
   `redis`, `api`, `worker`, `client-web`.
2. `postgres`: official `postgres:16` image, named volume for data
   persistence across `docker compose down`/`up` (not `down -v`), healthcheck
   via `pg_isready`, credentials/db name matching `.env.example`'s
   `DATABASE_URL` default (`cirq_sandbox`/`cirq_sandbox`/`cirq_sandbox`).
3. `redis`: official `redis:7` image, healthcheck via `redis-cli ping`. No
   persistence volume needed (the run queue is disposable — a lost queue on
   restart just means in-flight jobs are dropped, matching Edge Case 5's
   existing "jobs stay queued until a slot frees" semantics with no stronger
   durability promised).
4. `services/api/Dockerfile` (new): Python 3.11+ base image, installs the
   project (`pip install -e .`, reusing `pyproject.toml`'s dependency list).
   Used by both the `api` and `worker` compose services via the same image,
   different `command:`.
5. `api` service: built from `services/api/Dockerfile`, `command: uvicorn
   app.main:app --host 0.0.0.0 --port 8000 --app-dir services/api`,
   `depends_on` `postgres` and `redis` with `condition:
   service_healthy`, port 8000 published to the host, environment from
   `.env` (via `env_file:`).
6. `worker` service: same image as `api`, `command: python -m app.worker
   --app-dir services/api`, same `depends_on`/`env_file` as `api`, no
   published port.
7. `client-web` service: new `apps/studio/Dockerfile` running `npx expo
   start --web --port 8081` (the existing dev server, per
   `apps/studio/package.json`'s `web` script), port 8081 published to the
   host. A second Compose profile, `prod`, adds `client-web-prod`: same
   Dockerfile with a build stage that runs `npx expo export --platform web`
   and serves the static output via `npx serve dist -l 8082` — not started
   by a plain `docker compose up` (only via `docker compose --profile prod
   up client-web-prod`), since its purpose is verifying the production build
   works, not day-to-day dev.
8. Migrations are NOT run automatically by any service's entrypoint —
   `make migrate` (Requirement 11) is the only way schema changes get
   applied, run explicitly against the already-running `postgres` service.

### Makefile (dev task runner)

9. `Makefile` at the repo root, targets: `up`, `down`, `migrate`, `seed`,
   `test`, `logs`.
10. `make up`: fails fast with a message pointing to `.env.example` if
    `.env` doesn't exist (does NOT auto-create it — a silently-created
    `.env` with empty `GOOGLE_OAUTH_*`/`JWT_SECRET_KEY` would start
    something that looks running but can't actually authenticate anyone,
    which is worse than refusing to start). If `.env` exists, runs `docker
    compose up -d postgres redis api worker client-web` (default profile
    only — `client-web-prod` requires the explicit `--profile prod` compose
    invocation from Requirement 7, not wired to any Makefile target in v1).
11. `make migrate`: `docker compose exec api alembic -c
    services/api/alembic.ini upgrade head` — requires `api` to already be
    running (from `make up`); fails with the container-not-running error if
    not, no auto-start.
12. `make seed`: `docker compose exec api python -m app.seed` (new module,
    Requirement 16) — likewise requires `api` running.
13. `make test`: runs `pytest` (repo root, against the local `.venv`, NOT
    inside a container — matches the existing dev loop, doesn't require
    `docker compose up` first) followed by `cd apps/studio && npx tsc
    --noEmit`. Fails (non-zero exit) if either step fails; runs both even if
    the first fails, and reports both results, so a client type error isn't
    hidden by a backend test failure or vice versa.
14. `make logs`: `docker compose logs -f` (all services, follow mode).
15. `make down`: `docker compose down` (no `-v` — preserves the `postgres`
    volume from Requirement 2; a separate, undocumented `docker compose down
    -v` remains available directly for a full reset, but isn't a Makefile
    target since accidentally wiping local data via a short common command
    name is the kind of mistake this tooling should make harder, not easier).

### Seed data

16. New module `services/api/app/seed.py`: idempotent (safe to run more than
    once — checks for the dev user by a fixed, well-known `google_id` value
    `"cirq-studio-dev-seed-user"` before inserting, does nothing if it
    already exists rather than erroring or duplicating). Creates: one `users`
    row (`google_id="cirq-studio-dev-seed-user"`, `email="dev@localhost"`,
    `display_name="Dev User"` — inserted directly via the ORM, NOT through
    `services/api/app/auth.py`'s OAuth code path, since seed data has no
    real Google account behind it); three `circuits` rows owned by that
    user, one per non-Hello-Qubit preset (Bell state, GHZ state,
    Superposition — reusing `src/cirq_sandbox/preset_circuits.py`'s
    generators against the `weber` processor's topology), all
    `is_public=true` so the gallery isn't empty on a fresh environment; one
    `runs` row (`status="done"`) for the Bell state circuit with a
    plausible-looking result histogram, so Run History isn't empty either.
17. Seed data is local-dev-only by construction (the fixed `google_id` value
    from Requirement 16 could never collide with a real Google account,
    whose `google_id`s are Google-issued numeric strings) — no
    production/environment guard needed beyond that, since `make seed`
    itself is a manual, explicit dev action never wired into any automatic
    startup path (Requirement 8, Requirement 10).

### `cirq-studio` operations CLI

18. New package `services/api/app/cli/` (Python, reuses the same
    `services/api` install rather than a separate distribution), registered
    as an installed command via `pyproject.toml`'s `[project.scripts]`:
    `cirq-studio = "app.cli.main:app"`. Built with Typer (consistent
    rationale with the rest of the backend being Python-first).
19. Config: `cirq-studio` reads the target API's base URL from a
    `CIRQ_STUDIO_API_URL` environment variable, defaulting to
    `http://localhost:8000` (matching the `api` service's published port
    from Requirement 5) if unset.
20. Token storage: `~/.config/cirq-studio/credentials.json`, containing
    `{"token": "<jwt>", "expires_at": "<ISO-8601 timestamp, from the JWT's
    own exp claim>"}`. File permissions set to `0600` (owner read/write
    only) on creation, since it holds a bearer credential. The
    `~/.config/cirq-studio/` directory is created (including any missing
    parents) if it doesn't already exist.
21. **Auth trigger**: every `runs` subcommand (Requirements 25-28) first
    checks for a stored token (Requirement 20); if missing, or present but
    expired (`expires_at` in the past), runs the device-code flow
    (Requirements 29-32) automatically before proceeding with the original
    command. A successful device-flow run overwrites the stored credentials
    file. This applies whether the flow was triggered implicitly by a
    `runs` command or explicitly via `auth login` (Requirement 22).
22. `cirq-studio auth login`: runs the device-code flow (Requirements 29-32)
    unconditionally — even if a valid, unexpired token is already stored,
    an explicit `login` always re-authenticates and overwrites it. On
    success, calls `GET /auth/me` with the new token and prints the signed-in
    user's email and display name, exits 0.
23. `cirq-studio auth logout`: deletes `~/.config/cirq-studio/credentials.json`
    if it exists and prints a confirmation; if the file doesn't exist,
    prints "not signed in" and exits 0 (not an error — the end state the
    user wants, being logged out, is already true).
24. `cirq-studio auth whoami`: if a valid (present, unexpired) token is
    stored, calls `GET /auth/me` and prints the signed-in user's email and
    display name, exits 0. If no valid token is stored, prints "not signed
    in" and exits 1 — unlike the `runs` commands (Requirement 21),
    `whoami` does NOT trigger the device flow, since it's a read-only status
    check and silently starting an interactive login flow from a status
    query would be surprising.
25. `cirq-studio runs create (--circuit-id <uuid> | --file <path>)
    --processor <id> [--noisy | --noiseless] --repetitions <n>`: exactly one
    of `--circuit-id`/`--file` required (mirrors
    `cirq-sandbox-studio.md` Requirement 24's `circuit_id`/`definition`
    exclusivity) — `--file` reads a JSON file matching
    `cirq-sandbox-studio.md`'s Requirement 11 circuit-definition shape from
    disk. `--noisy`/`--noiseless` are mutually
    exclusive; if both are given, exits 1 with a usage error before any
    network call; if neither is given, defaults to `--noisy` (matches
    `engine.get_sandbox_engine`'s own `noisy: bool = True` default and the
    original CLI's default behavior in `src/cirq_sandbox/main.py`). Calls
    `POST /runs` with the stored token; on success (`202`) prints the
    returned `run_id` and exits 0; on any non-2xx response, prints the
    API's error detail verbatim (the `400` validation message, or the raw
    status/body for anything else — e.g. `401`, `404` unknown processor,
    `5xx`) and exits 1 — no retry, no swallowed detail (same "surface it,
    don't paper over it" principle as the backend's own error handling).
26. `cirq-studio runs get <run_id>`: calls `GET /runs/{id}`. If
    `status="queued"` or `"running"`, prints the status plus processor and
    repetitions (no histogram yet — none exists). If `status="done"`, prints
    the result histogram as a simple text table (bitstring → count, one per
    line). If `status="error"`, prints `error_message`.
27. `cirq-studio runs watch <run_id>`: opens `WS /runs/{id}/stream` with the
    token as the `?token=` query param (matching Requirement 5 of
    `cirq-sandbox-studio.md`), prints each state transition as it arrives
    (`queued` → `running` with each chunk's running histogram reprinted in
    place → final `done`/`error`), then exits 0 (`done`) or 1 (`error`).
    Plain text output — no TUI/progress-bar dependency, minimum complexity
    for a terminal that may not support cursor control (e.g. piped output).
    If the WebSocket connection drops unexpectedly (not a clean `done`,
    `error`, or the 4404 close from Edge Case 8) — e.g. a network
    interruption — prints a connection-lost error and exits 1; no
    auto-reconnect (same no-retry principle as Requirement 25).
28. `cirq-studio runs list [--page N]`: calls `GET /runs` (paginated per
    Requirement 36 of `cirq-sandbox-studio.md`), prints one line per run
    (id, status, processor, repetitions, created_at).

### Device-code auth flow (new backend capability)

29. New Google Cloud OAuth client required, of the **TV and Limited Input
    devices** type (distinct from the existing web-application client used
    by Requirements 1-2 of `cirq-sandbox-studio.md` — Google's device
    authorization grant requires this specific client type). This is an
    external, manual setup step in the Google Cloud Console — not something
    any agent in this pipeline can provision (same class of prerequisite as
    the original `GOOGLE_OAUTH_CLIENT_ID`/`SECRET` setup). New env vars:
    `GOOGLE_OAUTH_DEVICE_CLIENT_ID`, `GOOGLE_OAUTH_DEVICE_CLIENT_SECRET`,
    added to `.env.example`.
30. `cirq-studio`'s device flow (client-side, no new backend endpoint for
    this part): `POST` to Google's device authorization endpoint
    (`https://oauth2.googleapis.com/device/code`) with
    `GOOGLE_OAUTH_DEVICE_CLIENT_ID` and scope `openid email profile`;
    receives `device_code`, `user_code`, `verification_url`, `interval`,
    `expires_in`. Prints `"To sign in, visit <verification_url> and enter
    code: <user_code>"`.
31. Polls Google's token endpoint (`https://oauth2.googleapis.com/token`,
    `grant_type=urn:ietf:params:oauth:grant-type:device_code`) every
    `interval` seconds (from Requirement 30's response) until: (a) success —
    receives an `id_token`, proceeds to Requirement 32; (b)
    `authorization_pending` — keeps polling at the current interval; (c)
    `slow_down` — increases the polling interval by 5 seconds (per RFC 8628)
    and keeps polling, does not treat this as an error; (d) `expired_token`
    (user didn't complete it within `expires_in`) — prints an error, exits
    1, no partial credentials written; (e) `access_denied` (user declined)
    — prints an error, exits 1.
32. New backend endpoint `POST /auth/google/device-exchange`: request body
    `{"id_token": "<google id_token from Requirement 31>"}`. Verifies the
    token against Google's public keys (audience must match
    `GOOGLE_OAUTH_DEVICE_CLIENT_ID`) — on failure, `401`. On success,
    extracts `google_id`/`email`/`display_name` from the verified token's
    claims and runs the SAME user-upsert + JWT-issuance logic as
    `services/api/app/auth.py`'s existing callback handler (Requirement 2 of
    `cirq-sandbox-studio.md` — first login creates a `users` row, subsequent
    logins reuse it), returning `{"token": "<jwt>"}` (`200`) instead of a
    redirect (this is a pure JSON API endpoint, not a browser flow). Reuses
    the existing JWT-issuance helper — does not duplicate its logic.
33. `cirq-studio` writes the returned token to
    `~/.config/cirq-studio/credentials.json` (Requirement 20) after a
    successful Requirement 32 call, then proceeds with the original command
    that triggered the flow (Requirement 21).

## Data Flow

1. Developer runs `make up` → Makefile checks `.env` exists → `docker
   compose up -d postgres redis api worker client-web` → `postgres`/`redis`
   report healthy → `api`/`worker` start (no migrations applied yet) →
   `client-web` starts the Expo dev server on :8081.
2. Developer runs `make migrate` → `docker compose exec api alembic ...
   upgrade head` → schema created in the running `postgres` container.
3. Developer runs `make seed` → `docker compose exec api python -m
   app.seed` → dev user + sample circuits/runs inserted directly via the
   ORM.
4. Developer opens `http://localhost:8081` (web client) or runs `cirq-studio
   runs list` (CLI) — both now have real data to show.
5. `cirq-studio runs create --file circuit.json --processor weber --noisy
   --repetitions 500` → no stored token found → device flow (Requirements
   30-32) → browser-based Google consent on `verification_url` → CLI polls
   until approved → `POST /auth/google/device-exchange` → JWT stored → CLI
   proceeds to `POST /runs` with that JWT → prints `run_id`.
6. `cirq-studio runs watch <run_id>` → `WS /runs/{id}/stream` with the
   stored JWT → prints `queued` → `running` (histogram reprinted per chunk)
   → `done`, exits 0.

## Edge Cases

1. When `make up` is run without a `.env` file present, it exits
   non-zero with a message naming `.env.example` as the template to copy —
   no services are started.
2. When `make migrate` or `make seed` is run before `make up` (the `api`
   container isn't running), the underlying `docker compose exec` fails
   with Docker's own "service is not running" error — Makefile does not
   catch/reinterpret this, the raw Docker error is sufficient and accurate.
3. When `make seed` is run a second time, it exits 0 and makes no
   additional changes (Requirement 16's idempotency check on the fixed
   `google_id`).
4. When a `cirq-studio runs` command's stored token (Requirement 20) is
   present but expired, the device flow re-runs automatically
   (Requirement 21) — the user is never shown a raw 401 from the API for
   this case.
5. When the device flow's Google polling (Requirement 31) returns
   `expired_token` or `access_denied`, `cirq-studio` exits 1 with a clear
   message and writes nothing to `~/.config/cirq-studio/credentials.json` —
   a partially-completed login never leaves a corrupt/empty credentials
   file that a later command would trip over.
6. When `POST /auth/google/device-exchange` receives an `id_token` whose
   signature or audience doesn't verify, it returns `401` with no `users`
   row created — same "don't create side effects on a failed auth attempt"
   principle as `cirq-sandbox-studio.md`'s Requirement 2 (its existing web
   callback, per its own Edge Case 16).
7. When `cirq-studio runs create` is given neither or both of
   `--circuit-id`/`--file`, it exits 1 with a usage error before making any
   network call (client-side validation, mirrors `cirq-sandbox-studio.md`'s
   own Requirement 24 exclusivity check as a fast-fail rather than relying
   solely on the server's `400`).
8. When `cirq-studio runs watch` is run against a `run_id` that doesn't
   exist or isn't owned by the authenticated user, the WebSocket closes with
   4404 per `cirq-sandbox-studio.md`'s existing WS behavior — `cirq-studio`
   prints that as an error and exits 1, no retry/reconnect loop.
9. When `docker compose down` (Requirement 15, no `-v`) is followed by
   `make up` again, the `postgres` named volume (Requirement 2) means
   previously-migrated schema and seeded/created data are still present —
   `make migrate` on an already-migrated schema is a no-op (alembic's own
   idempotency), not an error.
10. When `api`/`worker` are running but `make migrate` (Requirement 11) has
    not yet been run, any request that touches the database fails — this is
    expected given Requirement 8's explicit no-auto-migration decision, not
    a bug; `make up` succeeding means the containers are running, not that
    the API is usable yet.
11. When the `client-web-prod` profile (Requirement 7) is started while
    `client-web` (dev) is also running, both bind different host ports
    (8081 dev, 8082 prod) — no port collision, both can run simultaneously
    for comparison.

## Acceptance Criteria

- [ ] `docker compose up -d postgres redis api worker client-web` (with a
      valid `.env`) brings up all five default-profile services, `api` and
      `worker` reach a running state only after `postgres`/`redis` report
      healthy.
- [ ] `make up` without a `.env` file present exits non-zero without
      starting any containers.
- [ ] `make migrate` applies the existing Alembic schema
      (`services/api/alembic/versions/88179c22c370_initial_schema.py`)
      against the running `postgres` service.
- [ ] `make seed` run twice in a row leaves exactly one dev user, three
      seeded circuits, and one seeded run — no duplicates.
- [ ] `make test` runs both `pytest` and the client `tsc --noEmit`, and
      fails (non-zero exit) if either fails, even if the other succeeds.
- [ ] `cirq-studio auth whoami` with no stored credentials prints "not
      signed in" and exits 1, without triggering the device flow (no
      verification URL/code is printed).
- [ ] `cirq-studio auth login` followed by `cirq-studio auth whoami` prints
      the signed-in user's email/display name and exits 0.
- [ ] `cirq-studio auth logout` after a successful login removes
      `~/.config/cirq-studio/credentials.json`, and a subsequent
      `cirq-studio auth whoami` again reports "not signed in".
- [ ] `cirq-studio auth logout` with no stored credentials exits 0 (not an
      error).
- [ ] `cirq-studio runs create --file <valid circuit.json> --processor weber
      --noiseless --repetitions 100` on a machine with no stored credentials
      prints the device-flow verification URL/code, and — once approved in
      a browser — completes the run submission and prints a `run_id`.
- [ ] `cirq-studio runs watch <run_id>` for that run prints at least one
      `running` update with a non-empty histogram before printing `done`.
- [ ] `cirq-studio runs create` with neither `--circuit-id` nor `--file`
      exits 1 without making any HTTP request (verify via a network-call
      assertion in the test, not just the exit code).
- [ ] `POST /auth/google/device-exchange` with a tampered/invalid
      `id_token` returns `401` and creates no `users` row.
- [ ] `~/.config/cirq-studio/credentials.json` is created with `0600`
      permissions after a successful device flow.
- [ ] `docker compose --profile prod up client-web-prod` serves the
      production Expo web export on port 8082, independent of whether
      `client-web` (dev, port 8081) is also running.

## Key Files

- `docker-compose.yml` — new; postgres, redis, api, worker, client-web,
  client-web-prod (profile `prod`).
- `services/api/Dockerfile` — new; shared image for `api`/`worker`.
- `apps/studio/Dockerfile` — new; shared image for `client-web`/`client-web-prod`
  (build-stage-selected).
- `Makefile` — new; `up`/`down`/`migrate`/`seed`/`test`/`logs`.
- `services/api/app/seed.py` — new; idempotent dev-data seeding.
- `services/api/app/cli/main.py` — new; `cirq-studio` Typer app, `auth`
  (login/logout/whoami) and `runs` (create/get/watch/list) subcommands.
- `services/api/app/cli/auth.py` — new; device-code flow client + token
  storage (`~/.config/cirq-studio/credentials.json`).
- `services/api/app/auth.py` — adds `POST /auth/google/device-exchange`
  (Requirement 32) to the existing auth router, reusing its user-upsert +
  JWT-issuance helpers rather than a new file/module.
- `pyproject.toml` — add `[project.scripts] cirq-studio = "app.cli.main:app"`
  and a Typer dependency.
- `.env.example` — add `GOOGLE_OAUTH_DEVICE_CLIENT_ID`,
  `GOOGLE_OAUTH_DEVICE_CLIENT_SECRET`.
- `README.md` — document `make`/`cirq-studio` usage alongside the existing
  manual instructions (which remain valid as the non-Docker path).
