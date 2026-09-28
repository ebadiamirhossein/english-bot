"""W32a: the word-dictionary command. **Human-run, dry by default.**

    python -m core.video.dictionary                    # the plan and its cost; no call
    python -m core.video.dictionary --pilot 60         # the pilot's plan; no call
    python -m core.video.dictionary --pilot 60 --apply # 60 words → a JSONL report, NO row
    python -m core.video.dictionary --apply            # the backfill (C1's scope)
    python -m core.video.dictionary --payload 25            # one video's map, its bytes (read-only)
    python -m core.video.dictionary --compare A.jsonl B.jsonl   # two pilot reports, side by side

**THIS FILE REACHES NO MODEL.** It parses arguments and prints; the plan, the
store and the run are `core.services.dictionary`'s, and the model is reached
only through `core.video.explain.define_words` — `VIDEO_MODEL_CALLERS` stays
`{explain.py}` (`test_core_video_never_calls_the_model` scans this file too).

────────────────────────────────────────────────────────────────────────────────
THE SCOPE — OPERATOR RULING C1, 2026-09-28

Not the whole 15,000-row list. **(a)** every key in the `ok` pool videos' lines,
plus **(b)** the 5,000 most frequent lexemes that carry a POS tag, by
`lexemes.freq_rank`. The 4,564 untagged rows (names, abbreviations) are left
out of (b); a video or a miss reaches them. `--scope all` exists for later and
is never the default.

THE MODEL — RULING Q1

The pilot runs once per model, the model chosen by exporting `LLM_MODEL` in the
shell for that one command (CLAUDE.md §2: a swap is one variable). A person
reads the two reports' `fa`/`lt`; the backfill then runs with the winner.

THE LINE TO READ BEFORE `--apply` — RULING C4

The dry run's last line ends with the ceiling in dollars, to set against the
month's usage and limit in the Anthropic Console **before** spending: the spend
limit has stopped the app once (#458).
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: Q1's pilot: 60 fixed words, the same for both models so the reports can be
#: read side by side. Common words with several senses, everyday B1–B2 words
#: (*shed* and *dinosaur*, W31e's two), informal and slang forms, two taboo-ish
#: words, function words, and three names. *moving* is here as its key, *move*.
PILOT_WORDS: tuple[str, ...] = (
    # several common senses
    "over", "run", "get", "miss", "move", "still", "mean", "fine", "deal", "break",
    "figure", "catch", "set", "turn", "point",
    # everyday B1–B2
    "shed", "dinosaur", "awkward", "bother", "cope", "reckon", "fancy", "grab", "hang",
    "mess", "rough", "spare", "stuck", "tough", "weird", "bet", "sort", "brilliant",
    "errand", "chore",
    # informal and slang
    "gonna", "wanna", "gotta", "kinda", "dude", "awesome", "yeah", "nope", "cool", "sick",
    "bro", "stuff", "freak", "chill", "crap",
    # taboo-ish
    "damn", "hell",
    # function words
    "the", "just", "like", "pretty", "whatever",
    # names
    "phillips", "ross", "vilnius",
)


def _model() -> str:
    from core.config import load_settings

    return str(load_settings().llm_model)


def _runtime_dir() -> Path:
    from core.config import load_settings

    return Path(load_settings().runtime_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m core.video.dictionary",
        description=(
            "Fill the word dictionary ahead of time. DRY BY DEFAULT: --apply is the "
            "only thing that spends money."
        ),
    )
    parser.add_argument("--apply", action="store_true",
                        help="MAKE BILLED CALLS. Without this nothing is sent.")
    parser.add_argument("--pilot", type=int, default=0, metavar="N",
                        help="the first N of the fixed pilot words; writes a JSONL report, no row")
    parser.add_argument("--out", type=Path, default=None, help="the pilot report's path")
    parser.add_argument("--top", type=int, default=None,
                        help="(b): how many tagged lexemes, by freq_rank (default 5000)")
    parser.add_argument("--scope", choices=("c1", "all"), default="c1")
    parser.add_argument("--limit", type=int, default=None, help="buy at most N words this run")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--payload", type=int, default=None, metavar="VIDEO",
                        help="print one video's meanings map size (read-only)")
    parser.add_argument("--user", type=int, default=None,
                        help="with --payload: that learner's exact map (the video must be theirs)")
    parser.add_argument("--l1", default="fa", help="with --payload and no --user: the language")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"),
                        help="print two pilot reports side by side (read-only)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.compare:
        return _compare(*args.compare)
    if args.payload is not None:
        return _payload(args.payload, args.user, args.l1)

    from core.db import connection
    from core.services import dictionary
    from core.services import glosses as glosses_service

    model = _model()
    with connection() as conn:
        languages = glosses_service.learner_languages(conn)
        if args.pilot:
            words = list(PILOT_WORDS[: args.pilot])
            logger.info("pilot words=%s model=%s l1=%s", len(words), model,
                        ",".join(languages) or "none")
        else:
            top = dictionary.TOP_LEXEMES if args.top is None else args.top
            plan = dictionary.plan_backfill(conn, top=top, scope=args.scope)
            words = list(plan.to_buy)
            if args.limit is not None:
                words = words[: max(0, args.limit)]
            logger.info(
                "scope=%s (a) pool_videos=%s pool_words=%s (b) tagged_lexemes=%s top=%s "
                "union=%s already_held=%s to_buy=%s excluded_untagged=%s "
                "excluded_not_a_token=%s",
                args.scope, plan.pool_videos, len(plan.pool), len(plan.lexemes),
                top if args.scope == "c1" else "all", len(plan.union),
                len(plan.union) - len(plan.to_buy), len(plan.to_buy),
                plan.untagged_excluded, plan.not_a_token_excluded,
            )
    cost = dictionary.estimate(len(words), n_langs=len(languages), model=model)
    logger.info("words_this_run=%s l1=%s concurrency=%s %s", len(words),
                ",".join(languages) or "none", args.concurrency, dictionary.cost_line(cost, model))

    out = None
    if args.pilot:
        out = args.out or _runtime_dir() / f"dictionary-pilot-{model}.jsonl"
    dictionary.run_backfill(
        words=words, apply=args.apply, concurrency=args.concurrency, source="backfill",
        model=model, languages=languages, pilot_out=out,
    )
    return 0


def _payload(video_id: int, user_id: int | None, lang: str) -> int:
    """The size of one video's meanings map, raw and gzipped — the number the
    W32 plan could only estimate (the Mac's dev database holds no videos).
    **Read-only.** With `--user`, that learner's exact map (the video must be
    theirs); without, the map a learner of `--l1` would get, with nothing
    saved — so any video can be measured (video 25 need not be assigned)."""
    from core.services import dictionary

    if user_id is not None:
        body = dictionary.meanings_for(user_id, video_id)
        if body is None:
            raise SystemExit(f"video {video_id} is not assigned to user {user_id}")
    else:
        body = dictionary.measure_meanings(video_id, lang)
        if body is None:
            raise SystemExit(f"video {video_id} does not exist")
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    logger.info(
        "video=%s l1=%s entries=%s forms=%s here=%s names=%s raw_bytes=%s gzip_bytes=%s",
        video_id, body["l1"], len(body["entries"]), len(body["forms"]), len(body["here"]),
        len(body["names"]), len(raw), len(gzip.compress(raw, mtime=0)),
    )
    return 0


def _compare(a: Path, b: Path) -> int:
    """Q1's read: two pilot reports, one word per block — each model's first
    sense, its register and its `fa` and `lt`. **Read-only; prints to stdout**,
    for a person, never a machine."""

    def load(path: Path) -> tuple[str, dict[str, dict]]:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        model = next((r.get("model") for r in rows if r.get("model")), path.stem)
        return model, {r["word"]: r for r in rows}

    def show(row: dict | None) -> str:
        if row is None:
            return "—"
        if "refused" in row:
            return f"REFUSED ({row['refused'][:60]})"
        if row.get("kind") == "name":
            return "a name"
        senses = row.get("senses") or []
        first = senses[0] if senses else {}
        l1 = first.get("l1", {})
        extra = f" (+{len(senses) - 1} more)" if len(senses) > 1 else ""
        return (f"[{row.get('register')}] {first.get('definition', '')}{extra}\n"
                f"        fa: {l1.get('fa', '—')}\n        lt: {l1.get('lt', '—')}")

    model_a, rows_a = load(a)
    model_b, rows_b = load(b)
    words = list(dict.fromkeys([*rows_a, *rows_b]))
    for word in words:
        print(f"── {word}")
        print(f"  {model_a}: {show(rows_a.get(word))}")
        print(f"  {model_b}: {show(rows_b.get(word))}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
