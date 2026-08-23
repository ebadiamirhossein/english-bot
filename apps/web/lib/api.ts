/**
 * Typed client for the FastAPI backend.
 *
 * Hand-written at W1b because there is exactly one route to type. From W3 it
 * is generated from the OpenAPI schema `apps/api/schemas` produces, so a
 * renamed field is a TypeScript error here rather than `undefined` on a
 * phone.
 *
 * It exists now for one reason: to prove the browser can reach the API and
 * get past CORS before any feature depends on it.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Health = {
  ok: boolean;
  schema_version: number | null;
};

/** The resolved session. Untyped until W2 gives a session a shape. */
export type AuthHealth = Record<string, unknown> | null;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      // The session cookie arrives at W2; sending credentials from the start
      // means CORS is exercised in its real shape, not a laxer one.
      credentials: "include",
      headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // A CORS refusal and a dead server look identical from here — say so
    // rather than inventing a reason.
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. It may be down, or the ` +
        `origin may not be allowed.`,
    );
  }

  if (!response.ok) {
    throw new ApiError(`${path} returned ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

export function getAuthHealth(): Promise<AuthHealth> {
  return request<AuthHealth>("/health/auth");
}
