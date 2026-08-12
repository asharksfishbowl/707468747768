/**
 * `services/api` base URL. `EXPO_PUBLIC_*` env vars are inlined at build time
 * by Expo automatically (no extra config), so this is set per-environment via
 * a `.env` file or the build/CI environment rather than hardcoded per platform.
 * Falls back to the local dev API for `expo start --web` with no `.env` set.
 */
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");
