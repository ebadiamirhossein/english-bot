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
  /**
   * Which session this attempt belongs to. W11.
   *
   * `item_attempts.session_id` has existed since migration 012 and **nothing
   * ever wrote it** — the column was added "for W10", the service took the
   * argument, and no caller passed one. A checkpoint is scored by counting the
   * attempts that belong to its sitting, so it is the first path that cannot
   * work without it.
   */
  session_id?: number;
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
  /**
   * `match_pairs`' correct bijection, **after grading only** (#118). Null for
   * every other type.
   *
   * Its answer is a mapping, not a string, so `canonical` is null for this type
   * by schema rule — which is why a wrong answer used to say "Here it is:" and
   * then show nothing. This is the half W6a could not fix: nothing on the
   * client had the pairing, and supplying it was an API change.
   *
   * It is not a leak. The projection still serves the two columns independently
   * sorted, so the pairing is destroyed in what arrives *before* answering.
   */
  pairs: [string, string][] | null;
};

/**
 * One card as the reviewer renders it (PRD §5, §8.5.4).
 *
 * `intervals` is what each of the four buttons would schedule, **in days,
 * computed on the server**. There is no interval arithmetic in this codebase
 * and nothing here to compute it from — the same rule as grading: the server
 * owns the calculation, the client renders the number it is handed.
 */
export type CardFace = {
  id: number;
  card_type: string;
  front: string;
  back: string;
  cue: string | null;
  context_sentence: string | null;
  source_ref: string | null;
  meaning: string | null;
  register: string;
  neutral_equivalent: string | null;
  who_says_this: string | null;
  /**
   * Whether this card asks for a **typed answer before the reveal** (#157).
   *
   * Decided on the server from `core.cards.TYPED_ANSWER_CARD_TYPES` and sent on
   * the wire, so there is no copy of that table here. A mirrored table is a
   * table that drifts — the same rule `response_mode` follows for items.
   */
  typed: boolean;
  intervals: Record<Rating, number>;
};

/** The four FSRS grades, in the order they are shown. */
export const RATINGS = ["again", "hard", "good", "easy"] as const;
export type Rating = (typeof RATINGS)[number];

/**
 * How much of today's deck is left, **after the caps**.
 *
 * Never the raw overdue count. Missed days shrink the task; they never pile up,
 * and a backlog is never presented (CLAUDE.md §4). A learner who skips a week
 * comes back to today's deck, not to the week.
 */
export type DeckCounts = {
  new_remaining: number;
  review_remaining: number;
  total_remaining: number;
};

export type ReviewQueue = {
  cards: CardFace[];
  /**
   * **Sent, and never rendered** (#160). `/review` used to print
   * *"N left today"*, and a number that grows while a learner is away is a
   * backlog presented — which CLAUDE.md §4 forbids. The session sizes block 1
   * from this and W19 reads it; the ban is on the surface, not on the number.
   */
  counts: DeckCounts;
  /**
   * The learner's first language, from `users.native_language` (#159).
   *
   * One per response rather than one per card: it is a per-user fact, and
   * eighty copies of it is eighty chances for two to disagree. Before this the
   * card face guessed from the SCRIPT, which tags every Latin-script line `en`
   * and is silently wrong for Lithuanian — no tofu, no direction symptom,
   * nothing on screen and nothing in a log.
   */
  l1_language: string;
};

