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
      <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col">
        <div className="flex justify-end px-3 pt-3">
          <AppMenu />
        </div>
        <main className="flex-1 space-y-7 px-5 pb-32 pt-4">{children}</main>
        <BottomNav />
      </div>
    </RequireSession>
  );
}
