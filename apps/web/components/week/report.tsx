import type { Week } from "@/lib/api";

/**
 * W11b: Sunday's report. PRD §4.2 — *"No tasks. Weekly report."*
 *
 * ──────────────────────────────────────────────────────────────────────────
 * **THE ONE RULE THIS FILE EXISTS FOR: NO NUMERIC ZERO REACHES THE SCREEN.**
 *
 * Not on an empty week, and not line by line on a week where one of the six
 * happens to be nothing. A zero on a report is a **score**, and a score of zero
 * on a week nobody promised anything about is guilt with no banned word in it —
 * which is exactly the kind of thing CLAUDE.md §4's phrase list cannot catch.
 *
 * So every line is conditional on its own number, and an empty week renders one
 * sentence rather than a table of zeros. Week one is both learners' state, so
 * this is the ordinary case rather than an edge one.
 *
 * **NOTHING HERE ASKS THE LEARNER TO DO ANYTHING.** No button, no target, no
 * "keep it up", no comparison with last week. *Drops are silent, raises are
 * announced* — the only line that celebrates is the passed unit, which is a
 * raise, and it is also the first thing in this product that has ever been
 * reachable to celebrate.
 *
 * **AND NOTHING COUNTS WHAT WAS NOT DONE.** No missed days, no shortfall, no
 * streak. A report that says what did not happen is a backlog with a date on
 * it, and #160's finding is that a screen with its own counter becomes one.
 *
 * ──────────────────────────────────────────────────────────────────────────
 * **What is NOT on this report, and why it is an absence rather than a gap.**
 * Minutes and videos watched (W12/W13), speaking (W14–W16), XP (W19), mastery
 * (#135 — no metric exists), coverage trend (#197, unruled), and free extensive
 * input, which §4.2 says is *tracked* and which nothing tracks (#253). None of
 * them is approximated with a substitute number (CLAUDE.md §3 rule 7).
 */

/** Pluralise without a library and without a zero ever reaching a caller. */
function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function WeekReport({ week }: { week: Week }) {
  if (week.empty) {
    // **One sentence, and it names no number.** It also makes no promise about
    // next week and asks for nothing: the emptiness of Sunday is deliberate
    // (PRD §4.2), and so is the emptiness of a week that had nothing in it.
    return (
      <p
        className="max-w-prose text-sm leading-relaxed text-muted-foreground"
        data-testid="week-empty"
      >
        Nothing to report yet.
      </p>
    );
  }

  const lines: string[] = [];

  if (week.days_with_a_session > 0) {
    lines.push(`You opened a session on ${count(week.days_with_a_session, "day", "days")}.`);
  }
  if (week.items_answered > 0) {
    // The right-count is a second clause rather than a second line, and it
    // disappears entirely at zero rather than reading "0 of them right".
    lines.push(
      week.items_right > 0
        ? `${count(week.items_answered, "practice item", "practice items")} answered, ${week.items_right} of them right.`
        : `${count(week.items_answered, "practice item", "practice items")} answered.`,
    );
  }
  if (week.cards_reviewed > 0) {
    lines.push(`${count(week.cards_reviewed, "card", "cards")} reviewed.`);
  }
  if (week.words_now_known > 0) {
    lines.push(`${count(week.words_now_known, "more word", "more words")} you know now.`);
  }
  if (week.units_passed > 0) {
    // The one raise this report can announce.
    lines.push(
      week.units_passed === 1
        ? "You passed a unit."
        : `${week.units_passed} units passed.`,
    );
  }

  return (
    <ul className="space-y-2.5" data-testid="week-lines">
      {lines.map((line) => (
        <li key={line} className="max-w-prose text-base leading-relaxed">
          {line}
        </li>
      ))}
    </ul>
  );
}
