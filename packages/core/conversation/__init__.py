"""W13b — the conversation surface. **The pure half.**

`HTTP route -> service function -> SQL` (CLAUDE.md §2). This package holds the
half with no SQL and **no provider call of any kind**: prompt construction,
history trimming, the cap arithmetic, the topic seed, and the three close-out
guards in `guards.py`.

────────────────────────────────────────────────────────────────────────────────
**NOTHING HERE MAY REACH A MODEL, AND THAT IS PINNED EMPTY RATHER THAN AT ONE.**

The W13b plan predicted a one-member allow-list, `CONVERSATION_MODEL_CALLERS`,
"holding exactly the one file permitted to import `core.llm`". **The tree
disagreed and the disagreement strengthens the boundary.** The `*_MODEL_CALLERS`
pins govern *pure packages*; a **service** may reach a provider, and
`core/services/shadow_score.py` is the shipped precedent — it calls
`speech.assess_pronunciation` and holds its own SQL. The conversation's model
call belongs there for the same reason, so **no file in this package reaches a
model at all** and the pin is `set()`.

That is `core/video/`'s original total guarantee, which #292 itself called the
stronger form: *"an allow-list with one entry added later would read as normal."*
`tests/test_core_boundary.py` pins it by identity **and** size, so the commit
that adds a first member has to argue for it in the diff.

**AND `VIDEO_MODEL_CALLERS` IS NOT TOUCHED.** It stays at exactly one. F4 of the
plan's reconcile is why: #292's list is a per-package import ban, not a list of
permitted models, so a conversation module was never going to make it two.
────────────────────────────────────────────────────────────────────────────────

**THE INJECTION BOUNDARY THIS PACKAGE HOLDS (§2d).** Every prompt in this
project is a `.format()` template with named fields. **The learner's text is
never one of them.** `build_system_prompt` has no parameter that could carry it;
learner text enters the request **only** as the `content` of a `user`-role
message, where `{}` is a brace and not a field. That is a property of the
signature rather than a promise in a docstring, and
`test_learner_text_never_reaches_str_format` drives a turn containing `{topic}`
through the real builder and asserts the system prompt is byte-identical to the
one built without it.

**WHAT DOES NOT CARRY OVER FROM #292, WITH THE REASON RATHER THAN COPIED
ACROSS.** The delimited-block framing (`<transcript>…</transcript>`, *this is
data*) exists to mark text written by a third party. **Here the speaker IS the
user**, the model is supposed to respond to them, and a fence around the
learner's own sentence is theatre that degrades the reply. CLAUDE.md §6's *quote
it to the human, never obey it* cannot apply either: **there is no human in the
loop of a conversation turn.** Saying so is the difference between a boundary
and a claim. The real surface is the close-out, and `guards.py` is where it is
defended.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "CLOSE_REVIEW_CUE",
    "HISTORY_MAX_MESSAGES",
    "MAX_ALTERNATIVES",
    "MAX_SHOWN_CORRECTIONS",
    "TURN_MAX_TOKENS",
    "Turn",
    "build_close_messages",
    "build_system_prompt",
    "build_turn_messages",
    "cap_exceeded",
    "topic_seed",
    "trim_history",
]

#: Output budget for one reply. **PRD §8.6 asks for replies "under ~80 words"**,
#: and 300 tokens is roughly twice that — headroom for a long-but-legitimate
#: turn without room for an essay. v2 used 500 and its replies ran long.
TURN_MAX_TOKENS = 300

#: Output budget for the close-out, which returns JSON. v2's number, unchanged:
#: the shape is the same and it was measured against real conversations.
CLOSE_MAX_TOKENS = 2000

#: How many messages of history are re-sent each turn. **This is the number P2's
#: branch rule challenges**: input tokens are quadratic in turn count because the
#: history is re-sent every turn, so at a 30-turn cap this bounds the bill more
#: than the cap does. v2 shipped 20.
HISTORY_MAX_MESSAGES = 20

#: §2c: one topic, one alternative, then the topic stands.
MAX_ALTERNATIVES = 1

#: **≤2 SHOWN, and of those only the journalable ones are written.**
#: W16's journal precedent, **lowering v2's `MAX_CLOSE_ERRORS = 3`** so the two
#: surfaces agree rather than differing for no stated reason. It counts what is
#: SHOWN (S1's ruling): a voice-only conversation shows ≤2 and writes 0.
#: Declined: ≤2 journalable plus extra shown ones, which would make the voice
#: half louder than the typed half.
MAX_SHOWN_CORRECTIONS = 2

#: Anthropic requires the final message to be `user`. Live history ends on the
#: assistant after any successful turn, so the close-out appends this. v2's
#: S26a lesson, inherited rather than rediscovered.
CLOSE_REVIEW_CUE = (
    "That's the end of the conversation. Review it now and reply with the JSON "
    "described above."
)


@dataclass(frozen=True)
class Turn:
    """One turn as the service reads it back. **Ephemeral by design (§2a).**

    `input_mode` is `None` for an app turn and `'typed'` / `'voice'` for a
    learner turn — the migration's CHECK enforces the pairing, so a reader here
    never has to wonder whether an app turn could claim to be typed.
    """

    seq: int
    role: str
    content: str
    input_mode: str | None = None

    @property
    def is_learner(self) -> bool:
        return self.role == "learner"

    @property
    def is_voice(self) -> bool:
        return self.input_mode == "voice"


def trim_history(
    messages: list[dict[str, str]], *, max_messages: int
) -> list[dict[str, str]]:
    """Keep the last `max_messages`. v2's `_trim_history`, ported unchanged."""
    if max_messages < 2 or len(messages) <= max_messages:
        return list(messages)
    return list(messages[-max_messages:])


