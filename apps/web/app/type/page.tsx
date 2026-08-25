import type { Metadata } from "next";

import { FONT_VARIABLES } from "./candidates";
import { Preview } from "./preview";

/**
 * W8a — the typography preview. **Temporary, unlinked, and it ships no default.**
 *
 * Three complete candidates plus the control, so the choice is made by looking
 * rather than by remembering. The chosen one lands in a later slice as a
 * one-line change to `app/layout.tsx` and `app/globals.css`, and **that slice
 * deletes this route** — filed as a known issue so an unlinked page is not left
 * to survive for years because nobody recalls it exists.
 *
 * **Why it sits outside `(app)`.** Everything under `app/(app)/` renders behind
 * `RequireSession` with the bottom nav and the app menu fixed over it — and that
 * chrome would stay in the current Geist and Fraunces whatever candidate was
 * selected, competing with the one thing being judged. This route is the whole
 * screen instead.
 *
 * **The trade that buys.** The page is reachable without signing in. That is
 * acceptable *here and nowhere else*: it makes no API call, reads no session,
 * and every sample below is typed into `preview.tsx` — there is no learner data
 * on it to reach. It carries `noindex` so unlinked does not quietly become
 * indexed.
 *
 * **No Vitest coverage, deliberately.** There is no logic here to assert: it is
 * static samples behind a `useState` switcher, and the only test that could say
 * anything useful is a person looking at it on a phone. Stated rather than left
 * to read later as a gap in #67.
 */
export const metadata: Metadata = {
  title: "Type",
  robots: { index: false, follow: false },
};

export default function TypePreviewPage() {
  // The candidate fonts are declared in `candidates.ts` and attached here, not
  // in the root layout — so they load on this route alone and no learner screen
  // gains a byte. The "today" control declares none and inherits the shipped
  // stack from the root layout, which is what makes it a control.
  return (
    <div className={FONT_VARIABLES}>
      <Preview />
    </div>
  );
}
