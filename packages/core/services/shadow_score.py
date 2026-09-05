"""W14 — the shadow line, and the scored attempt. **Not v2's `shadow.py`.**

`packages/core/services/shadow.py` is the v2 Telegram shadow and is untouched
until W22 (PRODUCT-PRINCIPLES §1). This module is the web surface's, and the two
share no code deliberately: v2's is a word-level ASR intelligibility diff with
no provider scoring, and this one is Azure pronunciation assessment. Merging
them would tie a surface that dies at W22 to one that does not.

────────────────────────────────────────────────────────────────────────────────
§1b — THE SHADOW TARGET IS A DECK SENTENCE AND NEVER A TRANSCRIPT CUE

**Assistant-recommended, operator-accepted 2026-09-03.**

R12 measured generated transcript tracks as ROLLING WINDOWS: ~92% of consecutive
cue pairs overlap (1405/1527, 655/714, 958/1038, 897/1034, 1471/1705, 272/317),
**and all three assigned videos are `generated`.** A cue is an arbitrary ~2.4 s
slice beginning mid-clause. W13-i reported loop-a-line and per-line 0.75x UNMET
on exactly this, and **W14 has a second reason W13-i did not have: Azure scores
against a REFERENCE TEXT, and `CompletenessScore` is defined as how much of the
reference was said.** A mid-clause fragment makes completeness meaningless by
construction and makes the boundary words noisy. **Shadowing a cue would ship an
unmet feature with a score attached to it** -- worse than the honest unmet
report.

**PRD §7.3's in-player *shadow this line* IS THEREFORE NOT DELIVERED, and #341
STAYS OPEN.** Reported, not approximated. The two standing refusals stand and
are not revisited: no merging cues into synthetic sentences, and no
manual-tracks-only behaviour.

**THE EXCLUSION IS A PREDICATE, NOT A HOPE.** W13-ii's `video.explain._line_for`
puts the CUE on a gloss, and `cards.save_captured_word` copies it straight onto
the card's `context_sentence` (`services/cards.py:1455`) -- so a video-sourced
card carries a rolling-window fragment, not a sentence. The same writer sets
`source_ref = 'video:<id>@<seconds>'` (`_capture_source_ref`, `:1363`), which is
what makes the exclusion exact rather than heuristic.

*(It selects nothing today: `python -m core.video.explain --apply` has never
run, so no video-sourced card exists. It is written now because the first one
appears the day T1 clears, and a selector written against an empty table is a
selector nobody checked.)*
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

#: §1b's exclusion, as one SQL fragment with one home. A second copy of this
#: predicate anywhere is the bug: the rule is *cue-derived sentences are not
#: shadowable*, and a caller that reimplemented it could drift silently.
NOT_CUE_DERIVED = "(cards.source_ref IS NULL OR cards.source_ref NOT LIKE 'video:%%')"

#: A sentence shorter than this is not worth scoring: `CompletenessScore` over
#: two words is dominated by its endpoints, and a one-word "line" is a
#: pronunciation drill, which is W17's and not this surface's.
MIN_SHADOW_CHARS = 12


@dataclass(frozen=True)
class ShadowLine:
    """One card's sentence, offered to be said aloud."""

    card_id: int
    sentence: str


