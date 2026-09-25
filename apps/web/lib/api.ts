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

/** `day_kind` on the wire. W16a writes only `journal`; `paragraph` is W16b's. */
export type DayKind = "journal" | "paragraph";

/**
 * `GET /write/today` (W16a). **A boolean, never a count** (Ruling 3): the
 * ceiling reaches the screen as whether today's writing is done, and nothing
 * says how many were used or when it resets. `session_id` is posted back so
 * block 4 can finish; `null` when `/write` was opened before the session.
 */
export type WriteToday = {
  day_kind: DayKind;
  session_id: number | null;
  ceiling_reached: boolean;
  /** W16b → `1e`'s prompt card. The unit's task, verbatim; `null` on the journal. */
  prompt: string | null;
};

export function getWriteToday(): Promise<WriteToday> {
  return request<WriteToday>("/write/today");
}

/**
 * One correction card, design `1k`'s anatomy. **W16a took `error_type`,
 * `murphy_units` and `has_errors` off the wire** — nothing rendered them.
 * `label` is the eyebrow, from `error_types.learner_label`, and is ABSENT when
 * the taxonomy has none.
 */
export type Correction = {
  you_said: string;
  correct_form: string;
  explanation: string;
  label?: string;
};

/**
 * What one journal entry produced. **`did_well` is ABSENT when there is nothing
 * worth saying — never blank, never a fallback** (Ruling 2).
 */
export type CorrectionResult = {
  is_english: boolean;
  did_well?: string;
  corrections: Correction[];
  /** W16b → `1n`. ABSENT on the journal and when the gate refused it. */
  structure?: StructureParagraph[];
  /** W16b → `1o`. `[]` on the journal and when nothing survived the offer rule. */
  word_offers: WordOffer[];
};

/** One run of structure prose; `quote` is the learner's own words, set in italic. */
export type StructureSegment = { text: string; quote: boolean };
export type StructureParagraph = { segments: StructureSegment[] };

/**
 * `1o`'s KeepRow: the phrase, the app's sentence it came from, and whether it is
 * kept. `token` (#419, W15) is the server's signature on this offer; it is sent
 * back unread and never shown.
 */
export type WordOffer = { phrase: string; sentence: string; in_deck: boolean; token: string };

/**
 * `POST /write/keep` (W16b). **#419, closed W15:** the offer's `token` is sent
 * back and the server refuses a pair it did not sign for this learner (`422`),
 * then re-applies the offer rule. *(Read "**It cannot prove the phrase was
 * offered** — this call sends both halves (#419)" — quoted, #82.)*
 */
export function keepPhrase(offer: WordOffer): Promise<{ status: "saved" | "already" }> {
  return request<{ status: "saved" | "already" }>("/write/keep", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phrase: offer.phrase, sentence: offer.sentence, token: offer.token }),
  });
}

/**
 * `POST /correct`. A `409` is the day's ceiling (Ruling 3), a `503` is the
 * model failing, and a `422` is a kind this day does not serve (finding (c) —
 * a Thursday tab left open); all arrive as `ApiError` with the status, and none
 * carries a message the screen shows.
 */
