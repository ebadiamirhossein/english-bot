/**
 * Input bounds mirrored from `packages/core/services/correction.py`.
 *
 * The server is the authority — it answers 422 outside these — but a learner
 * should not have to round-trip to find out a sentence was too short. Kept in
 * one file so the two places that need them cannot each invent their own, and
 * asserted against the Python constants by
 * `tests/test_web_shell.py::test_the_correction_bounds_match_the_service`.
 */

export const CORRECTION_MIN_CHARS = 10;
export const CORRECTION_MAX_CHARS = 1000;
