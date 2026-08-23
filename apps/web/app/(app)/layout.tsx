import { BottomNav } from "@/components/bottom-nav";

/**
 * The shell every screen sits in: one scrolling column, one fixed nav.
 *
 * Max width is a phone's width even on a laptop. Both learners will use this
 * on a phone; a layout that reflows into three columns on a desktop is a
 * second design to maintain for a screen nobody uses.
 */
export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col">
      <main className="flex-1 space-y-7 px-5 pb-32 pt-10">{children}</main>
      <BottomNav />
    </div>
  );
}