def shadow_line(conn: Any, user_id: int) -> ShadowLine | None:
    """The line this learner shadows next, or ``None`` when the deck has none.

    **ORDERING: never-shadowed first, then least-recently-shadowed, then by
    `due`.** v2's `select_shadow_sentence` excluded the K most recent chunks;
    this expresses the same intent without inventing a K, by reading the log
    that now exists. A learner with one usable card gets it again, which is
    correct -- saying a line twice is the exercise, not a bug (`speech_attempts`
    carries no UNIQUE for this reason).

    **`None` IS A REAL STATE AND THE BLOCK SAYS SO PLAINLY.** A deck of cards
    that all came from a video, or all lack a context sentence, yields no line.
    That is *nothing to shadow today*, never an error and never a backlog.

    **THE CONSENT GATE IS CHECKED FIRST AND COSTS A QUERY NOTHING.** A learner
    who is not on the allowlist gets `None` -- the same answer an empty deck
    gives -- so block 4 renders exactly as it did before W14 and the control is
    absent rather than disabled.
    """
    if not scoring_allowed_for(user_id):
        return None
    row = conn.execute(
        f"""
        SELECT cards.id,
               cards.context_sentence,
               MAX(speech_attempts.created_at) AS last_said
          FROM cards
          LEFT JOIN speech_attempts
                 ON speech_attempts.card_id = cards.id
                AND speech_attempts.user_id = cards.user_id
         WHERE cards.user_id = %s
           AND cards.context_sentence IS NOT NULL
           AND length(btrim(cards.context_sentence)) >= %s
           AND {NOT_CUE_DERIVED}
         GROUP BY cards.id, cards.context_sentence, cards.due
         ORDER BY last_said ASC NULLS FIRST, cards.due ASC, cards.id ASC
         LIMIT 1
        """,
        (user_id, MIN_SHADOW_CHARS),
    ).fetchone()
    if row is None:
        return None
    return ShadowLine(card_id=int(row["id"]), sentence=str(row["context_sentence"]))


# ---------------------------------------------------------------------------
# The scored attempt.
# ---------------------------------------------------------------------------

#: F0 is 5 audio hours a month. The soft ceiling is 80% of it, in seconds.
#: **A speaking surface that silently stops working is worse than one that says
#: it is unavailable today** -- so the control is withheld with a plain message
#: before the provider starts refusing, rather than after.
MONTHLY_QUOTA_SECONDS = 5 * 60 * 60
SOFT_CEILING_SECONDS = int(MONTHLY_QUOTA_SECONDS * 0.8)

#: 15 s of 48 kHz mono 16-bit is ~1.44 MB. The cap is the only defence a free
#: quota has against a recorder that never stopped.
MAX_AUDIO_BYTES = 2_000_000
MAX_AUDIO_SECONDS = 20.0


class ShadowError(Exception):
    """Base for refusals this surface states plainly to the learner."""


# ---------------------------------------------------------------------------
# THE CONSENT GATE. **TEMPORARY, AND #364 SAYS WHAT REMOVES IT.**
# ---------------------------------------------------------------------------
#
# `speech_attempts` is the first thing this product has ever built that sends a
# learner's **voice** to a third party. §1c's four data-processing questions are
# **unanswered**, and the fourth is *whether the second learner should be asked
# at all* -- she is a person whose voice would leave the country in a request
# she did not make.
#
# **W14 WAS CODE-COMPLETE WITHOUT THIS AND THAT WAS A REAL GAP.** `shadow_line`
# filtered on `cards.user_id`, which selects a learner's OWN cards and is not a
# permission; `score_attempt` and the route had no condition at all. Deploying
# would have put *Say it* on her phone.
#
# **WHAT REMOVES THE GATE -- BOTH, NOT EITHER:**
#   1. the second learner's agreement that her voice may leave her device;
#   2. answers to §1c's four questions (retention and whether it can be turned
#      off; where audio is processed AND whether that holds on the FREE tier;
#      what the DPA says about voice; whether it is special-category data).
#
# **IT IS NOT A FEATURE FLAG.** #364 exists so it is not cleared as one.


class NotConsented(ShadowError):
    """This learner is not on the allowlist.

    **Mapped to 404 at the route, never 403.** A 403 announces a feature the
    learner is excluded from, which is a worse thing to put on someone's phone
    than nothing at all. To a blocked learner the surface is indistinguishable
    from *no shadowable line today*, which is an ordinary state.
    """


def scoring_allowed_for(user_id: int, settings: Any = None) -> bool:
    """**One condition, one home.** Both callers consult it; neither reimplements.

    Empty allowlist means **nobody** -- forgetting the variable costs a feature,
    and the opposite default would cost a voice.

    **W13b MOVED THE PREDICATE AND LEFT THIS AS THE DELEGATION.** The
    conversation surface asks the identical question -- *may this learner's
    voice leave her device* -- and two copies of one condition is how they
    drift. The variable is unchanged (`SHADOW_ALLOWED_USER_IDS`) and is
    deliberately NOT renamed: it fails closed, so a half-applied rename on a
    live `.env` closes a feature rather than opening one, but it is still a
    production edit with no reason behind it.
    """
    from core.services.conversations import voice_allowed_for

    return voice_allowed_for(user_id, settings)


