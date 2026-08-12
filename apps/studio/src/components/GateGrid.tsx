import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import type { Placement, Qubit, Topology } from "../api/types";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";
import { gateColor } from "../theme/gates";
import { formatQubitLabel, qubitKey } from "../hooks/circuitMath";
import type { PlacementRef } from "../hooks/useCircuitBuilder";
import type { useCircuitBuilder } from "../hooks/useCircuitBuilder";

type Builder = ReturnType<typeof useCircuitBuilder>;

const CELL_SIZE = 56;
const MIN_COLUMNS = 4;

function findPlacementAt(moments: Placement[][], momentIndex: number, qubit: Qubit) {
  const key = qubitKey(qubit);
  const placements = moments[momentIndex] ?? [];
  const placementIndex = placements.findIndex((p) => p.qubits.some((q) => qubitKey(q) === key));
  return placementIndex === -1 ? null : { placement: placements[placementIndex], placementIndex };
}

interface GateGridProps {
  topology: Topology;
  builder: Builder;
}

/**
 * The qubit-grid canvas: qubit rows (BFS order, Requirement 9) crossed with
 * moment columns (design spec's "Moment/Timeline Layout"). Row headers are
 * the tap target for placing/arming a qubit; placed-gate cells are the tap
 * target for selecting a placement to remove or (for rotation gates) edit.
 */
export function GateGrid({ topology, builder }: GateGridProps) {
  const columns = Math.max(builder.moments.length + 1, MIN_COLUMNS);
  const controlKey = builder.controlQubit ? qubitKey(builder.controlQubit) : null;
  const twoQubitInProgress = Boolean(builder.controlQubit && builder.armedGate);

  return (
    <View style={styles.container}>
      <Pressable style={StyleSheet.absoluteFill} onPress={builder.deselectPlacement} />
      <ScrollView horizontal contentContainerStyle={styles.scrollContent}>
        <View>
          {topology.qubits.map((qubit) => {
            const key = qubitKey(qubit);
            const isControl = controlKey === key;
            const isMeasureSelected = builder.measureSelection.some((q) => qubitKey(q) === key);
            const isValidPartner = !isControl && builder.isValidPartner(qubit);

            return (
              <View key={key} style={styles.row}>
                <RowHeader
                  label={formatQubitLabel(qubit)}
                  onPress={() => builder.tapQubit(qubit)}
                  ringColor={
                    isControl || isValidPartner
                      ? gateColor(builder.armedGate ?? "H")
                      : isMeasureSelected
                        ? colors.gateMeasure
                        : undefined
                  }
                  desaturated={twoQubitInProgress && !isControl && !isValidPartner}
                />
                {Array.from({ length: columns }, (_, col) => {
                  const found = findPlacementAt(builder.moments, col, qubit);
                  const ref: PlacementRef | null = found ? { momentIndex: col, placementIndex: found.placementIndex } : null;
                  const isSelected =
                    ref &&
                    builder.selectedPlacement?.momentIndex === ref.momentIndex &&
                    builder.selectedPlacement?.placementIndex === ref.placementIndex;
                  return (
                    <Cell
                      key={col}
                      placement={found?.placement ?? null}
                      selected={Boolean(isSelected)}
                      onPress={ref ? () => builder.tapPlacedGate(ref) : undefined}
                    />
                  );
                })}
              </View>
            );
          })}
        </View>
      </ScrollView>

      {builder.selectedPlacement && (
        <Pressable style={styles.actionChip} onPress={builder.removeSelectedPlacement}>
          <Text style={styles.actionChipText}>Remove</Text>
        </Pressable>
      )}

      {builder.armedGate === "MEASURE" && !builder.pendingMeasureKeyEntry && builder.measureSelection.length > 0 && (
        <Pressable style={[styles.actionChip, { backgroundColor: colors.gateMeasure }]} onPress={builder.confirmMeasureSelection}>
          <Text style={[styles.actionChipText, { color: colors.background }]}>
            Confirm ({builder.measureSelection.length})
          </Text>
        </Pressable>
      )}

      {builder.pendingMeasureKeyEntry && (
        <MeasureKeyEntry
          isKeyTaken={builder.isMeasureKeyTaken}
          onConfirm={builder.confirmMeasureKey}
          onCancel={builder.cancelMeasureSelection}
        />
      )}

      {builder.pendingAngleEdit && (
        <AngleEditor
          initialAngle={builder.pendingAngleEdit.angle}
          gate={builder.pendingAngleEdit.gate}
          onCommit={builder.commitAngle}
          onCancel={builder.cancelAngleEdit}
          onRemove={builder.pendingAngleEdit.isNew ? undefined : builder.removePendingAngleGate}
        />
      )}
    </View>
  );
}

function RowHeader({
  label,
  onPress,
  ringColor,
  desaturated,
}: {
  label: string;
  onPress: () => void;
  ringColor?: string;
  desaturated?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.rowHeader,
        ringColor ? { borderColor: ringColor, borderWidth: 2 } : null,
        desaturated ? { opacity: 0.4 } : null,
      ]}
    >
      <Text style={styles.rowHeaderText}>{label}</Text>
    </Pressable>
  );
}

