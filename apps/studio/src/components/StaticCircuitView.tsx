import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import type { CircuitDefinition, Qubit } from "../api/types";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { radii, spacing } from "../theme/spacing";
import { gateColor } from "../theme/gates";
import { formatQubitLabel, qubitKey } from "../hooks/circuitMath";

const CELL_SIZE = 44;

/** Read-only circuit-snapshot rendering — Run History's "circuit that produced
 * it" and Gallery's preview both need this (design spec: "read-only grid
 * rendering, not editable"), so it's a separate, simpler component rather
 * than bolting a read-only mode onto the interactive `GateGrid`. */
export function StaticCircuitView({ definition }: { definition: CircuitDefinition }) {
  const rows = collectQubits(definition);

  return (
    <ScrollView horizontal>
      <View>
        {rows.map((qubit) => {
          const key = qubitKey(qubit);
          return (
            <View key={key} style={styles.row}>
              <View style={styles.rowHeader}>
                <Text style={styles.rowHeaderText}>{formatQubitLabel(qubit)}</Text>
              </View>
              {definition.moments.map((moment, col) => {
                const placement = moment.find((p) => p.qubits.some((q) => qubitKey(q) === key));
                if (!placement) {
                  return (
                    <View key={col} style={styles.cell}>
                      <View style={styles.wire} />
                    </View>
                  );
                }
                const isMeasure = placement.gate === "MEASURE";
                const color = gateColor(placement.gate);
                return (
                  <View key={col} style={styles.cell}>
                    <View
                      style={[
                        styles.chip,
                        isMeasure ? { borderColor: color, borderWidth: 2 } : { backgroundColor: color },
                      ]}
                    >
                      <Text style={[styles.chipText, isMeasure ? { color } : null]}>
                        {isMeasure ? "M" : placement.gate}
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
}

function collectQubits(definition: CircuitDefinition): Qubit[] {
  const seen = new Map<string, Qubit>();
  for (const moment of definition.moments) {
    for (const placement of moment) {
      for (const qubit of placement.qubits) {
        seen.set(qubitKey(qubit), qubit);
      }
    }
  }
  return Array.from(seen.values());
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center" },
  rowHeader: {
    width: 60,
    height: CELL_SIZE,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.xs / 2,
    marginBottom: spacing.xs / 2,
  },
  rowHeaderText: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.textMuted },
  cell: {
    width: CELL_SIZE,
    height: CELL_SIZE,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.xs / 2,
    marginBottom: spacing.xs / 2,
  },
  wire: { height: 2, width: "100%", backgroundColor: colors.border },
  chip: { width: CELL_SIZE - 10, height: CELL_SIZE - 10, borderRadius: radii.sm, alignItems: "center", justifyContent: "center" },
  chipText: { fontFamily: fonts.mono, fontSize: 10, color: colors.background, fontWeight: "700" },
});
