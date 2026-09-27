"""Word practice — a short drill from the learner's own cards. **W31d.**

**W24f, UN-DEFERRED (C6).** R8 deferred the picture drill *"until pictures are
loaded and used for a week"*; the operator un-deferred it the same day, on
*"I didn't find vocabulary flashcards"* and on the finding that the 18 approved
pictures reach nobody. This is where they surface.

**FOUR EXERCISES, ONE PER CARD, DUE CARDS FIRST:**

* **picture → choose the word** and **word → choose the picture**, only for a
  card whose lexeme has an approved picture (`lexeme_images`), with the credit
  under every picture (R10);
* **hear it → type it** (the word, spoken through `core.speech`);
* **meaning → type the word**.

**Every exercise keeps its sentence** (PRD §2.6.3): a typed prompt shows the
card's line with the word blanked, and every answer shows the whole line.

**GRADING GOES THROUGH THE EXISTING FSRS PATH, AND ONLY FOR DUE CARDS (Q8).**
A due card's answer is graded by `cards.grade_card` — the one scheduler, the
`card_reviews` row, `typed_matched` — Good when right, Again when not. **A drill
with too few due cards fills from cards that are not due, and those are practice
only: nothing is written**, because reviewing early moves FSRS stability (R7).
Typed answers are checked by `equivalence_key`, the rule the reviewer uses.

**THE TARGET WORD IS THE CARD'S LEXEME, OR ITS FRONT FOR A VIDEO CAPTURE.** Card
fronts differ by writer — a video capture fronts the word, an imported
recognition card may front a sentence, a production card fronts its meaning —
so the word is read from `lexeme_id` (or the capture's front), and the meaning
is whichever of front/back is not that word. **Migrated v2 chunk cards are left
out**: their answer is a phrase, not a word (#147's family).

**SLANG, INFORMAL AND TABOO ARE RECEPTIVE-ONLY (CLAUDE.md §4)**, so they are
never a *type it* exercise; they appear only as a picture choice, which is
recognition.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core import speech
from core.items.grading import equivalence_key

logger = logging.getLogger(__name__)

#: About five minutes at ~30 seconds an exercise.
DRILL_SIZE = 8
#: The registers a learner may be asked to PRODUCE (type).
TYPED_REGISTERS = ("neutral", "formal")
KINDS = ("picture_to_word", "word_to_picture", "hear_type", "meaning_type")
#: FSRS ratings, as `grade_card` takes them.
AGAIN, GOOD = 1, 3
BLANK = "_____"

_TOKEN = re.compile(r"[A-Za-z][A-Za-z']*")


class PracticeAudioUnavailable(Exception):
    """The speech provider failed. The route answers 503."""


@dataclass(frozen=True)
class Target:
    card: Any
    word: str
    meaning: str | None
    image: dict | None
    due: bool


@dataclass
class Exercise:
    card_id: int
    kind: str
    #: What the prompt shows; absent fields are not shown.
    word: str | None = None
    image: dict | None = None
    definition: str | None = None
    sentence: str | None = None
    options: list[dict] = field(default_factory=list)
    #: Whether this answer will be graded (a due card) — never shown as a count.
    graded: bool = False

    def wire(self) -> dict:
        return {
            "card_id": self.card_id, "kind": self.kind, "word": self.word,
            "image": self.image, "definition": self.definition,
            "sentence": self.sentence, "options": self.options, "graded": self.graded,
        }


def blank(sentence: str | None, word: str) -> str | None:
    """The sentence with the word — or an inflection of it — gapped, or None
    when the word is not in it (the answer then shows the whole line)."""
    from core.lexicon.normalize import lemmatize

    if not sentence:
        return None
    target = word.casefold()
    hit = False

    def swap(match: re.Match) -> str:
        nonlocal hit
        token = match.group(0).casefold()
        if token == target or lemmatize(token) == target:
            hit = True
            return BLANK
        return match.group(0)

    out = _TOKEN.sub(swap, sentence)
    return out if hit else None


def _target(card: Any, lemmas: dict[int, str], faces: dict[int, dict], due: bool) -> Target | None:
    if card.source_chunk_id is not None or card.card_type == "collocation":
        return None
    if card.lexeme_id is not None and card.lexeme_id in lemmas:
        word = lemmas[card.lexeme_id]
    elif (card.source_ref or "").startswith("video:"):
        word = card.front
    else:
        return None
    if not word or not re.fullmatch(r"[A-Za-z][A-Za-z' -]{0,40}", word):
        return None
    folded = word.casefold()
    meaning = None
    for text in (card.back, card.front):
        if text and text.casefold() != folded and folded not in text.casefold().split():
            meaning = text
            break
    image = faces.get(card.lexeme_id) if card.lexeme_id is not None else None
    return Target(card=card, word=word, meaning=meaning, image=image, due=due)


def _kind(t: Target, index: int, n_words: int, n_images: int) -> str | None:
    typed_ok = t.card.register in TYPED_REGISTERS
    if t.image is not None:
        wanted = "picture_to_word" if index % 2 == 0 else "word_to_picture"
        if wanted == "word_to_picture" and n_images >= 4:
            return wanted
        if n_words >= 4:
            return "picture_to_word"
        if n_images >= 4:
            return "word_to_picture"
    if not typed_ok:
        return None
    if t.meaning and index % 2 == 0:
        return "meaning_type"
    return "hear_type"


def start(user_id: int, *, now: datetime) -> list[Exercise]:
    """The drill: up to `DRILL_SIZE` exercises, due cards first, one per word."""
    from core.services import cards as cards_service
    from core.services import lexeme_images as images_service

    due = cards_service.due_queue(user_id, now=now, limit=40)
    extra = cards_service.cards_not_due(user_id, now=now, limit=40)
    cards = [(c, True) for c in due] + [(c, False) for c in extra]
    lemmas = images_service.lemmas_for([c.lexeme_id for c, _ in cards if c.lexeme_id])
    faces = images_service.all_faces()

    targets: list[Target] = []
    seen: set[str] = set()
    for card, is_due in cards:
        t = _target(card, lemmas, faces, is_due)
        if t is None or t.word.casefold() in seen:
            continue
        seen.add(t.word.casefold())
        targets.append(t)

    # Distractor pools: the learner's own words first, then the pictured words.
    picture_words = set(images_service.lemmas_for(list(faces)).values())
    word_pool = sorted({t.word for t in targets} | picture_words)

    exercises: list[Exercise] = []
    for t in targets:
        if len(exercises) == DRILL_SIZE:
            break
        kind = _kind(t, len(exercises), len(word_pool), len(faces))
        if kind is None:
            continue
        rng = random.Random(t.card.id)
        ex = Exercise(card_id=t.card.id, kind=kind, graded=t.due)
        if kind == "picture_to_word":
            others = [w for w in word_pool if w.casefold() != t.word.casefold()]
            choices = rng.sample(others, 3) + [t.word]
            rng.shuffle(choices)
            ex.image = t.image
            ex.options = [{"value": w, "label": w} for w in choices]
            ex.sentence = blank(t.card.context_sentence, t.word)
        elif kind == "word_to_picture":
            others = [lid for lid in faces if lid != t.card.lexeme_id]
            picks = rng.sample(others, 3) + [t.card.lexeme_id]
            rng.shuffle(picks)
            ex.word = t.word
            ex.options = [{"value": str(faces[lid]["id"]), "image": faces[lid]} for lid in picks]
            ex.sentence = t.card.context_sentence
        elif kind == "meaning_type":
            ex.definition = t.meaning
            ex.sentence = blank(t.card.context_sentence, t.word)
        else:  # hear_type
            ex.sentence = blank(t.card.context_sentence, t.word)
        exercises.append(ex)
    return exercises


@dataclass(frozen=True)
class AnswerOutcome:
    correct: bool
    answer: str
    sentence: str | None
    meaning: str | None
    graded: bool


def answer(
    user_id: int, *, card_id: int, kind: str, response: str, now: datetime,
    duration_ms: int | None = None,
) -> AnswerOutcome | None:
    """Check one answer, and grade it only if the card is due.

    `None` when the card is not this learner's or the kind does not fit it (a
    picture exercise for a word with no picture, a typed one for slang) — the
    route answers 404, and nothing is written.
    """
    from core.services import cards as cards_service
    from core.services import lexeme_images as images_service

    card = cards_service.card_for(user_id, card_id)
    if card is None or kind not in KINDS:
        return None
    lemmas = images_service.lemmas_for([card.lexeme_id] if card.lexeme_id else [])
    image = images_service.face_for("recognition", card.lexeme_id) if card.lexeme_id else None
    t = _target(card, lemmas, {card.lexeme_id: image} if image else {}, card.state.due <= now)
    if t is None:
        return None
    if kind in ("hear_type", "meaning_type") and card.register not in TYPED_REGISTERS:
        return None
    if kind in ("picture_to_word", "word_to_picture") and image is None:
        return None

    if kind == "word_to_picture":
        correct = response.strip() == str(image["id"]) if image else False
    else:
        correct = equivalence_key(response) == equivalence_key(t.word)

    graded = False
    if t.due:
        # **No `typed_response`, deliberately.** `grade_card` records
        # `typed_matched` against the card's BACK — the reviewer's question —
        # and a drill asks for the WORD, which on a capture card is the front.
        # Passing it stored a correct answer as `typed_matched = false` (found
        # by `test_a_right_answer_on_a_due_card_is_graded_good_through_fsrs`).
        # The rating carries the drill's verdict; `typed_matched` stays NULL,
        # which the column already means: *no typed answer was compared*.
        outcome = cards_service.grade_card(
            user_id, card_id, rating=GOOD if correct else AGAIN, now=now,
            duration_ms=duration_ms,
        )
        graded = outcome is not None
    return AnswerOutcome(
        correct=correct, answer=t.word, sentence=card.context_sentence,
        meaning=t.meaning, graded=graded,
    )


def word_audio(user_id: int, card_id: int) -> bytes | None:
    """The card's word, spoken. **Synthesis here, never in the route** —
    `items.item_audio`'s reason: for *hear it → type it* the spoken text IS the
    answer, and the route holds bytes, never the word. Per request, no cache
    (as `item_audio`). `None` when the card is not this learner's."""
    from core.services import cards as cards_service
    from core.services import lexeme_images as images_service

    card = cards_service.card_for(user_id, card_id)
    if card is None:
        return None
    lemmas = images_service.lemmas_for([card.lexeme_id] if card.lexeme_id else [])
    t = _target(card, lemmas, {}, False)
    if t is None:
        return None
    logger.info("practice audio user_id=%s card_id=%s", user_id, card_id)
    try:
        return speech.synthesize(t.word)
    except speech.SpeechError:
        # The word is never logged: it is the answer.
        logger.warning("practice audio failed user_id=%s card_id=%s", user_id, card_id)
        raise PracticeAudioUnavailable() from None
