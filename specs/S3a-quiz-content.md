# S3a · Quiz content and format

**Slice:** S3a (amends S3)
**Phase:** 1 — Foundation
**Depends on:** S3
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Goal

Fix three live-testing problems in the daily quiz: raw `error_type` codes in
user copy, ignored `track_weights`, and thin single-format questions.

## Non-goals

- Do not change the spacing ladder, scheduler, `services/errors.py`,
  `services/users.py`, or `handlers/correction.py`.
- No S4 streak / freeze / rescue work.

## Changes

1. **Labels, not codes** — every user-facing mention of an error type uses
   `error_types.label`.
2. **Track distribution** — `distribute_tracks(n, weights)` assigns tracks
   proportionally (5 @ 40/40/20 → 2/2/1), interleaved; prompt gets weights +
   per-question track and PRD §6 topic hints.
3. **Four formats** — gap ~40%, choice ~25%, reorder ~20%, spot ~15%; never
   more than two of the same format in a row. Concrete spoken sentences.
4. **Past prompts** — last 3 prompts per `error_id` read from prior quiz
   `sessions.payload` (no new column) and passed so the model does not repeat.
5. **Reorder / spot UI** — tappable tiles in the single edited message.

See the Cursor prompt / acceptance list for contracts and tests.
