# Design Spec: Cirq Sandbox Studio — Client UI

## Overview

Visual and interaction design for the Expo (React Native Web) client (`apps/studio/`)
specified in `specs/cirq-sandbox-studio/cirq-sandbox-studio.md` (Requirements 40-45).
This is the first design pass for the project — no prior visual identity exists. Covers
all 5 screens (Login, Builder, My Circuits, Run History, Gallery) plus cross-cutting
navigation, session, and confirmation patterns, across web, iOS, and Android from one
codebase.

## Goals

- Establish a single visual identity ("Lab Instrument, Softened") applied consistently
  across all screens and platforms.
- Specify a cross-platform gate-placement interaction (tap-to-arm/tap-to-place) that
  works identically on mouse and touch, with no separate input-type code paths.
- Specify layouts for the Builder screen (the hardest surface) on both web/desktop
  (3-column, all-visible) and mobile (full-screen grid + drawer/tab pattern).
- Specify the live-streaming histogram visualization, decoupled from WebSocket message
  frequency, with a clear streaming-vs-final visual distinction.
- Specify one shared empty/error-state pattern (with defined tone variants) and one
  shared confirm-dialog pattern, reused across all screens rather than bespoke
  per-screen treatments.

## Non-Goals

- Desktop-installed app (Tauri/Electron) — out of scope per the implementation spec's
  Non-Goals; do not design distinct layouts for it.
- Circuit co-editing / real-time multi-user collaboration UI — out of scope per the
  implementation spec's Non-Goals.
- Auto-routing/SWAP-insertion UI — out of scope; the grid only ever allows placements
  the device topology supports (Requirement 13), so no "fix this circuit" UI is needed.
- Light-mode theme — v1 ships dark-mode-only (see Visual Identity). A light theme is
  not designed here and is not a toggle in this spec.
- Accessibility audit (screen-reader labeling, contrast-ratio certification, focus-trap
  implementation detail) — flagged as a follow-up design pass, not covered here beyond
  the touch-target-size and color-differentiation baselines stated below.

## Visual Identity

**Direction: "Lab Instrument, Softened."** Dark-mode-first, precision-oriented, but
rounded and touch-friendly rather than sharp/cold — this is a tool for extended
circuit-building sessions and must work as well on a phone as a desktop.

- **Base palette:** background `#0F1419` (near-black slate), surface/card
  `#1A2129`, elevated surface (modals, armed-gate palette items) `#232B35`, border/
  divider `#2E3946`, primary text `#E8EDF2`, secondary/muted text `#8A97A6`.
- **Typography:** JetBrains Mono (or equivalent monospace fallback) for all
  precision-bearing content — gate labels on the grid, qubit row/col indices, angle
  input fields, repetitions input, histogram bitstring labels. Inter (or system sans
  fallback) for UI chrome — nav labels, buttons, headings, body copy, toasts, dialogs.
- **Gate category colors** (used for palette items, armed-gate glow, placed-gate fill,
  and adjacency-ring previews):
  - Single-qubit rotation gates (`RX`, `RY`, `RZ`): cyan `#4FD8E8`.
  - Pauli gates (`X`, `Y`, `Z`), `H`, `S`, `T`, and `SQRT_X` (non-rotation
    single-qubit gates): violet `#B98FF0`.
  - Two-qubit gates (`CNOT`, `CZ`, `SWAP`): coral `#E8734A`.
  - `MEASURE`: neutral white-outline (`#E8EDF2` stroke, transparent/no fill) —
    deliberately distinct from the three filled-color categories so it's never
    mistaken for a placeable computational gate.
  - These four colors are the only category colors used anywhere gates appear
    (palette, grid, histogram bitstring key legend if one is shown). No additional
    ad-hoc colors are introduced for gates.
