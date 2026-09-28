"""W32a: the word-dictionary command. **Human-run, dry by default.**

    python -m core.video.dictionary                    # the plan and its cost; no call
    python -m core.video.dictionary --pilot 60         # the pilot's plan; no call
    python -m core.video.dictionary --pilot 60 --apply # 60 words → a JSONL report, NO row
    python -m core.video.dictionary --apply            # the backfill (C1's scope)
    python -m core.video.dictionary --payload 25 --user 3   # W32b: one video's map, its bytes

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
                        help="W32b: print one video's meanings map size (read-only)")
    parser.add_argument("--user", type=int, default=None, help="the learner, for --payload")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.payload is not None:
        return _payload(args.payload, args.user)

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


def _payload(video_id: int, user_id: int | None) -> int:
    """W32b: the size of one video's meanings map, raw and gzipped. Read-only."""
    from core.services import dictionary

    if user_id is None:
        raise SystemExit("--payload needs --user (the map carries that learner's L1 and saves)")
    body = dictionary.meanings_for(user_id, video_id)
    if body is None:
        raise SystemExit(f"video {video_id} is not assigned to user {user_id}")
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    logger.info(
        "video=%s entries=%s forms=%s here=%s names=%s raw_bytes=%s gzip_bytes=%s",
        video_id, len(body["entries"]), len(body["forms"]), len(body["here"]),
        len(body["names"]), len(raw), len(gzip.compress(raw)),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
