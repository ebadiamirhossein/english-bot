"use client";

/**
 * The player. **W13-i.** PRD §7.3, ARCHITECTURE §6.
 *
 * **WHAT THIS BUILDS:** a YouTube embed that resumes where the learner stopped,
 * the transcript beside it as unsynced tappable text, unknown words marked from
 * the ledger, a **qualitative** difficulty chip before play, whole-video 0.75×,
 * and the progress ping that is block 2's log.
 *
 * **THE L1 SUBTITLE CONTROL IS GONE, 2026-09-02 (#353), AND THE OLD CLAUSE IS
 * QUOTED RATHER THAN DELETED (#82's shape):** this sentence read *"L1 subtitles
 * **off until asked for**"*. **It was never true in the direction that
 * mattered.** The button toggled `showL1`, `showL1` was read by nothing but the
 * button's own label and `aria-pressed`, and **there has never been an L1 track
 * to show**: PRD §2.5 says it is generated from the English transcript and
 * cached, never fetched from YouTube, and generating it is gated on §1a. A
 * learner tapped *Show FA*, it said *Hide FA*, and nothing appeared.
 *
 * **#353's SECOND CLOSE, NOT ITS FIRST.** Generating the track is §1a's and
 * unanswered; **removing a control that does nothing needs no ruling and no
 * spend**, and this record has twice ruled that an absent feature beats a
 * broken one — a control that answers a tap by relabelling itself leaves the
 * learner unable to tell whether it is broken, slow, or their own fault, and
 * that is the one thing this product's no-guilt posture cannot afford.
 * **The control returns with the track.**
 *
 * **WHAT IT DELIBERATELY DOES NOT BUILD, AND WHY — EACH NAMED ONCE:**
 *
 * - ~~**The follow-along highlight, loop-a-line and per-line 0.75× (R12).** No
 *   per-cue timings are stored anywhere: `videos.transcript` is one `TEXT`
 *   column and the fetch path discards every segment `start`. **Held, not
 *   dropped**; they return with migration `021` once **T5** says whether the
 *   timings can be recovered from the run dumps for free or need a billed
 *   re-fetch. See `components/video/transcript.tsx`.~~
 * - ~~**Tap-to-define and Add to deck (W13-ii, §1a).** Both reach a model, and the
 *   standing operator ruling of 2026-08-27 is that the app never generates while
 *   a learner waits. **Not this slice's to assume.**~~
 *
 *   *(Both struck by W31a as stale, old text kept: 021 stored the cue timings
 *   and W13-i's second commit built the highlight — which never rendered, since
 *   nothing styled `data-lit` (W31b's to fix); W13-ii shipped Add to deck as a
 *   read of a pre-generated gloss. Loop-a-line is W31b's.)*
 * - **Shadow-this-line.** W14/W15's — it needs Azure, which is a priced decision
 *   and not reachable code.
 * - **A completion control (#258).** Block completion is automatic. The ping
 *   below is the evidence; a tap would be the form nobody fills in.
 *
 * **NOTHING HERE IS GENERATED AND NOTHING IS BILLED.** The whole payload arrives
 * hydrated on block 2 of `GET /session/today`.
 *
 * **NO COVERAGE PERCENTAGE EXISTS ON THIS SCREEN AND NONE CAN.** The server
 * sends a band token or nothing; the number never leaves `packages/core`
 * (#288, #334, #330).
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **W31b — THE STUDY SCREEN.** The operator used `/watch` on 2026-09-27 and could
 * not learn from it (one wall of text, nothing synced, subtitles gone in
 * YouTube's fullscreen). The reference named was Trancy / Language Reactor, so:
 *
 * - **the line being spoken, large, directly under the player**, with the one
 *   before and after dimmed (`SubtitleBlock`); the whole transcript below as a
 *   **list of lines** (`LineList`, the ruling on #397), active line highlighted
 *   and scrolled into view inside the list, a line's time seeks to it;
 * - **YouTube's own fullscreen is off (`fs: 0`) and video plays inline
 *   (`playsinline: 1`)** — in YouTube's fullscreen, or iPhone's native player,
 *   our line is gone. **Focus** fills the screen with the player and the line
 *   instead: the Fullscreen API on our own wrapper where the browser allows it,
 *   a fixed full-viewport layout where it does not (iPhone Safari);
 * - **pause to read**: on a desktop pointer, hovering the current-line block —
 *   and only that block (C5) — pauses; leaving resumes if the hover paused it.
 *   A word tap pauses on any device;
 * - **loop the line** (Q3) on the derived line's bounds; 0.75× stays
 *   whole-player (YouTube has one rate per player).
 */

