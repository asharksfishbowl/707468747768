import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

/**
 * Platform-abstracted JWT storage (Requirement 3): `expo-secure-store` on
 * iOS/Android, `localStorage` on web (SecureStore has no web implementation).
 * The platform check happens once, here, rather than in each exported
 * function.
 */
const TOKEN_KEY = "cirq-sandbox-studio-jwt";

const backend =
  Platform.OS === "web"
    ? {
        get: async () => globalThis.localStorage?.getItem(TOKEN_KEY) ?? null,
        set: async (token: string) => globalThis.localStorage?.setItem(TOKEN_KEY, token),
        clear: async () => globalThis.localStorage?.removeItem(TOKEN_KEY),
      }
    : {
        get: () => SecureStore.getItemAsync(TOKEN_KEY),
        set: (token: string) => SecureStore.setItemAsync(TOKEN_KEY, token),
        clear: () => SecureStore.deleteItemAsync(TOKEN_KEY),
      };

export const getToken = (): Promise<string | null> => backend.get();
export const setToken = (token: string): Promise<void> => backend.set(token).then(() => undefined);
export const clearToken = (): Promise<void> => backend.clear().then(() => undefined);
