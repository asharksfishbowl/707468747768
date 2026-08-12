import React, { useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import { googleLoginUrl } from "../api/client";
import { useAuth } from "../state/AuthContext";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";

// Recommended once-per-app-load call for expo-web-browser's auth session
// helper (no-op on web, where the OAuth redirect is a plain page navigation
// instead — see the web branch of signIn below).
WebBrowser.maybeCompleteAuthSession();

function extractToken(url: string): string | null {
  const fragment = url.split("#")[1];
  if (!fragment) return null;
  return new URLSearchParams(fragment).get("token");
}

/** Login screen (Requirement 40, design spec's Screen-by-Screen Reference #1). */
export function Login() {
  const { login } = useAuth();
  const [status, setStatus] = useState<"default" | "redirecting" | "error">("default");

  const signIn = async () => {
    setStatus("redirecting");
    try {
      if (Platform.OS === "web") {
        // Full-page navigation to the API's OAuth entry point; the API
        // redirects back to `${CLIENT_BASE_URL}/auth/callback#token=...`,
        // which AuthContext's bootstrap effect picks up on next page load.
        globalThis.window?.location.assign(googleLoginUrl());
        return;
      }
      const redirectUri = AuthSession.makeRedirectUri({ path: "auth/callback" });
      const result = await WebBrowser.openAuthSessionAsync(googleLoginUrl(), redirectUri);
      if (result.type !== "success") {
        setStatus("default");
        return;
      }
      const token = extractToken(result.url);
      if (!token) {
        setStatus("error");
        return;
      }
      await login(token);
    } catch {
      setStatus("error");
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.wordmark}>Cirq Sandbox Studio</Text>
      <Text style={styles.tagline}>Build and run quantum circuits on Google's virtual QVM.</Text>

      {status === "error" && <Text style={styles.errorText}>Sign-in failed, try again</Text>}

      <Pressable style={styles.button} onPress={signIn} disabled={status === "redirecting"}>
        {status === "redirecting" ? (
          <ActivityIndicator color={colors.background} />
        ) : (
          <Text style={styles.buttonText}>Sign in with Google</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  wordmark: { fontFamily: fonts.sans, fontSize: fontSizes.xl, color: colors.textPrimary, fontWeight: "700" },
  tagline: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.textMuted, textAlign: "center" },
  errorText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.error },
  button: {
    marginTop: spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    minWidth: 220,
    paddingHorizontal: spacing.md,
    borderRadius: radii.sm,
    backgroundColor: colors.textPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.background, fontWeight: "700" },
});
