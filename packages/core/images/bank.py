"""`python -m core.images.bank` — W13d's picture bank. **Human-run, dry by
default (#196). NO BILLED CALL ANYWHERE:** Wikidata and Commons are free.

    python -m core.images.bank --propose                      # dry: the lemmas it would ask about; sends nothing
    python -m core.images.bank --propose --lemmas spoon,ladder  # dry, on the operator's own list
    python -m core.images.bank --propose --live --contact C --out DIR
                                                              # asks Wikidata/Commons; writes DIR/proposals.tsv,
                                                              # DIR/refused.tsv and DIR/sheet.html; writes NO row
    python -m core.images.bank --load                         # dry: data/lexeme_images.tsv against the table
    python -m core.images.bank --load --apply --contact C     # re-checks each file on Commons, downloads, writes

**THE APPROVAL IS A LINE IN `data/lexeme_images.tsv`, COMMITTED.** `--propose`
finds a candidate picture per lemma and applies the licence gate
(`core.images.judge`); the operator opens `sheet.html`, keeps the lines of
`proposals.tsv` whose picture shows the word, and appends them to the data
file. `--load --apply` writes exactly the file's lines — adding, replacing, and
WITHDRAWING any picture whose line was removed — so the file and the table
cannot disagree for long, and `git log` is the record of who approved what.

**`--apply` DOES NOT TRUST THE FILE'S LICENCE COLUMN.** Each file is read again
from Commons: a different SHA-1 (a new upload over the same title) or a licence
or author that no longer matches is REFUSED with its reason, and nothing about
that lemma changes. Wikimedia's own reuse page: *"you should verify the
copyright status of each image"*.

`C` is a contact for Wikimedia's User-Agent policy — an email address or a URL
the operator is willing to publish to Wikimedia's server logs. It is never
stored and never logged by this project.
"""

from __future__ import annotations

import argparse
import csv
import html
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from core.images import (
    ALLOWED_LICENCES,
    ATTRIBUTION_FREE,
    MAX_BYTES,
    bytes_match,
    judge,
)
from core.images.commons_api import CommonsClient, CommonsError
from core.services import lexeme_images
from core.services.paths import assert_path_outside_repo, repo_root

logger = logging.getLogger(__name__)

DATA_FILE = repo_root() / "data" / "lexeme_images.tsv"

COLUMNS = (
    "lemma",
    "commons_file",
    "original_sha1",
    "licence",
    "author",
    "licence_url",
    "source_url",
)

#: P18 values tried per item before the lemma is reported as having no admitted
#: picture. Two, because the second is usually a detail or a diagram.
FILES_PER_ITEM = 2

#: Per lemma: one search, one claims read, `FILES_PER_ITEM` file reads.
REQUESTS_PER_LEMMA = 2 + FILES_PER_ITEM

DEFAULT_PROPOSALS = 40


# ---------------------------------------------------------------------------
# the data file
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Line:
    lemma: str
    commons_file: str
    original_sha1: str
    licence: str
    author: str
    licence_url: str
    source_url: str

    def row(self) -> list[str]:
        return [getattr(self, c) for c in COLUMNS]


class DataFileError(ValueError):
    """The data file cannot be loaded at all. Every problem is listed."""


