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

export { API_BASE_URL } from "@/lib/env";
import { API_BASE_URL } from "@/lib/env";

export type Health = {
  ok: boolean;
  schema_version: number | null;
};

export type Session = {
  user_id: number;
  name: string;
  expires_at: string;
};

/** What `GET /health/auth` puts on the wire: the session, or literal `null`. */
type AuthHealthBody = Session | null;

/**
 * The three outcomes of asking "am I signed in", kept apart by construction.
 *
 * `GET /health/auth` answers **200 with `null`** for an anonymous caller rather
 * than 401 — deliberately, so one `curl` answers the question. That makes
 * "reachable, nobody signed in" and "could not reach the API" two different
 * facts that a nullable return type cannot express: a caller with
 * `Session | null` in hand has already lost the difference, and the only place
 * left to notice it is a `catch` block that is easy to write as
 * `.catch(() => signedOut)`.
 *
 * Modelling it as a union means the compiler asks every caller which of the
 * three it means, and "no session" can no longer be rendered as a connectivity
 * error — which is what reached a learner's phone.
 */
export type SessionState =
  | { kind: "signed-in"; session: Session }
  | { kind: "anonymous" }
  | { kind: "unreachable"; message: string };

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

/** One correction, the same shape learners already read in Telegram. */
export type Correction = {
  you_said: string;
  correct_form: string;
  error_type: string;
  explanation: string;
  murphy_units: string | null;
};

export type CorrectionResult = {
  is_english: boolean;
  has_errors: boolean;
  did_well: string;
  corrections: Correction[];
};

/**
 * Correct a piece of free writing.
 *
 * `Content-Type: application/json` is not decoration — it is what keeps this a
 * preflighted request. A form encoding would make it a simple request, and the
 * CORS preflight is the actual CSRF barrier for this API (see
 * `apps/api/README.md`). The route refuses anything else with 415.
 */
export function requestCorrection(text: string): Promise<CorrectionResult> {
  return request<CorrectionResult>("/correct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

/**
 * Ask whether this browser has a session. **Never throws.**
 *
 * A rejected promise here is what let "nobody is signed in yet" be rendered as
 * "could not reach the API". Every outcome comes back as a value the caller has
 * to name, so the anonymous case cannot fall into an error path by default.
 */
export async function getAuthHealth(): Promise<SessionState> {
  let body: AuthHealthBody;
  try {
    body = await request<AuthHealthBody>("/health/auth");
  } catch (error) {
    // Transport failure, a CORS refusal, or any non-2xx. This is the only
    // branch the connectivity message may come from.
    return {
      kind: "unreachable",
      message:
        error instanceof Error
          ? error.message
          : `Could not reach the API at ${API_BASE_URL}.`,
    };
  }
  // 200 with a null body is a complete, successful answer: reachable, and
  // nobody is signed in. It is the ordinary state of a first visit.
  return body ? { kind: "signed-in", session: body } : { kind: "anonymous" };
}

/**
 * One item as the learner receives it — **the hidden half is not on the wire.**
 *
 * `projection` is `Record<string, unknown>` on purpose. Mirroring the eleven
 * projection shapes here would be a second learner-visible serialiser in
 * TypeScript, which is the one thing W6 exists to prevent:
 * `core.items.projection.visible_projection` decides what a learner sees, the
 * blind-solver probe is shown exactly that, and this type's job is to carry the
 * decision unaltered. The eleven presentation components narrow it, each for
 * its own type and nowhere else (`components/items/presentation/index.ts`).
 *
 * `response_mode` arrives from the server so this app holds no copy of
 * `core.items.RESPONSE_MODE`. A mirrored table is a table that drifts.
 */
export type ItemPresentation = {
  id: number;
  response_mode: string;
  projection: Record<string, unknown>;
};

/**
 * One learner response. The client sends the field its mode produces; the
 * server decides which one *is* the answer, from the item's own type.
 */
export type ItemAnswer = {
  text?: string;
  option?: string;
  tile_index?: number;
  order?: string[];
  pairs?: Record<string, string>;
  self_marked?: boolean;
  latency_ms?: number;
};

/**
 * The verdict and the teaching half — **a different type from
 * `ItemPresentation`, deliberately.** `canonical` is the answer, and keeping it
 * in a separate shape is what makes "before grading" and "after grading" two
 * types rather than one type with a nullable field somebody forgets to check.
 *
 * `explanation` is almost always null: the generator prompt never asks for one
 * (#103). `murphy_units` is present when the item declares an error type
 * (#104).
 */
export type ItemAnswerResult = {
  correct: boolean;
  graded_by: string;
  canonical: string | null;
  explanation: string | null;
  murphy_units: string | null;
};

/** This learner's validated bank. */
export function getItems(limit = 20): Promise<ItemPresentation[]> {
  return request<ItemPresentation[]>(`/items?limit=${limit}`);
}

/**
 * Submit one response. **All grading happens on the other end of this call.**
 *
 * There is no client-side comparison anywhere in this app and there is nothing
 * to compare against: the projection carries no answer. "Instant feedback" is
 * one network round trip, because an optimistic check would be a second
 * definition of "the answer" — and `core/items/grading.py`'s fold is shared
 * with the uniqueness gate, so a fourth fold here would let an item pass the
 * gate and then be marked wrong for the identical string.
 */
export function answerItem(
  itemId: number,
  answer: ItemAnswer,
): Promise<ItemAnswerResult> {
  return request<ItemAnswerResult>(`/items/${itemId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  });
}

/**
 * Where the item's audio lives. Fetched by the browser on tap, never on load.
 *
 * A URL rather than a fetch: an `<audio src>` lets the platform handle range
 * requests, buffering and the lock-screen controls, and the cookie rides along
 * because the element is same-origin-credentialled by `crossOrigin`.
 */
export function itemAudioUrl(itemId: number): string {
  return `${API_BASE_URL}/items/${itemId}/audio`;
}
