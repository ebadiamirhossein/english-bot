"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarCheck, Compass, Layers, LineChart, Play } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The five places this app has. PRD §4: everything a learner does resolves to
 * Today; the others are where they look at, or go back to, what Today produced.
 *
 * **W32f — operator ruling 2026-09-28, superseding the four-item nav**, which
 * read *Today · Map · Review · Progress*: today's video and the saved words
 * were reachable only through *keep going* and Review. **Watch** opens today's
 * video (never a library, R2); **Words** replaces Review — one page of Review,
 * word practice and My words. `match` is every path that belongs to an item,
 * so `/review` (kept, an alias of Words) and the two word pages light Words.
 *
 * **No counter and no badge on any item** (#160, CLAUDE.md §4): a number on a
 * tab that grows while a learner is away is a backlog presented.
 */
export const NAV_ITEMS = [
  { href: "/", label: "Today", icon: CalendarCheck, match: [] as string[] },
  { href: "/watch", label: "Watch", icon: Play, match: ["/watch"] },
  { href: "/words", label: "Words", icon: Layers, match: ["/words", "/review", "/practice/words"] },
  { href: "/map", label: "Map", icon: Compass, match: ["/map"] },
  { href: "/progress", label: "Progress", icon: LineChart, match: ["/progress"] },
] as const;

function isActive(href: string, match: readonly string[], pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return match.some((m) => pathname === m || pathname.startsWith(`${m}/`));
}

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Main"
      // W32e: hidden in Focus and on a phone held sideways (`globals.css`).
      data-bottom-nav=""
      className="safe-bottom fixed inset-x-0 bottom-0 z-50 border-t border-border/80 bg-background/85 backdrop-blur-lg"
    >
      <ul className="mx-auto flex max-w-lg items-stretch lg:max-w-2xl justify-between px-2 pt-1.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon, match }) => {
          const active = isActive(href, match, pathname);
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                // 64px of tappable height: thumbs, on a moving bus. W32f: five
                // across a 320px phone is ~60px each — the label never wraps
                // or truncates (`whitespace-nowrap`; e2e/nav.spec.ts measures it).
                className={cn(
                  "flex h-16 flex-col items-center justify-center gap-1 whitespace-nowrap rounded-xl text-[0.7rem] font-medium transition-colors",
                  active
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex h-8 w-12 items-center justify-center rounded-full transition-colors",
                    active && "bg-accent",
                  )}
                >
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
