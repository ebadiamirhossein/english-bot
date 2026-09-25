"use client";

/**
 * How far the software keyboard covers an element's bottom edge. **#409, W15.**
 *
 * ────────────────────────────────────────────────────────────────────────────
 * **THE DEFECT: iOS Safari does not shrink the layout viewport for the
 * keyboard.** It shrinks the VISUAL viewport and leaves the page where it was,
 * so a composer pinned to the foot of an `h-full` column sits UNDER the
 * keyboard — typed into blind, with *Send* out of reach. No `apps/web` surface
 * read `visualViewport` before this (#407, #409).
 *
 * **THE MEASUREMENT: the element's bottom edge minus the visible bottom edge**
 * (`visualViewport.offsetTop + visualViewport.height`), both in the layout
 * viewport's coordinates, clamped at zero. The caller pads its own bottom by
 * that much, so its pinned footer rises to sit on the keyboard and the scroll
 * region above it shrinks. **The element's box does not move** (padding is
 * inside it), so the measurement cannot feed back on itself.
 *
 * **WHAT IT CANNOT PROVE, STATED:** Playwright raises no real keyboard. The
 * browser test stubs `visualViewport` at a keyboard's height and asserts the
 * composer lands above it — the arithmetic and the wiring, in a real layout
 * engine. **How iOS actually pans with a keyboard up is the phone check's.**
 *
 * With no `visualViewport` (jsdom, an old browser) it is `0` and changes nothing.
 * ────────────────────────────────────────────────────────────────────────────
 */

import { useEffect, useState, type RefObject } from "react";

export function useKeyboardInset(ref: RefObject<HTMLElement | null>): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const vv = typeof window === "undefined" ? undefined : window.visualViewport;
    if (!vv) return;
    const update = () => {
      const el = ref.current;
      if (!el) return;
      const covered = el.getBoundingClientRect().bottom - (vv.offsetTop + vv.height);
      const next = Math.max(0, Math.round(covered));
      setInset((prev) => (prev === next ? prev : next));
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, [ref]);

  return inset;
}