export function requestCorrection(
  text: string,
  { dayKind, sessionId }: { dayKind: DayKind; sessionId: number | null },
): Promise<CorrectionResult> {
  return request<CorrectionResult>("/correct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, day_kind: dayKind, session_id: sessionId }),
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
 * One of block 3's items, as `_focus_block` serves it. **W17 adds `pattern`.**
 *
 * `pattern` is present only on a weak-spot drill: the plain `learner_label` of
 * the error pattern the learner's journal evidences (*"Articles"*). **Never a
 * count** — no tally of how often the learner got it wrong crosses the wire
 * (CLAUDE.md §4). `seen` is #276 (c)'s: answered in an earlier session.
 */
export type FocusItem = ItemPresentation & {
  seen?: boolean;
  pattern?: string;
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

/**
 * Block 2's payload. **W13-i.**
 *
 * **There is no coverage percentage on this type and the server cannot send
 * one.** `coverageBand` is a token or null; the figure never leaves
 * `packages/core`. See `core/video/badge.py` for the three reasons (#288, #334,
 * #330) and `components/session/copy.ts` for the words each token renders as.
 *
 * **`transcriptAvailable` is a state, not an error (#335).** The 30-day purge
 * nulls the transcript and returns the row to `pending`, and nothing
 * coordinates that with the weekly assignment — so a learner really can open a
 * day whose video is still assigned and still watchable while the follow-along
 * text is gone. `youtubeId` survives the purge by design, which is why the
 * block stays `ready` rather than becoming `unavailable`: nothing failed.
 */
export type VideoBlockPayload = {
  video_id: number;
  youtube_id: string;
  title: string | null;
  duration_s: number | null;
  accent: string | null;
  track: string;
  resume_position_s: number;
  completed: boolean;
  transcript_available: boolean;
  transcript: string | null;
  /** Per-cue timings (migration 021). **Null is the third state** — transcript
   * present, cues absent: it renders, words stay tappable, the badge still
   * shows, and there is no highlight. Nothing is said to the learner about it. */
  transcript_cues: { text: string; start: number; duration?: number }[] | null;
  transcript_lang: string | null;
  /** Lemmas this learner has no `known`/`mastered` row for. The highlight set.
   *
   * **#284 is open and visible here**: a proper noun that appears only at the
   * start of a sentence is still counted unknown, so a learner will see names
   * marked. That is the row's visible half and it stays open. */
  unknown_lemmas: string[];
  /** `"below" | "in" | "above"`, or **null meaning WITHHELD** — a fourth answer
   * and not a fourth band. */
  coverage_band: "below" | "in" | "above" | null;
};

/** Today's video, without the transcript. **W13-i.**
 *
 * The transcript and the band arrive through block 2 of `GET /session/today`
 * and deliberately not through here: one contract, one producer (#190). This
 * answers *is there a video, where did I stop, have I finished it* — what a
 * client needs to confirm a write without re-hydrating five blocks. */
export type VideoToday = {
  video_id: number;
  youtube_id: string;
  title: string | null;
  duration_s: number | null;
  resume_position_s: number;
  completed: boolean;
};

/**
 * Report where the learner has got to.
 *
 * **This is block 2's log, and it is why there is no "I've watched it" button
 * (#258).** Block completion is automatic by the operator's ruling of
 * 2026-08-29; the per-kind rule turns on whether a block has a per-attempt log,
 * and `input` had none because it served nothing. This is that log.
 *
 * **The client never sends a completion.** `core/video/watch.py` decides it from
 * the position and the stored duration, so a browser cannot assert that a video
 * was finished — it can only report a position, which the server clamps to the
 * video's own length.
 */
export function reportVideoProgress(
  videoId: number,
  positionS: number,
): Promise<VideoToday> {
  return request<VideoToday>(`/video/${videoId}/progress`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position_s: Math.max(0, Math.floor(positionS)) }),
  });
}

/** Mark one block done and get the refreshed session back. */


/**
 * The Saturday checkpoint. PRD §3: twelve items, 80% to pass.
 *
 * **`score_pct` is null on a failure and that is deliberate, not missing data.**
 * v2's carried rule is *drops are silent, raises are announced*: a fraction on
 * the screen after a failed checkpoint is a punishment screen with no banned
 * word in it. The API withholds it, so no client can render one by accident.
 */
