import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CardFace as CardFaceData } from "@/lib/api";

import { CardFace } from "./card-face";
import { GradeButtons } from "./grade-buttons";

function card(over: Partial<CardFaceData> = {}): CardFaceData {
  return {
    id: 1,
    card_type: "recognition",
    front: "I went to the shops yesterday and it was shut.",
    back: "went",
    cue: null,
    context_sentence: "I went to the shops yesterday and it was shut.",
    source_ref: "himym_s2e4",
    meaning: "past of go",
    register: "neutral",
    neutral_equivalent: null,
    who_says_this: null,
    intervals: { again: 0, hard: 3, good: 7, easy: 15 },
    ...over,
  };
}

/**
 * Card 38's real face on production, verbatim. The gloss on the first line, the
 * gapped sentence as PRD §5's context hint on the second, and `context_sentence`
 * carrying the SAME sentence ungapped — with `hidden costs` still in it.
 *
 * A real row rather than an invented one, because the invented fixture is what
 * let this ship: a made-up `context_sentence` that happens not to contain the
 * back cannot fail the assertion the defect needed.
 */
function productionCard(over: Partial<CardFaceData> = {}): CardFaceData {
  return card({
    id: 38,
    card_type: "production",
    front:
      "extra expenses that are not obvious at first\n" +
      '"I wish someone had warned me to ask about _____ upfront," she said.',
    back: "hidden costs",
    context_sentence:
      '"I wish someone had warned me to ask about hidden costs upfront," she said.',
    source_ref: "reading_1",
    meaning: "extra expenses that are not obvious at first",
    ...over,
  });
}

/**
 * The card face. PRD §5's provenance rule and §8.5.4's four things.
 *
 * These assert the properties the schema is *for* — not the styling. Migration
 * 013 refuses to store an informal/slang card without all four fields, so the
 * component's job is to show them, and a component that quietly dropped one
 * would make the CHECK pointless.
 */
describe("card face", () => {
  it("keeps the back hidden until it is revealed", () => {
    render(<CardFace card={card()} revealed={false} />);
    expect(screen.queryByTestId("card-back")).toBeNull();
  });

  it("shows the back once revealed", () => {
    render(<CardFace card={card()} revealed />);
    expect(screen.getByTestId("card-back").textContent).toContain("went");
  });

  it("shows all of PRD §8.5.4's four things on a slang card", () => {
    render(
      <CardFace
        card={card({
          register: "slang",
          front: "That's a hard pass.",
          back: "hard pass",
          context_sentence: "So, that's a hard pass from me.",
          meaning: "a firm refusal",
          neutral_equivalent: "I'd rather not, thanks",
          who_says_this: "Friends and casual colleagues. Not in a client email.",
        })}
        revealed
      />,
    );
    // the line it came from, the meaning, the neutral equivalent, who says it
    expect(screen.getByTestId("card-context")).toBeTruthy();
    expect(screen.getByTestId("card-back").textContent).toContain(
      "a firm refusal",
    );
    expect(screen.getByTestId("card-neutral").textContent).toContain(
      "I'd rather not, thanks",
    );
    expect(screen.getByTestId("card-who-says").textContent).toContain(
      "client email",
    );
  });

  it("shows no register panel on a neutral card", () => {
    render(<CardFace card={card()} revealed />);
    expect(screen.queryByTestId("card-register-panel")).toBeNull();
  });

  it("hides the leech cue once the answer is on screen", () => {
    const leeched = card({ cue: "w___ (4)" });
    const { rerender } = render(<CardFace card={leeched} revealed={false} />);
    expect(screen.getByTestId("card-cue").textContent).toContain("w___");
    rerender(<CardFace card={leeched} revealed />);
    expect(screen.queryByTestId("card-cue")).toBeNull();
  });
});

/**
 * W8c — the answer is not printed on the front.
 *
 * **Every assertion here is by VALUE, never by key or by testid alone.** #116
 * exists because the first version of the per-type leak assertions checked JSON
 * key names: a field could arrive with the answer in it and pass, because the
 * key it arrived under was the expected one. A `queryByTestId(...)` being null
 * proves the element is gone, not that the string is; the string is what the
 * learner reads.
 *
 * "The front" here means everything rendered at `revealed={false}` — the whole
 * container, not one element. The defect was in a sibling of the field that was
 * being checked, which is exactly the failure mode a per-element assertion
 * cannot see.
 */
