import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CorrectionResult, WriteToday } from "@/lib/api";

import fixture from "./write.fixture.json";

/**
 * W16a — the writing screen's states and silent branches, in jsdom.
 *
 * **EVERY BODY HERE IS PYTHON-GENERATED** (`scripts/export_write_fixture.py`,
 * through `gates.shape` and the route's own serialiser) and compared against
 * real ASGI responses by `tests/test_write_fixture.py`. Nothing is hand-written,
 * because a hand-written fixture is a statement of what its author believed the
 * server sends (#190).
 *
 * **WHAT jsdom CANNOT SEE, STATED SO NOBODY READS A GREEN RUN AS MORE:** layout.
 * Whether the button is on screen, whether the head collapses, whether anything
 * overflows — all of that is `e2e/write.spec.ts`, in a real browser (§3a).
 *
 * **RED DEMONSTRATIONS** (recorded in the decisions log), each a mutation of
 * `writer.tsx`: the `corrections.length === 2` guard removed → *"one correction
 * carries no picked-two line"*; the `did_well` guard removed →
 * *"an absent opening line renders nothing"*; the min-chars check removed →
 * *"a too-short entry is refused without a request"*; `readOnly` dropped →
 * *"reading takes the button away"*; the 409 branch removed → *"the ceiling
 * mid-session"*; `sessionId` hardcoded to null → *"posts back the session"*.
 */

const TODAY = fixture.today as WriteToday;
const TODAY_NO_SESSION = fixture.today_no_session as WriteToday;
const TODAY_CEILING = fixture.today_ceiling as WriteToday;
const TWO = fixture.two as CorrectionResult;
const ONE = fixture.one as CorrectionResult;
const CLEAN = fixture.clean_no_line as CorrectionResult;
const NO_LABEL = fixture.no_label as CorrectionResult;
const NOT_ENGLISH = fixture.not_english as CorrectionResult;

const ENTRY = "Today I go to the dentist in the morning. She only clean my teeth.";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getWriteToday: vi.fn(), requestCorrection: vi.fn() };
});

const api = await import("@/lib/api");
const { Writer } = await import("@/components/write/writer");

beforeEach(() => {
  vi.mocked(api.getWriteToday).mockReset();
  vi.mocked(api.requestCorrection).mockReset();
});

async function open(today: WriteToday = TODAY) {
  vi.mocked(api.getWriteToday).mockResolvedValue(today);
  const view = render(<Writer />);
  await waitFor(() => expect(screen.getByTestId("write-screen").dataset.phase).not.toBe("loading"));
  return view;
}

async function submit(result: CorrectionResult | Error, text = ENTRY) {
  if (result instanceof Error) vi.mocked(api.requestCorrection).mockRejectedValue(result);
  else vi.mocked(api.requestCorrection).mockResolvedValue(result);
  fireEvent.change(screen.getByTestId("write-field"), { target: { value: text } });
  await userEvent.click(screen.getByTestId("write-submit"));
}

const BANNED = /wrong|incorrect|failed|missed|mistake|score|try harder|\d/i;

describe("the journal, empty (1d)", () => {
  it("shows the task, the length line in words, and an enabled button", async () => {
    await open();
    expect(screen.getByText("What happened today?")).not.toBeNull();
    expect(screen.getByTestId("write-length-line").textContent).toBe(
      "Five to ten sentences is about right.",
    );
    expect(screen.getByTestId("write-submit").hasAttribute("disabled")).toBe(false);
    expect(screen.getByTestId("write-leave").getAttribute("href")).toBe("/session");
  });

  it("shows no counter of any kind while the learner types (1f)", async () => {
    const { container } = await open();
    fireEvent.change(screen.getByTestId("write-field"), { target: { value: ENTRY } });
    expect(container.textContent).not.toMatch(/\d/);
    expect(container.textContent).not.toMatch(/left|remaining|characters|words/i);
  });

  it("leaves to home when there is no session to go back to", async () => {
    await open(TODAY_NO_SESSION);
    expect(screen.getByTestId("write-leave").getAttribute("href")).toBe("/");
  });
});

