import type { Metadata, Viewport } from "next";
import { Fraunces, Geist, Geist_Mono, Vazirmatn } from "next/font/google";

import "./globals.css";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

// Geist for everything you read at speed; Fraunces for headings, because a
// language app that looks like a dashboard reads like homework. One display
// face, one text face, nothing else.
const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const display = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["SOFT", "WONK", "opsz"],
});

// The Persian companion, and the ONLY reason it is declared at all is that nine
// production cards front a Farsi gloss today — the Trancy vocabulary import's
// `Translation` column, live since 2026-08-14 (#142). Geist, Geist Mono and
// Fraunces have no `arabic` subset available at all, so without this those nine
// cards render in whatever face the phone reaches for, differently on each
// phone, with no way for the app to know.
//
// **It must be declared FIRST wherever Farsi can appear, never appended after a
// Latin family.** `next/font` inserts its own metric-adjusted local fallback
// immediately after each family it generates, that fallback resolves to a system
// face WITH Arabic coverage, and the browser satisfies the Farsi from it and
// never reaches the companion. W8a measured the gloss at 201.54px with the
// companion appended — identical to the Latin family alone — where Vazirmatn
// renders it at 250.55px. A declared fallback in the wrong position is inert and
// nothing on screen says so. `--font-l1` in globals.css is where the ordering
// lives; this call only makes the face available.
//
// `preload: false` is a cost decision, not an oversight. The variable sits on
// <html>, so preloading would ship the Arabic subset to both learners on every
// route for the sake of nine cards one of them sees. The cost is a swap flash
// the first time a Farsi line paints.
const farsi = Vazirmatn({
  variable: "--font-vazirmatn",
  subsets: ["arabic", "latin"],
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: "Everyday English",
  description: "Ten minutes a day, in the English people actually speak.",
  applicationName: "Everyday English",
  appleWebApp: {
    capable: true,
    title: "Everyday English",
    // "default" keeps the status bar legible in both colour schemes; the
    // translucent option puts white text on our light background.
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  // viewport-fit=cover plus the safe-area padding in globals.css is what keeps
  // the bottom nav clear of the home indicator on an iPhone.
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f5f0" },
    { media: "(prefers-color-scheme: dark)", color: "#10201f" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // The font variables go on <html>, not <body>: `html { font-sans }` in
    // globals.css reads them from this element, and a variable defined one
    // level down silently leaves every page in Times.
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${display.variable} ${farsi.variable}`}
      // The theme script writes `class="dark"` onto this element before paint,
      // so the class React rendered and the class in the DOM differ by design.
      suppressHydrationWarning
    >
      <head>
        {/*
          Blocking, inline, and first: anything that waits for React paints the
          light palette and then flips, which is the flash every theme toggle is
          judged by. The script is defined next to the storage key it reads
          (lib/theme.ts) so the two cannot drift apart.
        */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