describe("the front never carries the answer", () => {
  it("withholds both the back and the source line on a production card", () => {
    const c = productionCard();
    const { container } = render(<CardFace card={c} revealed={false} />);
    const front = container.textContent ?? "";

    expect(front).not.toContain(c.back);
    expect(front).not.toContain(c.context_sentence);
    expect(screen.queryByTestId("card-context")).toBeNull();

    // …and the question itself is still there, so this is not passing by
    // rendering nothing.
    expect(front).toContain("extra expenses that are not obvious at first");
    expect(front).toContain("ask about _____ upfront");
  });

  it("gives the production card its source line back at the reveal", () => {
    const c = productionCard();
    render(<CardFace card={c} revealed />);
    const context = screen.getByTestId("card-context").textContent ?? "";
    expect(context).toContain("ask about hidden costs upfront");
    expect(context).toContain("reading_1");
  });

  // `cloze`, `audio` and `collocation` have no writer today — W8b deleted the
  // fourteen migrated cloze cards and the other two arrive with W13. They are
  // ruled on and asserted NOW rather than when the slice that creates them
  // rediscovers the same leak.
  const withheld = [
    {
      card_type: "cloze",
      front: "I _____ to the shops yesterday.",
      back: "went",
      context_sentence: "I went to the shops yesterday and it was shut.",
    },
    {
      card_type: "audio",
      front: "Listen and write what you hear.",
      back: "wear down",
      context_sentence: "These arguments just wear down everyone involved.",
    },
    {
      card_type: "collocation",
      front: "make / do _____ a decision",
      back: "make",
      context_sentence: "We need to make a decision before Friday.",
      // PRD §5's collocation front is a CHOICE between two verbs, both printed.
      // The answer being on the front is the card, not a leak — so the
      // back-absence rule does not apply to this type and saying so is more
      // honest than weakening the assertion for the other four.
      backIsOnTheFrontByDesign: true,
    },
  ];

  for (const spec of withheld) {
    it(`withholds the source line on a ${spec.card_type} card`, () => {
      const { backIsOnTheFrontByDesign, ...face } = spec;
      const c = card(face as Partial<CardFaceData>);
      const { container } = render(<CardFace card={c} revealed={false} />);
      const front = container.textContent ?? "";

      // The source sentence is what leaks on all three: on a collocation card
      // it is the sentence that says WHICH of the two printed verbs is right.
      expect(front).not.toContain(c.context_sentence);
      expect(screen.queryByTestId("card-context")).toBeNull();

      if (!backIsOnTheFrontByDesign) {
        expect(front).not.toContain(c.back);
      }
    });
  }

  it("keeps the source line on the front of a recognition card", () => {
    // PRD §5's recognition front IS the mined sentence, so the source line is
    // the question and withholding it would delete the card. The one type the
    // provenance rule was written for, and the reason it is not a blanket ban.
    const c = card({
      front: "So, that's a hard pass from me.",
      back: "hard pass",
      context_sentence: "So, that's a hard pass from me, sorry.",
      source_ref: "himym_s2e4",
    });
    render(<CardFace card={c} revealed={false} />);
    const context = screen.getByTestId("card-context").textContent ?? "";
    expect(context).toContain("hard pass from me, sorry");
    expect(context).toContain("himym_s2e4");
  });

  it("prints a recognition card's sentence once, not twice", () => {
    // `migrate_chunks._slang_plan` sets front AND context_sentence to the same
    // mined sentence, so all fifteen live slang cards showed it twice.
    const sentence = "So, that's a hard pass from me.";
    const { container } = render(
      <CardFace
        card={card({ front: sentence, context_sentence: sentence })}
        revealed={false}
      />,
    );
    const occurrences = (container.textContent ?? "").split(sentence).length - 1;
    expect(occurrences).toBe(1);
    // The provenance survives the deduplication — it is the half that was never
    // duplicated.
    expect(screen.getByTestId("card-context").textContent).toContain(
      "himym_s2e4",
    );
  });

  it("holds the register panel back until the reveal", () => {
    // On a recognition card the answer is the back AND the meaning, and
    // `neutral_equivalent` paraphrases the meaning. §8.5.4 constrains what the
    // CARD shows, not what the FRONT shows.
    const c = card({
      register: "slang",
      front: "So, that's a hard pass from me.",
      back: "hard pass",
      context_sentence: "So, that's a hard pass from me.",
      meaning: "a firm refusal",
      neutral_equivalent: "I'd rather not, thanks",
      who_says_this: "Friends and casual colleagues. Not in a client email.",
    });

    const { container, rerender } = render(
      <CardFace card={c} revealed={false} />,
    );
    expect(screen.queryByTestId("card-register-panel")).toBeNull();
    expect(container.textContent ?? "").not.toContain("I'd rather not, thanks");
    expect(container.textContent ?? "").not.toContain("a firm refusal");

    rerender(<CardFace card={c} revealed />);
    expect(screen.getByTestId("card-neutral").textContent).toContain(
      "I'd rather not, thanks",
    );
  });
});