export type Checkpoint = {
  /** How many of the twelve are already answered — the server's count (#269). */
  answered: number;
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

/**
 * W11b: the Sunday weekly report. PRD §4.2.
 *
 * **Every number here is something that HAPPENED.** There is no field for a
 * missed day, a shortfall, a target or last week, because *drops are silent,
 * raises are announced* and CLAUDE.md §4 forbids presenting a backlog — a
 * report that says what did not happen is a backlog with a date on it.
 *
 * **And there is no `minutes`, `xp` or block breakdown**, because nothing
 * writes those columns: they would be numbers that are always zero, and a zero
 * on a report is a score.
 *
 * `empty` is the server's answer to "did anything happen this week", and the
 * screen renders one line rather than a table of zeros when it is true.
 */
export type Week = {
  /** The Sunday this week ends on. PRD §4.2's week runs Mon → Sun. */
  week_ending: string;
  /**
   * Whether the learner's today IS that Sunday — **the server's answer, not the
   * browser's.** A `new Date().getDay()` here would put a learner in Vilnius on
   * the browser's idea of Sunday; `users.timezone` is what knows.
   */
  sunday: boolean;
  days_with_a_session: number;
  items_answered: number;
  items_right: number;
  cards_reviewed: number;
  words_now_known: number;
  units_passed: number;
  empty: boolean;
};

export function getWeek(): Promise<Week> {
  return request<Week>("/week");
}

/**
 * W13-ii: one tap on a transcript word → two cards.
 *
 * **THREE STATES AND NONE OF THEM IS AN ERROR.** `already_saved` is #178: a
 * learner who taps a word twice did a normal thing, and the raw
 * `UniqueViolation` underneath used to reach them as a 500. `no_gloss` is §1a's
 * PRE-GENERATE ruling on the wire — the definition is written before the week
 * by a human-run command, so a word nobody generated stays ungiossed and **the
 * app does not reach a model to fix that while the learner waits.**
 *
 * **No definition comes back.** The learner reads it in the deck, where
 * `card_face` is the single producer (#190).
 */
export type SaveWordResult = {
  state: "saved" | "already_saved" | "no_gloss";
  card_ids: number[];
};

export function saveWord(
  videoId: number,
  word: string,
): Promise<SaveWordResult> {
  return request<SaveWordResult>(`/video/${videoId}/save-word`, {
    method: "POST",
    body: JSON.stringify({ word }),
  });
}

// ── the conversation surface: `/talk` (W13b) and its two rungs (W15) ─────────
//
// **#398, CLOSED BY W15: THE CONVERSATION HAD NO LAYER HERE.** It was the one
// surface that called `fetch` directly and read `await res.json()` untyped — how
// `did_well` was returned for a month and rendered by nothing. Every endpoint it
// calls now has a named function and a named type, so an unread field is a
// compile-time fact rather than a sweep's finding. A `409` (the day's cap, or
// the spent alternative) and a `404` (no conversation, the voice gate, or a rung
// not on offer) arrive as `ApiError` with the status; **neither carries a
// number**.

/** Which exchange is open. `talk` is W13b's; `answer` and `retell` are W15's. */
export type ConversationKind = "talk" | "answer" | "retell";

/**
 * One turn's result. `reply` is **empty on a rung** — a rung takes one turn and
 * generates nothing until the close. `state` is `open` or `closing`, **never a
 * count**. `heard` is what Whisper heard on a VOICE turn (#427) and `null`
 * otherwise; the screen shows it as the learner's own line.
 */
export type ConversationTurn = {
  conversation_id: number;
  topic_label: string;
  reply: string;
  state: "open" | "closing";
  heard: string | null;
};

/**
 * One correction on the close-out. `label` is `error_types.learner_label`, the
 * card's eyebrow (`/write`'s `1k`); `null` for a code with none, and the card
 * then carries no eyebrow.
 */
export type ConversationCorrection = {
  you_said: string;
  correct_form: string;
  explanation: string;
  label: string | null;
};

/** A word offered to the deck and the token that proves it was offered (#408). */
export type ConversationWordOffer = { word: string; token: string };

/**
 * `POST /conversation/close`. **Shown ≠ written**: a correction on a voice turn
 * is shown and never journaled, and nothing here says which. `covered` and
 * `also` are a retell's points — **the video's own sentences, never a count or
 * a percentage of them** — and are empty on a talk and an answer. `summary` is
 * empty on a rung. `is_english` is false only for a rung answered in another
 * language.
 */
export type ConversationClose = {
  conversation_id: number;
  corrections: ConversationCorrection[];
  did_well: string;
  summary: string;
  word_offers: ConversationWordOffer[];
  is_english: boolean;
  covered: string[];
  also: string[];
};

/** One rung on offer today. `prompt` is the answer's task, verbatim; `null` on a retell. */
export type ConversationRung = { label: string; prompt: string | null };

/**
 * `GET /conversation/rungs` (W15). **A read, no model call** (#399 declined a
 * page that bills on load). A rung not on offer today is `null` — absent, never
 * greyed out. `voice` is the same gate `/topics` carries (#364).
 */
export type ConversationRungs = {
  answer: ConversationRung | null;
  retell: ConversationRung | null;
  voice: boolean;
};

export function getConversationRungs(): Promise<ConversationRungs> {
  return request<ConversationRungs>("/conversation/rungs");
}

/** `POST /conversation/topics`: three suggestions, and the voice gate. **Billed.** */
export function suggestConversationTopics(): Promise<{ topics: string[]; voice: boolean }> {
  return request<{ topics: string[]; voice: boolean }>("/conversation/topics", {
    method: "POST",
  });
}

/** `POST /conversation/open`. A rung ignores `topic_label`; a talk ignores nothing. */
export function openConversation(
  kind: ConversationKind,
  topicLabel?: string,
): Promise<ConversationTurn> {
  return request<ConversationTurn>("/conversation/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      topicLabel ? { kind, topic_label: topicLabel } : { kind },
    ),
  });
}

