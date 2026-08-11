# Design Coverage Inventory: Cirq Sandbox Studio

Source of truth: `specs/cirq-sandbox-studio/cirq-sandbox-studio.md` (Requirements
40-45, Edge Cases). No existing client code — this is greenfield; every screen below
is derived from the implementation spec, not audited from a real app.

Platform: Expo (React Native Web) — **web (incl. desktop browser) + iOS + Android**.
Desktop-installed app is out of scope (Non-Goal). Mock both mobile and desktop/web
frames.

## 1. Login (Req 40)

- Components: app brand/hero, "Sign in with Google" button
- States: default · redirecting (loading) · error (`?error=` from Edge Case 16 — OAuth
  denied/failed → "sign-in failed, try again")

## 2. Builder (Req 41-42) — core screen

- Components:
  - Processor picker (weber / rainbow / willow_pink)
  - Qubit-grid canvas: nodes = qubits, edges = connected pairs only, from the selected
    processor's `topology` (≤12 qubits, Req 9)
  - Gate palette: H, X, Y, Z, S, T, CNOT, CZ, SWAP, RX/RY/RZ (angle input), MEASURE
    (key input)
  - Moment/timeline layout — circuit reads left-to-right as columns (moments) over
    qubit rows, gates placed into cells
  - Placement interaction: single-qubit gate → a qubit node; two-qubit gate → a
    connected edge only (Req 13) — needs a clear "not placeable here" affordance for
    non-adjacent pairs
  - "Load preset" menu (Bell state, GHZ state, Superposition — Req 15)
  - Run panel: noisy/noiseless toggle, repetitions input (1-1000, client-validated),
    Run button
  - Live status badge: queued / running / done / error
  - Live-updating histogram (bar chart) as `partial_histogram` chunks stream in (Req
    30, 42)
  - Final result view (full histogram + counts)
- States: empty canvas · mid-build · Run disabled (no `MEASURE` gate yet — Edge Case
  4) · validation error (schema or connectivity — Edge Cases 1, 3, 12, 15, surfaced
  inline naming the offending gate/qubit) · queued · running (live chart) · done ·
  error (`error_message` from worker, Edge Cases 6-7)

## 3. My Circuits (Req 43)

- Components: saved-circuit list (name, processor, public/private badge, updated
  date), Save / Save As, Delete, public/private toggle
- States: empty ("no saved circuits yet") · populated list · delete confirm dialog
  (guardrail: destructive action) · saving (loading)

## 4. Run History (Req 44)

- Components: run list (status badge, processor, repetitions, timestamp), tap-through
  to run detail (stored result + circuit snapshot that produced it)
- States: empty · populated · run detail (done result / error message)

## 5. Gallery (Req 45)

- Components: public-circuit cards (name, owner display name), read-only preview,
  Clone button
- States: empty gallery · populated · preview · clone success feedback

## Cross-cutting

- Navigation shell: tab bar (mobile) vs. persistent top/side nav (desktop/web) across
  Builder / My Circuits / Run History / Gallery / Account
- Session expiry: 401 anywhere → back to Login (Edge Case 10)
- WS reconnect indicator on Builder (Edge Case 8)
- Logout confirm dialog (design-pattern choice, per skill guardrail — spec itself
  treats logout as a client-side no-op, Req 7, but the UX still warrants confirming a
  session-ending action)
- One shared confirm-dialog pattern for all destructive/session actions (delete
  circuit, logout)