describe("too short (1h)", () => {
  it("is refused without a request, text and focus kept, button still enabled", async () => {
    await open();
    await submit(TWO, "Tired");
    expect(api.requestCorrection).not.toHaveBeenCalled();
    expect(screen.getByTestId("write-notice").textContent).toContain("not much here yet");
    expect((screen.getByTestId("write-field") as HTMLTextAreaElement).value).toBe("Tired");
    expect(document.activeElement).toBe(screen.getByTestId("write-field"));
    expect(screen.getByTestId("write-submit").hasAttribute("disabled")).toBe(false);
    // Restating the target beside a refusal turns guidance into a mark.
    expect(screen.queryByTestId("write-length-line")).toBeNull();
  });
});

describe("reading (1i)", () => {
  it("takes the button away and makes the text read-only", async () => {
    await open();
    vi.mocked(api.requestCorrection).mockReturnValue(new Promise(() => {}));
    fireEvent.change(screen.getByTestId("write-field"), { target: { value: ENTRY } });
    await userEvent.click(screen.getByTestId("write-submit"));
    expect(screen.getByTestId("write-reading").textContent).toContain("Reading it");
    expect(screen.queryByTestId("write-submit")).toBeNull();
    expect(screen.queryByTestId("write-leave")).toBeNull();
    expect((screen.getByTestId("write-field") as HTMLTextAreaElement).readOnly).toBe(true);
  });

  it("posts back the kind and the session it was shown", async () => {
    await open();
    await submit(TWO);
    expect(api.requestCorrection).toHaveBeenCalledWith(ENTRY, {
      dayKind: "journal",
      sessionId: TODAY.session_id,
    });
  });
});

describe("the result (1k, 1l, 1m)", () => {
  it("two corrections: opening line, the text whole, the picked-two line, two labelled cards", async () => {
    await open();
    await submit(TWO);
    expect(screen.getByTestId("write-opening").textContent).toBe(TWO.did_well);
    expect(screen.getByTestId("write-written").textContent).toBe(ENTRY);
    expect(screen.getByTestId("write-picked")).not.toBeNull();
    expect(screen.getAllByTestId("write-correction")).toHaveLength(2);
    expect(screen.getAllByTestId("write-correction-label").map((n) => n.textContent)).toEqual(
      TWO.corrections.map((c) => c.label),
    );
    expect(screen.getByTestId("write-back").getAttribute("href")).toBe("/session");
  });

  it("one correction carries no picked-two line", async () => {
    await open();
    await submit(ONE);
    expect(screen.getAllByTestId("write-correction")).toHaveLength(1);
    expect(screen.queryByTestId("write-picked")).toBeNull();
  });

  it("no corrections removes the whole block, heading included", async () => {
    await open();
    await submit(CLEAN);
    expect(screen.queryByTestId("write-corrections")).toBeNull();
    expect(screen.queryByText("Worth a look")).toBeNull();
  });

  it("an absent opening line renders nothing — never a fallback", async () => {
    const { container } = await open();
    await submit(CLEAN);
    expect(CLEAN.did_well).toBeUndefined();
    expect(screen.queryByTestId("write-opening")).toBeNull();
    expect(container.textContent).not.toMatch(/nice|good job|well done/i);
  });

  it("a card with no label draws no eyebrow and still reads", async () => {
    await open();
    await submit(NO_LABEL);
    expect(screen.getByTestId("write-correction")).not.toBeNull();
    expect(screen.queryByTestId("write-correction-label")).toBeNull();
  });

  it("never marks the learner's text and carries no banned word or numeral", async () => {
    const { container } = await open();
    await submit(TWO);
    expect(container.innerHTML).not.toMatch(/line-through|text-red|bg-red/);
    const written = screen.getByTestId("write-written");
    expect(written.querySelector("mark, s, del, u")).toBeNull();
    expect(container.textContent).not.toMatch(BANNED);
  });
});