def read_lines(path: Path) -> list[Line]:
    """Parse and statically check the approved file. **No network, no SQL.**

    Refuses the WHOLE file on any bad line: an approval file that loads
    partially is one whose meaning depends on which lines happened to parse.
    """
    problems: list[str] = []
    lines: list[Line] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader, None)
        if header is None or tuple(header) != COLUMNS:
            raise DataFileError(f"{path.name}: header must be {'\t'.join(COLUMNS)}")
        for number, raw in enumerate(reader, start=2):
            if not raw or all(not cell.strip() for cell in raw):
                continue
            if len(raw) != len(COLUMNS):
                problems.append(f"line {number}: {len(raw)} columns, expected {len(COLUMNS)}")
                continue
            line = Line(*(cell.strip() for cell in raw))
            where = f"line {number} ({line.lemma})"
            if line.lemma in seen:
                problems.append(f"{where}: lemma appears twice")
            seen.add(line.lemma)
            if line.licence not in ALLOWED_LICENCES:
                problems.append(f"{where}: licence not admitted: {line.licence}")
            if line.licence not in ATTRIBUTION_FREE and not (
                line.author and line.licence_url.startswith("https://creativecommons.org/")
            ):
                problems.append(f"{where}: {line.licence} needs an author and a licence URL")
            if not line.commons_file.startswith("File:"):
                problems.append(f"{where}: commons_file must start with File:")
            if not line.source_url.startswith("https://commons.wikimedia.org/wiki/File:"):
                problems.append(f"{where}: source_url must be a Commons file page")
            if len(line.original_sha1) != 40 or any(
                c not in "0123456789abcdef" for c in line.original_sha1
            ):
                problems.append(f"{where}: original_sha1 is not a SHA-1")
            lines.append(line)
    if problems:
        raise DataFileError("\n".join(problems))
    return lines


# ---------------------------------------------------------------------------
# --load
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadPlan:
    add: list[Line]
    replace: list[Line]
    unchanged: list[Line]
    withdraw: list[str]
    unknown: list[str]

    @property
    def writes(self) -> int:
        return len(self.add) + len(self.replace) + len(self.withdraw)


def load_plan(lines: list[Line]) -> LoadPlan:
    stored = lexeme_images.stored()
    known = lexeme_images.lexeme_ids([l.lemma for l in lines])
    add, replace, unchanged, unknown = [], [], [], []
    for line in lines:
        if line.lemma not in known:
            unknown.append(line.lemma)
            continue
        current = stored.get(line.lemma)
        if current is None:
            add.append(line)
        elif (current.commons_file, current.original_sha1, current.licence, current.author) != (
            line.commons_file, line.original_sha1, line.licence, line.author,
        ):
            replace.append(line)
        else:
            unchanged.append(line)
    listed = {l.lemma for l in lines}
    withdraw = sorted(lemma for lemma in stored if lemma not in listed)
    return LoadPlan(add, replace, unchanged, withdraw, sorted(unknown))


def print_load_plan(plan: LoadPlan) -> None:
    print(f"add: {len(plan.add)}  replace: {len(plan.replace)}  "
          f"unchanged: {len(plan.unchanged)}  withdraw: {len(plan.withdraw)}")
    for line in plan.add:
        print(f"  + {line.lemma}  {line.commons_file}  {line.licence}")
    for line in plan.replace:
        print(f"  ~ {line.lemma}  {line.commons_file}  {line.licence}")
    for lemma in plan.withdraw:
        print(f"  - {lemma}")
    if plan.unknown:
        print(f"refused, not in the lexicon (never created): {', '.join(plan.unknown)}")
    if plan.add or plan.replace:
        print(f"--apply reads each file from Commons: up to "
              f"{2 * (len(plan.add) + len(plan.replace))} requests.")


def apply_line(client: CommonsClient, lexeme_id: int, line: Line) -> str | None:
    """Verify one approved line against Commons NOW and store it.
    Returns a refusal reason, or None when stored."""
    info = client.file_info(line.commons_file)
    if info is None:
        return "the file is no longer on Commons"
    if info.sha1 != line.original_sha1:
        return "the file was re-uploaded since it was approved (SHA-1 differs)"
    verdict = judge(info.extmetadata, info.mime)
    if not verdict.admitted:
        return verdict.reason
    if verdict.licence != line.licence:
        return f"Commons now reads {verdict.licence}, approved as {line.licence}"
    if verdict.author != line.author:
        return f"Commons now credits {verdict.author!r}, approved as {line.author!r}"
    data = client.download(info.thumb_url)
    if len(data) > MAX_BYTES:
        return f"thumbnail is {len(data)} bytes, over {MAX_BYTES}"
    if not bytes_match(info.mime, data):
        return f"downloaded bytes are not {info.mime}"
    lexeme_images.replace(
        lexeme_id=lexeme_id,
        commons_file=info.title,
        source_url=info.source_url,
        original_sha1=info.sha1,
        author=verdict.author,
        licence=verdict.licence,
        licence_url=verdict.licence_url,
        mime=info.mime,
        width=info.thumb_width,
        height=info.thumb_height,
        data=data,
    )
    return None


