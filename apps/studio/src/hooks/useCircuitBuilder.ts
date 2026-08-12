import { useCallback, useMemo, useState } from "react";
import type { CircuitDefinition, Placement, Qubit, Topology } from "../api/types";
import type { GateId } from "../theme/gates";
import { GATE_BY_ID } from "../theme/gates";
import {
  arePairConnected,
  connectedPairSet,
  existingMeasureKeys,
  firstFreeMoment,
  hasMeasureGate,
  placeAt,
  qubitKey,
  removeAt,
} from "./circuitMath";
import type { ToastTone } from "../components/Toast";

export interface PlacementRef {
  momentIndex: number;
  placementIndex: number;
}

interface PendingAngleEdit extends PlacementRef {
  gate: GateId;
  qubit: Qubit;
  angle: number;
  /** Absent for a brand-new placement (already added to `moments` with the
   * default angle 0, per design spec step 2) — present when re-opening an
   * already-placed rotation gate for editing (step 7). */
  isNew: boolean;
}

/**
 * Owns the in-progress circuit's `moments` state and the full tap-to-arm/
 * tap-to-place interaction model (design spec's "Grid/Gate Interaction
 * Model"). This is what makes placing a two-qubit gate on a non-adjacent
 * pair impossible via the interactive tap-to-place flow (build task's
 * Acceptance Criteria item 1): `tapQubit`'s two-qubit branch below only ever
 * calls `placeAt` for a qubit already proven, via `arePairConnected` against
 * the processor's own `topology.pairs`, to be a valid partner — no other
 * *interactive* placement path exists. (`loadDefinition` is a separate,
 * trusted-data entry point — see its own comment below.)
 */
