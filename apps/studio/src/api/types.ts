import type { GateId } from "../theme/gates";

/** [row, col] — Requirement 9's qubit coordinate shape. */
export type Qubit = [number, number];

/** One gate placement — Requirement 11's per-entry shape. */
export interface Placement {
  gate: GateId;
  qubits: Qubit[];
  angle_radians?: number;
  key?: string;
}

/** Requirement 11: the full circuit JSON shape, client- and server-side. */
export interface CircuitDefinition {
  processor_id: string;
  moments: Placement[][];
}

/** Requirement 9: a processor's fixed-size qubit connectivity subgraph. */
export interface Topology {
  qubits: Qubit[];
  pairs: [Qubit, Qubit][];
}

/** Requirement 8: one entry from GET /processors. */
export interface Processor {
  id: string;
  native_gates: string[];
  topology: Topology;
}

/** Requirements 18/19: circuit summary (list) vs. full (detail) shape. */
export interface CircuitSummary {
  id: string;
  name: string;
  processor_id: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface CircuitFull extends CircuitSummary {
  definition: CircuitDefinition;
}

export interface GalleryCircuit extends CircuitSummary {
  owner_display_name: string;
}

export type RunStatus = "queued" | "running" | "done" | "error";

/** Requirement 35/36: a run's persisted state. */
export interface RunSummary {
  id: string;
  status: RunStatus;
  processor_id: string;
  noisy: boolean;
  repetitions: number;
  /** Requirement 39's immutable snapshot of what was actually run. */
  definition: CircuitDefinition;
  result: Record<string, Record<string, number>> | null;
  error_message: string | null;
  created_at: string;
}

/** Requirement 34: messages relayed verbatim over WS /runs/{id}/stream. */
export interface RunStreamMessage {
  run_id: string;
  status: RunStatus;
  result?: Record<string, Record<string, number>> | null;
  error_message?: string | null;
  partial_histogram?: Record<string, Record<string, number>>;
  chunks_done?: number;
  chunks_total?: number;
}

export interface AuthenticatedUser {
  id: string;
  email: string;
  display_name: string;
}
