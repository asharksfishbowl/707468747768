import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { cloneCircuit, getCircuit, listGallery } from "../api/client";
import type { CircuitFull, GalleryCircuit } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { StaticCircuitView } from "../components/StaticCircuitView";
import { Toast } from "../components/Toast";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";

interface GalleryScreenProps {
  active: boolean;
}

/** Gallery screen (Requirement 45). */
export function GalleryScreen({ active }: GalleryScreenProps) {
  const [circuits, setCircuits] = useState<GalleryCircuit[]>([]);
  const [preview, setPreview] = useState<CircuitFull | null>(null);
  const [cloneToast, setCloneToast] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listGallery().then(setCircuits);
  }, []);

  useEffect(() => {
    if (active) refresh();
  }, [active, refresh]);

  const openPreview = async (circuit: GalleryCircuit) => {
    setPreview(await getCircuit(circuit.id));
  };

  const handleClone = async () => {
    if (!preview) return;
    await cloneCircuit(preview.id);
    setCloneToast("Cloned to My Circuits");
  };

  if (circuits.length === 0) {
    return (
      <View style={styles.screen}>
        <EmptyState icon="○" message="No public circuits yet" />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <FlatList
        data={circuits}
        keyExtractor={(c) => c.id}
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => openPreview(item)}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.meta}>
              {item.processor_id} · {item.owner_display_name}
            </Text>
          </Pressable>
        )}
      />

      <Modal visible={preview !== null} animationType="slide" onRequestClose={() => setPreview(null)}>
        <View style={styles.detailScreen}>
          <Pressable style={styles.closeButton} onPress={() => setPreview(null)}>
            <Text style={styles.closeButtonText}>Close</Text>
          </Pressable>
          {preview && (
            <>
              <Text style={styles.name}>{preview.name}</Text>
              <Text style={styles.meta}>
                {preview.processor_id} · {preview.is_public ? "Public" : "Private"}
              </Text>
              <StaticCircuitView definition={preview.definition} />
              <Pressable style={styles.cloneButton} onPress={handleClone}>
                <Text style={styles.cloneButtonText}>Clone</Text>
              </Pressable>
            </>
          )}
          <Toast message={cloneToast} tone="success" onDismiss={() => setCloneToast(null)} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  row: {
    padding: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  name: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.textPrimary },
  meta: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.textMuted },
  detailScreen: { flex: 1, backgroundColor: colors.background, padding: spacing.sm, gap: spacing.sm },
  closeButton: { alignSelf: "flex-end", minHeight: MIN_TOUCH_TARGET, justifyContent: "center" },
  closeButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary },
  cloneButton: {
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: radii.sm,
    backgroundColor: colors.gateRotation,
    alignItems: "center",
    justifyContent: "center",
  },
  cloneButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.background, fontWeight: "700" },
});