- **Semantic colors** (status/feedback — governing rule: category colors and
  semantic-state colors are drawn from disjoint hues, never shared, so a color never
  has to answer "is this a gate category or a system state?" — amber/warning
  `#F0B94F` (the single, universal color for every pre-Run validation nudge: the
  two-qubit "not connected" toast, and any other inline validation toast/form-error
  state), red/error `#E8524F` (worker/runtime errors, destructive-action confirm
  button), green/success `#4FE88A` (clone-success feedback, save-success feedback).
- **Shape/spacing:** corner radius 8-12px on all interactive surfaces (buttons, cards,
  palette items, modals, toasts). Minimum touch target 44x44pt on every tappable
  element on every platform (including mouse/web — consistency over platform-specific
  minimums). Base spacing unit 8px (multiples of 8 for padding/margins throughout).

## Grid/Gate Interaction Model (Builder)

Tap-to-arm, then tap-to-place. No drag-and-drop. Chosen over drag-and-drop for
identical interaction code across mouse (web/desktop) and touch (iOS/Android/mobile
web), and to avoid fat-finger imprecision dragging a gate icon onto a small grid cell
on a phone-sized screen.

1. **Arming a gate:** Tapping a gate in the palette arms it — the palette item elevates
   (subtle shadow/lift), gains a glowing outline in its category color (see Visual
   Identity), and the rest of the palette dims to ~60% opacity to draw focus to the
   armed item. Only one gate can be armed at a time; tapping a different palette item
   re-arms to that gate (previous arming clears). Tapping the armed item again
   disarms it (returns palette to neutral).
2. **Placing a single-qubit gate** (`H`, `X`, `Y`, `Z`, `S`, `T`, `RX`, `RY`, `RZ`):
   with the gate armed, tapping any qubit node on the grid places it into the next
   available moment column for that qubit's row (see Moment/Timeline Layout) and
   disarms the palette. `RX`/`RY`/`RZ` placement immediately opens an inline angle
   input (numeric, radians, monospace field) anchored to the placed gate; the gate
   renders on the grid with a default angle (`0`) until the user commits a value.
3. **Placing `MEASURE`:** armed like other gates; tapping a qubit node adds it to the
   in-progress `MEASURE` selection (node visually groups with the white-outline
   treatment); tapping an already-selected qubit again deselects it (toggle) — taps
   stay reversible until commit, consistent with the rest of this interaction model.
   A confirm affordance (e.g. a checkmark chip appearing near the last-tapped qubit)
   commits the selection and opens the `key` text input inline. As the user types, the
   key is validated live against existing `MEASURE` keys already placed in the
   circuit: a duplicate shows inline red text under the input ("Key already used") and
   disables the confirm chip until the value is unique (Edge Case 12) — this is a form
   error, distinct from the spatial toast/shake pattern used for grid-placement
   errors (see Grid Interaction step 4, Empty/Error States). The server's `400` on
   duplicate keys (Requirement 25e) remains a fallback safety net, not the primary
   signal. Tapping armed `MEASURE` again before confirming cancels the in-progress
   selection entirely.
4. **Placing a two-qubit gate** (`CNOT`, `CZ`, `SWAP`): with the gate armed, the first
   qubit tap sets the control qubit (visually pinned — outlined in the gate's category
   color, does not deselect on subsequent taps). Immediately after, the grid
   live-redraws every other qubit's visual state based on the selected processor's
   `topology.pairs` (Requirement 9/13):
   - Qubits connected to the control qubit (valid partners): solid ring in the gate's
     category color (coral `#E8734A`) plus a preview edge line drawn from control to
     that qubit.
   - Qubits not connected to the control qubit (invalid partners): desaturate to ~40%
     opacity (of the coral ring treatment) and become non-interactive for this
     placement (tapping one does nothing placement-wise).
   - Tapping a desaturated/invalid qubit instead triggers a gentle shake animation on
     that qubit node plus an inline toast anchored near it: "Not connected on this
     processor" (amber `#F0B94F`, the universal warning color — visually distinct
     from the coral ring/edge-preview also on screen at that moment, since category
     and semantic colors never share a hue, see Visual Identity — auto-dismisses
     after ~2.5s). This is the same toast pattern used for inline validation errors
     generally (see Empty/Error States).
   - Tapping a valid (ringed) qubit completes the placement: the gate renders on the
     connecting edge, both qubits' temporary ring/desaturation states clear, and the
     palette disarms.
   - Tapping the control qubit again (instead of a partner) cancels the two-qubit
     placement and returns the grid to its normal state, gate remains armed for
     another attempt.