/** `POST /conversation/turn`: one typed turn. */
export function sendConversationTurn(text: string): Promise<ConversationTurn> {
  return request<ConversationTurn>("/conversation/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

/**
 * `POST /conversation/turn/voice`: one spoken turn, the recording as the body.
 * **The audio is transcribed and discarded server-side**; `422` means it heard
 * nothing, `413` that the recording ran too long.
 */
export function sendConversationVoice(recording: Blob): Promise<ConversationTurn> {
  return request<ConversationTurn>("/conversation/turn/voice", {
    method: "POST",
    headers: { "Content-Type": recording.type || "audio/webm" },
    body: recording,
  });
}

/** `POST /conversation/close`. One-shot: a second call is a `404`. */
export function closeConversation(): Promise<ConversationClose> {
  return request<ConversationClose>("/conversation/close", { method: "POST" });
}

/**
 * `POST /conversation/save-word`. **The offer's token goes back with the word**
 * and the server refuses a word it did not sign for this learner (`422`, #408).
 * `already` is a state, not an error (#178).
 */
export function saveConversationWord(
  offer: ConversationWordOffer,
): Promise<{ state: "saved" | "already" }> {
  return request<{ state: "saved" | "already" }>("/conversation/save-word", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(offer),
  });
}

/**
 * W19: the progress screen. PRD §9, *gamification — the honest kind*.
 *
 * **Every number traces to a ledger** (`core.services.progress`'s banner names
 * each). **No field counts what was not done** — no missed days, no remaining,
 * no target shortfall, no partner. **There is no field for the radar, placement
 * history, the six-month target line or units mastered**: each needs data that
 * does not exist yet (W18's placement; #135's retention metric), so the client
 * cannot draw a number with nothing behind it.
 *
 * Zeros arrive honestly and the SCREEN draws none of them (W11b's split).
 */
export type KnownPoint = {
  /** The learner's local date the screen was read on. */
  local_date: string;
  known_words: number;
};

export type Progress = {
  /** Words the learner has shown they know. The starting frequency floor is
   * never counted (W4's ruling). */
  known_words: number;
  /** Ascending, at most six months — one point per day this screen was read.
   * **A line exists only from the second point**; nothing is reconstructed. */
  known_history: KnownPoint[];
  /** Weighted by effort; never lower than any value already shown. */
  xp: number;
  /** Days practised under v2's rule: a day off does not break it. */
  streak_days: number;
  freezes: number;
  units_passed: number;
};

export function getProgress(): Promise<Progress> {
  return request<Progress>("/progress");
}