export function useCircuitBuilder(processorId: string, topology: Topology) {
  const [moments, setMoments] = useState<Placement[][]>([]);
  const [armedGate, setArmedGate] = useState<GateId | null>(null);
  const [controlQubit, setControlQubit] = useState<Qubit | null>(null);
  const [measureSelection, setMeasureSelection] = useState<Qubit[]>([]);
  const [pendingMeasureKeyEntry, setPendingMeasureKeyEntry] = useState(false);
  const [pendingAngleEdit, setPendingAngleEdit] = useState<PendingAngleEdit | null>(null);
  const [selectedPlacement, setSelectedPlacement] = useState<PlacementRef | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: ToastTone } | null>(null);

  const pairs = useMemo(() => connectedPairSet(topology), [topology]);
  const measureKeys = useMemo(() => existingMeasureKeys(moments), [moments]);

  /** Whether `qubit` is a valid two-qubit partner for the current control
   * qubit — the same predicate `tapQubit` gates placement on, exposed so
   * GateGrid's adjacency-ring/desaturation preview uses this one
   * implementation instead of re-deriving connectivity itself. */
  const isValidPartner = useCallback(
    (qubit: Qubit) => Boolean(controlQubit) && arePairConnected(pairs, controlQubit!, qubit),
    [controlQubit, pairs],
  );

  const clearInProgressPlacement = useCallback(() => {
    setControlQubit(null);
    setMeasureSelection([]);
    setPendingMeasureKeyEntry(false);
  }, []);

  const armGate = useCallback(
    (gate: GateId) => {
      clearInProgressPlacement();
      setArmedGate((current) => (current === gate ? null : gate));
    },
    [clearInProgressPlacement],
  );

  const showToast = useCallback((message: string, tone: ToastTone = "warning") => {
    setToast({ message, tone });
  }, []);

  const dismissToast = useCallback(() => setToast(null), []);

  const tapQubit = useCallback(
    (qubit: Qubit) => {
      if (!armedGate) return;
      const def = GATE_BY_ID[armedGate];

      if (def.category === "measure") {
        setMeasureSelection((current) => {
          const key = qubitKey(qubit);
          const already = current.some((q) => qubitKey(q) === key);
          return already ? current.filter((q) => qubitKey(q) !== key) : [...current, qubit];
        });
        return;
      }

      if (def.qubitCount === 2) {
        if (!controlQubit) {
          setControlQubit(qubit);
          return;
        }
        if (qubitKey(qubit) === qubitKey(controlQubit)) {
          setControlQubit(null); // tapping control again cancels this placement attempt
          return;
        }
        if (!arePairConnected(pairs, controlQubit, qubit)) {
          showToast("Not connected on this processor", "warning");
          return;
        }
        const column = firstFreeMoment(moments, [controlQubit, qubit]);
        setMoments(placeAt(moments, column, { gate: armedGate, qubits: [controlQubit, qubit] }));
        setControlQubit(null);
        setArmedGate(null);
        return;
      }

      // Single-qubit gate (rotation or not).
      const column = firstFreeMoment(moments, [qubit]);
      const placement: Placement = def.requiresAngle
        ? { gate: armedGate, qubits: [qubit], angle_radians: 0 }
        : { gate: armedGate, qubits: [qubit] };
      setMoments(placeAt(moments, column, placement));
      setArmedGate(null);

      if (def.requiresAngle) {
        setPendingAngleEdit({ momentIndex: column, placementIndex: 0, gate: armedGate, qubit, angle: 0, isNew: true });
      }
    },
    [armedGate, controlQubit, moments, pairs, showToast],
  );

  const confirmMeasureSelection = useCallback(() => {
    if (measureSelection.length > 0) setPendingMeasureKeyEntry(true);
  }, [measureSelection]);

  const cancelMeasureSelection = useCallback(() => {
    setMeasureSelection([]);
    setPendingMeasureKeyEntry(false);
  }, []);

  const isMeasureKeyTaken = useCallback((key: string) => measureKeys.has(key), [measureKeys]);

  const confirmMeasureKey = useCallback(
    (key: string): boolean => {
      if (!key || isMeasureKeyTaken(key)) return false;
      const column = firstFreeMoment(moments, measureSelection);
      setMoments(placeAt(moments, column, { gate: "MEASURE", qubits: measureSelection, key }));
      setMeasureSelection([]);
      setPendingMeasureKeyEntry(false);
      setArmedGate(null);
      return true;
    },
    [isMeasureKeyTaken, measureSelection, moments],
  );

  const tapPlacedGate = useCallback(
    (ref: PlacementRef) => {
      const placement = moments[ref.momentIndex][ref.placementIndex];
      if (GATE_BY_ID[placement.gate].requiresAngle) {
        setPendingAngleEdit({
          ...ref,
          gate: placement.gate,
          qubit: placement.qubits[0],
          angle: placement.angle_radians ?? 0,
          isNew: false,
        });
        return;
      }
      setSelectedPlacement((current) =>
        current && current.momentIndex === ref.momentIndex && current.placementIndex === ref.placementIndex
          ? null
          : ref,
      );
    },
    [moments],
  );

  const deselectPlacement = useCallback(() => setSelectedPlacement(null), []);

  const removePlacement = useCallback((ref: PlacementRef) => {
    setMoments((current) => removeAt(current, ref.momentIndex, ref.placementIndex));
  }, []);

  const removeSelectedPlacement = useCallback(() => {
    if (!selectedPlacement) return;
    removePlacement(selectedPlacement);
    setSelectedPlacement(null);
  }, [removePlacement, selectedPlacement]);

  const commitAngle = useCallback(
    (angle: number) => {
      if (!pendingAngleEdit) return;
      const { momentIndex, placementIndex } = pendingAngleEdit;
      setMoments((current) => {
        const next = current.map((m) => m.slice());
        next[momentIndex][placementIndex] = { ...next[momentIndex][placementIndex], angle_radians: angle };
        return next;
      });
      setPendingAngleEdit(null);
    },
    [pendingAngleEdit],
  );

  const cancelAngleEdit = useCallback(() => setPendingAngleEdit(null), []);

  const removePendingAngleGate = useCallback(() => {
    if (!pendingAngleEdit) return;
    removePlacement(pendingAngleEdit);
    setPendingAngleEdit(null);
  }, [pendingAngleEdit, removePlacement]);

  /** Loads a definition wholesale (preset load, saved-circuit load, clear) —
   * a trusted-data entry point distinct from `tapQubit`'s guarded placement
   * flow, so it doesn't re-validate adjacency/topology membership itself;
   * the server re-validates on `POST /runs` regardless (Requirement 25), and
   * the Builder screen's switch-processor confirm warns the user directly
   * when this could leave stale placements. */
  const loadDefinition = useCallback(
    (definition: CircuitDefinition) => {
      setMoments(definition.moments);
      clearInProgressPlacement();
      setArmedGate(null);
      setPendingAngleEdit(null);
      setSelectedPlacement(null);
    },
    [clearInProgressPlacement],
  );

  const clearGrid = useCallback(() => loadDefinition({ processor_id: processorId, moments: [] }), [
    loadDefinition,
    processorId,
  ]);

  const definition: CircuitDefinition = useMemo(() => ({ processor_id: processorId, moments }), [
    processorId,
    moments,
  ]);

  return {
    moments,
    definition,
    armedGate,
    controlQubit,
    measureSelection,
    pendingMeasureKeyEntry,
    pendingAngleEdit,
    selectedPlacement,
    toast,
    hasMeasureGate: hasMeasureGate(moments),
    isEmpty: moments.every((m) => m.length === 0),
    armGate,
    isValidPartner,
    tapQubit,
    tapPlacedGate,
    deselectPlacement,
    removeSelectedPlacement,
    commitAngle,
    cancelAngleEdit,
    removePendingAngleGate,
    confirmMeasureSelection,
    cancelMeasureSelection,
    confirmMeasureKey,
    isMeasureKeyTaken,
    dismissToast,
    loadDefinition,
    clearGrid,
  };
}
