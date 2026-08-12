import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";
import { GATE_BY_ID, GATE_CATEGORY_COLOR, GATE_DEFINITIONS, type GateCategory, type GateId } from "../theme/gates";

const CATEGORY_ORDER: GateCategory[] = ["rotation", "pauli", "twoQubit", "measure"];
const CATEGORY_LABEL: Record<GateCategory, string> = {
  rotation: "Rotation",
  pauli: "Pauli / H / S / T",
  twoQubit: "Two-qubit",
  measure: "Measure",
};

interface GatePaletteProps {
  armedGate: GateId | null;
  onArm: (gate: GateId) => void;
  /** "rail" = fixed web/desktop left rail (Builder Layout, web ≥900px).
   * "drawer" = mobile swipe-up bottom sheet, collapsed by default. */
  variant: "rail" | "drawer";
}

export function GatePalette({ armedGate, onArm, variant }: GatePaletteProps) {
  const [expanded, setExpanded] = useState(false);

  if (variant === "drawer" && !expanded) {
    return (
      <Pressable style={styles.handleBar} onPress={() => setExpanded(true)}>
        <View style={styles.handle} />
        {armedGate && (
          <View style={[styles.armedIndicator, { backgroundColor: GATE_CATEGORY_COLOR[gateCategory(armedGate)] }]}>
            <Text style={styles.armedIndicatorText}>{armedGate}</Text>
          </View>
        )}
      </Pressable>
    );
  }

  const content = (
    <>
      {variant === "drawer" && (
        <Pressable style={styles.handleBar} onPress={() => setExpanded(false)}>
          <View style={styles.handle} />
        </Pressable>
      )}
      {CATEGORY_ORDER.map((category) => (
        <View key={category} style={styles.categoryGroup}>
          <Text style={[styles.categoryLabel, { color: GATE_CATEGORY_COLOR[category] }]}>
            {CATEGORY_LABEL[category]}
          </Text>
          <View style={styles.gateWrap}>
            {GATE_DEFINITIONS.filter((g) => g.category === category).map((gate) => {
              const armed = armedGate === gate.id;
              const color = GATE_CATEGORY_COLOR[category];
              return (
                <Pressable
                  key={gate.id}
                  onPress={() => {
                    onArm(gate.id);
                    if (variant === "drawer") setExpanded(false);
                  }}
                  style={[
                    styles.gateButton,
                    gate.category === "measure" ? { borderColor: color, borderWidth: 2 } : { backgroundColor: color },
                    armed ? styles.gateButtonArmed : null,
                    armedGate && !armed ? styles.gateButtonDimmed : null,
                  ]}
                >
                  <Text style={[styles.gateButtonText, gate.category === "measure" ? { color } : null]}>
                    {gate.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}
    </>
  );

  if (variant === "rail") {
    return <ScrollView style={styles.rail}>{content}</ScrollView>;
  }
  return <View style={styles.drawerExpanded}>{content}</View>;
}

function gateCategory(gate: GateId): GateCategory {
  return GATE_BY_ID[gate].category;
}

const styles = StyleSheet.create({
  rail: {
    width: 180,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    padding: spacing.xs,
  },
  drawerExpanded: {
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    padding: spacing.xs,
    maxHeight: 320,
  },
  handleBar: { alignItems: "center", paddingVertical: spacing.xs, flexDirection: "row", justifyContent: "center", gap: spacing.xs },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border },
  armedIndicator: { position: "absolute", right: spacing.sm, borderRadius: radii.sm, paddingHorizontal: spacing.xs, paddingVertical: 2 },
  armedIndicatorText: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.background, fontWeight: "700" },
  categoryGroup: { marginBottom: spacing.sm },
  categoryLabel: { fontFamily: fonts.sans, fontSize: fontSizes.xs, marginBottom: spacing.xs / 2, textTransform: "uppercase" },
  gateWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  gateButton: {
    minWidth: MIN_TOUCH_TARGET,
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.xs,
    borderRadius: radii.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  gateButtonArmed: { borderWidth: 2, borderColor: colors.textPrimary },
  gateButtonDimmed: { opacity: 0.6 },
  gateButtonText: { fontFamily: fonts.mono, fontSize: fontSizes.sm, color: colors.background, fontWeight: "700" },
});