import { Maximize, Minimize, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { VIDEO } from "@/components/session/copy";
import { LineList } from "@/components/video/line-list";
import { activeLineIndex } from "@/components/video/lines";
import { keyOf, resolve } from "@/components/video/meanings";
import { SubtitleBlock } from "@/components/video/subtitle-block";
import { Button } from "@/components/ui/button";
import { WordPopover, type Anchor } from "@/components/video/word-popover";
import { WordSheet, type SheetTarget } from "@/components/video/word-sheet";
import {
  defineWord,
  reportVideoProgress,
  videoMeanings,
  type MeaningEntry,
  type MeaningsMap,
  type VideoBlockPayload,
} from "@/lib/api";


/**
 * How often the position is reported. **Fifteen seconds, and the number is a
 * cost rather than a taste:** a twelve-minute video is ~48 writes, which is why
 * the route's limit is 600/hour and not 200. Shorter would write more often for
 * a resume position nobody reads that precisely; longer and a learner who closes
 * the tab loses the last minute of where they were.
 *
 * **The throttle lives here AND the limit lives on the route**, because a limit
 * that exists only in the client is not a limit.
 */
const PING_SECONDS = 15;

/** Whole-video playback rates. **YouTube has one rate per player**, so a slow
 * line is 0.75× together with Loop line (W31b, Q3). */
const RATES = [1, 0.75] as const;

/** `YT.PlayerState.PLAYING`. */
const PLAYING = 1;

/**
 * **W32b — the hover popover's delay.** About a quarter of a second on one
 * word before it shows, so a pointer passing over a line does not flicker a
 * popover under every word it crosses (the operator's spec). **Once one has
 * shown, the next word's shows at once** for `SKIP_MS` after it closed — the
 * standard tooltip skip delay — so reading along a line never waits twice.
 */
const HOVER_MS = 250;
const SKIP_MS = 300;

/**
 * **W32c — how long the sheet waits for a miss's lookup.** A live call took
 * 4.4–8.0 s on the host (W31e); twenty seconds covers that and `chat()`'s own
 * retries' first round, and then the sheet says *no meaning yet* and still
 * offers Save. The server keeps going and stores what it gets, so the next
 * hover of that word — by anyone — is instant.
 */
const LOOKUP_TIMEOUT_MS = 20_000;

/**
 * **W32d, operator ruling Q2 — the Focus button locks landscape on Android.**
 * The installed app's manifest keeps every screen portrait, so a phone cannot
 * be turned into Focus there; the button turns the video instead. The Screen
 * Orientation API allows a lock only in true fullscreen, and iPhone has neither
 * (the lock is absent; nothing happens). Touch screens only — a desktop has
 * nothing to lock. A refusal is silent: Focus still works, upright.
 */
function lockLandscape(): void {
  if (!window.matchMedia?.("(pointer: coarse)").matches) return;
  const orientation = screen.orientation as ScreenOrientation & {
    lock?: (o: string) => Promise<void>;
  };
  orientation?.lock?.("landscape").catch(() => {});
}

function unlockOrientation(): void {
  try {
    screen.orientation?.unlock?.();
  } catch {
    // Not locked, or no API: nothing to undo.
  }
}

/**
 * **W32e — a `MediaQueryList` listener that works on every Safari.** Before
 * Safari 14 (iOS 13 and older) a `MediaQueryList` is not an `EventTarget`: it
 * has `addListener` and no `addEventListener`, and W32d's
 * `addEventListener?.("change", …)` registered nothing there — silently, so a
 * phone turned after the page loaded never entered Focus. Both are checked
 * here, by existence; a list with neither is left alone. Returns the undo.
 */
export function onMediaChange(list: MediaQueryList, fn: () => void): () => void {
  if (typeof list.addEventListener === "function") {
    list.addEventListener("change", fn);
    return () => list.removeEventListener("change", fn);
  }
  const legacy = list as MediaQueryList & {
    addListener?: (fn: () => void) => void;
    removeListener?: (fn: () => void) => void;
  };
  if (typeof legacy.addListener === "function") {
    legacy.addListener(fn);
    return () => legacy.removeListener?.(fn);
  }
  return () => {};
}

/**
 * **W32e — YouTube's own captions, which double ours.** `cc_load_policy: 0`
 * does not override a viewer's saved YouTube caption preference (the operator's
 * iPhone, 2026-09-28: YouTube's line inside the video, ours under it).
 *
 * **THE CAPTIONS MODULE IS UNDOCUMENTED.** `unloadModule`, `setOption` and
 * `getOption` exist on the IFrame API's player and are not in its reference;
 * YouTube can remove or change them without notice. So every call is guarded by
 * the method's existence — **never by a swallow-everything `try`** (W31a's
 * rule): a missing method does nothing and says nothing.
 */
type CaptionsModule = {
  unloadModule?: (name: string) => void;
  setOption?: (module: string, option: string, value: unknown) => void;
  getOption?: (module: string, option: string) => unknown;
};

/** Turn YouTube's captions off: `unloadModule('captions')`, else an empty
 * track. False when the player has neither — nothing was tried. */
export function youtubeCaptionsOff(player: CaptionsModule): boolean {
  if (typeof player.unloadModule === "function") {
    player.unloadModule("captions");
    return true;
  }
  if (typeof player.setOption === "function") {
    player.setOption("captions", "track", {});
    return true;
  }
  return false;
}

/**
 * Whether a YouTube caption track is showing: `on` when `getOption('captions',
 * 'track')` names a language, `off` when it does not (no module loaded is no
 * captions shown), **`null` when the player cannot say — never guessed.**
 */
export function youtubeCaptions(player: CaptionsModule): "on" | "off" | null {
  if (typeof player.getOption !== "function") return null;
  const track = player.getOption("captions", "track");
  if (track && typeof track === "object") {
    const code = (track as { languageCode?: unknown }).languageCode;
    if (typeof code === "string" && code !== "") return "on";
  }
  return "off";
}

/** A desktop pointer: hover means something. Touch screens pause on tap. */
function canHoverPause(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(hover: hover) and (pointer: fine)").matches
  );
}