export type GradeResult = {
  due: string;
  interval_days: number;
  counts: DeckCounts;
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

/** Due cards, capped by the two daily budgets. Empty is an ordinary state. */
export function getReviewQueue(limit = 20): Promise<ReviewQueue> {
  return request<ReviewQueue>(`/review/queue?limit=${limit}`);
}

/**
 * Grade one card. The rating travels by name, never as a number.
 *
 * `fsrs.Rating`'s integers are the scheduler's business; putting them on the
 * wire would let a client hardcode `3` and keep working while the meaning
 * shifted under it.
 */
export function gradeCard(
  cardId: number,
  rating: Rating,
  durationMs?: number,
  extra?: { sessionId?: number; typedResponse?: string },
): Promise<GradeResult> {
  return request<GradeResult>(`/review/${cardId}/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rating,
      duration_ms: durationMs,
      session_id: extra?.sessionId ?? null,
      // Sent verbatim. The server recomputes whether it matched; this client
      // never carries a verdict back (#108's shape).
      typed_response: extra?.typedResponse ?? null,
    }),
  });
}

/**
 * Did that typed answer match? **Nothing is written by this call** (#157).
 *
 * The comparison lives on the server even though this client already holds
 * `back`: `test_no_answer_comparison_in_typescript` forbids a fold here, because
 * a second definition of "the answer" is how a learner ends up seeing a coin
 * flip. That is the same reason `answerItem` has no optimistic path.
 */
export function attemptCard(
  cardId: number,
  text: string,
): Promise<{ matched: boolean }> {
  return request<{ matched: boolean }>(`/review/${cardId}/attempt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

/**
 * One of PRD §4.1's five blocks.
 *
 * **`state` is the whole point of this type.** `empty` and `unavailable` are
 * different facts — nothing is due, versus this block could not be built — and
 * a learner told *nothing's due, go watch something* because a query fell over
 * has been lied to in a way that looks identical to the truth on screen. A
 * failure of the whole request is neither: it rejects, and the caller shows a
 * retry.
 */
export type SessionBlock = {
  n: number;
  kind: "review" | "input" | "focus" | "output" | "close";
  state: "ready" | "done" | "empty" | "unavailable";
  payload: Record<string, unknown>;
};

/**
 * A grammar lesson. W10b.
 *
 * **Global**: one per unit, the same for every learner. Nothing here is keyed by
 * user, and nothing carries a translation — a gloss is per-learner by nature
 * (#159) and one on a lesson would break that line.
 *
 * The diagram specs carry **no colour, font or coordinate field**. The renderer
 * owns all of it, which is what makes "no red in the lesson UI" structural.
 */
export type LessonSection = {
  target: string;
  explanation: string;
  when_to_use: string;
  when_not_to: string;
  examples: string[];
  /** Named `mistake`/`said`, not `wrong_example`/`wrong`: the frontend
   *  no-guilt scan reads raw source, so the identifier tripped it. The code
   *  was renamed rather than the guard weakened. */
  mistake: { said: string; corrected: string; why: string };
};

type DiagramBase = { target: string };

export type LessonDiagram =
  | (DiagramBase & {
      kind: "timeline";
      points: { label: string; at: number; now: boolean }[];
    })
  | (DiagramBase & {
      kind: "contrast_pair";
      situation: string;
      /** `first`/`second`, never `left`/`right`: on a phone they stack. */
      first: { form: string; example: string };
      second: { form: string; example: string };
      what_changes: string;
    })
  | (DiagramBase & { kind: "form_build"; slots: string[]; example: string })
  | (DiagramBase & {
      kind: "decision_tree";
      question: string;
      branches: { answer: string; form: string }[];
    })
  | (DiagramBase & {
      kind: "annotated_example";
      sentence: string;
      callouts: { part: string; note: string }[];
    });

export type Lesson = {
  unit_number: number;
  sections: LessonSection[];
  diagrams: LessonDiagram[];
};

export function getLesson(unitNumber: number): Promise<Lesson> {
  return request<Lesson>(`/lessons/${unitNumber}`);
}

export type SessionToday = {
  session_id: number;
  /** The learner's **local** date, from `users.timezone`. */
  date: string;
  l1_language: string;
  current_block: number;
  completed: boolean;
  blocks: SessionBlock[];
};

/**
 * Today's session, hydrated. **Nothing is generated to answer this call.**
 *
 * Opens each day. Yesterday leaves no badge, no count and no backlog — missed
 * days shrink the task and never pile up (CLAUDE.md §4).
 */
export function getSessionToday(): Promise<SessionToday> {
  return request<SessionToday>("/session/today");
}

/** Mark one block done and get the refreshed session back. */
export function completeBlock(
  sessionId: number,
  blockN: number,
): Promise<SessionToday> {
  return request<SessionToday>(`/session/${sessionId}/block/${blockN}/complete`, {
    method: "POST",
  });
}


/**
 * The Saturday checkpoint. PRD §3: twelve items, 80% to pass.
 *
 * **`score_pct` is null on a failure and that is deliberate, not missing data.**
 * v2's carried rule is *drops are silent, raises are announced*: a fraction on
 * the screen after a failed checkpoint is a punishment screen with no banned
 * word in it. The API withholds it, so no client can render one by accident.
 */
export type Checkpoint = {
  session_id: number;
  unit_number: number;
  can_do: string;
  item_count: number;
  /**
   * `ready` — twelve items are waiting.
   * `not_ready` — the bank could not fill this sitting, and **a short
   *   checkpoint is never served in its place** (CLAUDE.md §3 rule 7).
   * `done` — it has been sat.
   */
  state: "ready" | "not_ready" | "done";
  items: ItemPresentation[];
  passed: boolean | null;
  score_pct: number | null;
  retake_due_on: string | null;
};

export function getCheckpointToday(): Promise<Checkpoint> {
  return request<Checkpoint>("/checkpoint/today");
}

export function completeCheckpoint(sessionId: number): Promise<Checkpoint> {
  return request<Checkpoint>(`/checkpoint/${sessionId}/complete`, {
    method: "POST",
  });
}
