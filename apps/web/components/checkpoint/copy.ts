/**
 * Every user-facing string on the checkpoint. **One file, so the no-guilt scan
 * has one place to look** — the same shape `components/session/copy.ts` has.
 *
 * CLAUDE.md §4, and the two rules that shaped every line here:
 *
 * **NEVER GUILT.** No "you failed", no score presented as a mark, no
 * disappointed anything. `tests/test_no_murphy_reaches_a_learner.py`'s sibling
 * scan covers this file.
 *
 * **RAISES ANNOUNCED, DROPS SILENT.** A pass may celebrate and may say what it
 * scored. **A failure says neither.** It does not name the mark, does not show
 * a fraction, does not show a bar against 80%, and does not describe the retake
 * as a second chance — which would imply a first one was squandered. The API
 * withholds `score_pct` on a failure so no client can render one by accident;
 * this file is the second layer, not the only one.
 */
export const CHECKPOINT = {
  eyebrow: "Saturday",
  title: "This week’s checkpoint.",
  intro: "Twelve questions on this week’s grammar. There’s no clock.",

  // The bank could not fill the sitting. **Says what IS, never what is missing**
  // — no count of how many items exist, which would be a backlog (#160).
  notReady: {
    title: "Not ready yet.",
    body: "This week’s checkpoint isn’t built yet. Nothing to do here today — the session on Today is where the practice is.",
  },

  // A position, not a count of what is left. Same reasoning as block 3's
  // `progress`: CLAUDE.md §4 forbids presenting a backlog.
  progress: "Question {n} of {total}",
  finish: "Finish the checkpoint",

  passed: {
    title: "Unit passed.",
    // The one number a learner is shown, and only on the way up.
    body: "You got {correct} of {total}. The next unit is open — you’ll see it in tomorrow’s session.",
  },

  // **The whole not-passed path, and it is deliberately short.** It names no
  // score, no mark and no shortfall. "Not this time" is not available either:
  // it implies a verdict on the person rather than on the week.
  //
  // **The KEY is `notYet` and not the obvious word**, because the no-guilt scan
  // reads source text and not only string literals — so an identifier carrying
  // a banned word trips it. That is the scan being right rather than
  // over-eager: a key name leaks into stack traces, into logs and into the next
  // person's vocabulary for this state, and the state is *the unit stays open*,
  // not a verdict.
  notYet: {
    title: "We’ll come back to this one.",
    body: "This unit stays open and the practice carries on as usual. There’s another go on {date}.",
    // No date is a real state — `retake_due_on` is set by the writer, but a
    // client must not render "undefined" if it ever is not.
    bodyNoDate:
      "This unit stays open and the practice carries on as usual. There’ll be another go in a few days.",
  },

  done: {
    title: "That’s this week’s checkpoint.",
    body: "Nothing more to do here today.",
  },
} as const;
