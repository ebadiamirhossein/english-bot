"""What the placement bank holds: the targets the generator is asked for, the
authored speaking prompts, and how many of each the bank keeps.

**The grammar and listening targets are original text written for this
project** against PRD §6 (*"an A2–C1 bank tagged by CEFR and by the 19-type
error taxonomy"*); nothing is transcribed from a third party, and no Murphy
text is quoted (`data/LICENCES.md`'s standing rule). Each names its band IN
THE TARGET, because the generator's prompt is written for a B1→B2 learner and
the band is how an A2 or a C1 item is asked for.

**#440's lesson is applied here from the start:** a target that names a
neighbouring choice invites an item about it, so the article target rules the
a/an choice out in words the model reads. **And no target asks for a phrase the
item gates refuse** — `copy_rules.BANNED_IN_CONTENT` bans *should have* in item
content, so the C1 modal targets name *could have*, *might have* and *needn't
have* instead (`tests/test_placement_bank.py` asserts every target passes the
content check).
"""

from __future__ import annotations

import re

from core.placement import BANDS

#: PRD §6's per-sitting counts.
GRAMMAR_PER_SITTING = 25
#: **Five, not PRD §6's six, since W24r (C)**: the sixth clip was the C1 one,
#: and listening C1 is dropped (operator ruling, 2026-09-27; #463).
LISTENING_PER_SITTING = 5
SPEAKING_PER_SITTING = 1

#: **Six sittings: the six months of the program, monthly.** The bank is sized
#: so six sittings can each be disjoint from every other (`placement_run_items`
#: `UNIQUE (user_id, bank_id)`); a seventh would find sections thin, and the
#: build command tops the bank up from wherever it stands.
SITTINGS = 6

#: Per band. A ladder that lives at one band for a whole sitting uses at most
#: `ladder.HOLD_ITEMS`+ a few there before it stops as `held`, so 36 carries six
#: sittings with room; a thin band stops the ladder (`bank_thin`), it never
#: serves off-band.
GRAMMAR_PER_BAND = 36
#: **Listening stops at B2 (W24r (C), operator ruling 2026-09-27).** Its C1
#: target -- *could have* / *might have* "in fast speech" -- invited the reduced
#: spelling (*coulda*, *mighta*) into the transcript, and no transcript check can
#: match an answer whose point is that it is not written as spoken: the host's
#: fill discarded 6 of 6 (#463). So there is no listening C1 cell to fill, draw
#: or wait for.
LISTENING_BANDS: tuple[str, ...] = ("A2", "B1", "B2")
LISTENING_PER_BAND: dict[str, int] = {"A2": 6, "B1": 12, "B2": 12}

#: The types a placement grammar item may take: one point, one answer, graded
#: server-side by `core.items.response`. **Not** `l1_to_l2_production` (its
#: prompt is in one learner's L1 and the bank is shared), `match_pairs` (five
#: answers, not one point), `mcq` / `collocation_pick` (dropped for grammar,
#: `generate.DROPPED_FOR_GRAMMAR`).
GRAMMAR_TYPES: tuple[str, ...] = ("cloze_cued", "error_spot", "word_bank_order")
LISTENING_TYPE = "listening_gap"

#: Slots per generation call — a unit's eight, the size the generator has been
#: run at since W10c.
BATCH = 8