/**
 * W8c — #142 and #143 on the real card face.
 *
 * jsdom has no layout engine, so **no width is measured here**: that the
 * `font-l1` class resolves to Vazirmatn rather than to `next/font`'s own Arabic-
 * capable fallback is proved in a real browser and reported as three numbers.
 * What these assert is the other half — that the Farsi line is *marked*, per
 * line, so there is something for that stack to attach to.
 */
describe("mixed-direction card text", () => {
  // Card 17's real front: a Farsi gloss above an English sentence, in one field.
  const mixed = card({
    card_type: "production",
    front: "سطح ردیف؛ چیدمان در سطوح طبقه‌بندی (/tɪər/)\nthree _____s: dev, staging, and production.",
    back: "tier",
    context_sentence: "We split it into three tiers: dev, staging, and production.",
    source_ref: "vocabulary",
    meaning: "a level in a ranked arrangement",
  });

  it("tags the Farsi line fa and the English line beside it en", () => {
    const { container } = render(<CardFace card={mixed} revealed={false} />);
    const fa = container.querySelector('[lang="fa"]');
    const en = container.querySelector('[lang="en"]');

    expect(fa?.textContent).toContain("سطح ردیف");
    expect(en?.textContent).toContain("three _____s");
  });

  it("puts the L1 face on the Farsi line and not on the English one", () => {
    const { container } = render(<CardFace card={mixed} revealed={false} />);
    const fa = container.querySelector('[lang="fa"]');
    const en = container.querySelector('[lang="en"]');

    expect(fa?.className).toContain("font-l1");
    expect(en?.className).not.toContain("font-l1");
  });

  it("resolves direction per line, so the English hint is not dragged RTL", () => {
    // dir="auto" on the whole field would take its direction from the first
    // strong character — Farsi — and lay the English sentence out right-to-left
    // with its punctuation on the wrong end. Each line is its own run.
    const { container } = render(<CardFace card={mixed} revealed={false} />);
    const lines = Array.from(container.querySelectorAll('p [dir="auto"]'));
    expect(lines.length).toBeGreaterThanOrEqual(2);
    for (const line of lines) {
      expect(line.getAttribute("dir")).toBe("auto");
    }
  });

  it("leaves the provenance slug LTR — it is not learner text", () => {
    render(<CardFace card={mixed} revealed />);
    const ref = screen
      .getByTestId("card-context")
      .querySelector('[dir="ltr"]');
    expect(ref?.textContent).toContain("vocabulary");
  });

  it("marks every learner-facing field, not only the front", () => {
    render(<CardFace card={mixed} revealed />);
    for (const id of ["card-back", "card-context"]) {
      expect(
        screen.getByTestId(id).querySelector("[dir][lang]"),
      ).not.toBeNull();
    }
  });
});

/**
 * The four grades.
 *
 * The interval assertions are the load-bearing ones: they prove the numbers
 * come from the payload and are not recomputed here. A component that did its
 * own arithmetic would pass a "four buttons render" test and still show a
 * learner a schedule the database disagrees with.
 */
describe("grade buttons", () => {
  it("renders exactly the four FSRS grades, in order", () => {
    render(<GradeButtons card={card()} disabled={false} onGrade={() => {}} />);
    const labels = Array.from(
      screen.getByTestId("grade-buttons").querySelectorAll("button"),
    ).map((b) => b.textContent);
    expect(labels).toHaveLength(4);
    expect(labels[0]).toContain("Again");
    expect(labels[1]).toContain("Hard");
    expect(labels[2]).toContain("Good");
    expect(labels[3]).toContain("Easy");
  });

  it("renders the server's interval for each button and computes none itself", () => {
    // Deliberately not FSRS-shaped numbers. If the component derived them, it
    // could not reproduce these.
    render(
      <GradeButtons
        card={card({ intervals: { again: 0, hard: 2, good: 41, easy: 400 } })}
        disabled={false}
        onGrade={() => {}}
      />,
    );
    expect(screen.getByTestId("grade-again").textContent).toContain("today");
    expect(screen.getByTestId("grade-hard").textContent).toContain("2 days");
    expect(screen.getByTestId("grade-good").textContent).toContain("41 days");
    expect(screen.getByTestId("grade-easy").textContent).toContain("13 months");
    expect(
      screen.getByTestId("grade-easy").getAttribute("data-interval-days"),
    ).toBe("400");
  });

  it("reports the rating by name, never as a number", async () => {
    const onGrade = vi.fn();
    render(<GradeButtons card={card()} disabled={false} onGrade={onGrade} />);
    await userEvent.click(screen.getByTestId("grade-good"));
    expect(onGrade).toHaveBeenCalledWith("good");
  });

  it("refuses a second tap while a grade is in flight", async () => {
    const onGrade = vi.fn();
    render(<GradeButtons card={card()} disabled onGrade={onGrade} />);
    await userEvent.click(screen.getByTestId("grade-good"));
    expect(onGrade).not.toHaveBeenCalled();
  });
});