class NoSuchLine(ShadowError):
    """The card is not this learner's, or is not shadowable (§1b)."""


class QuotaExhausted(ShadowError):
    """This month's free scoring is spent. **Stated, never silent.**"""


class AudioRejected(ShadowError):
    """The upload was not the shape this surface accepts."""


#: `ErrorType` values for a word the learner said that is **not in the
#: reference** — a stutter, a repetition, a filler.
#:
#: **THE LEARNER IS SHOWN THE REFERENCE, NEVER THE TRANSCRIPT (#377).** Azure's
#: `Words` array is what it HEARD; with `EnableMiscue: true` it carries the
#: reference words *plus* insertions. Rendering it verbatim put the learner's
#: own disfluency into the sentence they were asked to read — observed live on
#: 2026-09-04, where a repeated `was` rendered as *"the model was was
#: incapable…"* with the first one marked weak.
#:
#: **THE STORE KEEPS EVERYTHING AND THE SCREEN DOES NOT.** An insertion is a
#: real thing the learner did and belongs in `speech_attempts.words`; it is not
#: part of the line they were asked to say, so it must not appear in it.
#:
#: **`Omission` IS DELIBERATELY NOT HERE.** An omitted word IS a reference word
#: — it is how a learner sees they stopped early (#370) — while an inserted one
#: is not. The asymmetry is the whole rule.
NOT_IN_REFERENCE = frozenset({"Insertion"})


def display_words(words: Any) -> list[dict]:
    """The per-word list **as the learner sees it**: the reference, in order.

    Separate from what is stored, and that separation is the fix for #377: the
    same tuple used to serve both, so a stutter reached the screen as text.
    """
    return [
        {"word": w.word, "accuracy": w.accuracy, "error_type": w.error_type}
        for w in words
        if w.error_type not in NOT_IN_REFERENCE
    ]


@dataclass(frozen=True)
class ScoredAttempt:
    """**What the LEARNER is shown: per-word colouring and nothing else.**

    The four aggregates are persisted and **not** returned here — §2.6, ruled
    2026-09-03. PRD §7.3 asks for per-word colouring; PRD §8 asks for the
    aggregates to be PERSISTED, and its stated payoff is W17's weak-spot
    surface, not a number on the attempt screen. **A number on a person's voice
    is the shape CLAUDE.md §4 bans**, and #303 carries §8.6's open question 3:
    *a score on every turn may be exactly the thing that makes someone stop
    speaking.*

    `improved` carries **raises only**: True when this attempt beat the last one
    on the same card, and **None when it did not**. Drops are silent — the
    screen re-renders and says nothing about the change.
    """

    attempt_id: int
    words: tuple[dict, ...]
    improved: bool | None


