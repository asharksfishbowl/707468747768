import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AppShell } from "./src/navigation/AppShell";
import { AuthProvider } from "./src/state/AuthContext";

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AppShell />
        <StatusBar style="light" />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
