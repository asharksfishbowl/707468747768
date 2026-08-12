import { Platform } from "react-native";

/**
 * Typography tokens — Design Spec "Visual Identity". JetBrains Mono (or an
 * equivalent monospace) for precision-bearing content (gate labels, qubit
 * indices, angle/repetitions inputs, histogram bitstring labels); a system
 * sans fallback for UI chrome (nav, buttons, headings, body, toasts, dialogs).
 *
 * No custom font files are bundled in v1 — the platform monospace/sans
 * fallbacks below satisfy the spec's "or equivalent monospace fallback" /
 * "or system sans fallback" clauses without adding a font-loading dependency.
 */
export const fonts = {
  mono: Platform.select({ web: "'JetBrains Mono', ui-monospace, monospace", default: "monospace" }),
  sans: Platform.select({ web: "Inter, system-ui, sans-serif", default: "System" }),
} as const;

export const fontSizes = {
  xs: 12,
  sm: 14,
  md: 16,
  lg: 20,
  xl: 28,
} as const;
