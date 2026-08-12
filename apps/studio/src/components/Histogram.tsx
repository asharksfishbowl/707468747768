import React, { useMemo } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withRepeat, withSequence, withTiming } from "react-native-reanimated";
import type { CircuitDefinition } from "../api/types";
import type { RunStatus } from "../api/types";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { spacing } from "../theme/spacing";

const CHART_HEIGHT = 160;
const BAR_WIDTH = 28;
const HEADROOM = 1.2;

/** Every MEASURE key in `definition`, in the order it's first placed, with the
 * number of qubits it spans — used to pre-plot the full, fixed outcome-space
 * x-axis before any `partial_histogram` data has arrived (design spec's
 * Live-Streaming Histogram, point 1: "Bar positions — fixed at run start"). */
function measureKeyBitWidths(definition: CircuitDefinition): { key: string; bitWidth: number }[] {
  const seen: { key: string; bitWidth: number }[] = [];
  for (const moment of definition.moments) {
    for (const placement of moment) {
      if (placement.gate === "MEASURE" && placement.key && !seen.some((s) => s.key === placement.key)) {
        seen.push({ key: placement.key, bitWidth: placement.qubits.length });
      }
    }
  }
  return seen;
}

interface HistogramProps {
  definition: CircuitDefinition;
  histogram: Record<string, Record<string, number>> | null;
  status: RunStatus;
}

/**
 * Live/final histogram (design spec's "Live-Streaming Histogram"): fixed bar
 * positions plotted at run start, cumulative counts animate in as
 * `partial_histogram` messages arrive, semi-transparent while streaming vs.
 * solid on the final `done` message.
 */
export function Histogram({ definition, histogram, status }: HistogramProps) {
  const keys = useMemo(() => measureKeyBitWidths(definition), [definition]);
  const isFinal = status === "done";

  return (
    <View>
      {keys.map(({ key, bitWidth }) => (
        <KeyHistogram
          key={key}
          measureKey={key}
          bitWidth={bitWidth}
          counts={histogram?.[key] ?? {}}
          isFinal={isFinal}
        />
      ))}
    </View>
  );
}

function KeyHistogram({
  measureKey,
  bitWidth,
  counts,
  isFinal,
}: {
  measureKey: string;
  bitWidth: number;
  counts: Record<string, number>;
  isFinal: boolean;
}) {
  const outcomeCount = 2 ** bitWidth;
  const maxCount = Math.max(1, ...Object.values(counts));
  const ceiling = maxCount * HEADROOM;

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <Text style={styles.title}>{measureKey}</Text>
        {isFinal ? <Text style={styles.finalBadge}>Final Result</Text> : <StreamingIndicator />}
      </View>
      <ScrollView horizontal style={{ height: CHART_HEIGHT + 24 }}>
        {Array.from({ length: outcomeCount }, (_, i) => {
          const label = i.toString(2).padStart(bitWidth, "0");
          const value = counts[String(i)] ?? 0;
          return <Bar key={label} label={label} value={value} ceiling={ceiling} isFinal={isFinal} />;
        })}
      </ScrollView>
    </View>
  );
}

function Bar({ label, value, ceiling, isFinal }: { label: string; value: number; ceiling: number; isFinal: boolean }) {
  const heightRatio = useSharedValue(0);

  React.useEffect(() => {
    heightRatio.value = withTiming(value / ceiling, { duration: 100 });
  }, [value, ceiling, heightRatio]);

  const animatedStyle = useAnimatedStyle(() => ({
    height: Math.max(2, heightRatio.value * CHART_HEIGHT),
  }));

  return (
    <View style={styles.barColumn}>
      <View style={styles.barTrack}>
        <Animated.View
          style={[
            styles.bar,
            { backgroundColor: isFinal ? colors.histogramFinal : colors.histogramStreaming },
            animatedStyle,
          ]}
        />
      </View>
      <Text style={styles.barLabel}>{label}</Text>
      <Text style={styles.barValue}>{value}</Text>
    </View>
  );
}

function StreamingIndicator() {
  const opacity = useSharedValue(1);

  React.useEffect(() => {
    opacity.value = withRepeat(withSequence(withTiming(0.4, { duration: 600 }), withTiming(1, { duration: 600 })), -1);
  }, [opacity]);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <Animated.Text style={[styles.streamingBadge, animatedStyle]}>Streaming…</Animated.Text>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: spacing.sm },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  title: { fontFamily: fonts.mono, fontSize: fontSizes.sm, color: colors.textPrimary },
  finalBadge: { fontFamily: fonts.sans, fontSize: fontSizes.xs, color: colors.success },
  streamingBadge: { fontFamily: fonts.sans, fontSize: fontSizes.xs, color: colors.textMuted },
  barColumn: { width: BAR_WIDTH, alignItems: "center", marginRight: spacing.xs / 2 },
  barTrack: { height: CHART_HEIGHT, justifyContent: "flex-end" },
  bar: { width: BAR_WIDTH - 8, borderRadius: 2 },
  barLabel: { fontFamily: fonts.mono, fontSize: 9, color: colors.textMuted, marginTop: 2 },
  barValue: { fontFamily: fonts.mono, fontSize: 9, color: colors.textPrimary },
});
