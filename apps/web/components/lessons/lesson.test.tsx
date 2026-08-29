import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Diagram } from "@/components/lessons/diagram";
import { LessonBody } from "@/components/lessons/lesson";
import { FocusBlock } from "@/components/session/blocks";
import type { Lesson, LessonDiagram, SessionBlock } from "@/lib/api";

/**
 * The lesson renderer. W10b.
 *
 * **The user action every test here exercises:** reaching block 3 of the daily
 * session, or opening `/lessons/{n}`, and reading the teaching behind the
 * grammar labels — the thing #182 says has never existed.
 */

const TARGETS = [
  "past simple: regular and irregular verbs",
  "past continuous for what was going on around it",
];

function section(target: string) {
  return {
    target,
    explanation: `Everything about ${target}, explained plainly.`,
    when_to_use: "When the time is finished.",
    when_not_to: "Not when the time is still open.",
    examples: ["I walked home yesterday.", "She bought the wrong milk."],
    mistake: {
      said: "I buyed a coat.",
      corrected: "I bought a coat.",
      why: "Buy is irregular, so it doesn't take -ed.",
    },
  };
}

const LESSON: Lesson = {
  unit_number: 1,
  sections: TARGETS.map(section),
  diagrams: [
    {
      kind: "timeline",
      target: TARGETS[0],
      points: [
        { label: "I walked home", at: 1, now: false },
        { label: "right now", at: 2, now: true },
      ],
    },
  ],
};

// Every string a learner must never see about themselves, plus every colour
// affordance the correction screen already bans. Hardcoded: this list IS the
// specification (rule 5).
const BANNED = [
  "line-through",
  "text-destructive",
  "bg-destructive",
  "text-red",
  "bg-red",
  "border-red",
  "❌",
];