GRAMMAR_TARGETS: dict[str, tuple[tuple[str, str], ...]] = {
    "A2": (
        ("verb_tense_past", "A2: the past simple of common irregular verbs"),
        ("subject_verb_agreement", "A2: the third-person -s in the present simple"),
        ("article_missing", "A2: a missing a or the before a singular noun, not choosing between a and an"),
        ("preposition", "A2: in, on and at for times and places"),
        ("plural_countable", "A2: regular and irregular plural nouns"),
        ("word_order", "A2: word order in questions with do and does"),
    ),
    "B1": (
        ("present_perfect", "B1: the present perfect or the past simple, with ever, never, just and a finished time"),
        ("conditional", "B1: the first conditional, if + present and will + verb"),
        ("modal_verb", "B1: should, have to and must for advice and obligation"),
        ("gerund_vs_infinitive", "B1: verbs followed by -ing and verbs followed by to + verb"),
        ("quantifier_modifier", "B1: much, many, a few and a little with countable and uncountable nouns"),
        ("verb_tense_past", "B1: the past continuous for an action the past simple interrupted"),
    ),
    "B2": (
        ("conditional", "B2: the second and third conditionals"),
        ("modal_verb", "B2: must have, might have and can't have for guesses about the past"),
        ("gerund_vs_infinitive", "B2: remember, stop and try with -ing or to, and how the meaning changes"),
        ("present_perfect", "B2: the present perfect continuous for how long something has been going on"),
        ("word_order", "B2: word order in indirect questions"),
        ("phrasal_verb", "B2: separable phrasal verbs with a pronoun object"),
    ),
    "C1": (
        ("conditional", "C1: mixed conditionals, a past condition with a present result"),
        ("word_order", "C1: inversion after never, rarely and not only"),
        # Not *should have*: `copy_rules.BANNED_IN_CONTENT` refuses that phrase in
        # any item, so a target that needs it buys items the free stage discards.
        ("modal_verb", "C1: needn't have, could have and might have for what was possible or unnecessary in the past"),
        ("verb_tense_past", "C1: the past perfect continuous for what had been going on before a past event"),
        ("gerund_vs_infinitive", "C1: the perfect forms to have done and having done"),
        ("collocation", "C1: strong collocations with make, do, take and have"),
    ),
}

#: Listening: the gapped word is a grammar-bearing word the learner has to HEAR,
#: so the item carries an error-taxonomy tag like a grammar item and
#: `probe_target` has something to rank. The audio round-trip gate
#: (`gates._audio_gate`) must hear the whole sentence AND the gapped word.
LISTENING_TARGETS: dict[str, tuple[tuple[str, str], ...]] = {
    "A2": (("verb_tense_past", "Listening, A2: hearing the past simple verb in a short everyday sentence"),),
    "B1": (
        ("present_perfect", "Listening, B1: hearing the verb in a present perfect sentence"),
        ("modal_verb", "Listening, B1: hearing the modal verb in everyday speech"),
    ),
    "B2": (
        ("conditional", "Listening, B2: hearing the verb form in the result half of an if-sentence"),
        ("phrasal_verb", "Listening, B2: hearing the particle of a phrasal verb"),
    ),
    # C1 is dropped (W24r (C)): its target read *"Listening, C1: hearing could
    # have or might have in fast speech"* -- see `LISTENING_BANDS`.
}

#: **Authored for this project, one per sitting**, each pitched at a band and
#: each answerable in about ninety seconds by talking about the learner's own
#: life (PRD §6: *"One prompt, free response"*). Everyday life first (CLAUDE.md
#: §4); nothing about work.
SPEAKING_PROMPTS: tuple[tuple[str, str], ...] = (
    ("B1", "Tell me about a place you like to go at the weekend, and why you like it."),
    ("B1", "Describe a meal you remember well. Where were you, and who were you with?"),
    ("B1", "What's something you've changed your mind about in the last few years?"),
    ("B2", "Some people say renting a flat is better than buying one. What do you think, and why?"),
    ("B2", "Talk about a time a plan didn't work out. What happened, and what did you do next?"),
    ("B2", "If you could live in another city for a year, where would you go, and what would you miss?"),
)


def band_can_do(band: str, *, listening: bool = False) -> str:
    """The payload's `can_do` for one band's cohort: what the item must do."""
    if band not in BANDS:
        raise ValueError(band)
    what = "hears and fills correctly" if listening else "answers correctly"
    return (
        f"A placement check at CEFR {band}: every item is one a learner at {band} "
        f"{what} and a learner below {band} gets wrong."
    )


def all_targets(targets: dict[str, tuple[tuple[str, str], ...]]) -> tuple[str, ...]:
    return tuple(text for band in BANDS for _, text in targets.get(band, ()))