5. **Animation:** All grid-state transitions in this section (arming glow, adjacency
   ring/desaturation, shake) use Reanimated `withTiming`, ~150-200ms ease, as a
   discrete state transition triggered on tap — not a continuously-tracked gesture.
   Confirmed feasible by Researcher at the ≤12-qubit/cell scale this screen is capped
   to (Requirement 9).
6. **Removing a placed gate:** tapping an already-placed non-rotation gate on the grid
   (any gate except `RX`/`RY`/`RZ` — see step 7 for those) selects it and surfaces a
   small inline "Remove" action (e.g. a chip/button adjacent to the gate); tapping
   elsewhere deselects without removing. This is the only path to remove a placed
   gate — there is no separate "eraser" tool.
7. **Editing/removing a placed rotation gate:** tapping a placed `RX`/`RY`/`RZ` gate
   reopens the same inline angle-input control used at placement (step 2), pre-filled
   with its current value, rather than the Remove chip from step 6 — this avoids
   forcing remove-and-replace for a simple angle correction, consistent with the
   direct-manipulation feel of the rest of this model. That reopened control includes
   its own "Remove" action alongside the angle field, so removal is still reachable
   from the same single tap target.

### Moment/Timeline Layout

The grid canvas is laid out as qubit rows (one per qubit in the processor's
`topology.qubits`, Requirement 9) crossed with moment columns (left-to-right,
increasing time). Each cell at (qubit row, moment column) either holds a placed gate
or is empty. A new single-qubit gate placement goes into the first moment column where
that qubit's cell is empty (i.e., appends to that qubit's timeline, not necessarily to
the rightmost global column, since different qubits can be at different moment depths
mid-build). A two-qubit gate placement occupies the same moment column across both
qubits it spans, choosing the first column where both are empty. Qubit rows are
ordered by the same BFS order as `topology.qubits` (Requirement 9) — not
re-sorted by user interaction — so row position stays stable across a build session.
When a two-qubit gate's placement column is later than one of its qubits' own
next-empty column (because the other qubit needed a later column to be free), the
skipped cell(s) on the ahead qubit's row render as plain blank space — the wire line
simply continues through with no gate and no placeholder/no-op mark. A skipped cell is
functionally identical to any other empty cell on that wire (still placeable);
inventing a distinct visual mark for it would imply a special state that doesn't
otherwise exist in this model.

## Builder Layout — Web/Desktop vs. Mobile

**Web/desktop (viewport width ≥ 900px):** Fixed 3-column layout, all three panels
visible simultaneously, no mode-switching or collapsing:
- Left rail (~180px fixed): gate palette, vertically scrollable if needed, grouped by
  category (rotation / Pauli+H/S/T / two-qubit / measure) with category color used as
  a section accent.
- Center (fills remaining width, dominant): qubit-grid canvas with the moment/timeline
  layout, horizontally scrollable if the circuit's moment count exceeds visible width.
  Processor picker and "Load preset" menu sit as a slim toolbar above the canvas.
- Right rail (~260px fixed): run panel — noisy/noiseless toggle, repetitions input,
  Run button, live status badge, live histogram, final result view (see Histogram
  section).

**Mobile (iOS/Android and web viewport < 900px):** The qubit-grid canvas is the
permanent full-screen base layer (always visible, maximizes space for the
hardest-to-shrink surface). Processor picker and "Load preset" sit as a slim toolbar
above the canvas, same as web.
- **Palette** is a swipe-up bottom-sheet drawer, collapsed by default to a thin handle
  bar showing just a drag handle plus (if a gate is armed) the armed gate's icon/color
  as an indicator chip. Swiping up expands it to show the full category-grouped
  palette (same content as the web rail, reflowed to a horizontal-scrolling or
  wrapped-grid layout). Placing a gate (arming + tapping a qubit) does not require the
  drawer to be open — arming works from the collapsed handle-bar indicator state too
  once a gate has been tapped once to expand, tapped again to arm; the drawer
  auto-collapses after a successful placement to return focus to the grid.
