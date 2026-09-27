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
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { VIDEO } from "@/components/session/copy";
import { Transcript } from "@/components/video/transcript";
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

/** Whole-video playback rates. **Not per-line — that needs timings (R12).** */
const RATES = [1, 0.75] as const;

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


  const cues = payload.transcript_cues ?? undefined;

  useEffect(() => {
    // **Only a READY player has a clock** (W31a). The effect re-runs when
    // readiness changes, so a video change — whose cleanup sets it false —
    // clears this interval before the old player is destroyed, and the new
    // one's starts only at the new `onReady`.
    if (!cues?.length || !playerReady) return;
    const timer = setInterval(() => {
      const current = player.current;
      if (current) setPositionS(current.getCurrentTime());
    }, HIGHLIGHT_MS);
    return () => clearInterval(timer);
  }, [cues, playerReady]);

  useEffect(() => {
    const timer = setInterval(() => void ping(), PING_SECONDS * 1000);
    // **Only the timer is torn down here.** The final position is sent by the
    // player effect's cleanup, above, for the ordering reason recorded there.
    return () => clearInterval(timer);
  }, [ping]);

  const band = payload.coverage_band;

  return (
    <div className="space-y-4" data-testid="video-player">
      {/* **The chip is BEFORE the player** — the row's criterion is "coverage
          badge shown before play", and a difficulty read after watching is not
          a decision aid. Absent when the server withheld it (#330), and its
          absence is silent: there is no "we can't tell you" line, because that
          would be a message about our instrument dressed as a message about
          the video. */}
      {band ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="coverage-band"
          data-band={band}
        >
          {VIDEO.band[band]}
        </p>
      ) : null}

      <div className="aspect-video w-full overflow-hidden rounded-lg bg-muted">
        <div
          ref={mount}
          className="h-full w-full"
          data-testid="player-mount"
          data-player-ready={playerReady ? "true" : "false"}
        />
      </div>

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
      </div>

      {completed ? (
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

      {payload.transcript_available && payload.transcript ? (
        <Transcript
          onWordTap={onWordTap}
          text={payload.transcript}
          unknownLemmas={payload.unknown_lemmas}
          language={payload.transcript_lang ?? "en"}
          cues={cues}
          positionS={cues?.length ? positionS : undefined}
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
