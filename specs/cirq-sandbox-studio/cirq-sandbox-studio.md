# Spec: Cirq Sandbox Studio (Web + Mobile)

## Overview

Cirq Sandbox Studio is a public, multi-user product that lets people learn, build, and
run quantum circuits against the existing `cirq_sandbox` QVM engine
(`src/cirq_sandbox/engine.py`) from a browser or mobile app, without installing Python
or touching the CLI. It adds a new HTTP/WebSocket API service (`services/api/`) in
front of the existing sandbox engine, and a new Expo client (`apps/studio/`) that
provides a visual, drag-and-drop circuit builder, live run results, and per-user saved
circuits with optional public sharing.

## Goals

- Users can sign in with Google, build a circuit visually against a real device's
  qubit topology, run it on the local QVM sandbox, and see results update live.
- Users can save named circuits, revisit past runs, and optionally publish a circuit to
  a public gallery for others to view and clone.
- The same client codebase runs on web, iOS, and Android.
- Abuse/cost is bounded: capped qubits per circuit, capped repetitions per run, and a
  server-wide concurrency cap on simultaneous simulation jobs.

## Non-Goals

- Desktop installed app (Tauri/Electron wrapper) — deferred to a later phase.
- Real cloud/QCS execution via `cirq_google.Engine` (`get_cloud_engine` in
  `engine.py`) — deferred to a later phase; v1 only calls `get_sandbox_engine`.
- Auto-routing (SWAP insertion) to reconcile circuits that violate device connectivity
  — rejected in favor of a builder grid that only allows placements the device
  actually supports.
- Circuit co-editing or real-time multi-user collaboration on a single circuit.
- Auth providers other than Google (no email/password, no GitHub).
- Per-user request rate limiting beyond the server-wide job concurrency cap.
- Refresh-token rotation — v1 access tokens are valid for 24 hours; after expiry the
  user re-authenticates via Google OAuth again.
- Any lasting link between a clone and its original — cloning creates a fully
  independent copy owned by the cloning user; neither side's later edits affect the
  other.

## Requirements

### Auth

1. `GET /auth/google/login` redirects the browser/webview to Google's OAuth consent
   screen with `services/api` as the redirect target.
2. `GET /auth/google/callback` exchanges the OAuth code for the user's Google profile
   (id, email, display name), creates a `users` row if one doesn't exist for that
   Google id, and issues a JWT access token valid for 24 hours. If the user denies
   consent or the code exchange fails, no `users` row is created and the API redirects
   to the client's Login screen with an `?error=` query parameter instead of a token.
3. The client stores the JWT via a platform-abstracted storage helper
   (`apps/studio/src/api/tokenStorage.ts`): `expo-secure-store` on iOS/Android,
   `localStorage` on web.
4. All `/processors`, `/circuits/*`, and `/runs/*` REST endpoints require
   `Authorization: Bearer <jwt>`; requests without a valid, unexpired JWT return
   `401`.
5. The `WS /runs/{id}/stream` endpoint accepts the JWT as a query parameter
   (`?token=<jwt>`), since browser `WebSocket` cannot set custom headers.
6. `GET /auth/me` returns the authenticated user's id, email, and display name.
7. There is no server-side logout endpoint or token blocklist in v1 — "logging out" is
   the client discarding its stored JWT (Requirement 3) and returning to the Login
   screen. The token simply expires naturally at 24 hours either way.

### Processors and topology

8. `GET /processors` returns the list of processor ids from `list_virtual_processors()`
   in `src/cirq_sandbox/engine.py`, each with: `id`, `native_gates` (derived from
   `device.metadata.compilation_target_gatesets[0]`), and `topology` — a fixed-size
   qubit subgraph as defined in Requirement 9.