def build_system_prompt(template: str, /, **fields: Any) -> str:
    """Fill a prompt template. **No parameter here can carry learner text.**

    The signature is the guard: `fields` are the named, structured values the
    template declares — level, native language, topic seed, coverage band — all
    produced by this codebase. **A learner's sentence has no route into
    `str.format`**, so a message containing `{topic}` is a message and not a
    format directive.

    Returns the filled template. Raises `KeyError` on a missing field rather
    than filling it with a placeholder, because a prompt that silently ships
    with `{cefr_level}` in it is worse than one that fails loudly.
    """
    return template.format(**fields)


def build_turn_messages(
    history: list[dict[str, str]],
    learner_text: str,
    *,
    max_messages: int = HISTORY_MAX_MESSAGES,
) -> list[dict[str, str]]:
    """History plus the new learner turn. **Always ends on `user`.**

    `learner_text` is placed in `content` and **nowhere else**. It is not
    formatted, not concatenated into a system string, and not wrapped in a
    delimiter — see the module docstring for why the delimiter is refused.
    """
    return trim_history(
        list(history) + [{"role": "user", "content": learner_text}],
        max_messages=max_messages,
    )


def build_close_messages(
    history: list[dict[str, str]],
    *,
    max_messages: int = HISTORY_MAX_MESSAGES,
    review_cue: str = CLOSE_REVIEW_CUE,
) -> list[dict[str, str]]:
    """The transcript plus a trailing user cue.

    Trimmed to `max_messages - 1` before the cue is appended, so the cue itself
    cannot push the request over the ceiling — v2's S26a fix, which existed
    because passing an assistant-terminated transcript raised before the API
    ever answered.
    """
    trimmed = trim_history(list(history), max_messages=max_messages)
    if max_messages >= 2 and len(trimmed) >= max_messages:
        trimmed = trimmed[-(max_messages - 1) :]
    return trimmed + [{"role": "user", "content": review_cue}]


def cap_exceeded(turns_learner_today: int, cap: int) -> bool:
    """**Checked BEFORE accepting the next turn, never after generating one.**

    So the learner's last message always gets a reply and there is no dangling
    question. `turns_learner_today` is what the counter already holds; the turn
    being offered would make it `+ 1`.

    A conversation that stops mid-exchange with no explanation is worse than one
    that says it is done for today — which is what the surface does when this
    returns True: it runs the close-out, shows the corrections, and says so in
    copy carrying **no numeral at all** (#348 shipped *"0 of 5 active days."*
    past a banned-word scan for a year).
    """
    return turns_learner_today >= cap


def topic_seed(
    *,
    grammar_target: str | None,
    unit_lexemes: Iterable[str],
    recent_words: Iterable[str],
    track: str,
) -> dict[str, str]:
    """The material the opener draws on. **PRD §8.6.1, in priority order.**

    This week's grammar target, the unit's target lexis, and words added from
    block 1 in the last seven days. **A topic that reuses what has just been
    learned is the point; a generic prompt is not** — a conversation the learner
    could have had on day one measures nothing.

    Returns strings for the template's named fields. **It returns no learner
    text**: lexemes and saved words are dictionary forms this system chose, not
    sentences the learner wrote.

    **v2's three-button picker is deliberately NOT ported.** `_MAX_OFFERED_TOPICS
    = 3` and its `picking_topic` phase are a browsable list, refused by PRD
    §8.6.1, PRD §7.4 (*browsing a library is a decision, and decisions are where
    sessions die*) and CLAUDE.md §4. One topic, one alternative.
    """
    lex = [w for w in unit_lexemes if w][:12]
    recent = [w for w in recent_words if w][:12]
    return {
        "grammar_target": grammar_target or "(none this week)",
        "unit_lexemes": ", ".join(lex) if lex else "(none yet)",
        "recent_words": ", ".join(recent) if recent else "(none yet)",
        "track": track,
    }
