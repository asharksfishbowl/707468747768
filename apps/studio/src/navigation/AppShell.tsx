import React, { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { BuilderScreen } from "../screens/Builder";
import { GalleryScreen } from "../screens/Gallery";
import { Login } from "../screens/Login";
import { MyCircuitsScreen } from "../screens/MyCircuits";
import { RunHistoryScreen } from "../screens/RunHistory";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useAuth } from "../state/AuthContext";
import type { CircuitFull } from "../api/types";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, spacing, WEB_LAYOUT_BREAKPOINT } from "../theme/spacing";

type Destination = "builder" | "myCircuits" | "runHistory" | "gallery" | "account";

const DESTINATIONS: { id: Destination; label: string }[] = [
  { id: "builder", label: "Builder" },
  { id: "myCircuits", label: "My Circuits" },
  { id: "runHistory", label: "Run History" },
  { id: "gallery", label: "Gallery" },
  { id: "account", label: "Account" },
];

/**
 * Nav shell + top-level screen switcher (design spec's Cross-Cutting
 * Navigation). All 5 screens stay mounted simultaneously (visibility
 * toggled via `display`, not conditional rendering) so the Builder screen's
 * in-progress circuit and the Run panel's WebSocket connection survive
 * switching to another destination and back — the list screens (My
 * Circuits/Run History/Gallery) instead take an `active` prop and refetch
 * whenever they become the visible destination, so their data still stays
 * fresh without needing a remount.
 */
export function AppShell() {
  const { status, user, logout } = useAuth();
  const { width } = useWindowDimensions();
  const isWebLayout = width >= WEB_LAYOUT_BREAKPOINT;
  const [destination, setDestination] = useState<Destination>("builder");
  const [loadRequest, setLoadRequest] = useState<CircuitFull | null>(null);

  if (status === "loading") {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.textPrimary} />
      </View>
    );
  }

  if (status === "unauthenticated") {
    return <Login />;
  }

  const handleLoadCircuit = (circuit: CircuitFull) => {
    setLoadRequest(circuit);
    setDestination("builder");
  };

  const nav = (
    <NavBar destination={destination} onSelect={setDestination} orientation={isWebLayout ? "side" : "bottom"} />
  );

  return (
    <View style={[styles.root, isWebLayout ? styles.rootRow : styles.rootColumn]}>
      {isWebLayout && nav}
      <View style={styles.content}>
        <Screen visible={destination === "builder"}>
          <BuilderScreen loadRequest={loadRequest} onConsumeLoadRequest={() => setLoadRequest(null)} />
        </Screen>
        <Screen visible={destination === "myCircuits"}>
          <MyCircuitsScreen
            active={destination === "myCircuits"}
            onLoadCircuit={handleLoadCircuit}
            onNavigateToBuilder={() => setDestination("builder")}
          />
        </Screen>
        <Screen visible={destination === "runHistory"}>
          <RunHistoryScreen active={destination === "runHistory"} />
        </Screen>
        <Screen visible={destination === "gallery"}>
          <GalleryScreen active={destination === "gallery"} />
        </Screen>
        <Screen visible={destination === "account"}>
          <AccountView email={user?.email ?? ""} displayName={user?.display_name ?? ""} onLogout={logout} />
        </Screen>
      </View>
      {!isWebLayout && nav}
    </View>
  );
}

function Screen({ visible, children }: { visible: boolean; children: React.ReactNode }) {
  return <View style={[styles.screenLayer, { display: visible ? "flex" : "none" }]}>{children}</View>;
}

function NavBar({
  destination,
  onSelect,
  orientation,
}: {
  destination: Destination;
  onSelect: (d: Destination) => void;
  orientation: "side" | "bottom";
}) {
  return (
    <View style={orientation === "side" ? styles.sideNav : styles.bottomNav}>
      {DESTINATIONS.map((d) => (
        <Pressable key={d.id} style={styles.navItem} onPress={() => onSelect(d.id)}>
          <Text style={destination === d.id ? styles.navItemActive : styles.navItemText}>{d.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function AccountView({ email, displayName, onLogout }: { email: string; displayName: string; onLogout: () => void }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <View style={styles.account}>
      <Text style={styles.accountName}>{displayName}</Text>
      <Text style={styles.accountEmail}>{email}</Text>
      <Pressable style={styles.logoutButton} onPress={() => setConfirming(true)}>
        <Text style={styles.logoutButtonText}>Log out</Text>
      </Pressable>
      <ConfirmDialog
        visible={confirming}
        title="Log out?"
        body="You'll need to sign in again to continue."
        confirmLabel="Log out"
        variant="accent"
        onConfirm={() => {
          setConfirming(false);
          onLogout();
        }}
        onCancel={() => setConfirming(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  root: { flex: 1, backgroundColor: colors.background },
  rootRow: { flexDirection: "row" },
  rootColumn: { flexDirection: "column" },
  content: { flex: 1 },
  screenLayer: { flex: 1 },
  sideNav: { width: 180, borderRightWidth: 1, borderRightColor: colors.border, paddingTop: spacing.sm },
  bottomNav: { flexDirection: "row", borderTopWidth: 1, borderTopColor: colors.border },
  navItem: { flex: 1, minHeight: MIN_TOUCH_TARGET, alignItems: "center", justifyContent: "center" },
  navItemText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textMuted },
  navItemActive: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary, fontWeight: "700" },
  account: { flex: 1, padding: spacing.sm, gap: spacing.xs },
  accountName: { fontFamily: fonts.sans, fontSize: fontSizes.lg, color: colors.textPrimary },
  accountEmail: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textMuted },
  logoutButton: {
    marginTop: spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: 8,
    backgroundColor: colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
    maxWidth: 200,
  },
  logoutButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.textPrimary },
});
