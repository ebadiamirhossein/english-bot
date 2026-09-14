/**
 * Input bounds mirrored from `packages/core/writing/rules.py` (W16a).
 *
 * The server is the authority — it answers 422 outside these — but a learner
 * should not have to round-trip to find out an entry was too short. **The floor
 * is W3's ten, unchanged; the ceiling is Q-B's two thousand**, raised from the
 * 1,000 that silently truncated a 300-word entry (D8). Asserted against the
 * Python constants by
 * `tests/test_web_shell.py::test_the_writing_bounds_match_the_service`.
 *
 * **Neither number is ever shown to a learner.** The too-short check is a floor
 * inside the submit handler; its value appears in no string (design `1u`).
 */

export const WRITING_MIN_CHARS = 10;
export const WRITING_MAX_CHARS = 2000;