9. The `topology` subgraph is computed by: taking the full qubit connectivity graph
   from `engine.get_sandbox_engine(processor_id).get_processor(processor_id).get_device().metadata.qubit_pairs`,
   selecting the anchor qubit as the one with the lowest `(row, col)` tuple, then
   breadth-first-traversing the connectivity graph from that anchor, collecting qubits
   in BFS order until either 12 qubits are collected or the graph is exhausted (if the
   device has fewer than 12 qubits total, all of them are included). `topology.qubits`
   is the list of `[row, col]` pairs collected; `topology.pairs` is the list of
   `[[row,col],[row,col]]` edges from `qubit_pairs` where both endpoints are in the
   collected set.
10. This BFS subgraph selection lives in a new module
    `services/api/app/topology.py`, unit-testable independent of the HTTP layer.

### Circuit builder data model

11. A circuit is represented client- and server-side as JSON:
    ```json
    {
      "processor_id": "weber",
      "moments": [
        [ {"gate": "H", "qubits": [[0,0]]} ],
        [ {"gate": "CNOT", "qubits": [[0,0],[0,1]]} ],
        [ {"gate": "MEASURE", "qubits": [[0,0],[0,1]], "key": "result"} ]
      ]
    }
    ```
    Each entry in a moment is one gate placement. `qubits` are `[row, col]` pairs that
    must be members of the processor's `topology.qubits` (Requirement 9).
12. Supported `gate` values: `H`, `X`, `Y`, `Z`, `S`, `T`, `SQRT_X`, `CNOT`, `CZ`,
    `SWAP`, `RX`, `RY`, `RZ`, `MEASURE`. `RX`/`RY`/`RZ` require a numeric
    `angle_radians` field. `MEASURE` requires a `key` field (string, unique per
    circuit). `SQRT_X` (the square-root-of-NOT gate, `cirq.X ** 0.5` — Cirq's own
    canonical "Hello Qubit" first example) takes no extra fields.