- **Run panel** is not simultaneously visible with the grid on mobile; it's reachable
  via a two-tab bottom tab bar scoped to the Builder screen: **Build** (grid + palette,
  default tab) and **Run** (noisy/noiseless toggle, repetitions input, Run button,
  status, histogram, result). Starting a run from the Run tab keeps the user on that
  tab to watch the live histogram; switching back to Build tab mid-run does not cancel
  the run — the status badge on the Run tab shows a small live-updating indicator
  (e.g. a colored dot matching current status) so progress is visible without leaving
  Build.

## Save / Save As (Builder toolbar)

Save and Save As are two distinct actions in the Builder screen's toolbar (both on
web and mobile — toolbar sits above the grid canvas in both layouts, per Builder
Layout above), governing how a circuit's name is captured before `POST`/`PUT
/circuits` (Requirements 17, 20):

- **Save, on a circuit with no name yet** (i.e. not yet persisted, or loaded from an
  unsaved `definition`): opens a name-entry modal — a single text field ("Name your
  circuit") with Save/Cancel buttons. Confirming calls `POST /circuits`.
- **Save, on an already-named/persisted circuit:** no prompt — saves silently
  (`PUT /circuits/{id}`) and shows a brief green `#4FE88A` toast confirmation
  ("Saved").
- **Save As** (available whenever a circuit is loaded, named or not): always opens the
  same name-entry modal, pre-filled with "{current name} copy" (editable) when a name
  already exists, or blank if the circuit was never named. Confirming always calls
  `POST /circuits` (creates a new row, distinct from the source circuit if one
  existed) — Save As never overwrites the circuit it was invoked from.

## Live-Streaming Histogram (Run panel)

Populated via `WS /runs/{id}/stream` `partial_histogram` messages (Requirement 30),
which are **cumulative** snapshots (not deltas) — each message reflects the full
running total across all chunks completed so far, per Requirement 29-30. A run is
chunked into groups of 100 repetitions server-side (max 10 chunks for the 1000-repetition
cap, Requirement 29), so worst case is ≤10 WebSocket messages for an entire run.

1. **Bar positions — fixed at run start, never reordered.** Before the first
   `partial_histogram` message arrives (i.e., as soon as status becomes `"running"`),
   the full x-axis is pre-plotted: one bar position for every possible outcome
   bitstring of the circuit's `MEASURE` key(s) (2^n positions for n measured qubits),
   ordered ascending by bitstring value, all at zero height. As `partial_histogram`
   data arrives, only bar heights change — no bar is ever inserted, removed, or
   repositioned mid-run. If the outcome space is wider than the visible chart area
   (e.g. many measured qubits), the histogram scrolls horizontally; bars are never
   collapsed to a top-N subset or reordered by frequency.
2. **Redraw cadence — decoupled from WebSocket arrival rate.** Incoming
   `partial_histogram` messages are batched; the chart redraws on a fixed ~10fps
   cadence regardless of how many WS messages arrived in that window, animating each
   bar to its latest cumulative value with a ~100ms ease-out tween. This avoids
   per-message tween stacking/interruption if multiple chunks resolve close together,
   while still being visually smooth for the sparse (~10-message) case a typical run
   produces.
3. **Y-axis — dynamic with headroom, animated rescale.** The y-axis scales to
   (current max-observed bar count) + ~20% headroom, recalculated only when a bar's
   value approaches the current ceiling (not on every redraw tick). When a rescale is
   needed, the axis animates to its new scale (tween) rather than snapping instantly.
4. **Streaming vs. final visual state.** While `status = "running"`: bars render with
   a semi-transparent/textured fill (in the same neutral chart color, not a gate
   category color — the histogram is outcome data, not gate data), and a small
   pulsing "Streaming…" text indicator sits near the chart title. On the `"done"`
   message (Requirement 32): bars animate to full opacity/solid fill, the y-axis locks
   to the final max (no further rescale), and the indicator switches to a static
   "Final Result" badge. This opacity/texture change is the primary signal that the
   histogram is final — no re-reading of status text required to tell streaming from
   done.
5. **Chart color:** the histogram itself uses a single neutral accent (not a gate
   category color, to avoid implying a specific gate is responsible for a given
   outcome bar) — cyan `#4FD8E8` at reduced saturation (~70%) for streaming fill,
   full-saturation cyan for final fill. (Reuses the rotation-gate cyan since outcome
   data has no gate-category association of its own; this is a deliberate exception to
   "gate colors only mean gates" — the histogram is the one place cyan appears without
   representing a rotation gate.)