function Cell({
  placement,
  selected,
  onPress,
}: {
  placement: Placement | null;
  selected: boolean;
  onPress?: () => void;
}) {
  if (!placement) {
    return (
      <View style={styles.cell}>
        <View style={styles.wire} />
      </View>
    );
  }
  const isMeasure = placement.gate === "MEASURE";
  const color = gateColor(placement.gate);
  return (
    <Pressable style={styles.cell} onPress={onPress}>
      <View
        style={[
          styles.gateChip,
          isMeasure ? { borderColor: color, borderWidth: 2 } : { backgroundColor: color },
          selected ? styles.gateChipSelected : null,
        ]}
      >
        <Text style={[styles.gateChipText, isMeasure ? { color } : null]}>
          {placement.gate === "MEASURE" ? "M" : placement.gate}
        </Text>
      </View>
    </Pressable>
  );
}

function AngleEditor({
  initialAngle,
  gate,
  onCommit,
  onCancel,
  onRemove,
}: {
  initialAngle: number;
  gate: string;
  onCommit: (angle: number) => void;
  onCancel: () => void;
  onRemove?: () => void;
}) {
  const [text, setText] = useState(String(initialAngle));

  return (
    <View style={styles.inlinePanel}>
      <Text style={styles.inlinePanelTitle}>{gate} angle (radians)</Text>
      <TextInput
        style={styles.textInput}
        value={text}
        onChangeText={setText}
        keyboardType="numbers-and-punctuation"
        autoFocus
      />
      <View style={styles.inlinePanelRow}>
        <Pressable style={styles.inlineButton} onPress={onCancel}>
          <Text style={styles.inlineButtonText}>Cancel</Text>
        </Pressable>
        {onRemove && (
          <Pressable style={[styles.inlineButton, { borderColor: colors.error }]} onPress={onRemove}>
            <Text style={[styles.inlineButtonText, { color: colors.error }]}>Remove</Text>
          </Pressable>
        )}
        <Pressable
          style={[styles.inlineButton, { backgroundColor: colors.gateRotation }]}
          onPress={() => {
            const parsed = Number.parseFloat(text);
            onCommit(Number.isFinite(parsed) ? parsed : 0);
          }}
        >
          <Text style={[styles.inlineButtonText, { color: colors.background }]}>Set</Text>
        </Pressable>
      </View>
    </View>
  );
}

function MeasureKeyEntry({
  isKeyTaken,
  onConfirm,
  onCancel,
}: {
  isKeyTaken: (key: string) => boolean;
  onConfirm: (key: string) => boolean;
  onCancel: () => void;
}) {
  const [key, setKey] = useState("");
  const taken = key.length > 0 && isKeyTaken(key);

  return (
    <View style={styles.inlinePanel}>
      <Text style={styles.inlinePanelTitle}>MEASURE key</Text>
      <TextInput style={styles.textInput} value={key} onChangeText={setKey} autoFocus placeholder="result" placeholderTextColor={colors.textMuted} />
      {taken && <Text style={styles.errorText}>Key already used</Text>}
      <View style={styles.inlinePanelRow}>
        <Pressable style={styles.inlineButton} onPress={onCancel}>
          <Text style={styles.inlineButtonText}>Cancel</Text>
        </Pressable>
        <Pressable
          disabled={!key || taken}
          style={[styles.inlineButton, { backgroundColor: colors.gateMeasure, opacity: !key || taken ? 0.4 : 1 }]}
          onPress={() => onConfirm(key)}
        >
          <Text style={[styles.inlineButtonText, { color: colors.background }]}>Confirm</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, position: "relative" },
  scrollContent: { padding: spacing.xs },
  row: { flexDirection: "row", alignItems: "center" },
  rowHeader: {
    width: 72,
    height: CELL_SIZE,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.xs,
    marginBottom: spacing.xs,
  },
  rowHeaderText: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.textPrimary },
  cell: {
    width: CELL_SIZE,
    height: CELL_SIZE,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.xs,
    marginBottom: spacing.xs,
  },
  wire: { height: 2, width: "100%", backgroundColor: colors.border },
  gateChip: {
    width: CELL_SIZE - 12,
    height: CELL_SIZE - 12,
    borderRadius: radii.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  gateChipSelected: { borderWidth: 2, borderColor: colors.textPrimary },
  gateChipText: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.background, fontWeight: "700" },
  actionChip: {
    position: "absolute",
    bottom: spacing.sm,
    right: spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.sm,
    backgroundColor: colors.error,
    alignItems: "center",
    justifyContent: "center",
  },
  actionChipText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary, fontWeight: "600" },
  inlinePanel: {
    position: "absolute",
    bottom: spacing.sm,
    left: spacing.sm,
    right: spacing.sm,
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: spacing.xs,
  },
  inlinePanelTitle: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary },
  inlinePanelRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.xs },
  textInput: {
    fontFamily: fonts.mono,
    fontSize: fontSizes.md,
    color: colors.textPrimary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.xs,
    paddingVertical: spacing.xs / 2,
    minHeight: MIN_TOUCH_TARGET,
  },
  inlineButton: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  inlineButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary },
  errorText: { fontFamily: fonts.sans, fontSize: fontSizes.xs, color: colors.error },
});
