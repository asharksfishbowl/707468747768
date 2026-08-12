import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { deleteCircuit, getCircuit, listMyCircuits, updateCircuit } from "../api/client";
import type { CircuitFull, CircuitSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";

interface MyCircuitsScreenProps {
  active: boolean;
  onLoadCircuit: (circuit: CircuitFull) => void;
  onNavigateToBuilder: () => void;
}

/** My Circuits screen (Requirement 43). */
export function MyCircuitsScreen({ active, onLoadCircuit, onNavigateToBuilder }: MyCircuitsScreenProps) {
  const [circuits, setCircuits] = useState<CircuitSummary[]>([]);
  const [pendingDelete, setPendingDelete] = useState<CircuitSummary | null>(null);

  const refresh = useCallback(() => {
    listMyCircuits().then(setCircuits);
  }, []);

  useEffect(() => {
    if (active) refresh();
  }, [active, refresh]);

  const handleLoad = async (circuit: CircuitSummary) => {
    const full = await getCircuit(circuit.id);
    onLoadCircuit(full);
  };

  const handleTogglePublic = async (circuit: CircuitSummary) => {
    await updateCircuit(circuit.id, { is_public: !circuit.is_public });
    refresh();
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    await deleteCircuit(pendingDelete.id);
    setPendingDelete(null);
    refresh();
  };

  if (circuits.length === 0) {
    return (
      <View style={styles.screen}>
        <EmptyState icon="○" message="No saved circuits yet" ctaLabel="Create your first circuit" onPressCta={onNavigateToBuilder} />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <FlatList
        data={circuits}
        keyExtractor={(c) => c.id}
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => handleLoad(item)}>
            <View style={styles.rowMain}>
              <Text style={styles.name}>{item.name}</Text>
              <Text style={styles.meta}>
                {item.processor_id} · updated {new Date(item.updated_at).toLocaleDateString()}
              </Text>
            </View>
            <View style={styles.rowActions}>
              <Text style={styles.badge}>{item.is_public ? "Public" : "Private"}</Text>
              <Switch value={item.is_public} onValueChange={() => handleTogglePublic(item)} />
              <Pressable style={styles.deleteButton} onPress={() => setPendingDelete(item)}>
                <Text style={styles.deleteButtonText}>Delete</Text>
              </Pressable>
            </View>
          </Pressable>
        )}
      />
      <ConfirmDialog
        visible={pendingDelete !== null}
        title="Delete this circuit?"
        body="This can't be undone."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    minHeight: MIN_TOUCH_TARGET,
  },
  rowMain: { flex: 1 },
  name: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.textPrimary },
  meta: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.textMuted },
  rowActions: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  badge: { fontFamily: fonts.sans, fontSize: fontSizes.xs, color: colors.textMuted },
  deleteButton: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.xs,
    justifyContent: "center",
    borderRadius: radii.sm,
    backgroundColor: colors.surfaceElevated,
  },
  deleteButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.error },
});
