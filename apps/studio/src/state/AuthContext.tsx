import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from "react";
import { Platform } from "react-native";
import { getMe, setUnauthorizedHandler } from "../api/client";
import { clearToken, getToken, setToken } from "../api/tokenStorage";
import type { AuthenticatedUser } from "../api/types";

/** Web-only: the API's OAuth callback redirects to `#token=<jwt>` (a URL
 * fragment, never sent to any server — see services/api/app/auth.py's
 * `google_callback`). Consumed once on load, then stripped from the URL. */
function consumeWebRedirectToken(): string | null {
  if (Platform.OS !== "web" || !globalThis.window) return null;
  const hash = globalThis.window.location.hash;
  if (!hash.startsWith("#token=")) return null;
  const token = new URLSearchParams(hash.slice(1)).get("token");
  globalThis.window.history.replaceState(null, "", globalThis.window.location.pathname);
  return token;
}

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthenticatedUser | null;
  /** Stores a freshly-issued JWT (Requirement 3) and loads the user it belongs to. */
  login: (token: string) => Promise<void>;
  /** Requirement 7: logging out is just discarding the stored JWT client-side. */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  const logout = useCallback(async () => {
    await clearToken();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const login = useCallback(async (token: string) => {
    await setToken(token);
    const me = await getMe();
    setUser(me);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    // Edge Case 10: any authenticated REST call that comes back 401 clears the
    // token and drops the app back to Login — no confirm dialog, this isn't a
    // user-initiated action, just a state transition following an already-
    // expired session.
    setUnauthorizedHandler(() => {
      void logout();
    });
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    (async () => {
      const redirectToken = consumeWebRedirectToken();
      const existing = redirectToken ?? (await getToken());
      if (!existing) {
        setStatus("unauthenticated");
        return;
      }
      try {
        if (redirectToken) await setToken(redirectToken);
        const me = await getMe();
        setUser(me);
        setStatus("authenticated");
      } catch {
        await clearToken();
        setStatus("unauthenticated");
      }
    })();
  }, []);

  const value = useMemo(() => ({ status, user, login, logout }), [status, user, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
