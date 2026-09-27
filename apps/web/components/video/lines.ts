/**
 * W31b — the study screen's pure rules. **The lines themselves are built on
 * the server** (`packages/core/video/lines.py`), because W31c derives a saved
 * word's sentence from the same function and a client that could supply the
 * sentence could supply any sentence. This file only reads them.
 */

/** One display line as `video_payload` sends it. Untimed lines (no cues) carry
 * `null` times: the list still shows and every word is still tappable. */
export type VideoLine = { start: number | null; end: number | null; text: string };

/**
 * **The active line is the one with the greatest `start` at or before `t`** —
 * the same rule as `core.video.cues.active_cue`, and for the same reason: it is
 * total (one answer) and monotone (it never jumps back). `null` before the
 * first line starts, or when the lines are untimed.
 */
export function activeLineIndex(lines: VideoLine[], t: number): number | null {
  let found: number | null = null;
  for (let i = 0; i < lines.length; i += 1) {
    const start = lines[i].start;
    if (start === null) return null;
    if (start <= t) found = i;
    else break;
  }
  return found;
}

/** A piece of a line: a tappable word, a sound tag, or the text between. */
export type Piece = { kind: "word" | "tag" | "text"; text: string };

const PIECES = /(\[[^\]]*\])|([A-Za-zÀ-ɏ0-9][A-Za-zÀ-ɏ0-9']*)/g;

/**
 * Split a line for display. **A sound tag (`[laughter]`) is one piece and is
 * never a word** — it renders dimmed and cannot be tapped, because there is
 * nothing in it to learn (the operator, 2026-09-27).
 */
export function pieces(text: string): Piece[] {
  const out: Piece[] = [];
  let last = 0;
  for (const match of text.matchAll(PIECES)) {
    const at = match.index ?? 0;
    if (at > last) out.push({ kind: "text", text: text.slice(last, at) });
    out.push({ kind: match[1] ? "tag" : "word", text: match[0] });
    last = at + match[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

/** `m:ss`, for the line list's seek control. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
