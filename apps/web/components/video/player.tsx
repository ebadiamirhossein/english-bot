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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { VIDEO } from "@/components/session/copy";
import { LineList } from "@/components/video/line-list";
import { activeLineIndex } from "@/components/video/lines";
import { SubtitleBlock } from "@/components/video/subtitle-block";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  reportVideoProgress,
  saveWord,
  type SaveWordResult,
  type VideoBlockPayload,
} from "@/lib/api";

/**
 * What a tap came to. The server's three states, plus **the four ways a request
 * can come back refused**, each with its own sentence (W31a). Before, all four
 * were one catch-all line, which is how a malformed request (#465) read to the
 * operator as a dropped connection.
 */
type TapOutcome =
  | SaveWordResult["state"]
  | "not_assigned"
  | "rate_limited"
  | "offline"
  | "server";

function refusal(error: unknown): TapOutcome {
  if (!(error instanceof ApiError)) return "server";
  if (error.status === undefined) return "offline";
  if (error.status === 404) return "not_assigned";
  if (error.status === 429) return "rate_limited";
  return "server";
}

const TAP_COPY: Record<TapOutcome, string> = {
  saved: VIDEO.saveWord.saved,
  already_saved: VIDEO.saveWord.already,
  no_gloss: VIDEO.saveWord.notReady,
  not_assigned: VIDEO.saveWord.notAssigned,
  rate_limited: VIDEO.saveWord.rateLimited,
  offline: VIDEO.saveWord.offline,
  server: VIDEO.saveWord.server,
};

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
};

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
   * W13-ii. What the last tap did, or `null` for "nothing tapped yet".
   *
   * **ONE MESSAGE, REPLACED, NEVER A LIST.** A tapped-word history that grew
   * down the screen would be a counter of work done, and the one place this
   * product has never allowed one is beside the thing the learner is doing.
   *
   * **`already_saved` IS NOT AN ERROR AND IS NOT STYLED AS ONE** (#178): the
   * learner tapped a word they had already saved, which is a normal thing to do
   * and, on a second viewing, the expected thing.
   */
  const [tapped, setTapped] = useState<
    { word: string; state: TapOutcome } | null
  >(null);

  const onWordTap = useCallback(
    (word: string) => {
      // **Optimistic nothing.** The message appears when the server answers,
      // because "Added to your deck" before the write lands is a claim the app
      // cannot make -- the same reason `item-card.tsx` shows no verdict while a
      // grade is in flight.
      void saveWord(payload.video_id, word)
        .then((result) => setTapped({ word, state: result.state }))
        .catch((error: unknown) => setTapped({ word, state: refusal(error) }));
    },
    [payload.video_id],
  );

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
    player.current = new window.YT.Player(host, {
      videoId: payload.youtube_id,
      events: {
        onReady: () => {
          readyRef.current = true;
          setPlayerReady(true);
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
    if (pausedByHover.current && readyRef.current) player.current?.playVideo();
    pausedByHover.current = false;
  }, []);
  const onLineWordTap = useCallback(
    (word: string) => {
      // **A tap pauses, on every device** — the learner stopped to look at a
      // word. On a desktop the hover has usually paused already.
      pauseIfPlaying();
      onWordTap(word);
    },
    [onWordTap, pauseIfPlaying],
  );

  // ── Focus (W31b) ──────────────────────────────────────────────────────────
  const root = useRef<HTMLDivElement | null>(null);
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
      .then(() => setFocus("native"))
      .catch(() => setFocus("fixed"));
  }, []);

  const exitFocus = useCallback(() => {
    const doc = document as Document & { webkitExitFullscreen?: () => void };
    if (document.fullscreenElement) {
      void (document.exitFullscreen?.() ?? doc.webkitExitFullscreen?.());
    }
    setFocus("off");
  }, []);

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

  const focused = focus !== "off";
  const band = payload.coverage_band;
  const hasText = payload.transcript_available && lines.length > 0;

  return (
    <div
      ref={root}
      data-testid="video-player"
      data-focus={focus}
      className={
        focused
          ? "fixed inset-0 z-50 flex h-[100dvh] w-full flex-col justify-center gap-3 overflow-hidden bg-background p-3"
          : "space-y-4"
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
          className="mx-auto aspect-video w-full overflow-hidden rounded-lg bg-muted"
          style={focused ? { width: "min(100%, calc((100dvh - 14rem) * 16 / 9))" } : undefined}
        >
          <div
            ref={mount}
            className="h-full w-full"
            data-testid="player-mount"
            data-player-ready={playerReady ? "true" : "false"}
          />
        </div>
      </div>

      {timed ? (
        <SubtitleBlock
          lines={lines}
          active={active}
          unknown={unknown}
          onWordTap={onLineWordTap}
          onHoverStart={onHoverStart}
          onHoverEnd={onHoverEnd}
          large={focused}
        />
      ) : focused ? (
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
          {focused ? VIDEO.study.focusExit : VIDEO.study.focus}
        </Button>
      </div>

      {completed && !focused ? (
        <p className="text-sm text-muted-foreground" data-testid="video-watched">
          {VIDEO.watched}
        </p>
      ) : null}

      {tapped ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="save-word-result"
          data-outcome={tapped.state}
          aria-live="polite"
        >
          {TAP_COPY[tapped.state]}
        </p>
      ) : null}

      {focused ? null : hasText ? (
        <LineList
          lines={lines}
          active={active}
          unknown={unknown}
          onWordTap={onLineWordTap}
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