6. **Error during a run:** if the worker publishes `status = "error"` mid-run
   (Requirement 33, Edge Cases 6-7) instead of `"done"`, the histogram area is replaced
   by the worker/runtime error state (see Empty/Error States) — any partial bars
   rendered up to that point are discarded from view, consistent with the backend
   discarding partial results on error (Edge Case 6).

## Empty/Error States

One shared layout, three tone variants — not bespoke per-screen treatments.

**Shared layout** (used by the Empty and Worker/Runtime-Error variants): a centered
icon, a short one-line message below it, and an optional single CTA button below that,
all vertically centered within the screen's content area. Consistent scanning position
regardless of which screen it appears on.

- **Empty variant:** neutral outline-style icon in muted text color (`#8A97A6`).
  - My Circuits (no saved circuits): message "No saved circuits yet" + CTA button
    "Create your first circuit" (navigates to Builder).
  - Run History (no runs yet): message "No runs yet" — no CTA (nothing to create from
    this screen; user runs a circuit from Builder).
  - Gallery (no public circuits exist yet): message "No public circuits yet" — no CTA.
- **Inline validation-error variant** (Builder, pre-Run — e.g. Edge Cases 1, 3, 12, 15:
  invalid gate placement, connectivity mismatch, duplicate `MEASURE` key): does **not**
  use the shared centered layout. Renders as a transient toast/banner anchored near
  the offending grid cell, amber `#F0B94F`, auto-dismisses after ~2.5s, non-blocking
  (the grid remains fully interactive while it's showing). This is the same toast
  mechanism as the two-qubit "not connected" toast described in the Grid Interaction
  section — one toast component, reused for every pre-Run inline validation message,
  with copy naming the specific offending gate/qubit per Edge Cases 1/3/12/15's
  requirement that server errors name the specific violation (client-side inline
  checks mirror that same specificity where the check can be done client-side ahead of
  submission).
- **Worker/runtime-error variant** (Builder, post-Run — Requirement 33, Edge Cases 6-7:
  simulation failed, job timed out): uses the shared centered icon+message+CTA layout,
  replacing the run panel's result/histogram area (not a toast, not a full-screen
  takeover of the whole Builder screen — scoped to the run panel/Run tab region only).
  Icon and message text use red `#E8524F`. Message is the `error_message` string
  returned by the API (Requirement 33 surfaces it verbatim; the client displays it
  as-is, not paraphrased). CTA button: "Retry Run" (re-submits the same `definition`
  that was just run via a new `POST /runs`).

## Confirm-Dialog Pattern (shared: delete circuit, logout, load preset, switch processor)

One fixed convention, no per-action exceptions. Centered modal over a dimmed scrim.

- **Copy:** title states the action as a question — "Delete this circuit?" for delete,
  "Log out?" for logout. Body is one line stating the consequence — "This can't be
  undone." for delete, "You'll need to sign in again to continue." for logout.
- **Buttons:** exactly two, right-aligned, horizontal. Cancel (outline/neutral style)
  on the left of the pair, has default focus. Confirm (filled style) on the right.
  - Delete's confirm button is filled red `#E8524F` — red is reserved exclusively for
    irreversible data-loss actions.
  - Logout's confirm button is filled with the standard accent color (cyan `#4FD8E8`),
    not red — logout is disruptive (ends the session) but not destructive (no data is
    lost; per Requirement 7 the JWT simply gets discarded client-side).
- **Dismissal:** scrim tap, platform back-button/gesture (Android hardware back,
  browser back where applicable), and Escape key (web) all map to Cancel — never to
  Confirm. There is no dismissal path that triggers the destructive/session action.
- **Trigger points:** four triggers in v1, all using the identical component with only
  the copy/button-color props varying:
  - My Circuits' Delete action (per circuit) — red confirm button.
  - The nav shell's Logout action (see Cross-Cutting Navigation) — accent confirm
    button.
  - Builder's "Load preset" action, but **only when the current grid is non-empty**
    (an empty grid has nothing to lose, so this replace happens silently with no
    dialog) — accent confirm button, copy: "Load this preset? Your current circuit
    will be replaced."
  - Builder's processor-picker change, but **only when the current grid is
    non-empty** (same silent-if-empty rule) — accent confirm button, copy: "Switch
    processor? Placed gates may no longer be valid on the new topology."
  - The latter two are unsaved-work warnings, not irreversible-data-loss warnings —
    same severity tier as logout, hence the accent (not red) confirm button, even
    though they discard in-progress grid state.

