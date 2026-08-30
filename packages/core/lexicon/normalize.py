"""Text → tokens → lemmas. **The only place in the codebase that does either.**

The seed builder, every ledger write and every coverage computation call the
``tokenize`` and ``lemmatize`` defined here. That is not a style preference. If
seeding lemmatised ``running → run`` while coverage lemmatised
``running → running``, the ledger would silently never match, coverage would
read low forever, and nothing would fail — the S24 ``Meaning``/``Translation``
mismatch in a different costume. Three things make it structural rather than
conventional: the ledger stores ``lexeme_id`` and never a string, so a second
tokeniser cannot write a mismatched row; an identity test asserts the call
sites hold the *same function object*; and an AST test forbids a second
word-tokenising regex anywhere in ``core`` or ``apps``.

Resolving is not creating. ``lemmatize`` returns ``None`` for a form it cannot
account for — it can fail, but it cannot invent a lemma. Growing the lexicon is
``core.services.lexicon.ensure_lexeme``, called only from an explicit tap with
a surface form the learner actually produced. **It can still resolve WRONGLY,
which is a different guarantee and was confused with this one for eight slices
— see ``lemmatize``'s docstring and #177.**
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# packages/core/lexicon/normalize.py → lexicon → core → packages → repo root.
# `data/` is repo-level for the same reason `migrations/` is: it is shared by
# every app, and `pip install -e packages/core` leaves the tree in place.
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
LEXEMES_FILE = DATA_DIR / "lexemes.tsv"
INFLECTIONS_FILE = DATA_DIR / "inflections.tsv"

# ── what gets thrown away before anything is counted ────────────────────────

# Caption annotations: `[Music]`, `[Applause]`, `(upbeat music)`. Square
# brackets are stripped unconditionally — they are vanishingly rare in speech.
# Parentheses only when they hold at most three words, because a real aside in
# a transcript is usually longer and is genuine English the learner heard.
ANNOTATION = re.compile(r"\[[^\]]{0,80}\]|\((?:\s*\S+){1,3}\s*\)")

# Straight and curly apostrophes and quotes, folded so `don't` and `don’t` are
# one token. This is a **superset** of what
# `core.services.reading.normalize_for_match` folds: every character that fold
# handles is handled identically here, plus U+02BC and U+2032, which turn up in
# machine-generated transcripts and which reading has never had to see. A test
# pins the shared part rather than importing across the purity boundary — a
# lexicon that folded less than the services do would split `don’t` from
# `don't` and quietly halve a contraction's frequency.
APOSTROPHES = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u0060": "'", "\u00b4": "'",
    "\u02bc": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u00ab": '"', "\u00bb": '"',
})

# ASR disfluency. A closed list on purpose: real interjections — `wow`, `oh`,
# `yeah`, `okay` — stay in the denominator, because they are words a learner
# either knows or does not.
FILLERS = frozenset({"uh", "uhh", "um", "umm", "mm", "mmm", "hmm", "er",
                     "erm", "ah", "eh", "mhm", "uhm"})

# Expanded before tokenising. A `gonna` lexeme would fragment the ledger — a
# learner who knows `going` and `to` does not need a third row — and W13's
# tap-to-define wants the expansion anyway. The surface form travels with the
# token, so the player can still highlight what was actually written.
CONTRACTIONS: dict[str, tuple[str, ...]] = {
    "aren't": ("are", "not"), "can't": ("can", "not"),
    "couldn't": ("could", "not"), "didn't": ("did", "not"),
    "doesn't": ("does", "not"), "don't": ("do", "not"),
    "hadn't": ("had", "not"), "hasn't": ("has", "not"),
    "haven't": ("have", "not"), "isn't": ("is", "not"),
    "mightn't": ("might", "not"), "mustn't": ("must", "not"),
    "needn't": ("need", "not"), "shan't": ("shall", "not"),
    "shouldn't": ("should", "not"), "wasn't": ("was", "not"),
    "weren't": ("were", "not"), "won't": ("will", "not"),
    "wouldn't": ("would", "not"), "ain't": ("is", "not"),
    "i'm": ("i", "am"), "i've": ("i", "have"), "i'll": ("i", "will"),
    "i'd": ("i", "would"), "you're": ("you", "are"),
    "you've": ("you", "have"), "you'll": ("you", "will"),
    "you'd": ("you", "would"), "he's": ("he", "is"), "he'll": ("he", "will"),
    "he'd": ("he", "would"), "she's": ("she", "is"),
    "she'll": ("she", "will"), "she'd": ("she", "would"),
    "it's": ("it", "is"), "it'll": ("it", "will"), "it'd": ("it", "would"),
    "we're": ("we", "are"), "we've": ("we", "have"), "we'll": ("we", "will"),
    "we'd": ("we", "would"), "they're": ("they", "are"),
    "they've": ("they", "have"), "they'll": ("they", "will"),
    "they'd": ("they", "would"), "that's": ("that", "is"),
    "that'll": ("that", "will"), "there's": ("there", "is"),
    "there're": ("there", "are"), "here's": ("here", "is"),
    "what's": ("what", "is"), "who's": ("who", "is"),
    "where's": ("where", "is"), "how's": ("how", "is"),
    "let's": ("let", "us"), "gonna": ("going", "to"),
    "wanna": ("want", "to"), "gotta": ("got", "to"),
    "gimme": ("give", "me"), "lemme": ("let", "me"),
    "kinda": ("kind", "of"), "sorta": ("sort", "of"),
    "outta": ("out", "of"), "dunno": ("do", "not", "know"),
    "y'all": ("you", "all"), "'cause": ("because",), "cuz": ("because",),
}

# Numerals, and words. A hyphenated compound stays one token because the seed
# list carries hyphenated entries; one that is not in the table resolves to
# nothing and is counted unknown, which is the honest answer.
TOKEN = re.compile(r"[0-9]+(?:[.,:/][0-9]+)*|[A-Za-z](?:[A-Za-z'-]*[A-Za-z])?")
SENTENCE_END = re.compile(r"[.!?\n\r]")

# ── casing ──────────────────────────────────────────────────────────────────

# Auto-generated YouTube captions are often entirely lowercase and sometimes
# entirely uppercase, and W12 selects videos by the coverage number, so the
# proper-noun rule cannot be applied blind. Outside this band the rule is
# switched off for that text and the report says so.
CASING_MIN_TOKENS = 30
CAPITALISED_MIN = 0.02
CAPITALISED_MAX = 0.40
ALL_CAPS_MAX = 0.30


@dataclass(frozen=True, slots=True)
class Token:
    """One word of running text, after contraction expansion."""

    surface: str
    lower: str
    sentence_initial: bool
    is_numeric: bool

    @property
    def is_filler(self) -> bool:
        return self.lower in FILLERS

    @property
    def is_capitalised(self) -> bool:
        return self.surface[:1].isupper()


def fold_apostrophes(text: str) -> str:
    return text.translate(APOSTROPHES)


@lru_cache(maxsize=1)
def seeded_lemmas() -> frozenset[str]:
    """Every lemma in `data/lexemes.tsv` — what a guess is checked against."""
    return frozenset(row[0] for row in _read_tsv(LEXEMES_FILE))


@lru_cache(maxsize=1)
def lexeme_rows() -> tuple[tuple[str, str, int, int, str], ...]:
    """`data/lexemes.tsv` as (lemma, pos, freq_rank, freq_band, cefr)."""
    rows = []
    for row in _read_tsv(LEXEMES_FILE):
        lemma, pos, rank, band, cefr = row[:5]
        rows.append((lemma, pos, int(rank), int(band), cefr))
    return tuple(rows)


@lru_cache(maxsize=1)
def cefr_tagged_lemmas() -> frozenset[str]:
    """Lemmas the CEFR-J wordlist actually levels — curated vocabulary.

    This is the discriminator the proper-noun rule needs. The OpenSubtitles
    frequency list is lowercased, so capitalisation is gone by the time it
    reaches us and names sit high in it: `john` at rank 548, `sarah` at 1221,
    `paris` at 1107. None of them carries a CEFR tag; `internet` carries A1.
    "Is this in the lexeme table" cannot tell a name from a word here, and
    "does a vocabulary syllabus level it" can.
    """
    return frozenset(row[0] for row in lexeme_rows() if row[4])


@lru_cache(maxsize=1)
def inflections() -> dict[str, str]:
    """Surface form → lemma, generated offline by `scripts/build_lexicon.py`."""
    return {row[0]: row[1] for row in _read_tsv(INFLECTIONS_FILE)}


def _read_tsv(path: Path) -> list[list[str]]:
    """Comment lines, then one header row, then data.

    The header is skipped **by position** — the first non-comment line — and
    never by matching its text. Skipping any row whose first field read `lemma`
    or `surface` looked equivalent and silently dropped the English word
    *surface*, rank 1946, B1: no error, one lexeme short, and a hole in
    coverage that nothing would have pointed at.
    """
    rows: list[list[str]] = []
    header_seen = False
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            if not header_seen:
                header_seen = True
                continue
            rows.append(line.rstrip("\n").split("\t"))
    return rows


def tokenize(text: str) -> list[Token]:
    """Running text → word tokens, contractions expanded, annotations gone."""
    cleaned = ANNOTATION.sub(" ", fold_apostrophes(text))
    tokens: list[Token] = []
    at_sentence_start = True
    previous_end = 0
    for match in TOKEN.finditer(cleaned):
        if SENTENCE_END.search(cleaned[previous_end : match.start()]):
            at_sentence_start = True
        previous_end = match.end()
        raw = match.group(0)
        for offset, word in enumerate(_expand(raw)):
            tokens.append(
                Token(
                    surface=word,
                    lower=word.lower(),
                    sentence_initial=at_sentence_start and offset == 0,
                    is_numeric=word[0].isdigit(),
                )
            )
        at_sentence_start = False
    return tokens


def _expand(raw: str) -> tuple[str, ...]:
    """One raw token → one or more words, capitalisation carried to the first."""
    expansion = CONTRACTIONS.get(raw.lower())
    if expansion is None:
        # A residual possessive or `is` clitic — `Dave's`, `the dog's here`.
        # Reading it as `is` misfiles the possessive, knowingly: it attaches to
        # a token the learner either knows or does not, in the same way.
        if raw.lower().endswith("'s") and len(raw) > 2:
            stem = raw[:-2]
            return (stem, "is") if stem else (raw,)
        return (raw,)
    if raw[:1].isupper():
        return (expansion[0].capitalize(), *expansion[1:])
    return expansion


def casing_profile(tokens: list[Token]) -> str:
    """`conventional`, `lowercase`, `uppercase` or `unreliable`.

    Below `CASING_MIN_TOKENS` the ratios mean nothing — a short text has too
    few sentences — so it is reported as conventional and the proper-noun rule
    is applied normally.
    """
    words = [t for t in tokens if not t.is_numeric]
    if len(words) < CASING_MIN_TOKENS:
        return "conventional"
    capitalised = sum(1 for t in words if t.is_capitalised) / len(words)
    all_caps = sum(1 for t in words if t.surface.isupper() and len(t.surface) > 1)
    all_caps /= len(words)
    if all_caps > ALL_CAPS_MAX:
        return "uppercase"
    if capitalised < CAPITALISED_MIN:
        return "lowercase"
    if capitalised > CAPITALISED_MAX:
        return "unreliable"
    return "conventional"


def lemmatize(surface: str, vocabulary: frozenset[str] = frozenset()) -> str | None:
    """Surface form → lemma, or ``None`` when it cannot be accounted for.

    Three steps, each a lookup and never a guess that stands on its own:

    1. the committed inflection table maps it;
    2. the form is already a lemma we know;
    3. suffix rules propose candidates, and a candidate is accepted **only if
       it is already a known lemma**. That check is what turns a guess into a
       lookup — the function can fail to resolve, but it cannot invent.

    **That last claim was true literally and false in effect until W12a.** The
    accepted candidate has to be a known lemma, but the seed list holds
    OpenSubtitles artefacts — `ti` at rank 9,856, `tru`, `we` — so `tier`
    resolved to `ti` through a rule that never invented anything. *Cannot
    invent* is not the same guarantee as *cannot resolve wrongly*, and reading
    it as though it were is what let the defect stand from W4 to W12a. **W12a
    (#177) deleted the `-er` and `-est` rules**; comparatives come from the
    inflection table, which was repaired in the same commit (#282).

    The table is consulted *before* the identity check, and the order is
    load-bearing for homographs. `saw` earns a lexeme row of its own at rank
    10,415 off `sawing`/`sawed`, while `see` sits at rank 49; identity-first
    would leave "I saw a film" resolving to the carpentry tool. The builder
    only writes a table entry when its lemma outranks the form's own entry, so
    a table hit already means the better-ranked reading won.

    ``vocabulary`` widens the accepted set beyond the seed file, and the caller
    passes the lemmas this learner already has ledger rows for. Without it a
    lexeme grown from a tap (``origin='grown'``, absent from `data/`) could
    never be recognised in a transcript again.

    An unresolved token is counted **unknown**, so coverage reads low rather
    than falsely high — the safe direction.
    """
    lower = fold_apostrophes(surface).lower()
    known = seeded_lemmas()
    mapped = inflections().get(lower)
    if mapped is not None and (mapped in known or mapped in vocabulary):
        return mapped
    if lower in known or lower in vocabulary:
        return lower
    for candidate in _suffix_candidates(lower):
        if candidate in known or candidate in vocabulary:
            return candidate
    return None


def _suffix_candidates(word: str):
    """Undo the regular English endings, most specific first.

    Every candidate is checked against the lemma table before it is accepted,
    so an over-eager rule costs nothing: the worst case is that no candidate
    matches and the token counts as unknown.
    """
    length = len(word)
    if word.endswith("ies") and length > 4:
        yield word[:-3] + "y"
    if word.endswith("ied") and length > 4:
        yield word[:-3] + "y"
    if word.endswith("es") and length > 3:
        yield word[:-2]
        yield word[:-1]
    if word.endswith("s") and not word.endswith("ss") and length > 2:
        yield word[:-1]
    if word.endswith("ed") and length > 3:
        yield word[:-2]
        yield word[:-1]
        if length > 4 and word[-3] == word[-4]:  # stopped → stop
            yield word[:-3]
    if word.endswith("ing") and length > 4:
        yield word[:-3]
        yield word[:-3] + "e"                    # making → make
        if length > 5 and word[-4] == word[-5]:  # running → run
            yield word[:-4]
    # `-er` and `-est` were HERE and were deleted in W12a (#177). They stripped
    # a derivational `-er` onto whatever stem happened to be a known lemma:
    # `tier` → `ti` (an OpenSubtitles artefact at rank 9,856), `router` →
    # `route`, `blogger` → `blog`. Measured over the 11,215 `-er`/`-est` words
    # in `/usr/share/dict/words`, they bought 2,814 resolutions, of which the
    # comparatives were `freer`, `freest`, `bluer`, `bluest`, `eerier`,
    # `eeriest`, `vaguer` and `vaguest` — all eight now answered by the
    # inflection table, which was repaired in the same commit (#282). Every
    # remaining one of the 2,814 pointed at a NOUN or VERB lemma and so read
    # coverage HIGH, which is the unsafe direction this module refuses
    # everywhere else. Comparatives are the inflection table's job; `bigger`,
    # `happiest` and `nicer` were always answered at step 1 and still are.
    if word.endswith("ily") and length > 4:
        yield word[:-3] + "y"
    if word.endswith("ly") and length > 3:
        yield word[:-2]
