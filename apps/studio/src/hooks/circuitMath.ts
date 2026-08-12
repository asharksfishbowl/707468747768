import type { Placement, Qubit, Topology } from "../api/types";

/** String key for a [row, col] qubit — used for Set/Map membership checks. */
export function qubitKey(q: Qubit): string {
  return `${q[0]},${q[1]}`;
}

/** Display label for a qubit's grid row header — shared by GateGrid and
 * StaticCircuitView so the two renderings can't drift apart. */
export function formatQubitLabel(q: Qubit): string {
  return `[${q[0]},${q[1]}]`;
}

function pairKey(a: Qubit, b: Qubit): string {
  const [x, y] = [qubitKey(a), qubitKey(b)].sort();
  return `${x}|${y}`;
}

/** All connected pairs in a topology, as an order-independent lookup set. */
export function connectedPairSet(topology: Topology): Set<string> {
  return new Set(topology.pairs.map(([a, b]) => pairKey(a, b)));
}

export function arePairConnected(pairs: Set<string>, a: Qubit, b: Qubit): boolean {
  return pairs.has(pairKey(a, b));
}

/**
 * Design spec's Moment/Timeline Layout: a placement goes into the first
 * moment column where every qubit it touches is still empty — a single-qubit
 * gate appends to that one qubit's own timeline; a two-qubit gate uses the
 * first column where *both* qubits are free.
 */
export function firstFreeMoment(moments: Placement[][], qubits: Qubit[]): number {
  const keys = qubits.map(qubitKey);
  for (let col = 0; col < moments.length; col++) {
    const occupied = new Set(moments[col].flatMap((p) => p.qubits.map(qubitKey)));
    if (keys.every((k) => !occupied.has(k))) return col;
  }
  return moments.length;
}

export function placeAt(moments: Placement[][], column: number, placement: Placement): Placement[][] {
  const next = moments.map((m) => m.slice());
  while (next.length <= column) next.push([]);
  next[column] = [...next[column], placement];
  return next;
}

export function removeAt(moments: Placement[][], momentIndex: number, placementIndex: number): Placement[][] {
  const next = moments.map((m) => m.slice());
  next[momentIndex].splice(placementIndex, 1);
  return next;
}

export function existingMeasureKeys(moments: Placement[][]): Set<string> {
  const keys = new Set<string>();
  for (const moment of moments) {
    for (const placement of moment) {
      if (placement.gate === "MEASURE" && placement.key) keys.add(placement.key);
    }
  }
  return keys;
}

export function hasMeasureGate(moments: Placement[][]): boolean {
  return moments.some((moment) => moment.some((p) => p.gate === "MEASURE"));
}