def apply_plan(client: CommonsClient, plan: LoadPlan) -> dict[str, str]:
    """Write the plan. Returns `{lemma: reason}` for every refused line."""
    ids = lexeme_images.lexeme_ids([l.lemma for l in plan.add + plan.replace])
    refused: dict[str, str] = {}
    for line in plan.add + plan.replace:
        reason = apply_line(client, ids[line.lemma], line)
        if reason:
            refused[line.lemma] = reason
            print(f"  refused {line.lemma}: {reason}")
        else:
            print(f"  stored {line.lemma}")
    if plan.withdraw:
        print(f"  withdrawn: {lexeme_images.remove(plan.withdraw)}")
    return refused


# ---------------------------------------------------------------------------
# --propose
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Proposal:
    lemma: str
    line: Line | None
    thumb_url: str | None
    reason: str | None


def propose_one(client: CommonsClient, lemma: str) -> Proposal:
    qid = client.item_for(lemma)
    if qid is None:
        return Proposal(lemma, None, None, "no Wikidata item labelled exactly this lemma")
    names = client.images_of(qid)[:FILES_PER_ITEM]
    if not names:
        return Proposal(lemma, None, None, f"{qid} has no image (P18)")
    last = "no file readable"
    for name in names:
        info = client.file_info(name)
        if info is None:
            continue
        verdict = judge(info.extmetadata, info.mime)
        if not verdict.admitted:
            last = f"{info.title}: {verdict.reason}"
            continue
        line = Line(
            lemma=lemma,
            commons_file=info.title,
            original_sha1=info.sha1,
            licence=verdict.licence,
            author=verdict.author,
            licence_url=verdict.licence_url or "",
            source_url=info.source_url,
        )
        return Proposal(lemma, line, info.thumb_url, None)
    return Proposal(lemma, None, None, last)


