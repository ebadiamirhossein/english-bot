"use client";

import { useState, type CSSProperties, type ReactNode } from "react";

import { CANDIDATES, type Candidate } from "./candidates";

/**
 * The switcher and the samples. **Static content only** — no fetch, no session,
 * no learner data. Every sentence below is typed into this file.
 *
 * The samples are the four things the reviewer actually shows: a cloze card with
 * its real gap, a slang recognition card with its §8.5.4 register panel, a
 * production card carrying a Farsi gloss, and W6a's result box in both states.
 * Nothing here imports the real components — they read the API's shapes, and a
 * preview that needed a card row would need a session and a database.
 *
 * **The result box keeps W6a's structure and only inherits a candidate's
 * tokens.** Outcome is carried by fill versus outline, one tier versus two, and
 * a rule down the edge — three signals before a word is read, and none of them
 * colour. The palette has no red in it by design, so a candidate may change the
 * ground and the type and may not touch how the box says what it says.
 */

/** The real five-underscore gap from `core.services.anki.GAP`, not a stand-in. */
const GAP = "_____";

export function Preview() {
  const [choice, setChoice] = useState<Candidate>(CANDIDATES[0]);

  return (
    <div
      style={choice.tokens as unknown as CSSProperties}
      className="min-h-dvh"
    >
      <div
        style={{
          background: "var(--tp-ground)",
          color: "var(--tp-ink)",
          fontFamily: "var(--tp-body)",
        }}
        className="min-h-dvh"
      >
        <div
          className="mx-auto max-w-lg px-5 pb-24 pt-6"
          style={{ display: "grid", gap: "var(--tp-gap)" }}
        >
          <Switcher choice={choice} onChoose={setChoice} />
          <ClozeCard />
          <SlangCard />
          <ProductionCard />
          <ResultCorrect />
          <ResultNotQuite />
          <GlyphCheck />
        </div>
      </div>
    </div>
  );
}

function Switcher({
  choice,
  onChoose,
}: {
  choice: Candidate;
  onChoose: (c: Candidate) => void;
}) {
  return (
    <div style={{ display: "grid", gap: "0.625rem" }}>
      <div className="flex flex-wrap gap-2">
        {CANDIDATES.map((candidate) => {
          const active = candidate.id === choice.id;
          return (
            <button
              key={candidate.id}
              type="button"
              onClick={() => onChoose(candidate)}
              data-testid={`tp-${candidate.id}`}
              data-active={String(active)}
              className="px-3 py-2 text-sm"
              style={{
                fontFamily: "var(--tp-ui)",
                borderRadius: "calc(var(--tp-radius) * 0.7)",
                border: `1px solid ${active ? "var(--tp-accent)" : "var(--tp-edge)"}`,
                background: active ? "var(--tp-accent-soft)" : "transparent",
                color: "var(--tp-ink)",
                fontWeight: active ? 600 : 400,
              }}
            >
              {candidate.label}
            </button>
          );
        })}
      </div>
      <p
        style={{
          fontFamily: "var(--tp-ui)",
          color: "var(--tp-quiet)",
          fontSize: "0.8125rem",
          lineHeight: 1.6,
        }}
      >
        <strong style={{ color: "var(--tp-ink)" }}>Soft:</strong> {choice.claim}
        <br />
        <strong style={{ color: "var(--tp-ink)" }}>Costs:</strong> {choice.cost}
      </p>
      {/*
        Said on the page rather than left to be discovered. All four sets here
        are the light palette, and the page ignores the theme so the four are
        compared under one light. If your phone is on dark, this is not what
        the reviewer looks like there — the dark half of whichever set you pick
        is drawn in the slice that ships it.
      */}
      <p
        style={{
          fontFamily: "var(--tp-ui)",
          color: "var(--tp-quiet)",
          fontSize: "0.75rem",
          lineHeight: 1.6,
        }}
      >
        All four are the light palette, shown under one light so they compare.
        The dark half gets drawn once you have picked one.
      </p>
    </div>
  );
}

// ── the shared card shell, so the samples differ by content and not by chrome ─