describe("a lesson renders its sections behind their labels", () => {
  it("shows every target as a header, with the label text untouched", () => {
    render(<LessonBody lesson={LESSON} />);
    for (const target of TARGETS) {
      expect(screen.getByText(target)).toBeTruthy();
    }
  });

  it("opens the first section and leaves the rest closed", () => {
    render(<LessonBody lesson={LESSON} />);
    const bodies = screen.getAllByTestId("lesson-section-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0].textContent).toContain(TARGETS[0].slice(0, 12));
  });

  it("opens another section when its label is tapped", async () => {
    render(<LessonBody lesson={LESSON} />);
    const toggles = screen.getAllByTestId("lesson-section-toggle");
    await userEvent.click(toggles[1]);
    const body = screen.getAllByTestId("lesson-section-body")[0];
    expect(body.textContent).toContain("past continuous");
  });

  it("shows the when-to and the when-not-to, which is the half textbooks skip", () => {
    render(<LessonBody lesson={LESSON} />);
    const body = screen.getAllByTestId("lesson-section-body")[0];
    expect(body.textContent).toContain("When the time is finished");
    expect(body.textContent).toContain("Not when the time is still open");
  });
});

describe("the wrong example is subordinate to its correction", () => {
  it("shows the correction, and the mistake beneath it", () => {
    render(<LessonBody lesson={LESSON} />);
    expect(screen.getByTestId("lesson-corrected").textContent).toContain(
      "I bought a coat.",
    );
    expect(screen.getByTestId("lesson-mistake-said").textContent).toContain(
      "I buyed a coat.",
    );
  });

  it("never marks the mistake with a cross, a strike or a colour", () => {
    const { container } = render(<LessonBody lesson={LESSON} />);
    const html = container.innerHTML;
    for (const banned of BANNED) {
      expect(html).not.toContain(banned);
    }
  });

  it("puts the correction BEFORE the mistake in the document", () => {
    render(<LessonBody lesson={LESSON} />);
    const corrected = screen.getByTestId("lesson-corrected");
    const said = screen.getByTestId("lesson-mistake-said");
    expect(
      corrected.compareDocumentPosition(said) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

describe("each of the five diagram kinds renders", () => {
  const specs: LessonDiagram[] = [
    {
      kind: "timeline",
      target: "t",
      points: [
        { label: "before", at: 1, now: false },
        { label: "here", at: 2, now: true },
      ],
    },
    {
      kind: "contrast_pair",
      target: "t",
      situation: "Talking about a plan",
      first: { form: "will", example: "I'll get it." },
      second: { form: "going to", example: "I'm going to get it." },
      what_changes: "Whether you decided just now.",
    },
    {
      kind: "form_build",
      target: "t",
      slots: ["subject", "have/has", "past participle"],
      example: "She has finished.",
    },
    {
      kind: "decision_tree",
      target: "t",
      question: "Is the time finished?",
      branches: [
        { answer: "yes", form: "past simple" },
        { answer: "no", form: "present perfect" },
      ],
    },
    {
      kind: "annotated_example",
      target: "t",
      sentence: "After that, the rain got worse.",
      callouts: [{ part: "After that", note: "moves the story on" }],
    },
  ];

  for (const spec of specs) {
    it(`renders a ${spec.kind}`, () => {
      render(<Diagram spec={spec} />);
      expect(screen.getByTestId("lesson-diagram")).toBeTruthy();
      expect(screen.getByTestId(`diagram-${spec.kind.replace(/_/g, "-")}`)).toBeTruthy();
    });
  }

  it("uses no colour affordance in any kind", () => {
    for (const spec of specs) {
      const { container, unmount } = render(<Diagram spec={spec} />);
      for (const banned of BANNED) {
        expect(container.innerHTML).not.toContain(banned);
      }
      unmount();
    }
  });

  it("orders a timeline by `at` and never by array position", () => {
    render(
      <Diagram
        spec={{
          kind: "timeline",
          target: "t",
          points: [
            { label: "second", at: 9, now: true },
            { label: "first", at: 1, now: false },
          ],
        }}
      />,
    );
    const text = screen.getByTestId("diagram-timeline").textContent ?? "";
    expect(text.indexOf("first")).toBeLessThan(text.indexOf("second"));
  });

  it("renders nothing for a kind it does not know, rather than an error", () => {
    const { container } = render(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      <Diagram spec={{ kind: "pie_chart", target: "t" } as any} />,
    );
    expect(container.innerHTML).toBe("");
  });
});

describe("a lesson with no diagrams renders without a hole", () => {
  it("shows every section and no diagram frame", () => {
    render(<LessonBody lesson={{ ...LESSON, diagrams: [] }} />);
    expect(screen.getAllByTestId("lesson-section-toggle")).toHaveLength(2);
    expect(screen.queryByTestId("lesson-diagram")).toBeNull();
  });

  it("still shows the section body of the open section", () => {
    render(<LessonBody lesson={{ ...LESSON, diagrams: [] }} />);
    expect(screen.getAllByTestId("lesson-section-body")).toHaveLength(1);
  });
});

/**
 * Block 3 with a lesson — the half W10 shipped as `lesson: null` and #182 asked
 * for. **The user action: opening the daily session and reading the teaching.**
 */
describe("block 3 renders the lesson when there is one", () => {
  const withLesson = {
    n: 3,
    kind: "focus",
    state: "ready",
    payload: {
      unit_number: 1,
      can_do: "I can tell a friend what I did yesterday.",
      grammar_targets: TARGETS.map((target) => ({ target })),
      lesson: LESSON,
      items: [],
    },
  } as unknown as SessionBlock;

  it("replaces the bare label list with the lesson's own sections", () => {
    render(<FocusBlock block={withLesson} />);
    expect(screen.getByTestId("lesson")).toBeTruthy();
    expect(screen.queryByTestId("focus-targets")).toBeNull();
  });

  it("stops saying the explanation is on its way", () => {
    const { container } = render(<FocusBlock block={withLesson} />);
    expect(container.textContent).not.toContain("written explanation");
  });

  it("keeps the label text byte-identical to what the server sent", () => {
    render(<FocusBlock block={withLesson} />);
    for (const target of TARGETS) {
      expect(screen.getByText(target)).toBeTruthy();
    }
  });

  it("renders no Murphy citation, because none can arrive", () => {
    const { container } = render(<FocusBlock block={withLesson} />);
    expect(container.textContent).not.toContain("Murphy");
  });

  it("still shows the can-do above the lesson", () => {
    render(<FocusBlock block={withLesson} />);
    expect(screen.getByTestId("focus-can-do").textContent).toContain("yesterday");
  });
});

describe("the lesson is paced — one section per completed session (#245)", () => {
  // OPERATOR RULING, 2026-08-29: a section advances per COMPLETED SESSION, not
  // per calendar day, so a learner who skips a day loses nothing. The index is
  // computed server-side; these assert only that the component renders what it
  // is given.

  it("opens the section it is given, not always the first", () => {
    // The fixture has two sections, so section 1 is the second and last one.
    render(<LessonBody lesson={LESSON} section={1} />);
    const bodies = screen.getAllByTestId("lesson-section-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0].textContent).toContain(TARGETS[1].slice(0, 12));
  });

  it("opens the first section when it is given no pacing at all", () => {
    // `/lessons/{unit}` is an operator route with no learner behind it, and the
    // pre-W11 shape had no index either. Both must keep working unchanged.
    render(<LessonBody lesson={LESSON} />);
    const bodies = screen.getAllByTestId("lesson-section-body");
    expect(bodies).toHaveLength(1);
    expect(bodies[0].textContent).toContain(TARGETS[0].slice(0, 12));
  });

  it("opens NOTHING once the teaching is finished, and repeats nothing", () => {
    // The ruling's two clauses, one each: no new teaching AND no repeated
    // section. Repeating the last one is the behaviour it names and forbids.
    render(<LessonBody lesson={LESSON} teachingComplete />);
    expect(screen.queryAllByTestId("lesson-section-body")).toHaveLength(0);
  });

  it("keeps every label reachable when the teaching is finished", () => {
    // Nothing is hidden. A learner who has read all four sections can still
    // open any of them — they are simply not opened FOR them.
    render(<LessonBody lesson={LESSON} teachingComplete />);
    for (const target of TARGETS) {
      expect(screen.getByText(target)).toBeTruthy();
    }
    expect(screen.getAllByTestId("lesson-section-toggle")).toHaveLength(
      TARGETS.length,
    );
  });

  it("still opens on a tap once the teaching is finished", async () => {
    render(<LessonBody lesson={LESSON} teachingComplete />);
    const toggles = screen.getAllByTestId("lesson-section-toggle");
    await userEvent.click(toggles[1]);
    expect(screen.getAllByTestId("lesson-section-body")).toHaveLength(1);
  });
});