describe("the notices", () => {
  it("not English: the text stays, editable, with the button", async () => {
    await open();
    await submit(NOT_ENGLISH);
    expect(screen.getByTestId("write-notice").dataset.notice).toBe("not_english");
    expect((screen.getByTestId("write-field") as HTMLTextAreaElement).readOnly).toBe(false);
    expect((screen.getByTestId("write-field") as HTMLTextAreaElement).value).toBe(ENTRY);
  });

  it("a failure keeps the text and Try again re-sends the same text (1q)", async () => {
    await open();
    await submit(new api.ApiError("/correct returned 503", 503));
    expect(screen.getByTestId("write-notice").textContent).toContain("Nothing’s lost");
    expect(screen.getByTestId("write-notice").textContent).not.toMatch(/503|error|sorry|connection/i);
    vi.mocked(api.requestCorrection).mockResolvedValue(TWO);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(api.requestCorrection).toHaveBeenLastCalledWith(ENTRY, expect.anything());
    expect(api.requestCorrection).toHaveBeenCalledTimes(2);
  });

  // **Finding (c).** The server now refuses a paragraph posted outside its day
  // (`422 wrong_day_kind`) — a Thursday tab left open into Friday. The screen asks
  // for today's task again and keeps the text; it shows no error copy. Red
  // demonstration: without the 422 branch the trouble notice rendered and today
  // was fetched once.
  it("a refused day kind fetches today's task again and keeps the text", async () => {
    await open();
    await submit(new api.ApiError("/correct returned 422", 422));
    await waitFor(() => expect(api.getWriteToday).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId("write-screen").dataset.phase).toBe("composing"));
    expect((screen.getByTestId("write-field") as HTMLTextAreaElement).value).toBe(ENTRY);
    expect(screen.queryByTestId("write-notice")).toBeNull();
  });
});

describe("the ceiling (1q unavailable)", () => {
  it("from the server's boolean: one line, no field, no control", async () => {
    const { container } = await open(TODAY_CEILING);
    expect(screen.getByTestId("write-ceiling").textContent).toBe(
      "That’s the writing done for today. There’ll be a new one tomorrow.",
    );
    expect(screen.queryByTestId("write-field")).toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryByTestId("write-leave")).toBeNull();
    expect(container.textContent).not.toMatch(/\d/);
  });

  it("the ceiling mid-session: a 409 lands on the same state", async () => {
    await open();
    await submit(new api.ApiError("/correct returned 409", 409));
    expect(screen.getByTestId("write-ceiling")).not.toBeNull();
    expect(screen.queryByTestId("write-submit")).toBeNull();
  });
});

// ── W16b: the paragraph (1e, 1g, 1n, 1o) ────────────────────────────────────
//
// **RED DEMONSTRATIONS** (decisions log), each a mutation of `writer.tsx`: the
// structure block moved below "What you wrote" → *"structure leads"*; the
// `offers.length > 0` guard removed → *"no offers, no heading"*; `in_deck`
// ignored (`useState(false)`) → *"a kept phrase arrives in the deck"*;
// `keepPhrase` not awaited before the flip → *"a failed keep stays offerable"*.

const TODAY_PARAGRAPH = fixture.today_paragraph as WriteToday;
const PARAGRAPH = fixture.paragraph as CorrectionResult;
const PARAGRAPH_BARE = fixture.paragraph_bare as CorrectionResult;
const PARAGRAPH_ONE_OFFER = fixture.paragraph_one_offer as CorrectionResult;

const PARA_TEXT =
  "I think is a good idea to move in another country for work, but it depends of the person.";

