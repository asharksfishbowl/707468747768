import { colors } from "./colors";

/**
 * Gate metadata — single source of truth for the palette (Requirement 12's gate
 * list) and the grid's placement rules, reused by GatePalette.tsx and
 * GateGrid.tsx so category membership/colors never drift between the two.
 *
 * Mirrors services/api/app/circuit_builder.py's _SINGLE_QUBIT_GATES /
 * _TWO_QUBIT_GATES / _PARAMETERIZED_GATES dicts (that module is the backend's
 * own single source of truth for the same gate list) and the design spec's
 * "Gate category colors" table.
 */
export type GateCategory = "rotation" | "pauli" | "twoQubit" | "measure";

export type GateId =
  | "H"
  | "X"
  | "Y"
  | "Z"
  | "S"
  | "T"
  | "SQRT_X"
  | "CNOT"
  | "CZ"
  | "SWAP"
  | "RX"
  | "RY"
  | "RZ"
  | "MEASURE";

export interface GateDefinition {
  id: GateId;
  label: string;
  category: GateCategory;
  qubitCount: 1 | 2 | "any";
  requiresAngle: boolean;
}

export const GATE_DEFINITIONS: GateDefinition[] = [
  { id: "RX", label: "RX", category: "rotation", qubitCount: 1, requiresAngle: true },
  { id: "RY", label: "RY", category: "rotation", qubitCount: 1, requiresAngle: true },
  { id: "RZ", label: "RZ", category: "rotation", qubitCount: 1, requiresAngle: true },
  { id: "H", label: "H", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "X", label: "X", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "Y", label: "Y", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "Z", label: "Z", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "S", label: "S", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "T", label: "T", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "SQRT_X", label: "√X", category: "pauli", qubitCount: 1, requiresAngle: false },
  { id: "CNOT", label: "CNOT", category: "twoQubit", qubitCount: 2, requiresAngle: false },
  { id: "CZ", label: "CZ", category: "twoQubit", qubitCount: 2, requiresAngle: false },
  { id: "SWAP", label: "SWAP", category: "twoQubit", qubitCount: 2, requiresAngle: false },
  { id: "MEASURE", label: "MEASURE", category: "measure", qubitCount: "any", requiresAngle: false },
];

export const GATE_CATEGORY_COLOR: Record<GateCategory, string> = {
  rotation: colors.gateRotation,
  pauli: colors.gatePauli,
  twoQubit: colors.gateTwoQubit,
  measure: colors.gateMeasure,
};

/** O(1) gate-by-id lookup — the single place `GATE_DEFINITIONS` gets scanned,
 * so every consumer (GatePalette, GateGrid, useCircuitBuilder, gateColor
 * below) shares one lookup instead of each re-deriving its own `.find()`. */
export const GATE_BY_ID: Record<GateId, GateDefinition> = Object.fromEntries(
  GATE_DEFINITIONS.map((g) => [g.id, g]),
) as Record<GateId, GateDefinition>;

export function gateColor(gateId: GateId): string {
  return GATE_CATEGORY_COLOR[GATE_BY_ID[gateId].category];
}
