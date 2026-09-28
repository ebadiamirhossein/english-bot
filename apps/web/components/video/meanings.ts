/**
 * **W32b — reading the meanings map.** Pure: no fetch, no state. The map
 * arrives once when `/watch` loads (`GET /video/{id}/meanings`); every hover and
 * every tap after that is a lookup here, with no network at all.
 *
 * **The client does not lemmatise.** The server keyed every page token with
 * the same function the gloss writer and reader share (`gloss_key`) and sent
 * `forms` where the key differs from the token. Which substrings ARE tokens is
 * pinned on both sides by `lib/meaning-keys.contract.json`.
 */

import type { CardImage, HereMeaning, MeaningsMap } from "@/lib/api";

export type Sense = { pos: string; definition: string; l1: string | null };

export type Resolved = {
  word: string;
  key: string;
  /** `word`: something to show. `name`: a person or place — nothing to learn.
   * `miss`: nothing stored yet. */
  kind: "word" | "name" | "miss";
  /** The video's own meaning — context beats dictionary. */
  here: HereMeaning | null;
  senses: Sense[];
  register: string | null;
  neutral: string | null;
  who: string | null;
  saved: "none" | "in_deck" | "pending" | "no_meaning";
  image: CardImage | null;
};

const nameSets = new WeakMap<MeaningsMap, Set<string>>();

function namesOf(map: MeaningsMap): Set<string> {
  let names = nameSets.get(map);
  if (!names) {
    names = new Set(map.names);
    nameSets.set(map, names);
  }
  return names;
}

/** The page token, lower-cased as the server lower-cases it (`str.lower`). */
export function tokenOf(word: string): string {
  return word.toLowerCase();
}

export function keyOf(map: MeaningsMap, word: string): string {
  const token = tokenOf(word);
  return map.forms[token] ?? token;
}

export function resolve(map: MeaningsMap, word: string): Resolved {
  const token = tokenOf(word);
  const key = map.forms[token] ?? token;
  const here = map.here[key] ?? map.here[token] ?? null;
  const entry = map.entries[key];
  const base = {
    word,
    key,
    here,
    saved: map.saved[token] ?? map.saved[key] ?? "none",
    image: map.images[key] ?? null,
  };
  const none = { senses: [] as Sense[], register: null, neutral: null, who: null };
  // A gloss the video holds wins over everything — even a name's (W31e's
  // *phillips* row was carded like any gloss).
  if (!here && (namesOf(map).has(token) || entry?.k === "n")) {
    return { ...base, ...none, kind: "name" };
  }
  if (entry?.k === "w") {
    return {
      ...base,
      kind: "word",
      senses: entry.s.map(([pos, definition, l1]) => ({ pos, definition, l1 })),
      register: entry.r,
      neutral: entry.n ?? null,
      who: entry.w ?? null,
    };
  }
  if (here) {
    return { ...base, ...none, kind: "word", register: here.r, neutral: here.n ?? null, who: here.w ?? null };
  }
  return { ...base, ...none, kind: "miss" };
}

/** What the popover shows: the "here" meaning first, else sense 1. */
export function firstMeaning(
  found: Resolved,
): { definition: string; l1: string | null; here: boolean } | null {
  if (found.here) return { definition: found.here.d, l1: found.here.l1 ?? null, here: true };
  const first = found.senses[0];
  return first ? { definition: first.definition, l1: first.l1, here: false } : null;
}
