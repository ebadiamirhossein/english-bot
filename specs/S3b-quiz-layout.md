# S3b · Quiz question layout

**Slice:** S3b (amends S3a)
**Phase:** 1 — Foundation
**Depends on:** S3a
**Status:** ⬜ not started
**Spec written:** 2026-08-03

---

## Goal

Make quiz questions readable. Body is for reading; buttons are for tapping.
Separate feedback from the next question. Fix feedback and completion copy.

## Non-goals

No changes to spacing, scheduler, `errors.py`, `users.py`, `correction.py`,
grading logic, or question-generation code paths beyond the spot 8-word prompt
rule in `quiz.txt`.

## Locked decisions

1. **Body reads / buttons tap** — every format must be fully readable in the
   message body before the user looks at buttons.
2. **Spot ≤ 8 words** — nine tile buttons are too many to scan.