/**
 * How often the highlight re-reads the player clock. Four times a second: fast
 * enough that a cue boundary lands within a quarter-second of the word being
 * said, slow enough to cost nothing. **It writes nothing and is not the
 * progress ping** — see `positionS`.
 */
const HIGHLIGHT_MS = 250;

/**
 * The slice of the IFrame API this component calls. **Every method but
 * `destroy` exists only after `onReady`** (W31a, `ENGLISH-WEB-2`): the
 * constructor returns at once and the API attaches the rest when the iframe has
 * loaded, so nothing here calls one until `playerReady` says so.
 */
type Player = {
  getCurrentTime: () => number;
  setPlaybackRate: (rate: number) => void;
  destroy: () => void;
  pauseVideo: () => void;
  playVideo: () => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  getPlayerState: () => number;
} & CaptionsModule;

declare global {
  interface Window {
    YT?: {
      Player: new (el: HTMLElement, options: Record<string, unknown>) => Player;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

/**
 * Load the IFrame Player API once per document.
 *
 * **The one external script this app loads, and it is loaded from the component
 * that needs it** rather than in the root layout — a learner who never opens a
 * video day never fetches it.
 */
function useIframeApi(): boolean {
  const [ready, setReady] = useState(
    () => typeof window !== "undefined" && Boolean(window.YT),
  );
  useEffect(() => {
    if (typeof window === "undefined" || window.YT) {
      setReady(Boolean(window.YT));
      return;
    }
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      setReady(true);
    };
    if (!document.getElementById("yt-iframe-api")) {
      const script = document.createElement("script");
      script.id = "yt-iframe-api";
      script.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(script);
    }
  }, []);
  return ready;
}

export function VideoPlayer({
  payload,
}: {
  payload: VideoBlockPayload;
  /**
   * **#353: KEPT ON THE CONTRACT AND UNUSED, DELIBERATELY.** Every caller
   * already passes it, and the L1 track is this component's the day §1a is
   * ruled; removing it would mean editing `blocks.tsx`, `runner.tsx` and their
   * tests to put it back. It is not destructured, so nothing reads a value the
   * player cannot act on.
   */
  l1Language: string;
}) {
  const ready = useIframeApi();
  const mount = useRef<HTMLDivElement | null>(null);
  const player = useRef<Player | null>(null);
  /** The player's own box: Focus puts it in fullscreen, and the popover and
   * the sheet are placed inside it (W32b). */
  const root = useRef<HTMLDivElement | null>(null);
  /**
   * **W31a — `ENGLISH-WEB-2`.** True from the player's `onReady` until its
   * teardown. The clocks below start only when it is true, because a
   * `YT.Player` that has been constructed but not readied has no
   * `getCurrentTime` — calling it was the unhandled `TypeError` Sentry recorded
   * for user 3, four times a second until the iframe loaded.
   *
   * State for the effects, a ref for `ping`, which runs inside the player
   * effect's cleanup where state is already stale.
   */
  const [playerReady, setPlayerReady] = useState(false);
  const readyRef = useRef(false);
  /**
   * **W32e — YouTube's captions: what the player says, and whether we are
   * done switching them off.** `unknown` when the player cannot say (the hint
   * then never shows). **Switched off once per video**: when a track is first
   * seen on — or, where nothing can be seen, at ready and at the first module
   * change — and never again, so a learner who turns YouTube's CC back on
   * keeps it rather than watching a button undo itself.
   */
  const [ytCaptions, setYtCaptions] = useState<"on" | "off" | "unknown">("unknown");
  const captionsDone = useRef(false);
  const [hintDismissed, setHintDismissed] = useState(false);
  const [rate, setRate] = useState<number>(1);
  const [completed, setCompleted] = useState(payload.completed);
  /**
   * The player's position, for the follow-along highlight only.
   *
   * **A SECOND, FASTER CLOCK THAN THE PROGRESS PING, AND IT WRITES NOTHING.**
   * The ping is block 2's log and runs every 15 s (`PING_SECONDS`); a highlight
   * that moved once every 15 s would be worse than none. This one is local
   * state, never sent, and **runs only when there are cues to sync to** — a
   * transcript in the third state starts no interval at all.
   */
  const [positionS, setPositionS] = useState(payload.resume_position_s);

  /**
   * **W31c: a tap opens the word sheet**, which shows the word and saves it.
   * (W13-ii saved on the tap itself and showed one line of result here; the
   * result now lives in the sheet, with W31a's honest copy for every outcome.)
   * `sheetOpen` is a ref too, for the hover handlers (C5: leaving the line
   * never resumes while a sheet is open).
   */
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const sheetOpen = useRef(false);
  sheetOpen.current = sheet !== null;

  /**
   * **W32b — every meaning this video can show, fetched ONCE when the page
   * opens.** After that a hover or a tap is a lookup in memory: no request, so
   * under a second (the operator, 2026-09-27). `unavailable` keeps today’s path —
   * the sheet asks the server per word — so a lost map costs speed, not words.
   */
  const [meanings, setMeanings] = useState<MeaningsMap | "loading" | "unavailable" | "none">("none");
  const hasLines = payload.transcript_available && payload.lines.length > 0;
  useEffect(() => {
    if (!hasLines) {
      setMeanings("none");
      return;
    }
    let live = true;
    setMeanings("loading");
    videoMeanings(payload.video_id)
      .then((map) => live && setMeanings(map))
      .catch(() => live && setMeanings("unavailable"));
    return () => {
      live = false;
    };
  }, [payload.video_id, hasLines]);
  const map = typeof meanings === "object" ? meanings : null;

  /** A Save the sheet made: the map learns it, so the next tap says *kept*. */
  const onKept = useCallback((word: string, state: "in_deck" | "pending") => {
    setMeanings((current) =>
      typeof current === "object"
        ? { ...current, saved: { ...current.saved, [keyOf(current, word)]: state } }
        : current,
    );
  }, []);

  // ── a miss, looked up once (W32c) ────────────────────────────────────────
  /** The map, for callbacks that must not re-bind on every merge. */
  const mapRef = useRef<MeaningsMap | null>(null);
  mapRef.current = map;
  /** Words already asked about on this page: a miss is looked up ONCE, even
   * when the answer was *no meaning* — reopening the sheet never spends again. */
  const tried = useRef(new Set<string>());
  const [lookingKey, setLookingKey] = useState<string | null>(null);
  const lookUp = useCallback(
    (word: string, line: number | null) => {
      const current = mapRef.current;
      if (!current) return;
      const key = keyOf(current, word);
      if (tried.current.has(key)) return;
      tried.current.add(key);
      setLookingKey(key);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), LOOKUP_TIMEOUT_MS);
      defineWord(payload.video_id, word, line, controller.signal)
        .then((result) => {
          const entry: MeaningEntry | null =
            result.state === "defined" && result.entry
              ? result.entry
              : result.state === "name"
                ? { k: "n" }
                : null;
          if (!entry) return;
          setMeanings((now) =>
            typeof now === "object" ? { ...now, entries: { ...now.entries, [key]: entry } } : now,
          );
        })
        .catch(() => {
          // **A refusal is silent here and said in the sheet**: the word stays
          // a miss, which reads *no meaning yet* and still offers Save.
        })
        .finally(() => {
          clearTimeout(timer);
          setLookingKey((k) => (k === key ? null : k));
        });
    },
    [payload.video_id],
  );

  // ── the hover popover (W32b) ─────────────────────────────────────────────
  const [popover, setPopover] = useState<{ word: string; anchor: Anchor } | null>(null);
  const popoverShown = useRef(false);
  popoverShown.current = popover !== null;
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warmUntil = useRef(0);
  const clearHover = useCallback(() => {
    if (hoverTimer.current !== null) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
  }, []);
  const onWordHover = useCallback(
    (word: string, _line: number | null, el: HTMLElement, immediate: boolean) => {
      // A desktop pointer only — a phone's tap opens the sheet instead, and a
      // tap's focus must not also raise a popover under the learner's finger.
      if (!canHoverPause()) return;
      clearHover();
      const show = () => {
        const box = root.current?.getBoundingClientRect();
        const at = el.getBoundingClientRect();
        if (!box) return;
        setPopover({
          word,
          anchor: {
            x: at.left - box.left + at.width / 2,
            top: at.top - box.top,
            bottom: at.bottom - box.top,
            width: box.width,
          },
        });
      };
      if (immediate || Date.now() < warmUntil.current) show();
      else hoverTimer.current = setTimeout(show, HOVER_MS);
    },
    [clearHover],
  );
  const onWordHoverEnd = useCallback(() => {
    clearHover();
    if (popoverShown.current) warmUntil.current = Date.now() + SKIP_MS;
    setPopover(null);
  }, [clearHover]);
  useEffect(() => clearHover, [clearHover]);
  useEffect(() => {
    if (!popover) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPopover(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [popover]);
  /** The sheet's pause, so closing it resumes only what the tap (or a hover
   * that led to the tap) paused. */
  const pausedForSheet = useRef(false);

  const ping = useCallback(async () => {
    const current = player.current;
    // **Not ready is not an error; it is nothing to report yet.** The clock is
    // read OUTSIDE the `try` below, which is for the network and nothing else —
    // it used to wrap this call too, and silently swallowed the same TypeError
    // the highlight clock was throwing (W31a).
    if (!current || !readyRef.current) return;
    const position = current.getCurrentTime();
    try {
      const result = await reportVideoProgress(payload.video_id, position);
      setCompleted(result.completed);
    } catch {
      // **A failed ping is silent, and that is deliberate.** The learner is
      // watching a video; a toast about a resume position they did not ask to
      // save would interrupt the one block that is meant to be uninterrupted.
      // The position is lost, the video is not, and the next ping carries it.
    }
  }, [payload.video_id]);

  useEffect(() => {
    if (!ready || !mount.current || player.current || !window.YT) return;
    // **A fresh element per player (W31a).** YT replaces the element it is
    // given with its iframe, so building the next video's player on the same
    // node would hand it one YT had already taken away.
    const host = document.createElement("div");
    host.className = "h-full w-full";
    mount.current.appendChild(host);
    const wrapper = mount.current;
    captionsDone.current = false;
    setYtCaptions("unknown");
    /** W32e: at ready, and at every module change (the captions module loads
     * when a saved preference asks for it, usually as playback starts). */
    const settleCaptions = (moduleChange: boolean) => {
      const current = player.current;
      if (!current) return;
      if (!captionsDone.current) {
        const seen = youtubeCaptions(current);
        if (seen === "on") {
          youtubeCaptionsOff(current);
          captionsDone.current = true;
        } else if (seen === null) {
          youtubeCaptionsOff(current);
          captionsDone.current = moduleChange;
        }
      }
      setYtCaptions(youtubeCaptions(current) ?? "unknown");
    };
    player.current = new window.YT.Player(host, {
      videoId: payload.youtube_id,
      events: {
        onReady: () => {
          readyRef.current = true;
          setPlayerReady(true);
          settleCaptions(false);
        },
        onApiChange: () => {
          if (readyRef.current) settleCaptions(true);
        },
      },
      // **The resume position, honoured on the embed itself** — the learner
      // picks up where they stopped rather than restarting. #335's purged case
      // never reaches here; that branch renders no player at all.
      playerVars: {
        start: payload.resume_position_s,
        // **L1 subtitles OFF by default. PRD §7.3 and the row's own criterion.**
        // `cc_load_policy: 0` is the explicit off rather than the omitted
        // default, so a later YouTube default change cannot turn them on.
        // **W32e: it does not beat a viewer's saved caption preference** —
        // `settleCaptions` above does what it cannot, where the player lets it.
        cc_load_policy: 0,
        rel: 0,
        modestbranding: 1,
        // **W31b: YouTube's own fullscreen is OFF, and video plays inline.** In
        // YouTube's fullscreen — or iPhone Safari's native player, which is
        // what a missing `playsinline` gives — our subtitle line is not on the
        // screen, which is what the operator found on 2026-09-27. Focus (below)
        // is the full screen that keeps it.
        fs: 0,
        playsinline: 1,
        origin: typeof window === "undefined" ? undefined : window.location.origin,
      },
    });
    return () => {
      // **THE LAST POSITION IS SENT HERE, BEFORE `destroy`, AND THAT PLACEMENT
      // IS THE WHOLE OF IT.** React runs cleanups in the order the effects were
      // declared, so a final ping living in the interval effect below would run
      // AFTER this one had already nulled the ref -- `ping` would find no
      // player, return early, and closing the tab would silently lose the
      // place. Found by `player.test.tsx`'s unmount case, which fakes
      // `window.YT.Player` rather than stubbing `ping`; a test that had stubbed
      // the callback would have asserted that a function calls itself and
      // passed on the broken ordering.
      void ping();
      readyRef.current = false;
      setPlayerReady(false);
      player.current?.destroy();
      player.current = null;
      wrapper.replaceChildren();
    };
  }, [ready, payload.youtube_id, payload.resume_position_s, ping]);


  const lines = payload.lines;
  const timed = payload.lines_timed && lines.length > 0;
  const unknown = useMemo(
    () => new Set(payload.unknown_lemmas.map((w) => w.toLowerCase())),
    [payload.unknown_lemmas],
  );
  const active = timed ? activeLineIndex(lines, positionS) : null;

  /** W31b, Q3: the line being looped, or null. A ref too, for the clock. */
  const [loopIndex, setLoopIndex] = useState<number | null>(null);
  const loopRef = useRef<number | null>(null);
  loopRef.current = loopIndex;
  const linesRef = useRef(lines);
  linesRef.current = lines;

  useEffect(() => {
    // **Only a READY player has a clock** (W31a). The effect re-runs when
    // readiness changes, so a video change — whose cleanup sets it false —
    // clears this interval before the old player is destroyed, and the new
    // one's starts only at the new `onReady`.
    if (!timed || !playerReady) return;
    const timer = setInterval(() => {
      const current = player.current;
      if (!current) return;
      const t = current.getCurrentTime();
      const looping = loopRef.current;
      if (looping !== null) {
        const line = linesRef.current[looping];
        if (line && line.start !== null && line.end !== null && t >= line.end) {
          current.seekTo(line.start, true);
          setPositionS(line.start);
          return;
        }
      }
      setPositionS(t);
    }, HIGHLIGHT_MS);
    return () => clearInterval(timer);
  }, [timed, playerReady]);

  useEffect(() => {
    // A new video is a new set of lines: whatever was looping is gone.
    setLoopIndex(null);
  }, [payload.video_id]);

  useEffect(() => {
    const timer = setInterval(() => void ping(), PING_SECONDS * 1000);
    // **Only the timer is torn down here.** The final position is sent by the
    // player effect's cleanup, above, for the ordering reason recorded there.
    return () => clearInterval(timer);
  }, [ping]);

  const seek = useCallback((seconds: number) => {
    if (!readyRef.current) return;
    player.current?.seekTo(seconds, true);
    setPositionS(seconds);
  }, []);

  // ── pause to read (W31b) ──────────────────────────────────────────────────
  /** True when the pause was ours, so leaving resumes only what hover paused. */
  const pausedByHover = useRef(false);
  const pauseIfPlaying = useCallback((): boolean => {
    const current = player.current;
    if (!readyRef.current || !current) return false;
    if (current.getPlayerState() !== PLAYING) return false;
    current.pauseVideo();
    return true;
  }, []);
  const onHoverStart = useCallback(() => {
    if (!canHoverPause()) return;
    pausedByHover.current = pauseIfPlaying() || pausedByHover.current;
  }, [pauseIfPlaying]);
  const onHoverEnd = useCallback(() => {
    if (!canHoverPause()) return;
    // **Unless a word sheet is open** (C5): the learner is reading it. The
    // hover's pause is handed to the sheet, which resumes it on close.
    if (sheetOpen.current) return;
    if (pausedByHover.current && readyRef.current) player.current?.playVideo();
    pausedByHover.current = false;
  }, []);
  const onLineWordTap = useCallback(
    (word: string, line: number | null) => {
      // **A tap pauses, on every device** — the learner stopped to look at a
      // word. On a desktop the hover has usually paused already, and that
      // pause becomes the sheet's.
      pausedForSheet.current = pauseIfPlaying() || pausedByHover.current;
      pausedByHover.current = false;
      clearHover();
      setPopover(null);
      setSheet({ word, line });
    },
    [pauseIfPlaying, clearHover],
  );
  const closeSheet = useCallback(() => {
    setSheet(null);
    if (pausedForSheet.current && readyRef.current) player.current?.playVideo();
    pausedForSheet.current = false;
  }, []);

  // ── Focus (W31b) ──────────────────────────────────────────────────────────
  /** `native`: the Fullscreen API on our wrapper. `fixed`: a full-viewport
   * layout, where the browser has no element fullscreen (iPhone Safari). */
  const [focus, setFocus] = useState<"off" | "native" | "fixed">("off");

  const enterFocus = useCallback(() => {
    const el = root.current as
      | (HTMLDivElement & { webkitRequestFullscreen?: () => Promise<void> | void })
      | null;
    if (!el) return;
    const doc = document as Document & { webkitFullscreenEnabled?: boolean };
    const request = el.requestFullscreen ?? el.webkitRequestFullscreen;
    const enabled = doc.fullscreenEnabled ?? doc.webkitFullscreenEnabled ?? false;
    if (!request || !enabled) {
      setFocus("fixed");
      return;
    }
    Promise.resolve(request.call(el))
      .then(() => {
        setFocus("native");
        lockLandscape();
      })
      .catch(() => setFocus("fixed"));
  }, []);

  const exitFocus = useCallback(() => {
    const doc = document as Document & { webkitExitFullscreen?: () => void };
    unlockOrientation();
    if (document.fullscreenElement) {
      void (document.exitFullscreen?.() ?? doc.webkitExitFullscreen?.());
    }
    setFocus("off");
  }, []);

  // ── landscape → Focus (W32d) ────────────────────────────────────────────
  /**
   * **Turning a phone sideways on `/watch` enters Focus; turning it back exits
   * — but only a Focus the rotation entered.** A Focus the learner chose stays.
   * A rotation is not a user gesture, so the browser refuses the Fullscreen
   * API and W31b's own fallback gives the full-viewport layout (`fixed`); the
   * Focus button, a gesture, still gets true fullscreen where the browser has
   * it. Touch screens only: a desktop window made wide is not a phone turned.
   */
  const focusRef = useRef(focus);
  focusRef.current = focus;
  const rotated = useRef(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const sideways = window.matchMedia(
      "(orientation: landscape) and (hover: none) and (pointer: coarse)",
    );
    const apply = () => {
      if (sideways.matches) {
        if (focusRef.current === "off") {
          rotated.current = true;
          enterFocus();
        }
      } else if (rotated.current) {
        rotated.current = false;
        exitFocus();
      }
    };
    apply();
    return onMediaChange(sideways, apply);
  }, [enterFocus, exitFocus]);

  useEffect(() => {
    // The browser's own exit (Esc, a swipe) ends native focus too.
    const sync = () => {
      if (!document.fullscreenElement) setFocus((f) => (f === "native" ? "off" : f));
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      document.removeEventListener("webkitfullscreenchange", sync);
    };
  }, []);

  useEffect(() => {
    if (focus !== "fixed") return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFocus("off");
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [focus]);

  useEffect(() => {
    // **W32e — the bottom nav steps aside for Focus** (`globals.css`). On
    // iPhone, Focus is the fixed layout, and the nav — the same `z-50`, later
    // in the DOM — was painted over it: over Exit, the video's bottom edge and
    // the word sheet's Save (the operator's iPhone, sideways, 2026-09-28).
    if (focus === "off") return;
    const html = document.documentElement;
    html.dataset.videoFocus = focus;
    return () => {
      delete html.dataset.videoFocus;
    };
  }, [focus]);

  const focused = focus !== "off";
  const band = payload.coverage_band;
  const hasText = payload.transcript_available && lines.length > 0;

  return (
    <div
      ref={root}
      data-testid="video-player"
      data-focus={focus}
      data-meanings={meanings === "loading" || meanings === "unavailable" || meanings === "none" ? meanings : "ready"}
      data-yt-captions={ytCaptions}
      className={
        focused
          ? "fixed inset-0 z-[70] flex h-[100dvh] w-full flex-col justify-center gap-3 overflow-hidden bg-background p-3"
          : "relative space-y-4"
      }
    >
      {/* **The chip is BEFORE the player** — the row's criterion is "coverage
          badge shown before play", and a difficulty read after watching is not
          a decision aid. Absent when the server withheld it (#330), and its
          absence is silent. Hidden in Focus, which is for watching. */}
      {band && !focused ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="coverage-band"
          data-band={band}
        >
          {VIDEO.band[band]}
        </p>
      ) : null}

      <div className={focused ? "flex min-h-0 shrink items-center justify-center" : ""}>
        <div
          data-testid="video-box"
          className="relative mx-auto aspect-video w-full overflow-hidden rounded-lg bg-muted"
          // W32d: the caption is on the video now, so Focus gives the video
          // everything but the controls row (~3.5rem with its gap) — W31b's
          // 14rem was the line's room under it.
          style={focused ? { width: "min(100%, calc((100dvh - 4.5rem) * 16 / 9))" } : undefined}
        >
          <div
            ref={mount}
            className="h-full w-full"
            data-testid="player-mount"
            data-player-ready={playerReady ? "true" : "false"}
          />
          {focused ? null : (
            // **W32e (B1) — full screen where people look for it**: the video's
            // bottom-right corner, drawn in our layer above the iframe. Focus
            // has its exit in the row under the picture, which stays clear.
            <button
              type="button"
              aria-label={VIDEO.study.focus}
              title={VIDEO.study.focus}
              data-testid="focus-corner"
              onClick={enterFocus}
              className="absolute bottom-2 right-2 z-10 flex h-11 w-11 items-center justify-center rounded-md bg-black/60 text-white transition-colors hover:bg-black/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white lg:h-9 lg:w-9"
            >
              <Maximize className="h-5 w-5" aria-hidden />
            </button>
          )}
          {focused && timed ? (
            <SubtitleBlock
              lines={lines}
              active={active}
              unknown={unknown}
              onWordTap={onLineWordTap}
              onWordHover={onWordHover}
              onWordHoverEnd={onWordHoverEnd}
              onHoverStart={onHoverStart}
              onHoverEnd={onHoverEnd}
              caption
            />
          ) : null}
        </div>
      </div>

      {ytCaptions === "on" && !hintDismissed && !focused ? (
        // **W32e (B3) — only when the player SAYS a YouTube track is on**, and
        // switching it off did not take. Dismissible; never shown on a guess.
        // Not in Focus, where ours are on the picture rather than below it.
        <div
          className="flex items-center gap-2 rounded-lg bg-muted/40 py-1 pl-3 pr-1 text-sm text-muted-foreground"
          data-testid="yt-captions-hint"
          role="note"
        >
          <p className="min-w-0 flex-1">{VIDEO.study.ytCaptions}</p>
          <Button
            size="sm"
            variant="ghost"
            className="min-h-11 min-w-11 shrink-0 lg:min-h-8 lg:min-w-8"
            aria-label={VIDEO.study.ytCaptionsDismiss}
            data-testid="yt-captions-hint-dismiss"
            onClick={() => setHintDismissed(true)}
          >
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      ) : null}

      {timed && !focused ? (
        <SubtitleBlock
          lines={lines}
          active={active}
          unknown={unknown}
          onWordTap={onLineWordTap}
          onWordHover={onWordHover}
          onWordHoverEnd={onWordHoverEnd}
          onHoverStart={onHoverStart}
          onHoverEnd={onHoverEnd}
        />
      ) : focused && !timed ? (
        <p className="text-center text-sm text-muted-foreground" data-testid="no-timed">
          {VIDEO.study.noTimed}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {RATES.map((option) => (
          <Button
            key={option}
            size="sm"
            variant={rate === option ? "default" : "outline"}
            data-testid={`rate-${option}`}
            onClick={() => {
              setRate(option);
              if (readyRef.current) player.current?.setPlaybackRate(option);
            }}
          >
            {option}×
          </Button>
        ))}
        {timed ? (
          <Button
            size="sm"
            variant={loopIndex !== null ? "default" : "outline"}
            data-testid="loop-line"
            className="min-h-11 lg:min-h-8"
            aria-pressed={loopIndex !== null}
            disabled={loopIndex === null && active === null}
            onClick={() => setLoopIndex((current) => (current === null ? active : null))}
          >
            {loopIndex !== null ? VIDEO.study.loopOn : VIDEO.study.loop}
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="outline"
          className="ml-auto min-h-11 lg:min-h-8"
          data-testid={focused ? "focus-exit" : "focus-enter"}
          onClick={focused ? exitFocus : enterFocus}
        >
          {focused ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
          {focused ? VIDEO.study.focusExit : VIDEO.study.focus}
        </Button>
      </div>

      {completed && !focused ? (
        <p className="text-sm text-muted-foreground" data-testid="video-watched">
          {VIDEO.watched}
        </p>
      ) : null}

      <WordSheet
        videoId={payload.video_id}
        target={sheet}
        onClose={closeSheet}
        map={map}
        lineText={sheet && sheet.line !== null ? lines[sheet.line]?.text ?? null : null}
        onKept={onKept}
        onMiss={lookUp}
        lookingUp={Boolean(sheet && map && lookingKey === keyOf(map, sheet.word))}
      />

      {popover && map ? (
        <WordPopover anchor={popover.anchor} found={resolve(map, popover.word)} l1Language={map.l1} />
      ) : null}

      {focused ? null : hasText ? (
        <LineList
          lines={lines}
          active={active}
          unknown={unknown}
          onWordTap={onLineWordTap}
          onWordHover={onWordHover}
          onWordHoverEnd={onWordHoverEnd}
          onSeek={timed ? seek : undefined}
        />
      ) : (
        // **#335 on the screen.** The video plays; only the follow-along text
        // is gone. No apology, no blame, no "expired" — nothing the learner did
        // caused this and nothing they can do fixes it.
        <p
          className="max-w-prose text-sm leading-relaxed text-muted-foreground"
          data-testid="no-transcript"
        >
          {VIDEO.noTranscript}
        </p>
      )}
    </div>
  );
}
