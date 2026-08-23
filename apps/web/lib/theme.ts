/**
 * Theme preference — the ONLY browser storage this app is allowed.
 *
 * CLAUDE.md §5 keeps everything about a learner on the server. W1c narrowed
 * that to permit one exception: which colour scheme they picked, which is a
 * property of the device rather than of the learner. Session, progress and
 * learner content stay server-side, and `sessionStorage` stays banned outright.
 *
 * `tests/test_web_shell.py` enforces the narrowing: `localStorage` may appear
 * in this file and nowhere else, and only under THEME_STORAGE_KEY. That is why
 * this is hand-rolled rather than `next-themes` — a dependency would put the
 * one permitted write inside node_modules where the test cannot see it, which
 * would make the exception unbounded in practice.
 *
 * On iOS this value can be evicted after seven days without a visit (WebKit
 * caps script-writable storage that way). Harmless: it falls back to "system",
 * which is what the app did before the toggle existed. Android Chrome has no
 * equivalent eviction.
 */

export const THEME_STORAGE_KEY = "theme";

export type Theme = "light" | "dark" | "system";

export const THEMES: readonly Theme[] = ["light", "dark", "system"] as const;

function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

/** The stored choice, or "system" when there isn't one (or storage is denied). */
export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : "system";
  } catch {
    // Private mode, or storage blocked entirely. Following the system is a
    // perfectly good answer, so this is not worth surfacing to anyone.
    return "system";
  }
}

/** Persist the choice and apply it immediately. */
export function writeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The toggle still works for this session; it just will not be remembered.
  }
  applyTheme(theme);
}

/** Resolve "system" through the media query, then set the class on <html>. */
export function applyTheme(theme: Theme): void {
  const dark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

/**
 * The script that runs before first paint, as a string.
 *
 * It has to be inline and blocking in <head>: anything that waits for React
 * paints the light palette first and then flips, which is the flash every
 * theme toggle is judged by. Kept here, next to the key it reads, so the two
 * cannot drift apart — and written without optional chaining or `let` so it
 * parses on anything that can run the app at all.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var d=t==="dark"||((!t||t==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d);}catch(e){}})();`;
