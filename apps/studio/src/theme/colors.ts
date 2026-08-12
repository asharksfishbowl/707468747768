/**
 * Color tokens — Design Spec "Visual Identity" ("Lab Instrument, Softened").
 * Dark-mode-only (see design spec's Non-Goals — no light theme in v1).
 */
export const colors = {
  background: "#0F1419",
  surface: "#1A2129",
  surfaceElevated: "#232B35",
  border: "#2E3946",
  textPrimary: "#E8EDF2",
  textMuted: "#8A97A6",

  // Gate category colors — the ONLY colors used anywhere a gate appears
  // (palette, grid, histogram legend). Never reused for semantic/status colors.
  gateRotation: "#4FD8E8", // RX, RY, RZ
  gatePauli: "#B98FF0", // X, Y, Z, H, S, T, SQRT_X
  gateTwoQubit: "#E8734A", // CNOT, CZ, SWAP
  gateMeasure: "#E8EDF2", // white-outline, no fill

  // Semantic colors — disjoint hues from the gate categories above.
  warning: "#F0B94F",
  error: "#E8524F",
  success: "#4FE88A",

  // Histogram accent (deliberate exception — reuses gateRotation cyan since
  // outcome data has no gate-category association of its own; see design spec's
  // Live-Streaming Histogram section, point 5).
  histogramStreaming: "rgba(79, 216, 232, 0.7)",
  histogramFinal: "#4FD8E8",
} as const;

/** Run-status → color, shared by RunPanel's live status badge and Run
 * History's list rows so the two can't drift apart. */
export const RUN_STATUS_COLOR = {
  queued: colors.textMuted,
  running: colors.gateRotation,
  done: colors.success,
  error: colors.error,
} as const;