function Card({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return (
    <article
      data-testid={testId}
      style={{
        borderRadius: "var(--tp-radius)",
        border: "1px solid var(--tp-edge)",
        background: "var(--tp-panel)",
        padding: "var(--tp-pad)",
        display: "grid",
        gap: "1rem",
      }}
    >
      {children}
    </article>
  );
}

/**
 * The card sentence. Weight comes from the candidate's token rather than from a
 * literal, because "a narrow weight range so the page has no hard jumps" is one
 * of the things being judged and it has to travel with the rest of the set.
 */
function Sentence({ children }: { children: ReactNode }) {
  const style = {
    fontFamily: "var(--tp-display)",
    fontSize: "var(--tp-card-size)",
    lineHeight: "var(--tp-card-leading)",
    fontWeight: "var(--tp-card-weight)",
    whiteSpace: "pre-line",
  } as unknown as CSSProperties;
  return <p style={style}>{children}</p>;
}

function Quiet({ children }: { children: ReactNode }) {
  return (
    <p
      style={{
        color: "var(--tp-quiet)",
        fontSize: "var(--tp-body-size)",
        lineHeight: "var(--tp-body-leading)",
      }}
    >
      {children}
    </p>
  );
}

function Label({ children }: { children: ReactNode }) {
  return (
    <p
      style={{
        fontFamily: "var(--tp-ui)",
        color: "var(--tp-quiet)",
        fontSize: "0.6875rem",
        letterSpacing: "0.14em",
        textTransform: "uppercase",
      }}
    >
      {children}
    </p>
  );
}

// ── the samples ────────────────────────────────────────────────────────────

function ClozeCard() {
  return (
    <Card testId="tp-cloze">
      <Label>Cloze · the gap has to survive every candidate</Label>
      <Sentence>
        {`"I wish someone had warned me to ask about ${GAP} upfront," she said.`}
      </Sentence>
      <Quiet>
        Five underscores, the real gap the deck stores. If it reads as one solid
        rule at arm&rsquo;s length, that candidate is out however good the rest
        of it looks.
      </Quiet>
    </Card>
  );
}

function SlangCard() {
  return (
    <Card testId="tp-slang">
      <Label>Recognition · slang</Label>
      <Sentence>
        Honestly, I&rsquo;m gonna have to take a rain check on Friday.
      </Sentence>
      <p
        style={{
          fontFamily: "var(--tp-display)",
          fontSize: "var(--tp-card-size)",
          lineHeight: "var(--tp-card-leading)",
          color: "var(--tp-accent)",
        }}
      >
        take a rain check
      </p>
      <div
        style={{
          borderRadius: "calc(var(--tp-radius) * 0.8)",
          background: "var(--tp-accent-soft)",
          padding: "1rem",
          display: "grid",
          gap: "0.5rem",
          fontSize: "var(--tp-body-size)",
          lineHeight: "var(--tp-body-leading)",
        }}
      >
        <Label>informal</Label>
        <p>
          Safe anywhere: <strong>could we do it another time?</strong>
        </p>
        <p style={{ color: "var(--tp-quiet)" }}>
          Friends and easy-going colleagues. Not to a landlord or a doctor.
        </p>
      </div>
      <p
        style={{
          fontSize: "var(--tp-body-size)",
          lineHeight: "var(--tp-body-leading)",
          color: "var(--tp-quiet)",
          fontStyle: "italic",
        }}
      >
        &ldquo;Rain check on the pizza?&rdquo;
        <span style={{ fontStyle: "normal" }}> — HIMYM S02E14</span>
      </p>
    </Card>
  );
}

function ProductionCard() {
  return (
    <Card testId="tp-production">
      <Label>Production · the card face that carries Farsi</Label>
      {/*
        `dir="auto"` and `lang` are what `l1-to-l2-production.tsx` already does
        and what `card-face.tsx` does not — filed as a known issue rather than
        fixed here. The font stack is the other half: without a declared Arabic
        family this line renders in whatever the phone picks.
      */}
      <p
        dir="auto"
        lang="fa"
        style={{
          fontFamily: "var(--tp-l1)",
          fontSize: "var(--tp-card-size)",
          lineHeight: "calc(var(--tp-card-leading) * 1.15)",
        }}
      >
        هزینه‌های پنهان
      </p>
      <Quiet>
        Farsi renders in the candidate&rsquo;s declared companion, not in
        whatever the phone reaches for. Compare the weight of this line against
        the English above it — if one looks bolder than the other, the pairing is
        off.
      </Quiet>
      <Sentence>hidden costs</Sentence>
    </Card>
  );
}

// ── W6a's result box: tokens inherited, structure untouched ─────────────────

function ResultCorrect() {
  return (
    <div
      data-testid="tp-result-correct"
      style={{
        minHeight: "5rem",
        borderRadius: "var(--tp-radius)",
        padding: "1.25rem",
        background: "var(--tp-accent-soft)",
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
      }}
    >
      <span aria-hidden style={{ fontSize: "1.5rem", lineHeight: 1 }}>
        👍
      </span>
      <p
        style={{
          fontFamily: "var(--tp-display)",
          fontSize: "1.25rem",
          lineHeight: "var(--tp-card-leading)",
        }}
      >
        That&rsquo;s it.
      </p>
    </div>
  );
}

function ResultNotQuite() {
  return (
    <div
      data-testid="tp-result-not-quite"
      style={{
        minHeight: "5rem",
        borderRadius: "var(--tp-radius)",
        padding: "1.25rem",
        background: "var(--tp-panel)",
        border: "1px solid var(--tp-edge)",
        borderLeft: "4px solid var(--tp-accent)",
      }}
    >
      <Quiet>Not quite. Here it is:</Quiet>
      <p
        style={{
          marginTop: "0.375rem",
          fontFamily: "var(--tp-display)",
          fontSize: "1.5rem",
          lineHeight: "var(--tp-card-leading)",
          color: "var(--tp-accent)",
        }}
      >
        hidden costs
      </p>
    </div>
  );
}

function GlyphCheck() {
  return (
    <Card testId="tp-glyphs">
      <Label>The glyphs this has to get right</Label>
      <p
        style={{
          fontFamily: "var(--tp-display)",
          fontSize: "var(--tp-card-size)",
          lineHeight: 1.9,
          letterSpacing: "0.04em",
        }}
      >
        Il1 · rn m · 0O · {GAP} · 13 15 18
      </p>
      <Quiet>
        This is learning content, not marketing copy. A candidate that cannot
        keep l, I and 1 apart is a candidate that will teach someone the shape of
        the letter next to the one they meant.
      </Quiet>
    </Card>
  );
}
