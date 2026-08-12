import React, { useEffect } from "react";
import { StyleSheet, Text } from "react-native";
import Animated, { runOnJS, useSharedValue, useAnimatedStyle, withDelay, withTiming } from "react-native-reanimated";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { radii, spacing } from "../theme/spacing";

export type ToastTone = "warning" | "success" | "error";

const TONE_COLOR: Record<ToastTone, string> = {
  warning: colors.warning,
  success: colors.success,
  error: colors.error,
};

// Design spec: toasts "auto-dismiss after ~2.5s". Driven through Reanimated's
// timeline (withDelay + withTiming's completion callback) rather than a raw
// timer, consistent with every other state transition in the Grid Interaction
// Model using the same animation primitive.
const AUTO_DISMISS_DELAY_MS = 2500;
const FADE_MS = 200;

interface ToastProps {
  message: string | null;
  tone?: ToastTone;
  onDismiss: () => void;
}

/**
 * Shared transient toast (design spec's Empty/Error States: "one toast
 * component, reused for every pre-Run inline validation message" — also used
 * for the two-qubit "not connected" warning and clone-success feedback).
 */
export function Toast({ message, tone = "warning", onDismiss }: ToastProps) {
  const opacity = useSharedValue(0);

  useEffect(() => {
    if (!message) return;
    opacity.value = withTiming(1, { duration: FADE_MS });
    opacity.value = withDelay(
      AUTO_DISMISS_DELAY_MS,
      withTiming(0, { duration: FADE_MS }, (finished) => {
        if (finished) runOnJS(onDismiss)();
      }),
    );
  }, [message, onDismiss, opacity]);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  if (!message) return null;

  return (
    <Animated.View style={[styles.container, { borderColor: TONE_COLOR[tone] }, animatedStyle]}>
      <Text style={[styles.text, { color: TONE_COLOR[tone] }]}>{message}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    bottom: spacing.md,
    alignSelf: "center",
    backgroundColor: colors.surfaceElevated,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    maxWidth: "90%",
  },
  text: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.sm,
  },
});
