/**
 * W32b — reading the meanings map. The map is `write.fixture.json`'s
 * `watch_meanings`, built by the server's own `assemble_meanings` over the real
 * lines and keys (`scripts/export_write_fixture.py`), never written by hand.
 *
 * **RED BEFORE THE CODE (2026-09-28):** `meanings.ts` did not exist.
 */
import { describe, expect, it } from "vitest";

import { pieces } from "@/components/video/lines";
import { firstMeaning, keyOf, resolve } from "@/components/video/meanings";
import fixture from "@/components/write/write.fixture.json";
import type { MeaningsMap } from "@/lib/api";
import contract from "@/lib/meaning-keys.contract.json";

const map = fixture.watch_meanings as unknown as MeaningsMap;

describe("the page's tokens, pinned with the server", () => {
  it("reads every contract line into exactly the tokens the server keys", () => {
    // `tests/test_word_meanings.py` reads the same file through
    // `core.services.dictionary.page_tokens`: a hover can only find what the
    // server keyed if both sides split and lower-case a line the same way.
    expect(contract.lines.length).toBeGreaterThan(0);
    for (const line of contract.lines) {
      const tokens = pieces(line.text)
        .filter((p) => p.kind === "word")
        .map((p) => p.text.toLowerCase());
      expect(tokens, line.text).toEqual(line.tokens);
    }
  });
});

describe("resolve", () => {
  it("finds an inflected word through the server's forms, with no lemmatising here", () => {
    expect(keyOf(map, "relaxed")).toBe("relax");
    const found = resolve(map, "relaxed");
    expect(found.kind).toBe("word");
    expect(found.senses[0].definition).toBe("to stop worrying and feel calm");
    expect(found.senses[0].l1).toBe("آرام شدن");
  });

  it("puts the video's own meaning first, labelled as here, with the dictionary's under it", () => {
    const found = resolve(map, "Mastodon");
    expect(found.here?.d).toMatch(/model of an ancient/);
    expect(found.senses).toHaveLength(1);
    expect(firstMeaning(found)).toEqual({
      definition: found.here?.d,
      l1: "ماکت ماموت",
      here: true,
    });
  });

  it("keeps every sense, most common first", () => {
    expect(resolve(map, "model").senses.map((s) => s.definition)).toEqual([
      "a small copy of something bigger",
      "a person whose job is to wear clothes for photos",
    ]);
  });

  it("carries the register and the safer word for an informal word", () => {
    const found = resolve(map, "okay");
    expect([found.register, found.neutral, found.who]).toEqual([
      "informal",
      "all right",
      "anyone, in everyday talk",
    ]);
  });

  it("says a name is a name, and a word with no entry is a miss", () => {
    expect(resolve(map, "Ross").kind).toBe("name");
    expect(resolve(map, "van").kind).toBe("miss");
    expect(firstMeaning(resolve(map, "van"))).toBeNull();
  });

  it("reads what this learner already saved, by token or by key", () => {
    const saved: MeaningsMap = { ...map, saved: { relax: "in_deck", van: "pending" } };
    expect(resolve(saved, "relaxed").saved).toBe("in_deck");
    expect(resolve(saved, "van").saved).toBe("pending");
    expect(resolve(saved, "model").saved).toBe("none");
  });
});