13. `CNOT`, `CZ`, and `SWAP` are two-qubit gates; their `qubits` pair must appear in
    the processor's `topology.pairs` (Requirement 9) for that circuit's
    `processor_id`. All other gates (besides `MEASURE`, which can span any number of
    the circuit's placed qubits) take exactly one qubit.
14. A new module `services/api/app/circuit_builder.py` converts this JSON into a
    `cirq.Circuit` on `cirq_google.GridQubit` instances: `X`→`cirq.X`, `Y`→`cirq.Y`,
    `Z`→`cirq.Z`, `H`→`cirq.H`, `S`→`cirq.S`, `T`→`cirq.T`, `SQRT_X`→`cirq.X ** 0.5`,
    `CNOT`→`cirq.CNOT`, `CZ`→`cirq.CZ`, `SWAP`→`cirq.SWAP`,
    `RX`→`cirq.rx(angle_radians)`, `RY`→`cirq.ry(angle_radians)`,
    `RZ`→`cirq.rz(angle_radians)`, `MEASURE`→`cirq.measure(*qubits, key=key)`.

### Presets

15. A new module `src/cirq_sandbox/preset_circuits.py` provides preset generators that
    take a `topology` (Requirement 9's shape) and return a JSON circuit definition
    (Requirement 11's shape) using qubits from that topology: `hello_qubit_preset`
    (Cirq's own canonical first example, adapted to this app's JSON shape: `SQRT_X` on
    `topology.qubits[0]`, then measure that one qubit — the simplest possible preset,
    single qubit, no connectivity requirement), `bell_state_preset` (reuses
    `bell_state_circuit`'s H+CNOT+measure structure from `circuits.py`, adapted to emit
    JSON instead of a `cirq.Circuit`, using the first connected pair in
    `topology.pairs`), `ghz_state_preset` (H on `topology.qubits[0]`, then a CNOT chain
    from that qubit outward along `topology.pairs` covering `min(4,
    len(topology.qubits))` total qubits — 4 by default, fewer only if the processor's
    topology itself has fewer than 4 qubits — then measure all qubits used),
    `superposition_preset` (H on every qubit in the topology, then measure all).
16. `GET /circuits/presets?processor_id=<id>` returns all four presets generated
    against that processor's topology, in this order: `hello_qubit_preset`,
    `bell_state_preset`, `ghz_state_preset`, `superposition_preset` — Hello Qubit
    first, matching Cirq's own recommended learning progression (simplest example
    first).

### Saved circuits and gallery

17. `POST /circuits` creates a circuit: body is `{name: string, definition: <circuit
    JSON from Requirement 11>, is_public: bool}`, owned by the authenticated user.
18. `GET /circuits` lists the authenticated user's own circuits (id, name,
    processor_id, is_public, created_at, updated_at), newest first, paginated
    (`?page=`, `?page_size=`, default 20).
19. `GET /circuits/{id}` returns a full circuit (including `definition`) if it's owned
    by the requester or `is_public` is true; otherwise `404`.
20. `PUT /circuits/{id}` updates `name`, `definition`, and/or `is_public`; only the
    owner may call this; a request from a non-owner (regardless of whether the
    circuit is public, or whether it exists at all) returns `404`, consistent with
    Requirement 19's existence-hiding policy.
21. `DELETE /circuits/{id}` deletes a circuit; only the owner may call this; same `404`
    policy as Requirement 20.
22. `GET /circuits/gallery` lists circuits where `is_public = true`, across all users,
    newest first, paginated like Requirement 18. Each item includes the owner's
    display name.
23. `POST /circuits/{id}/clone` requires the target circuit to be public (or owned by
    the requester); creates a new circuit row owned by the requester with the same
    `definition` and `name` (suffixed `" (copy)"`), `is_public = false`. The clone has
    no reference back to the original beyond this one-time copy — later edits to
    either do not affect the other.

### Runs

24. `POST /runs` body: `{circuit_id: uuid | null, definition: <circuit JSON> | null,
    processor_id: string, noisy: bool, repetitions: int}`. Exactly one of `circuit_id`
    or `definition` is provided — `circuit_id` runs a saved circuit (server loads its
    `definition`), `definition` runs an unsaved in-progress builder circuit. Either
    way, the resolved `definition` is copied verbatim into the new `runs` row
    (Requirement 39) at creation time, so a later edit or deletion of the source
    `circuits` row never affects an already-created run.
25. `POST /runs` (and `POST`/`PUT /circuits`, for the `definition` field) first
    validates `definition` against the JSON schema implied by Requirements 11-13 —
    unknown `gate` values, missing required fields (`angle_radians` for
    `RX`/`RY`/`RZ`, `key` for `MEASURE`), or malformed `qubits` values return `400`
    with a schema-validation error before any of the semantic checks below run.
    `POST /runs` then validates before enqueueing, in this order, returning `400` with
    a message naming the specific violation on the first failure found: (a)
    `repetitions` must satisfy `1 <= repetitions <= 1000`; (b) the circuit must
    contain at least one `MEASURE` gate; (c) every qubit referenced anywhere in
    `definition` must be a member of the resolved processor's `topology.qubits`
    (Requirement 9) — this also bounds the circuit to at most 12 distinct qubits,
    since `topology.qubits` itself is capped there; (d) every two-qubit gate's
    `qubits` pair must be in the processor's `topology.pairs`; (e) no two `MEASURE`
    placements share the same `key` (Edge Case 12).
26. On successful validation, `POST /runs` creates a `runs` row with `status =
    "queued"`, enqueues a job (circuit definition, processor_id, noisy, repetitions,
    run id) onto a Redis-backed queue, and returns HTTP `202` with body `{run_id,
    status: "queued"}` immediately (does not block on execution).
27. A worker process (`services/api/app/worker.py`) consumes jobs from the Redis
    queue, respecting a server-wide concurrency cap read from the
    `MAX_CONCURRENT_JOBS` environment variable (default `4`).
28. For each job, the worker: builds a `cirq.Circuit` via `circuit_builder.py`
    (Requirement 14) on the processor's device qubits; compiles it with
    `cirq.optimize_for_target_gateset(circuit,
    gateset=device.metadata.compilation_target_gatesets[0])` (the same call used in
    `src/cirq_sandbox/main.py` today, generalized to arbitrary circuits, not just
    `bell_state_circuit`'s output); sets the run's status to `"running"` and publishes
    that transition.
29. The worker splits `repetitions` into chunks of 100 (a `1000`-repetition run is 10
    chunks; a run with `repetitions < 100` is 1 chunk of that size), calling
    `engine.get_sandbox_engine(processor_id, noisy).get_sampler(processor_id).run(compiled,
    repetitions=chunk_size)` once per chunk, accumulating a running histogram keyed by
    the circuit's `MEASURE` key(s).
30. After each chunk, the worker publishes `{run_id, status: "running", partial_histogram:
    {...}, chunks_done, chunks_total}` to a Redis pub/sub channel named
    `run:{run_id}`.
31. A single job (all chunks combined) has a hard wall-clock timeout read from the
    `JOB_TIMEOUT_SECONDS` environment variable (default `120`). If exceeded, the
    worker aborts remaining chunks, sets the run's status to `"error"` with
    `error_message = "timed out after {JOB_TIMEOUT_SECONDS}s"`, and publishes that
    final state.
32. On successful completion of all chunks, the worker persists the final histogram to
    the `runs` row (`status = "done"`, `result` = combined histogram JSON) and
    publishes the final `{run_id, status: "done", result}` message.
33. If `cirq.optimize_for_target_gateset` or `sampler.run` raises, the worker sets
    `status = "error"` with `error_message` set to the exception's string, persists it,
    and publishes it — no retry.
34. `WS /runs/{id}/stream` subscribes the connected client to the `run:{run_id}` Redis
    pub/sub channel and relays each message verbatim as a JSON WebSocket frame; on
    connect, it first sends the run's current persisted state (covers the case where
    the client connects after some chunks already completed).
35. `GET /runs/{id}` returns the run's current persisted state (status, processor_id,
    noisy, repetitions, result or null, error_message or null, created_at) for clients
    that poll instead of using the WebSocket.
