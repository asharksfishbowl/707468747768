import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";

export type EmptyStateTone = "empty" | "error";

interface EmptyStateProps {
  tone?: EmptyStateTone;
  icon: string;
  message: string;
  ctaLabel?: string;
  onPressCta?: () => void;
}

/**
 * Shared centered icon+message+(optional CTA) layout — design spec's
 * Empty/Error States: one layout, reused for every screen's empty state and
 * for the Builder's post-Run worker/runtime-error state (scoped to the run
 * panel region, not this component's concern — the parent decides where to
 * mount it).
 */
export function EmptyState({ tone = "empty", icon, message, ctaLabel, onPressCta }: EmptyStateProps) {
  const tintColor = tone === "error" ? colors.error : colors.textMuted;

  return (
    <View style={styles.container}>
      <Text style={[styles.icon, { color: tintColor }]}>{icon}</Text>
      <Text style={[styles.message, { color: tintColor }]}>{message}</Text>
      {ctaLabel && onPressCta && (
        <Pressable style={styles.cta} onPress={onPressCta}>
          <Text style={styles.ctaText}>{ctaLabel}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
    gap: spacing.xs,
  },
  icon: {
    fontSize: fontSizes.xl,
  },
  message: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.md,
    textAlign: "center",
  },
  cta: {
    marginTop: spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.sm,
    justifyContent: "center",
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.sm,
  },
  ctaText: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.sm,
    color: colors.textPrimary,
  },
});