## Cross-Cutting Navigation

- **Nav shell:** mobile (iOS/Android and web < 900px) uses a bottom tab bar with 5
  destinations: Builder, My Circuits, Run History, Gallery, Account (Account surfaces
  the signed-in user's display name/email from `GET /auth/me`, Requirement 6, plus the
  Logout action). Web/desktop (≥ 900px) uses a persistent left-side or top nav bar with
  the same 5 destinations always visible, no hamburger/collapse — consistent with the
  Builder screen's own no-mode-switching approach on wide viewports.
- **Session expiry (Edge Case 10):** any authenticated REST call receiving `401`
  clears the stored JWT (Requirement 3/10) and navigates immediately to the Login
  screen (no confirm dialog — this is not a user-initiated action, just a state
  transition following an already-expired session). No error toast is needed beyond
  landing back on Login; Login screen itself shows no special "you were logged out"
  messaging in v1 (out of scope — the plain Login screen is sufficient).
- **WS reconnect indicator (Edge Case 8):** if the Builder screen's WebSocket
  connection drops mid-run and needs to reconnect, a small non-blocking status chip
  appears near the run-status badge (e.g. "Reconnecting…" in muted text color); on
  reconnect, the client relies on the server's on-connect current-state send
  (Requirement 34) to resync the histogram/status, and the chip disappears. This
  reuses the same visual weight as the "Streaming…" histogram indicator (small,
  non-modal, near the status area) rather than a full-screen interruption.
- **Logout:** available from the Account tab/section of the nav shell (see above);
  triggers the shared confirm-dialog pattern before clearing the token (Requirement 7)
  and navigating to Login.

## Screen-by-Screen Reference

Each screen below is mocked for both a mobile frame (iOS/Android/narrow web) and a
desktop/web frame (≥ 900px), per the Builder layout split principles above applied
screen-by-screen (only Builder has a materially different structural split between
the two; other screens reflow the same list/detail content responsively).

