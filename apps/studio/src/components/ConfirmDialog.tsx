import React, { useEffect } from "react";
import { Modal, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";

export type ConfirmVariant = "destructive" | "accent";

interface ConfirmDialogProps {
  visible: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  variant: ConfirmVariant;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Shared confirm-dialog pattern (design spec) — one component for all four
 * v1 triggers (delete circuit/red, logout/accent, load preset/accent, switch
 * processor/accent), copy/color varying only via props. Scrim tap, Android
 * back, and Escape (web) all map to Cancel — never to Confirm.
 */
export function ConfirmDialog({
  visible,
  title,
  body,
  confirmLabel,
  variant,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (Platform.OS !== "web" || !visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    globalThis.window?.addEventListener("keydown", handler);
    return () => globalThis.window?.removeEventListener("keydown", handler);
  }, [visible, onCancel]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <Pressable style={styles.scrim} onPress={onCancel}>
        <Pressable style={styles.card} onPress={() => {}}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.body}>{body}</Text>
          <View style={styles.buttonRow}>
            <Pressable style={[styles.button, styles.cancelButton]} onPress={onCancel}>
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
            <Pressable
              style={[
                styles.button,
                { backgroundColor: variant === "destructive" ? colors.error : colors.gateRotation },
              ]}
              onPress={onConfirm}
            >
              <Text style={styles.confirmText}>{confirmLabel}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.sm,
  },
  card: {
    width: "100%",
    maxWidth: 400,
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.lg,
    padding: spacing.sm,
    gap: spacing.xs,
  },
  title: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.lg,
    color: colors.textPrimary,
    fontWeight: "600",
  },
  body: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.sm,
    color: colors.textMuted,
  },
  buttonRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  button: {
    minHeight: MIN_TOUCH_TARGET,
    minWidth: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  cancelButton: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: colors.border,
  },
  cancelText: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.sm,
    color: colors.textPrimary,
  },
  confirmText: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.sm,
    color: colors.background,
    fontWeight: "600",
  },
});
