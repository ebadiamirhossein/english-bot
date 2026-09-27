import { AppMenu } from "@/components/app-menu";
import { BottomNav } from "@/components/bottom-nav";
import { RequireSession } from "@/components/require-session";

/**
 * The shell every signed-in screen sits in: one scrolling column, one fixed nav.
 *
 * Max width is a phone's width even on a laptop. Both learners will use this
 * on a phone; a layout that reflows into three columns on a desktop is a
 * second design to maintain for a screen nobody uses.
 *
 * **W24c (R5, 2026-09-27) overrules that at ≥1024 px ONLY:** the operator
 * does use a desktop, and a 32rem column of 16px type read as a narrow strip
 * of very small text. The column widens to 42rem and the root type scales to
 * 112.5% (`globals.css`) — still ONE column, so D12's refusal of a two-column
 * grid stands. Below 1024 px nothing changes, and `e2e/layout.spec.ts` holds
 * the phone to baselines committed before this edit.
 *
 * W2 wraps it in `RequireSession`. That guard is a client component because the
 * session cookie is host-only on the API's origin and the Vercel edge never
 * sees it — see the component for why that is the right trade and why the API,
 * not this, is the enforcement point.
 */
export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <RequireSession>
      <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col lg:max-w-2xl">
        <div className="flex justify-end px-3 pt-3">
          <AppMenu />
        </div>
        {/* **`flex flex-col min-h-0` ADDED BY W13b/3b so a full-height route can
            actually claim this box.** `main` was already `flex-1` in a
            `min-h-dvh` column, so its height was definite — but a BLOCK child
            asking for `h-full` inside it had nothing to resolve against, which
            is why `/talk` reached for `100dvh` and put its composer off-screen.
            **Harmless for every other screen:** these children are stacked
            full-width blocks, and a column flex container with the default
            `align-items: stretch` lays them out identically. `space-y-7` uses
            sibling margins, which flex honours. */}
        <main className="flex min-h-0 flex-1 flex-col space-y-7 px-5 pb-32 pt-4">
          {children}
        </main>
        <BottomNav />
      </div>
    </RequireSession>
  );
}
