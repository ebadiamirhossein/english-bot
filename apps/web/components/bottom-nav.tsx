"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarCheck, Compass, Layers, LineChart } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The four places this app has. PRD §4: everything a learner does resolves to
 * Today; the other three are where they look at what Today produced.
 */
export const NAV_ITEMS = [
  { href: "/", label: "Today", icon: CalendarCheck },
  { href: "/map", label: "Map", icon: Compass },
  { href: "/review", label: "Review", icon: Layers },
  { href: "/progress", label: "Progress", icon: LineChart },
] as const;

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
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                // 64px of tappable height: thumbs, on a moving bus.
                className={cn(
                  "flex h-16 flex-col items-center justify-center gap-1 rounded-xl text-[0.7rem] font-medium transition-colors",
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
