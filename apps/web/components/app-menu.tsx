"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, Monitor, Moon, Plus, Sun } from "lucide-react";

import { Reminders } from "@/components/push/reminders";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { THEMES, type Theme, readTheme, writeTheme } from "@/lib/theme";
import { addPasskey, signOut, wasCancelled } from "@/lib/webauthn";

const ICONS: Record<Theme, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

const LABELS: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
  system: "Follow system",
};

/**
 * Theme, reminders, add-a-device, sign out.
 *
 * A header menu rather than a fifth item in the bottom nav: "four places" is a
 * product idea (PRD §4), not a layout accident, and
 * `test_bottom_nav_has_the_four_places_the_app_has` keeps asserting four.
 *
 * "Add this device" is here because it is the thing that keeps a lost phone
 * from being an operator SQL task — with a second passkey enrolled, losing one
 * device costs nothing.
 */
export function AppMenu() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("system");
  const [note, setNote] = useState<string | null>(null);

  // Read on mount, not during render: the server has no localStorage, and the
  // pre-paint script in app/layout.tsx has already applied the class by now.
  useEffect(() => setTheme(readTheme()), []);

  function choose(next: Theme) {
    setTheme(next);
    writeTheme(next);
  }

  async function addDevice() {
    setNote(null);
    try {
      await addPasskey();
      setNote("This device is set up.");
    } catch (error) {
      setNote(
        wasCancelled(error)
          ? "Nothing was added. Try again when you’re ready."
          : "That didn’t go through. Try again in a moment.",
      );
    }
  }

  async function leave() {
    await signOut();
    router.replace("/sign-in");
  }

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon-lg"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Settings"
        onClick={() => setOpen((was) => !was)}
      >
        {(() => {
          const Icon = ICONS[theme];
          return <Icon className="h-5 w-5" aria-hidden />;
        })()}
      </Button>

      {/* **`z-[60]`, above the bottom nav's `z-50` (W20).** At both `z-50` the
          nav, later in the document, painted over the menu's lower rows on a
          keyboard-height phone — found by `e2e/reminders.spec.ts` once the
          reminders section made the menu tall enough to reach it. An open menu
          is the thing being used; the nav can wait under it. */}
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-[60] mt-2 w-60 space-y-1 rounded-2xl border border-border bg-popover p-2 shadow-lg"
        >
          {/* W20: the mono eyebrow, ruling 0.3's, so the two sections match. */}
          <p className="px-2 pt-1 font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground">
            Appearance
          </p>
          {THEMES.map((option) => {
            const Icon = ICONS[option];
            return (
              <button
                key={option}
                role="menuitemradio"
                aria-checked={theme === option}
                onClick={() => choose(option)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm transition-colors",
                  theme === option
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-muted",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                <span className="flex-1 text-left">{LABELS[option]}</span>
                {theme === option ? (
                  <Check className="h-4 w-4" aria-hidden />
                ) : null}
              </button>
            );
          })}

          <div className="my-1 h-px bg-border" />

          {/* W20. Draws nothing — not even its divider — unless reminders are
              set up on the server and this browser can have them. */}
          <Reminders />

          <button
            role="menuitem"
            onClick={addDevice}
            className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm transition-colors hover:bg-muted"
          >
            <Plus className="h-4 w-4" aria-hidden />
            <span className="flex-1 text-left">Add this device</span>
          </button>
          <button
            role="menuitem"
            onClick={leave}
            className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm transition-colors hover:bg-muted"
          >
            <span className="flex-1">Sign out</span>
          </button>

          {note ? (
            <p className="px-2.5 pb-1 pt-2 text-xs text-muted-foreground">
              {note}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