36. `GET /runs` lists the authenticated user's own run history, newest first,
    paginated like Requirement 18.

### Data model (Postgres)

37. `users` table: `id` (uuid, pk), `google_id` (string, unique), `email` (string),
    `display_name` (string), `created_at`.
38. `circuits` table: `id` (uuid, pk), `owner_id` (fk → users.id), `name` (string),
    `definition` (jsonb, Requirement 11's shape), `processor_id` (string), `is_public`
    (bool, default false), `created_at`, `updated_at`.
39. `runs` table: `id` (uuid, pk), `owner_id` (fk → users.id), `circuit_id` (fk →
    circuits.id, nullable — null when run from an unsaved `definition`), `definition`
    (jsonb snapshot of what was actually run), `processor_id` (string), `noisy`
    (bool), `repetitions` (int), `status` (enum: `queued`, `running`, `done`,
    `error`), `result` (jsonb, nullable), `error_message` (string, nullable),
    `created_at`.

### Client (Expo — `apps/studio/`)

40. Login screen: "Sign in with Google" button opens `GET /auth/google/login` in a web
    browser/auth session (Expo `AuthSession`), receives the JWT, stores it via
    `tokenStorage.ts` (Requirement 3).
41. Builder screen: fetches `GET /processors`, lets the user pick a processor, renders
    that processor's `topology` as a grid of qubit nodes with edges drawn only between
    connected pairs; a gate palette (Requirement 12's gate list) lets the user tap/drag
    a gate onto a qubit (single-qubit gates) or onto a connected pair (two-qubit
    gates), building up the `moments` array (Requirement 11); a "Load preset" menu
    fetches `GET /circuits/presets?processor_id=<id>` and loads one into the grid,
    replacing the current circuit.
42. Run panel (part of the Builder screen): noisy/noiseless toggle, repetitions input
    (client-side validated `1-1000` before submit), Run button that calls `POST
    /runs` then opens the `WS /runs/{id}/stream` connection; displays live status
    (`queued`/`running`/`done`/`error`), a live-updating bar chart of
    `partial_histogram` as chunks arrive, and the final result on `done`.
43. My Circuits screen: `GET /circuits` list, tap to load into Builder, Save/Save As
    (`POST`/`PUT /circuits`), Delete (`DELETE /circuits/{id}`), a public/private
    toggle bound to `is_public`.
44. Run History screen: `GET /runs` list, tap a run to view its stored result and the
    circuit that produced it.
45. Gallery screen: `GET /circuits/gallery` list, tap to preview (read-only,
    `GET /circuits/{id}`), Clone button (`POST /circuits/{id}/clone`) copies it into
    the signed-in user's own My Circuits.

## Data Flow

1. User taps "Sign in with Google" → client opens `GET /auth/google/login` →
   Google → `GET /auth/google/callback` → API creates/finds the `users` row, issues a
   JWT → client stores it (Requirement 3).
2. User opens Builder → client calls `GET /processors` → renders processor picker;
   user selects one → grid renders from that processor's `topology`.
3. User drags gates onto the grid → client builds the `moments` array in local state
   (Requirement 11) — no network call per gate placement.
4. User sets repetitions/noisy toggle and taps Run → client calls `POST /runs` with
   either `circuit_id` (if the circuit was previously saved and unmodified) or
   `definition` (the current local `moments` state) → API validates (Requirement 25),
   creates a `runs` row (`status = "queued"`), enqueues a job, returns `run_id`.
5. Client opens `WS /runs/{id}/stream?token=<jwt>` → API sends current persisted state
   immediately, then relays every subsequent pub/sub message on channel
   `run:{run_id}`.
6. Worker dequeues the job → builds + compiles the `cirq.Circuit` (Requirement 28) →
   sets/publishes `status = "running"` → runs repetition chunks one at a time against
   `engine.get_sandbox_engine(...).get_sampler(...)`, publishing a partial histogram
   after each chunk (Requirements 29-30) → on completion, persists and publishes
   `status = "done"` with the full result (Requirement 32).
7. Client's WS handler updates the live bar chart on each `running` message and shows
   the final result on the `done` message; the run now also appears in `GET /runs`
   (Run History).
8. User optionally taps Save → `POST /circuits` (or `PUT` if updating an existing
   saved circuit) persists the `definition` → circuit now appears in `GET /circuits`
   (My Circuits) and, if `is_public` is set, in `GET /circuits/gallery`.

## Edge Cases

1. When a `POST /runs` request's circuit uses a two-qubit gate on a qubit pair not in
   the processor's `topology.pairs`, the API returns `400` naming the specific gate
   and qubit pair — no auto-routing, no silent circuit modification (Requirement 25d).
2. When `repetitions` in `POST /runs` is `0`, negative, or `> 1000`, the API returns
   `400` before enqueueing anything (Requirement 25a).
3. When a circuit references more than 12 distinct qubits, the API returns `400`
   before enqueueing — enforced via the "every qubit must be in `topology.qubits`"
   check (Requirement 25c), server-side, even though the client UI already
   constrains the grid to ≤12 qubits, since `definition` can be hand-crafted.
4. When a circuit definition contains zero `MEASURE` gates, the API returns `400`
   before enqueueing (Requirement 25b) — `sampler.run` requires at least one
   measurement to produce a sampleable result, so this is rejected before it would
   otherwise fail deep inside Cirq.
5. When the Redis queue is at `MAX_CONCURRENT_JOBS` capacity, new jobs remain
   `status = "queued"` in Postgres and in the Redis queue until a worker slot frees up
   — the client's WS connection simply keeps showing `"queued"` until the worker picks
   it up and publishes `"running"`.
6. When a job's total wall-clock time exceeds `JOB_TIMEOUT_SECONDS`, it is marked
   `status = "error"` with `error_message = "timed out after {JOB_TIMEOUT_SECONDS}s"`
   (Requirement 31); any chunks already completed are discarded, not partially saved
   as the result.
7. When `cirq.optimize_for_target_gateset` or `sampler.run` raises for any reason
   (e.g. an internal Cirq validation failure not caught by Requirement 25's
   pre-checks), the run is marked `status = "error"` with the exception message
   surfaced verbatim in `error_message` — no retry, no generic "something went wrong".
8. When a client's WebSocket disconnects mid-run and reconnects (or a different device
   opens `WS /runs/{id}/stream` for the same run), the API's on-connect current-state
   send (Requirement 34) ensures the client sees the latest state immediately rather
   than waiting for the next chunk.
9. When `GET /circuits/{id}`, `PUT /circuits/{id}`, `DELETE /circuits/{id}`, or
   `POST /circuits/{id}/clone` targets a circuit that is not owned by the requester
   (and, for `GET`/`clone` only, is also not public), the API returns `404` uniformly
   — never `403` — so a non-owner cannot distinguish "exists but not yours" from
   "doesn't exist" (Requirements 19-21, 23).
10. When a JWT is expired or malformed on any authenticated REST call, the API returns
    `401`; the client clears the stored token and returns to the Login screen.
11. When a JWT is expired or malformed on the `WS /runs/{id}/stream` connection query
    param, the API closes the connection immediately with close code `4401` before
    subscribing to any channel.
12. When two `MEASURE` placements in one circuit definition use the same `key`, the
    API returns `400` from `POST /runs` (Requirement 25e) and from `POST`/`PUT
    /circuits` when saving — measurement keys must be unique within a circuit.
13. When a processor has fewer than 12 total qubits, `topology.qubits` (Requirement 9)
    contains all of that processor's qubits rather than padding or erroring.
14. When `POST /circuits/{id}/clone` is called on the requester's own public circuit,
    it succeeds and produces a second independent copy (cloning your own circuit is
    allowed, not blocked as a no-op).
15. When a submitted `definition` uses a `gate` value outside the supported list
    (Requirement 12), omits a gate-specific required field (e.g. `RX` without
    `angle_radians`), or has a malformed `qubits` value, the API returns `400` from
    schema validation (Requirement 25) — this is checked before, and independently of,
    the semantic/connectivity checks.
16. When a user denies Google OAuth consent, or the authorization-code exchange with
    Google fails for any reason, `GET /auth/google/callback` creates no `users` row
    and redirects to the client's Login screen with `?error=` set rather than issuing
    a token (Requirement 2); the client shows a "sign-in failed, try again" state.

## Acceptance Criteria

- [ ] `POST /auth/google/callback` creates a new `users` row on first login for a
      given Google account and reuses the same row on subsequent logins.
- [ ] `GET /processors` returns each processor from `list_virtual_processors()` with a
      `topology` containing at most 12 qubits and only edges between qubits in that
      set.
- [ ] Building a circuit in the Builder screen that places a two-qubit gate on a
      non-adjacent pair is impossible through the UI (the grid only allows drops on
      `topology.pairs`).
- [ ] `POST /runs` with 13 distinct qubits in `definition` returns `400` and creates
      no `runs` row.
- [ ] `POST /runs` with `repetitions = 1500` returns `400` and creates no `runs` row.
- [ ] `POST /runs` with a valid circuit, `repetitions = 1000`, returns HTTP `202`
      with body `{run_id, status: "queued"}`, and the run reaches `status = "done"`
      with a histogram whose total sampled count equals `1000`.
- [ ] `POST /runs` with a circuit containing zero `MEASURE` gates returns `400` and
      creates no `runs` row.
- [ ] `POST /runs` with a `definition` containing a `gate` value not in the supported
      list (e.g. `"gate": "TOFFOLI"`) returns `400` and creates no `runs` row.
- [ ] Visiting `GET /auth/google/callback` with an invalid/expired OAuth code redirects
      to the Login screen with `?error=` set and creates no `users` row.
- [ ] A second user's `GET /circuits/{id}`, `PUT /circuits/{id}`, and
      `DELETE /circuits/{id}` against a circuit they don't own and that isn't public
      all return `404` (not `403`).
- [ ] Connecting to `WS /runs/{id}/stream` for an in-flight run receives at least one
      `"running"` message with a non-empty `partial_histogram` before the final
      `"done"` message.
- [ ] The Bell-state preset run against any processor shows the expected 00/11-dominant,
      01/10-rare correlation (same signature verified in `build-queue.groovy` TASK #2
      for the CLI's hardcoded Bell circuit).
- [ ] Saving a circuit with `is_public: true` makes it appear in
      `GET /circuits/gallery` for a *different* authenticated user.
- [ ] Cloning a gallery circuit creates a row owned by the cloning user; editing the
      clone's `definition` via `PUT` does not change the original owner's circuit.
- [ ] A job that runs longer than `JOB_TIMEOUT_SECONDS` (default 120s; simulate with
      an artificially large per-chunk delay in a test double, or a lowered
      `JOB_TIMEOUT_SECONDS` in the test environment) ends with `status = "error"` and
      `error_message = "timed out after {JOB_TIMEOUT_SECONDS}s"`.
- [ ] `pytest tests/` (existing test suite, `tests/test_circuits.py`) still passes
      unmodified — `circuits.py` is not changed by this feature.
- [ ] The Expo app builds and runs on web (`expo start --web`), and at minimum boots
      to the Login screen on iOS and Android simulators/emulators.

## Key Files

- `src/cirq_sandbox/engine.py` — reused unmodified (`get_sandbox_engine`,
  `list_virtual_processors`).
- `src/cirq_sandbox/circuits.py` — reused unmodified (`bell_state_circuit`).
- `src/cirq_sandbox/main.py` — unchanged; remains the standalone CLI entry point,
  separate from the new API service.
- `src/cirq_sandbox/preset_circuits.py` — new; preset generators (Requirement 15).
- `services/api/app/main.py` — new; FastAPI app, route registration.
- `services/api/app/auth.py` — new; Google OAuth flow + JWT issuance/verification.
- `services/api/app/topology.py` — new; BFS subgraph selection (Requirement 9).
- `services/api/app/circuit_builder.py` — new; JSON definition → `cirq.Circuit`
  (Requirement 14).
- `services/api/app/routes/processors.py` — new; `GET /processors`.
- `services/api/app/routes/circuits.py` — new; circuits CRUD + presets + gallery +
  clone.
- `services/api/app/routes/runs.py` — new; `POST /runs`, `GET /runs`,
  `GET /runs/{id}`.
- `services/api/app/ws.py` — new; `WS /runs/{id}/stream`.
- `services/api/app/worker.py` — new; Redis queue consumer, chunked execution
  (Requirements 27-33).
- `services/api/app/models.py` — new; SQLAlchemy models for `users`, `circuits`,
  `runs`.
- `apps/studio/src/screens/Login.tsx` — new.
- `apps/studio/src/screens/Builder.tsx` — new; grid + gate palette + run panel.
- `apps/studio/src/screens/MyCircuits.tsx` — new.
- `apps/studio/src/screens/RunHistory.tsx` — new.
- `apps/studio/src/screens/Gallery.tsx` — new.
- `apps/studio/src/api/client.ts` — new; REST + WebSocket client.
- `apps/studio/src/api/tokenStorage.ts` — new; platform-abstracted JWT storage.
