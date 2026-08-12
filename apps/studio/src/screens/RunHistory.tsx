import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { listMyRuns } from "../api/client";
import type { RunSummary } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Histogram } from "../components/Histogram";
import { StaticCircuitView } from "../components/StaticCircuitView";
import { colors, RUN_STATUS_COLOR } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, spacing } from "../theme/spacing";

interface RunHistoryScreenProps {
  active: boolean;
}

/** Run History screen (Requirement 44). */
export function RunHistoryScreen({ active }: RunHistoryScreenProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunSummary | null>(null);

  const refresh = useCallback(() => {
    listMyRuns().then(setRuns);
  }, []);

  useEffect(() => {
    if (active) refresh();
  }, [active, refresh]);

  if (runs.length === 0) {
    return (
      <View style={styles.screen}>
        <EmptyState icon="○" message="No runs yet" />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <FlatList
        data={runs}
        keyExtractor={(r) => r.id}
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => setDetail(item)}>
            <View style={[styles.statusDot, { backgroundColor: RUN_STATUS_COLOR[item.status] }]} />
            <View style={styles.rowMain}>
              <Text style={styles.name}>{item.processor_id}</Text>
              <Text style={styles.meta}>
                {item.repetitions} reps · {new Date(item.created_at).toLocaleString()}
              </Text>
            </View>
            <Text style={styles.status}>{item.status}</Text>
          </Pressable>
        )}
      />

      <Modal visible={detail !== null} animationType="slide" onRequestClose={() => setDetail(null)}>
        <View style={styles.detailScreen}>
          <Pressable style={styles.closeButton} onPress={() => setDetail(null)}>
            <Text style={styles.closeButtonText}>Close</Text>
          </Pressable>
          {detail && (
            <>
              <Text style={styles.name}>
                {detail.processor_id} · {detail.repetitions} reps
              </Text>
              <StaticCircuitView definition={detail.definition} />
              {detail.status === "error" ? (
                <EmptyState tone="error" icon="⚠" message={detail.error_message ?? "This run failed."} />
              ) : (
                detail.result && (
                  <Histogram definition={detail.definition} histogram={detail.result} status={detail.status} />
                )
              )}
            </>
          )}
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    padding: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    minHeight: MIN_TOUCH_TARGET,
  },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  rowMain: { flex: 1 },
  name: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.textPrimary },
  meta: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.textMuted },
  status: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textMuted },
  detailScreen: { flex: 1, backgroundColor: colors.background, padding: spacing.sm, gap: spacing.sm },
  closeButton: { alignSelf: "flex-end", minHeight: MIN_TOUCH_TARGET, justifyContent: "center" },
  closeButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary },
});
