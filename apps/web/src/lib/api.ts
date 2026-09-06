// Thin client for the AURA API boundary (services/api).
// Everything the frontend shows in Phase 1 must come from a real backend
// response through this module - no mocked/fake payloads live here.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface LivenessResponse {
  status: string;
}

export interface ReadinessResponse {
  status: "ok" | "unavailable";
  checks: {
    database: "ok" | "unavailable";
    redis: "ok" | "unavailable";
  };
}

export interface ServiceStatusResponse {
  name: string;
  version: string;
  environment: string;
}

export class ApiUnreachableError extends Error {
  constructor(cause: unknown) {
    super("Could not reach the AURA API");
    this.cause = cause;
  }
}

async function getJson<T>(path: string): Promise<{ httpStatus: number; body: T }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  } catch (cause) {
    throw new ApiUnreachableError(cause);
  }

  const body = (await response.json()) as T;
  return { httpStatus: response.status, body };
}

export function getLiveness(): Promise<{ httpStatus: number; body: LivenessResponse }> {
  return getJson<LivenessResponse>("/healthz");
}

export function getReadiness(): Promise<{ httpStatus: number; body: ReadinessResponse }> {
  return getJson<ReadinessResponse>("/readyz");
}

export function getServiceStatus(): Promise<{ httpStatus: number; body: ServiceStatusResponse }> {
  return getJson<ServiceStatusResponse>("/api/v1/status");
}

export { API_BASE_URL };