#: **Never drawn as a yes/no word.** Found by reading the first dry print, not
#: by a test: `lexemes.pos` comes from the frequency list's tagger and marks
#: *his*, *some*, *you* and *what* as NOUN, so a content-word filter on `pos`
#: alone put pronouns in the test. Three groups:
#:
#: * function words, whatever their tag — a yes to *his* measures nothing;
#: * fragments the subtitle tokeniser split off a contraction (*haven* from
#:   *haven't*, *don* from *don't*), which rank high for that reason only;
#: * words an adult placement check does not show a stranger out of context —
#:   sex, violence, religion, swearing. The CEFR tag says they are common; a
#:   first screen of a product says something else.
NOT_A_TEST_WORD: frozenset[str] = frozenset("""
    a an the this that these those my your his her its our their mine yours hers ours theirs
    i you he she it we they me him us them myself yourself himself herself itself
    ourselves yourselves themselves who whom whose which what where when why how
    some any many much more most few little less least all both each every either
    neither none no nobody nothing somebody someone something anybody anyone anything
    everybody everyone everything one two three four five six seven eight nine ten
    first second last other another such same own enough several
    be am is are was were been being do does did done have has had having
    can could will would shall should may might must ought
    to of in on at by for with from about into onto over under up down out off
    through across along around before after behind between beyond during since until
    and or but so because if than then though although while whether yet also too
    very just only even still already ever never always often sometimes again
    not yes yeah yep nope ok okay oh hey hi hello bye please thanks thank sorry
    here there now today tonight tomorrow yesterday
    haven don didn doesn isn wasn weren couldn wouldn shouldn aren hasn hadn mustn ain
    sex sexy naked kill killer murder dead death die gun shoot rape drug drugs
    god hell damn jesus christ church pray bitch shit fuck ass bastard whore
""".split())

#: **Written with a capital letter in normal use — never shown lower-case as a
#: test word (launch 2026-09-26, B4; W18-R1's reading found *englishman*).**
#: The lexicon is lower-cased by construction (`scripts/build_lexicon.py`), so
#: the draw cannot see capitals; this list is the pool read by a person on
#: 2026-09-26 (every content word ranked 1–10,000 with a CEFR tag, 5,000 of
#: them). **In:** the days, the months that are not also ordinary words, a
#: nationality, a faith, a title, three oceans and seas, the Olympics, a
#: political adjective, three acronyms. **Out, deliberately:** *march* and *may*
#: (ordinary words too; *may* is a function word above), *polish*, *turkey*,
#: *arctic* (lower-case as an adjective), *valentine* and *scrooge* (lower-case
#: as common nouns), *god*, *internet*, *heaven*.
CAPITALISED_IN_USE: frozenset[str] = frozenset("""
    monday tuesday wednesday thursday friday saturday sunday
    january february april june july august september october november december
    englishman christian mrs atlantic pacific mediterranean olympic olympics soviet
    dna dvd hiv
""".split())

#: Pairs no rule below reaches, each spelling → the one it is keyed under.
_SPELLING_PAIRS: dict[str, str] = {
    "grey": "gray", "moustache": "mustache", "jewellery": "jewelry",
    "judgement": "judgment", "programme": "program", "whisky": "whiskey",
    "practise": "practice", "adviser": "advisor", "enquiry": "inquiry",
    "mamma": "mama",
}
_SPELLING_RULES: tuple[tuple[str, str], ...] = (
    (r"our(ite|able|ably|hood|ful|less|s)?$", r"or\1"),  # colour, favourite
    (r"(?<=[a-z]{2})is(e|ed|es|ing|ation|ations)$", r"iz\1"),  # realise
    (r"tre$", "ter"),  # centre, theatre, metre
    (r"ence$", "ense"),  # defence, licence
    (r"([aeiou])ll(er|ed|ing|ous)$", r"\1l\2"),  # traveller, marvellous
    (r"logue$", "log"),  # catalogue
)


def spelling_key(lemma: str) -> str:
    """Two spellings of one word share a key: *moustache* and *mustache*,
    *colour* and *color* (launch 2026-09-26, B4).

    **Checked against the whole draw pool, not trusted:** over the 5,000
    candidates it groups exactly 39 pairs, every one a spelling of one word,
    and nothing else — `tests/test_placement_bank.py` holds that list
    hardcoded, so a rule that starts merging two different words fails there.
    """
    key = _SPELLING_PAIRS.get(lemma, lemma)
    for pattern, replacement in _SPELLING_RULES:
        key = re.sub(pattern, replacement, key)
    return key