def write_proposals(out: Path, proposals: list[Proposal]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "proposals.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        writer.writerow(COLUMNS)
        for p in proposals:
            if p.line:
                writer.writerow(p.line.row())
    with (out / "refused.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", quoting=csv.QUOTE_NONE,
                            lineterminator="\n", escapechar="\\")
        writer.writerow(("lemma", "reason"))
        for p in proposals:
            if p.reason:
                writer.writerow((p.lemma, p.reason))
    (out / "sheet.html").write_text(contact_sheet(proposals), encoding="utf-8")


def contact_sheet(proposals: list[Proposal]) -> str:
    """One page the operator reads before approving: each picture beside its
    word, licence and credit. **Hot-linked from Wikimedia because it is the
    operator's own review on the operator's own machine**; no learner ever loads
    this page."""
    e = html.escape
    rows = []
    for p in proposals:
        if p.line:
            rows.append(
                f"<tr><td><b>{e(p.lemma)}</b></td>"
                f"<td><img src=\"{e(p.thumb_url or '')}\" width=\"220\" alt=\"\"></td>"
                f"<td>{e(p.line.licence)}<br>{e(p.line.author or '—')}<br>"
                f"<a href=\"{e(p.line.source_url)}\">{e(p.line.commons_file)}</a></td></tr>"
            )
        else:
            rows.append(f"<tr><td>{e(p.lemma)}</td><td colspan=\"2\"><i>{e(p.reason or '')}</i></td></tr>")
    return (
        "<!doctype html><meta charset=\"utf-8\"><title>W13d proposals</title>"
        "<p>Keep a line of proposals.tsv only if the picture shows the word as a "
        "learner means it. Then append the kept lines to data/lexeme_images.tsv.</p>"
        f"<table border=\"1\" cellpadding=\"6\">{''.join(rows)}</table>"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W13d picture bank. Dry by default; nothing here is billed."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--propose", action="store_true")
    mode.add_argument("--load", action="store_true")
    parser.add_argument("--live", action="store_true", help="--propose: ask Wikidata/Commons")
    parser.add_argument("--apply", action="store_true", help="--load: verify, download, write")
    parser.add_argument("--contact", default="", help="Wikimedia User-Agent contact")
    parser.add_argument("--out", type=Path, help="--propose --live: directory outside the repo")
    parser.add_argument("--limit", type=int, default=DEFAULT_PROPOSALS)
    parser.add_argument(
        "--lemmas",
        default="",
        help="--propose: comma-separated lemmas the operator chose, instead of the query",
    )
    parser.add_argument("--file", type=Path, default=DATA_FILE)
    args = parser.parse_args(argv)
    if args.propose and args.apply:
        parser.error("--propose never writes a row: approve lines into the data file, then --load")
    if args.load and args.live:
        parser.error("--load is dry or --apply")
    if (args.live or args.apply) and not args.contact.strip():
        parser.error("--contact is required for any request to Wikimedia (User-Agent policy)")
    if args.propose and args.live and args.out is None:
        parser.error("--propose --live needs --out, a directory outside the repository")
    logging.basicConfig(level=logging.INFO)  # #140

    if args.propose:
        # The operator's own list wins over the query. Measured 2026-09-25 on
        # the Mac: the query's first 40 were mostly abstract nouns (*protection,
        # incident, theme*) — the NOUN tag narrows little — so naming the
        # picturable words directly is the cheaper route to a useful sheet.
        # Every named lemma must exist in the lexicon; none is ever created.
        chosen = [w.strip().lower() for w in args.lemmas.split(",") if w.strip()]
        if chosen:
            known = lexeme_images.lexeme_ids(chosen)
            missing = [w for w in chosen if w not in known]
            if missing:
                print(f"refused, not in the lexicon: {', '.join(missing)}")
                return 1
            lemmas = chosen
        else:
            lemmas = lexeme_images.proposal_lemmas(args.limit)
        print(f"{len(lemmas)} lemma(s), up to {REQUESTS_PER_LEMMA * len(lemmas)} requests "
              f"to Wikidata/Commons, none billed:")
        print("  " + ", ".join(lemmas) if lemmas else "  (none)")
        if not args.live:
            print("\ndry run — nothing was sent and nothing was written.")
            return 0
        out = assert_path_outside_repo(args.out, label="--out")
        client = CommonsClient(args.contact)
        try:
            proposals = [propose_one(client, lemma) for lemma in lemmas]
        except CommonsError as exc:
            print(f"stopped: {exc} — nothing was written.")
            return 1
        finally:
            client.close()
        write_proposals(out, proposals)
        kept = sum(1 for p in proposals if p.line)
        print(f"{kept} proposed, {len(proposals) - kept} refused, {client.requests} requests.")
        print(f"read {out / 'sheet.html'}; approve by appending lines of "
              f"{out / 'proposals.tsv'} to data/lexeme_images.tsv")
        return 0

    try:
        lines = read_lines(args.file)
    except DataFileError as exc:
        print(f"refused, nothing was written:\n{exc}")
        return 1
    plan = load_plan(lines)
    print_load_plan(plan)
    if not args.apply:
        print("\ndry run — nothing was sent and nothing was written.")
        return 0
    if plan.writes == 0:
        print("\nthe table already matches the file — nothing to write.")
        return 0
    from core.runs import confirm

    if not confirm(f"This changes {plan.writes} picture(s).", str(plan.writes)):
        print("stopped — nothing was sent.")
        return 1
    client = CommonsClient(args.contact)
    try:
        refused = apply_plan(client, plan)
    except CommonsError as exc:
        print(f"stopped: {exc} — lines before it were written; run again to finish.")
        return 1
    finally:
        client.close()
    print(f"done: {plan.writes - len(refused)} written, {len(refused)} refused, "
          f"{client.requests} requests.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
