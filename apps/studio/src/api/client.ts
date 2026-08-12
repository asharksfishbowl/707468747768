import { API_BASE_URL, WS_BASE_URL } from "../config";
import { getToken } from "./tokenStorage";
import type {
  AuthenticatedUser,
  CircuitDefinition,
  CircuitFull,
  CircuitSummary,
  GalleryCircuit,
  Processor,
  RunStatus,
  RunSummary,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Fires whenever any authenticated request gets a `401` — Edge Case 10:
 * client discards the JWT and returns to Login. `AuthContext` registers the
 * handler; this module only knows "a 401 happened", not what to do about it
 * (one function, one job — HTTP mechanics here, session policy in
 * AuthContext).
 */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** Same "a 401/auth-failure happened" signal as `request()`'s 401 branch
 * below, but reachable from `openRunStream`'s WS close-code 4401 (Requirement
 * 5/Edge Case 11) — the REST and WS paths share one JWT, so they share one
 * notion of "this session is no longer valid" rather than each reinventing
 * their own. */
export function notifyUnauthorized(): void {
  onUnauthorized?.();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401) {
    notifyUnauthorized();
    throw new ApiError(401, "session expired");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth (Requirements 1, 2, 6)
// ---------------------------------------------------------------------------

/** URL to open in a browser/auth session to start the Google OAuth flow. */
export function googleLoginUrl(): string {
  return `${API_BASE_URL}/auth/google/login`;
}

export function getMe(): Promise<AuthenticatedUser> {
  return request("/auth/me");
}

// ---------------------------------------------------------------------------
// Processors (Requirement 8)
// ---------------------------------------------------------------------------

export function listProcessors(): Promise<Processor[]> {
  return request("/processors");
}

// ---------------------------------------------------------------------------
// Circuits (Requirements 16-23)
// ---------------------------------------------------------------------------

export function listPresets(processorId: string): Promise<CircuitDefinition[]> {
  return request(`/circuits/presets?processor_id=${encodeURIComponent(processorId)}`);
}

export function listMyCircuits(page = 1): Promise<CircuitSummary[]> {
  return request(`/circuits?page=${page}`);
}

export function listGallery(page = 1): Promise<GalleryCircuit[]> {
  return request(`/circuits/gallery?page=${page}`);
}

export function getCircuit(id: string): Promise<CircuitFull> {
  return request(`/circuits/${id}`);
}

export function createCircuit(body: {
  name: string;
  definition: CircuitDefinition;
  is_public: boolean;
}): Promise<CircuitFull> {
  return request("/circuits", { method: "POST", body: JSON.stringify(body) });
}

export function updateCircuit(
  id: string,
  body: Partial<{ name: string; definition: CircuitDefinition; is_public: boolean }>,
): Promise<CircuitFull> {
  return request(`/circuits/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteCircuit(id: string): Promise<void> {
  return request(`/circuits/${id}`, { method: "DELETE" });
}

export function cloneCircuit(id: string): Promise<CircuitFull> {
  return request(`/circuits/${id}/clone`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Runs (Requirements 24-26, 35-36)
// ---------------------------------------------------------------------------

export function createRun(body: {
  circuit_id: string | null;
  definition: CircuitDefinition | null;
  processor_id: string;
  noisy: boolean;
  repetitions: number;
}): Promise<{ run_id: string; status: RunStatus }> {
  return request("/runs", { method: "POST", body: JSON.stringify(body) });
}

export function listMyRuns(page = 1): Promise<RunSummary[]> {
  return request(`/runs?page=${page}`);
}

export function getRun(id: string): Promise<RunSummary> {
  return request(`/runs/${id}`);
}

// ---------------------------------------------------------------------------
// Run stream (Requirements 5, 34)
// ---------------------------------------------------------------------------

/** Opens `WS /runs/{id}/stream?token=<jwt>` (Requirement 5 — the JWT arrives
 * as a query param since browser `WebSocket` can't set headers). */
export async function openRunStream(runId: string): Promise<WebSocket> {
  const token = await getToken();
  return new WebSocket(`${WS_BASE_URL}/runs/${runId}/stream?token=${token ?? ""}`);
}