describe("the paragraph (W16b)", () => {
  it("1e: the prompt card carries the unit's task verbatim, and the eyebrow says this week", async () => {
    await open(TODAY_PARAGRAPH);
    expect(screen.getByTestId("write-prompt").textContent).toBe(TODAY_PARAGRAPH.prompt);
    expect(screen.getByText("Write · this week")).not.toBeNull();
    expect(screen.getByText("The prompt")).not.toBeNull();
    expect((screen.getByTestId("write-field") as HTMLTextAreaElement).placeholder).toBe(
      "Write your paragraph here.",
    );
  });

  it("posts the paragraph as a paragraph", async () => {
    await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH, PARA_TEXT);
    expect(api.requestCorrection).toHaveBeenCalledWith(PARA_TEXT, {
      dayKind: "paragraph",
      sessionId: TODAY_PARAGRAPH.session_id,
    });
  });

  it("1n: structure leads, quotes are italic, no opening line and no picked-two line", async () => {
    const { container } = await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH, PARA_TEXT);
    const structure = screen.getByTestId("write-structure");
    const written = screen.getByTestId("write-written");
    expect(structure.compareDocumentPosition(written) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByTestId("write-structure-paragraph")).toHaveLength(PARAGRAPH.structure!.length);
    expect(screen.getByTestId("write-structure-quote").tagName).toBe("EM");
    expect(screen.queryByTestId("write-opening")).toBeNull();
    expect(screen.queryByTestId("write-picked")).toBeNull();
    expect(container.textContent).not.toMatch(/more below|\d/i);
  });

  it("1o: two rows, one offered and one already in the deck", async () => {
    await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH, PARA_TEXT);
    expect(screen.getByTestId("write-keep-intro").textContent).toMatch(/^Two phrases/);
    const rows = screen.getAllByTestId("write-keep-row");
    expect(rows.map((r) => r.dataset.state)).toEqual(
      PARAGRAPH.word_offers.map((o) => (o.in_deck ? "in_deck" : "offer")),
    );
    expect(screen.getAllByTestId("write-keep-button")).toHaveLength(1);
    expect(screen.getAllByTestId("write-keep-in-deck")).toHaveLength(1);
  });

  it("1o: Keep saves the phrase with its sentence and the row flips to In your deck", async () => {
    vi.spyOn(api, "keepPhrase").mockResolvedValue({ status: "saved" });
    await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH, PARA_TEXT);
    const offer = PARAGRAPH.word_offers.find((o) => !o.in_deck)!;
    await userEvent.click(screen.getByTestId("write-keep-button"));
    expect(api.keepPhrase).toHaveBeenCalledWith(offer.phrase, offer.sentence);
    await waitFor(() => expect(screen.queryAllByTestId("write-keep-button")).toHaveLength(0));
    expect(screen.getAllByTestId("write-keep-in-deck")).toHaveLength(2);
  });

  it("a failed keep stays offerable, with no error copy", async () => {
    vi.spyOn(api, "keepPhrase").mockRejectedValue(new api.ApiError("/write/keep returned 422", 422));
    const { container } = await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH, PARA_TEXT);
    await userEvent.click(screen.getByTestId("write-keep-button"));
    await waitFor(() => expect(screen.getByTestId("write-keep-button").hasAttribute("disabled")).toBe(false));
    expect(container.textContent).not.toMatch(/422|error|couldn/i);
  });

  it("no structure and no offers: no block, no heading, no empty row", async () => {
    await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH_BARE, PARA_TEXT);
    expect(PARAGRAPH_BARE.structure).toBeUndefined();
    expect(PARAGRAPH_BARE.word_offers).toEqual([]);
    expect(screen.queryByTestId("write-structure")).toBeNull();
    expect(screen.queryByTestId("write-keep")).toBeNull();
    expect(screen.queryByText("Worth keeping")).toBeNull();
    expect(screen.getAllByTestId("write-correction").length).toBeGreaterThan(0);
  });

  it("one offer reads naturally", async () => {
    await open(TODAY_PARAGRAPH);
    await submit(PARAGRAPH_ONE_OFFER, PARA_TEXT);
    expect(screen.getAllByTestId("write-keep-row")).toHaveLength(1);
    expect(screen.getByTestId("write-keep-intro").textContent).toMatch(/^One phrase/);
  });
});