def wav_duration_seconds(audio: bytes) -> float:
    """Seconds of PCM, from **our own bytes** and never from the provider.

    CLAUDE.md §3 rule 5: an expected value derived from the thing under test
    proves nothing, and a quota guard that trusts the provider's own accounting
    cannot detect the provider disagreeing. **P0a measured the gap and it is
    real**: Azure reported `Duration` 1.65 s for audio whose own header says
    1.72 s — it trims to recognised speech, so reading its number would
    under-count the quota by ~4% on that sample and more on a hesitant one.

    Parsed with `struct` rather than `wave.open`, deliberately: the audio-path
    AST guard flags any call named `open`, and **weakening that guard to admit a
    stdlib convenience is exactly the erosion S3 warns about.** It also means
    the header is validated rather than trusted, which a client-supplied file
    needs anyway.
    """
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise AudioRejected("not a RIFF/WAVE payload")
    pos = 12
    fmt: tuple[int, int, int] | None = None
    while pos + 8 <= len(audio):
        chunk_id = audio[pos : pos + 4]
        (size,) = struct.unpack_from("<I", audio, pos + 4)
        body = pos + 8
        if chunk_id == b"fmt " and size >= 16:
            audio_format, channels, rate = struct.unpack_from("<HHI", audio, body)
            bits = struct.unpack_from("<H", audio, body + 14)[0]
            if audio_format != 1 or bits != 16:
                raise AudioRejected("need uncompressed 16-bit PCM")
            fmt = (channels, rate, bits)
        elif chunk_id == b"data":
            if fmt is None:
                raise AudioRejected("data chunk before fmt chunk")
            channels, rate, bits = fmt
            frame_bytes = channels * (bits // 8)
            if rate <= 0 or frame_bytes <= 0:
                raise AudioRejected("degenerate WAV header")
            usable = min(size, len(audio) - body)
            return usable / (rate * frame_bytes)
        pos = body + size + (size % 2)
    raise AudioRejected("no data chunk")


def seconds_used_this_month(conn: Any, now: datetime) -> float:
    """Our own ledger of what we sent, summed across ALL users.

    Across all users because **the quota is the RESOURCE's, not the learner's**
    — one account, two learners. A per-learner sum would let the pair spend
    double.
    """
    row = conn.execute(
        """
        SELECT COALESCE(sum(audio_seconds), 0)::float8 AS used
          FROM speech_attempts
         WHERE created_at >= date_trunc('month', %s::timestamptz)
        """,
        (now,),
    ).fetchone()
    return float(row["used"]) if row else 0.0


def _reference_for(conn: Any, user_id: int, card_id: int) -> str:
    """This card's sentence — **re-checked against §1b, not trusted from the client.**

    The client sends a `card_id` it was given, and a client can send any id. So
    ownership AND the cue exclusion are enforced here, in the service, rather
    than relying on the selector that produced the payload.
    """
    row = conn.execute(
        f"""
        SELECT cards.context_sentence
          FROM cards
         WHERE cards.id = %s
           AND cards.user_id = %s
           AND cards.context_sentence IS NOT NULL
           AND length(btrim(cards.context_sentence)) >= %s
           AND {NOT_CUE_DERIVED}
        """,
        (card_id, user_id, MIN_SHADOW_CHARS),
    ).fetchone()
    if row is None:
        raise NoSuchLine(f"card {card_id} is not a shadowable line for this learner")
    return str(row["context_sentence"])


def _previous_pron_score(conn: Any, user_id: int, card_id: int) -> float | None:
    row = conn.execute(
        """
        SELECT pron_score FROM speech_attempts
         WHERE user_id = %s AND card_id = %s
         ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, card_id),
    ).fetchone()
    return float(row["pron_score"]) if row else None


def score_attempt(
    user_id: int,
    card_id: int,
    audio: bytes,
    *,
    session_id: int | None = None,
    now: datetime | None = None,
) -> ScoredAttempt:
    """Score one spoken attempt. **The one function the route calls.**

    **THE AUDIO IS HELD IN MEMORY AND DROPPED.** It is never written, cached or
    re-encoded to disk on any path through here — success or failure — and the
    recognised transcript never leaves `core.speech`'s parser.

    **NO ROW IS WRITTEN UNLESS A MEASUREMENT EXISTS.** Every refusal below
    raises before the INSERT, so a quota refusal, an unrecognised utterance or a
    provider fault leaves no trace that could later read as a low score.

    **THERE IS NO RETRY QUEUE.** A failed attempt is gone, and the learner is
    invited to say it again if they want to. A queue of unscored attempts is a
    backlog, and CLAUDE.md §4 forbids presenting one.
    """
    from core import speech
    from core.db import connection

    # **THE GATE FIRST, BEFORE THE AUDIO IS EVEN MEASURED.** Hiding the control
    # is not enough: the route is reachable with any card id, so the refusal
    # lives here too -- and it must precede the provider call, because a gate
    # that refused after sending the audio would have already done the thing it
    # exists to prevent.
    if not scoring_allowed_for(user_id):
        raise NotConsented("shadow scoring is not enabled for this learner")

    moment = now or datetime.now(timezone.utc)
    if len(audio) > MAX_AUDIO_BYTES:
        raise AudioRejected("recording is too long")
    seconds = wav_duration_seconds(audio)
    if seconds > MAX_AUDIO_SECONDS:
        raise AudioRejected("recording is too long")

    with connection() as conn:
        reference = _reference_for(conn, user_id, card_id)
        if seconds_used_this_month(conn, moment) + seconds > SOFT_CEILING_SECONDS:
            raise QuotaExhausted("this month's free scoring is spent")
        previous = _previous_pron_score(conn, user_id, card_id)

    # **The provider call happens OUTSIDE the connection**, so a 20s timeout
    # never holds a pool checkout open. The pool has 5 slots and two learners.
    payload = speech.assess_pronunciation(audio, reference)
    result = speech.parse_assessment(payload)

    # **TWO LISTS, AND THE SPLIT IS #377's FIX.** `stored` is the measurement
    # and keeps every word Azure returned, insertions included — the learner
    # really did say them. `shown` is the reference line and cannot contain a
    # word that was never in it.
    stored = tuple(
        {"word": w.word, "accuracy": w.accuracy, "error_type": w.error_type}
        for w in result.words
    )
    words = tuple(display_words(result.words))
    phonemes = [
        {"phoneme": p.phoneme, "accuracy": p.accuracy} for p in result.phonemes
    ]
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO speech_attempts
                (user_id, session_id, card_id, surface, reference_text,
                 accuracy, fluency, completeness, pron_score, prosody,
                 words, phonemes, audio_seconds, provider, created_at)
            VALUES (%s, %s, %s, 'shadow', %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s, 'azure', %s)
            RETURNING id
            """,
            (
                user_id, session_id, card_id, reference,
                result.accuracy, result.fluency, result.completeness,
                result.pron_score, result.prosody,
                Jsonb(list(stored)), Jsonb(phonemes), seconds, moment,
            ),
        ).fetchone()
        conn.commit()

    # **Raises announced, drops silent** (CLAUDE.md §4). `True` only on a real
    # improvement; `None` covers both *first attempt* and *worse*, and the
    # component has no branch that can tell those apart.
    improved: bool | None = None
    if previous is not None and result.pron_score > previous:
        improved = True

    logger.info(
        "shadow attempt user=%s card=%s seconds=%.2f words=%s phonemes=%s",
        user_id, card_id, seconds, len(words), len(phonemes),
    )
    return ScoredAttempt(
        attempt_id=int(row["id"]), words=words, improved=improved
    )


class LineAudioUnavailable(ShadowError):
    """The provider could not synthesise the line. **Not the learner's fault.**"""


def line_audio(user_id: int, card_id: int) -> bytes:
    """This card's sentence as speech, so a learner can hear the target.

    **WHY THIS EXISTS, and it is a §4 argument rather than a convenience.** The
    surface marks a word amber and **cannot demonstrate the difference.** On
    2026-09-03 `model` scored 44 and was marked correctly, and the operator
    concluded he had said it right -- **because the app supplied no evidence to
    the contrary.** A verdict with no appeal is what CLAUDE.md §4 guards
    against even when no banned word appears on screen. PRD §8 rung 1's other
    half -- playback of the learner's OWN attempt -- is **blocked on #369**, an
    unresolved collision with the discard rule. **This half is blocked on
    nothing.**

    **§1a: THIS IS NOT GENERATION WHILE A LEARNER WAITS.** No model authors
    anything -- the sentence already exists in `cards.context_sentence`, chosen
    when the card was made. TTS renders stored text as sound. **The precedent is
    shipped, not argued:** `GET /items/{id}/audio` has synthesised on demand,
    with a learner waiting, since W6 (ruling ⟨R1⟩), and **#106 is its standing
    flag** -- no cache, so a sentence heard forty times is paid forty times.
    **#106 applies here unchanged and is not re-argued.**

    **GATED BY THE SAME ALLOWLIST AS SCORING (#364), and that is not belt and
    braces:** a blocked learner who could hear the line would learn the feature
    exists. **The gate must not leak through the quieter door.**
    """
    from core import speech
    from core.db import connection

    if not scoring_allowed_for(user_id):
        raise NotConsented("shadow is not enabled for this learner")
    with connection() as conn:
        reference = _reference_for(conn, user_id, card_id)
    try:
        return speech.synthesize(reference)
    except speech.SpeechError as exc:
        # Converted here rather than propagated, so `apps/api` never holds a
        # provider error object -- `services/items.py:55`'s precedent.
        raise LineAudioUnavailable(str(exc)) from exc