1. **Login:** centered app brand/hero (wordmark + short tagline) above a single
   "Sign in with Google" button (Google's standard branded button treatment). States:
   default; redirecting (button shows inline loading spinner, disabled); error
   (Edge Case 16 — inline message above the button, "Sign-in failed, try again", red
   text, button remains available to retry). No confirm dialog on this screen.
2. **Builder:** see Grid/Gate Interaction Model, Builder Layout, and Live-Streaming
   Histogram sections above for full detail. States: empty canvas (no gates placed —
   grid renders with no additional empty-state messaging, since the palette/toolbar
   already communicate what to do); mid-build; Run button disabled with an inline
   hint ("Add a MEASURE gate to run") when no `MEASURE` gate is placed yet (Edge Case
   4); validation error (inline toast, see Empty/Error States); queued/running/done/
   error (see Live-Streaming Histogram and Empty/Error States).
3. **My Circuits:** list of saved circuits (name, processor id, public/private badge,
   updated date), each row tappable to load into Builder. Save/Save As accessible from
   the Builder screen's toolbar (not this screen) and write back here. Delete action
   per row (trash icon) triggers the shared confirm-dialog. Public/private toggle
   inline per row. States: empty (see Empty/Error States); populated list; delete
   confirm dialog open; saving-in-progress (Save/Save As button shows inline spinner).
4. **Run History:** list of past runs (status badge, processor id, repetitions,
   timestamp), each row tappable to a run-detail view showing the stored result
   (histogram, non-live/static rendering since it's historical) and the circuit
   snapshot that produced it (read-only grid rendering, not editable — matches
   Requirement 39's `definition` being an immutable snapshot). States: empty (see
   Empty/Error States); populated list; run detail (done result rendered as a static
   final-state histogram; error result rendered with the same worker/runtime-error
   copy/color treatment as Builder, scoped to the detail view).
5. **Gallery:** grid/list of public-circuit cards (name, owner display name), each
   tappable to a read-only preview (same static grid rendering as Run History's
   circuit snapshot). Clone button on the preview triggers `POST
   /circuits/{id}/clone`; success shows a brief green `#4FE88A` toast ("Cloned to My
   Circuits") and does not navigate away from the preview. States: empty (see
   Empty/Error States); populated; preview; clone-success toast.

## Acceptance Criteria

- [ ] Every screen in the Screen-by-Screen Reference has both a mobile frame and a
      desktop/web frame produced.
- [ ] Gate category colors (cyan/violet/coral/white-outline) are used consistently for
      the same gate groupings across the palette, placed-gate rendering on the grid,
      and the armed-gate glow — no gate appears in a color outside its defined
      category anywhere in the mockups, and no category color is reused for a
      semantic/status color (or vice versa) anywhere in the mockups.
- [ ] The two-qubit gate placement flow (control-qubit tap → live adjacency
      ring/desaturation redraw → valid-partner tap or invalid-partner
      shake-and-toast) is depicted as a distinct sequence of at least 3 grid states
      (armed/no control selected, control selected with adjacency redraw, completed
      placement).
- [ ] The Builder screen mockups show the 3-column web layout and the mobile
      full-screen-grid-plus-drawer/tab layout as visually distinct frames, not a single
      frame claimed to cover both.
- [ ] The histogram mockups depict at least two states: mid-stream (semi-transparent
      fill + "Streaming…" indicator, partial bar heights) and final (solid fill +
      "Final Result" badge, locked axis).
- [ ] The confirm-dialog mockup is produced once (not duplicated per trigger) and
      annotated with all four of its trigger variants (delete-circuit/red, logout/
      accent, load-preset/accent, switch-processor/accent) and their respective copy.
- [ ] The `MEASURE` key-entry mockup shows the inline duplicate-key form-error state
      (red text + disabled confirm chip), distinct from the spatial toast/shake
      pattern used elsewhere on the grid.
- [ ] The Save/Save As mockups distinguish all three flows: first Save (name-entry
      modal), subsequent Save on a named circuit (silent + toast, no modal), and
      Save As (always-prompted modal, pre-filled "{name} copy").
- [ ] Every empty-state and worker/runtime-error-state mockup uses the shared
      centered icon+message+(optional CTA) layout; no screen introduces a
      structurally different empty/error layout.
- [ ] Every interactive element specified (buttons, palette items, grid cells, nav
      tabs, toggle) is annotated or demonstrably sized at the 44x44pt minimum touch
      target.
- [ ] The design spec names every screen, state, and component listed in
      `specs/cirq-sandbox-studio/design-component-inventory.md` — no item from that
      inventory is unaddressed.

## Key Files

- `apps/studio/src/theme/` — new; color tokens, typography tokens, spacing constants
  implementing Visual Identity.
- `apps/studio/src/components/GateGrid.tsx` — new; qubit-grid canvas, moment/timeline
  layout, adjacency-redraw interaction.
- `apps/studio/src/components/GatePalette.tsx` — new; arm/disarm palette, category
  grouping, web-rail vs. mobile-drawer variants.
- `apps/studio/src/components/RunPanel.tsx` — new; noisy toggle, repetitions input,
  Run button, status badge, embeds Histogram.
- `apps/studio/src/components/Histogram.tsx` — new; fixed-position bars, batched
  10fps redraw, dynamic y-axis, streaming/final visual states.
- `apps/studio/src/components/ConfirmDialog.tsx` — new; shared modal, delete/logout
  variants via props.
- `apps/studio/src/components/EmptyState.tsx` — new; shared centered icon+message+CTA
  layout, empty/error tone variants via props.
- `apps/studio/src/components/Toast.tsx` — new; transient inline toast, used by
  grid-adjacency errors, inline validation errors, clone-success feedback.
- `apps/studio/src/screens/Login.tsx`, `Builder.tsx`, `MyCircuits.tsx`,
  `RunHistory.tsx`, `Gallery.tsx` — layout/composition per Screen-by-Screen Reference
  (files already listed as new in the implementation spec's Key Files; this spec
  defines their visual/interaction content).
