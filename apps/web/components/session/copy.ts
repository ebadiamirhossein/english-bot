/**
 * Every word the session runner says, in one place.
 *
 * Two rules shape all of it, and both are constitutional rather than stylistic:
 *
 * **Never guilt** (CLAUDE.md §4). No "you failed", no broken-streak message, no
 * disappointed emoji. The banned-phrase scan in `tests/test_web_shell.py` runs
 * over this file like every other source file in `app`, `components` and `lib`.
 *
 * **Never present a backlog** (CLAUDE.md §4, PRD §12 rule 5). Nothing here
 * counts what a learner did not do, mentions yesterday, or names what was not
 * shown. A learner returning after a week sees today.
 */

/**
 * Block 1 with nothing due. **The app offers watching; it never invents work.**
 *
 * Ruled 2026-08-26. No filler item, no "practise anyway", no streak language.
 *
 * **It deliberately links nowhere.** The video side is W12 (the engine) and W13
 * (the player), so there is no video to point at yet, and a link to a screen
 * that does not exist would be worse than a sentence that stands on its own.
 * Filed against W13, where this becomes a real suggestion with an actual video.
 *
 * There is deliberately **no session-level variant** of this copy. Block 4
 * always carries the unit's written task, so an all-blocks-empty session is
 * unreachable today, and a green test over an unreachable path proves nothing
 * (CLAUDE.md §3 rule 4).
 */
export const NOTHING_DUE = {
  title: "Nothing’s due today.",
  body: "Go watch something you actually enjoy — in English, with subtitles if you want them. That counts, and it’s the part that makes the rest work.",
} as const;

/**
 * A block that could not be built. **Never the same words as an empty block.**
 *
 * This is the distinction the whole `state` field exists for. A learner told
 * *nothing’s due* because a query timed out has been lied to, and on the screen
 * the lie is indistinguishable from the truth. So this copy says something went
 * quiet — not that there is nothing to do — and offers the way back.
 *
 * No apology and no blame in either direction: it is neither the learner's
 * fault nor worth an "oops".
 */
export const BLOCK_UNAVAILABLE = {
  title: "This part didn’t load.",
  body: "It’ll be here next time you open the session.",
  action: "Try again",
} as const;

/** Per-block headings and the honest line under each empty one. */
export const BLOCKS = {
  review: {
    eyebrow: "Review",
    title: "The things you nearly know.",
  },
  input: {
    eyebrow: "Input",
    title: "Something to watch.",
    // Structural, not a failure. Saying so is more honest than hiding the block
    // and implying the product has four.
    //
    // **CORRECTED 2026-09-01.** This comment said `videos` and
    // `video_assignments` "do not exist yet"; both exist (migrations 019 and
    // 020, production `schema_version` 20). **The learner-facing string below is
    // unchanged and is still true** -- what is missing is W13's player, which is
    // what the string actually says.
    // **W13-i BUILT THE PLAYER, SO THIS LINE STOPS BEING TRUE ON MOST DAYS AND
    // CHANGES MEANING RATHER THAN GOING AWAY.** The old string is quoted rather
    // than deleted (#82's shape): *"The video side isn\u2019t built yet. It arrives
    // with the player."* It said the SURFACE was missing. What the block now
    // says is that there is no video ON THIS DAY \u2014 PRD \u00a77.1 assigns video on
    // Monday, Wednesday and Friday, so four days in seven have none, and that
    // is the ordinary state rather than a gap.
    //
    // **No backlog and no yesterday** (CLAUDE.md \u00a74): it does not say a video
    // was missed, count what was not watched, or mention another day by name.
    //
    // **W24d (2026-09-27): A VIDEO EVERY DAY, WHEN THE POOL HAS ONE.** The line
    // read *"No video today. There\u2019ll be one on Monday, Wednesday and
    // Friday."* until operator decision 2 made video daily. A day with no video
    // is now one the pool could not serve in band and unseen, so no day can be
    // promised -- not a weekday, not tomorrow. It points at what always counts.
    empty: "No video today \u2014 anything you enjoy watching in English counts just as much.",
  },
  focus: {
    eyebrow: "Focus",
    title: "This week’s grammar.",
    empty: "No unit is set up yet.",
    // #182, in one line a learner can read. **W10b built the teaching, so this
    // line is now CONDITIONAL rather than unconditional**: it renders only when
    // `payload.lesson` is null, which is still most units — generation is
    // human-run (#196) — and also a stored lesson below the current
    // `LESSON_VERSION`, which the service refuses to serve. The string is
    // unchanged and correct in both cases.
    noLesson: "The written explanation for these is on its way.",
    // W10c: the items exist now, so the line apologising for their absence is
    // gone rather than reworded. `progress` replaces it — a position, not a
    // count of what is left, because CLAUDE.md §4 forbids presenting a backlog.
    progress: "Practice · {n} of {total}",
    // W11, and every word of it is load-bearing.
    //
    // **Not "you've completed the unit"** — the checkpoint has not happened, so
    // there is nothing to congratulate and a congratulation here would make the
    // checkpoint read as optional.
    //
    // **Not an apology and not a backlog** — it says what IS available, never
    // what is not (CLAUDE.md §4, #160). "You've seen all of it" would read as
    // an accusation on the day a learner is told there is no new teaching.
    //
    // **It must not be `noLesson`.** A learner who has read all four sections
    // being told "the written explanation is on its way" is a lie the screen
    // cannot be distinguished from the truth — the same reason `empty` and
    // `unavailable` are two block states rather than one.
    teachingComplete:
      "That’s all of this week’s grammar. The sections stay open above — practice below.",
  },
  output: {
    /** For `empty` and `unavailable`, which draw no task card. */
    eyebrow: "Output",
    title: "Say something of your own.",
    empty: "No task is set up yet.",
    /**
     * **W16a — design `1c`, keyed by the payload's `day_kind`.** One component,
     * one field; the Tuesday and Thursday cards differ only in these three
     * strings. **Only `journal` exists in W16a** — the paragraph card is W16b's.
     * The old ready-state copy is quoted rather than deleted (#82's shape): the
     * card read *"Output"* / *"Say something of your own."* above the unit's
     * written task, with a *"Write it"* button.
     *
     * **No day name, no count of sentences, no *you haven't written since…*,
     * no dot or badge** (`1c`'s *absent* note).
     */
    journal: {
      eyebrow: "Today · your turn to write",
      title: "Write a few lines about your day.",
      body: "In your own words, in English. I’ll read it and point out one or two things.",
    },
    /**
     * **W16b — `1c`'s Thursday card.** The design's title reads *"One
     * paragraph, on a question."* **Not taken, and the reason is the data:** the
     * paragraph is the unit's `output_task_written`, and most of the 24 are
     * tasks, not questions (*"Write six sentences about yesterday…"*). A title
     * that says what the prompt is not is the design asking for something the
     * data cannot support (§1a).
     *
     * **`body` read *"A bit longer than usual. I’ll go through all of it
     * afterwards."*** (quoted, #82's shape) — the design's string, kept by the
     * first W16b pass while `WRITE.paragraph.subline` below dropped *all of it*
     * for Q-D's cap of eight. One surface promised what the other had already
     * ruled false; found by the session that stood down (finding (b)).
     */
    paragraph: {
      eyebrow: "Today · this week’s paragraph",
      title: "One paragraph, on this week’s task.",
      body: "A bit longer than usual. I’ll go through it afterwards.",
    },
    action: "Start writing",
  },
  close: {
    /**
     * **W13b/5a takes the design's `1i` card copy.** Old values quoted rather
     * than deleted (#82's shape): `eyebrow: "Close"`, `title: "That’s today."`.
     *
     * The design's line does more than name the block: *the rest of the English
     * is up to you* is the product declining to claim the day is finished
     * because the app is. CLAUDE.md §4 — ten minutes is the floor, never the
     * ceiling, and nothing here counts what was not done.
     */
    eyebrow: "Today · to close",
    title: "That’s the session. The rest of the English is up to you.",
  },
} as const;

/** What the runner says when every block is behind you. */
export const SESSION_DONE = {
  title: "Done for today.",
  body: "Same time tomorrow — and tomorrow is its own session, not this one plus more.",
} as const;

/**
 * **W24e — keep going** (operator decision 1, 2026-09-27): an optional next
 * thing after a finished session, and on Sunday. **The rules are the product's,
 * not Duolingo's:** no count, no score, no backlog, nothing a learner *should*
 * do, and nothing said when they do none of it. Each label names an activity,
 * never an amount — *a few cards*, not *7 cards*.
 */
export const KEEP_GOING = {
  lead: "If you\u2019d like a bit more:",
  /** R1: Sunday offers only something to watch — PRD §4.2's free input. */
  sundayLead: "If you feel like watching something:",
  watch: "Watch something",
  talk: "Talk for a bit",
  cards: "A few cards",
  write: "Write a few lines",
} as const;

/** W24e — `/watch`, keep going's video page. */
export const WATCH = {
  eyebrow: "Keep going",
  title: "Something to watch.",
  body: "Chosen for you, at your level. Stop whenever you like.",
  finding: "Finding something to watch\u2026",
  /** Nothing in band and unseen, or today's extra is watched. No count, no day promised. */
  none: "Nothing more to watch here today \u2014 anything you enjoy watching in English counts just as much.",
  back: "Back to today",
} as const;

/**
 * The typed-answer verdicts (#157).
 *
 * **Neither of them marks the learner.** A match is confirmed; a miss shows the
 * answer and says nothing about the person who typed. The four grade buttons
 * follow either way — this verdict informs the self-grade, it does not replace
 * it, because a card's back is a single string with no accepted variants beside
 * it and a near-miss is often correct English.
 */
export const TYPED = {
  label: "Type what you think it is",
  submit: "Check",
  skip: "Show me",
  matched: "That’s it.",
  // Deliberately not a verdict about the answer at all: it hands over the card
  // and lets the learner decide. "Not quite" would still be a mark, and this
  // comparison is a single-string fold that cannot see a good paraphrase.
  unmatched: "Here it is:",
} as const;

/**
 * **#276 (c), operator ruling 2026-08-29.** Unit 1's practice bank is sixteen
 * items behind an eight-a-day window, so a learner meets the same sentences on a
 * two-day rotation. Ruling (b) — hiding sat checkpoint items — was REFUSED: it
 * would take the bank from sixteen to four and trade a repetition defect for an
 * emptiness one.
 *
 * So the app says it plainly instead. **No apology, no "again", no count of how
 * many times** — a tally is a score, and a score on repetition is a reproach.
 * It states the fact and stops. Covered by the `.tsx` no-guilt scan like every
 * other string here.
 */
export const SEEN_BEFORE = "You've answered this one before.";

/**
 * **W17 — the eyebrow above a weak-spot drill in block 3.** The pattern's plain
 * label sits beside it in a bordered pill (*"Articles"*), from
 * `error_types.learner_label`.
 *
 * **It names where the drill comes from, and nothing about how often.** No
 * count, no "again", no "you keep getting this wrong": the journal's count is a
 * threshold the server reads and never a number the learner sees (#412,
 * CLAUDE.md §4). Covered by the `.tsx`/`.ts` no-guilt scan.
 */
export const DRILL_EYEBROW = "From your own English";


/**
 * The player. **W13-i.**
 *
 * **THERE IS NO PERCENTAGE HERE AND NONE CAN REACH HERE.** `core/video/badge.py`
 * returns `below` | `in` | `above` or nothing at all, and the figure never
 * crosses the wire — so this object cannot render a number it was never given.
 * Three reasons, and none of them is a taste:
 *
 * - **#288** — the assumed-known floor ranks proper nouns as common vocabulary
 *   (`john` 548, `michael` 763, `paris` 1107, `sarah` 1221, all inside the
 *   top-2,000 floor), so every coverage figure is inflated by an amount
 *   **nobody has counted**, and the inflation is largest on dialogue-heavy
 *   transcripts — which is what this pool is.
 * - **#334** — `score_breakdown.coverage_fit` returns 1.0 anywhere inside the
 *   band, so the obvious extraction would put **100%** on the screen.
 * - **#330** — a percentage over a 234-character transcript measures one
 *   paragraph.
 *
 * **The bar is not lowered (CLAUDE.md §3 rule 7).** No number is adjusted and no
 * band widened; what is declined is *displaying* a figure the record knows to
 * be wrong. PRD §7.3's `"94% known — slightly hard"` is amended in place.
 *
 * **Difficulty, never a score.** Each line says what the video will be like to
 * watch. None of them says how much the learner knows, because that is the
 * claim the instrument cannot support — and none of them is a verdict about the
 * learner in either direction.
 */
export const VIDEO = {
  /** No badge: the transcript is too short to mean anything (#330), or the
   * basis was degraded. **Absence, not a fourth band** — the block simply shows
   * no chip rather than a chip saying nothing. */
  band: {
    below: "Expect some new words.",
    in: "Should be about right.",
    above: "Should be an easy watch.",
  },
  /**
   * **UNRENDERED SINCE 2026-09-02 (#353), AND KEPT ON PURPOSE.** This comment
   * read: *"L1 subtitles are OFF until tapped — PRD §7.3, and the row's own
   * criterion. The control names the language the learner would get, not
   * 'translation'."* — quoted rather than deleted (#82's shape), because the
   * second sentence is a copy decision worth keeping and the first described a
   * control that toggled nothing.
   *
   * **The control was removed, not the strings.** There has never been an L1
   * track to show — PRD §2.5 has it generated from the English transcript and
   * cached, never fetched from YouTube, and generating it is gated on §1a — so
   * the button relabelled itself and nothing appeared. **These two strings are
   * what the control says the day the track lands**, and re-authoring them then
   * would mean re-making a decision that is already made.
   */
  subtitles: {
    show: "Show {language}",
    hide: "Hide {language}",
  },
  /**
   * W13-ii. **What a tap says, and the three answers are three different
   * sentences.** #178: *already saved* is not an error and must not read like
   * one; *not ready yet* is §1a's PRE-GENERATE ruling on a screen — the word
   * has no definition **yet**, and nothing the learner did caused that.
   *
   * **None of these blames anyone.** `test_no_guilt_copy_anywhere_in_the_frontend`
   * covers this file automatically; the harder half is that none of them
   * implies the learner should have known better, which no regex can check.
   */
  saveWord: {
    saved: "Added to your deck.",
    already: "Already in your deck.",
    notReady: "No definition for that one yet.",
    // **NOT `failed`.** `copy_rules.BANNED` bans the bare word in anything the
    // app says, and `test_no_guilt_copy_anywhere_in_the_frontend` caught this
    // key and its three uses in `player.tsx`. **The scan was right about more
    // than the word**: a request that did not come back is the app's problem,
    // and naming the state after a failure invites copy that reads like the
    // learner's. `unavailable` is `BLOCK_STATES`' own word for the same thing.
    //
    // **W31a: `unavailable` IS GONE AND FOUR SENTENCES REPLACE IT.** It read
    // *"Could not add that just now."* and it was the answer to everything that
    // was not a 200 — so sixteen 422s from a malformed request (#465) read to the
    // operator like a flaky connection. Each refusal now says what it is. The old
    // line is quoted here and nowhere else; `player.test.tsx` refuses it.
    notAssigned: "This video isn’t in your list any more.",
    rateLimited: "That’s a lot of words at once — try again in a minute.",
    offline: "Couldn’t reach the server. Check your connection and tap again.",
    server: "That didn’t go through on our side — not yours. Try again in a moment.",
  },
  /** **#335.** The transcript was purged at thirty days and the video is still
   * assigned and still watchable. It says what IS there, does not apologise,
   * does not blame, and does not use the word "expired" — nothing the learner
   * did caused this and nothing they can do fixes it. */
  noTranscript:
    "The follow-along text isn’t available for this one. The video still plays.",
  /**
   * **W31b — the study screen.** Plain labels; nothing counts, nothing scores.
   * `noTimed` is Focus mode's one line for a video with no timings — it says
   * what is there (the video) and not what went missing.
   */
  study: {
    focus: "Focus",
    focusExit: "Exit focus",
    loop: "Loop line",
    loopOn: "Looping this line",
    noTimed: "This video has no timed subtitles.",
  },
  /** Shown once the watch signal has been written. **Not a congratulation and
   * not a streak** — a plain statement of where they are. */
  watched: "You’ve watched this one.",
  /** The resume affordance. It never says how much is left. */
  resume: "Pick up where you left off",
} as const;

/**
 * Block 4's speak half. W14.
 *
 * **THIS IS THE HIGHEST-RISK COPY IN THE APP AND IT IS WORTH SAYING WHY.** A
 * pronunciation score is the single most likely surface here to read as a
 * verdict on the person rather than on the attempt — #348 is the live instance
 * of a guilt message shipping, and #303 carries PRD §8.6's open question 3:
 * *a score on every turn may be exactly the thing that makes someone stop
 * speaking.*
 *
 * So: **no number anywhere**, no "score", no percentage, no grade word. The
 * weaker words are tinted amber and underlined; nothing announces them.
 *
 * `improved` is the ONLY comparison the learner ever sees, and it fires only
 * upward — **raises announced, drops silent** (CLAUDE.md §4).
 *
 * `unavailable` is the quota message. **It says the scoring is off, not that
 * the learner is done** — and it invites the line to be said anyway, because
 * saying it aloud is the exercise and the score is only the feedback.
 */
export const SHADOW = {
  prompt: "Say this out loud:",
  start: "Say it",
  stop: "Done",
  again: "Say it again",
  waiting: "Listening back…",
  improved: "Clearer that time.",
  unavailable: "Scoring is off today. The line is still worth saying.",
  trouble: "That didn’t come through. Have another go whenever you like.",
  /**
   * The listen control. **It is the appeal, not a convenience.**
   *
   * The surface marks a word amber and cannot demonstrate the difference: on
   * 2026-09-03 `model` scored 44, was marked correctly, and the operator
   * concluded he had said it right — **because nothing on screen could show
   * him otherwise.** A verdict with no appeal is what §4 guards against even
   * with no banned word present.
   *
   * **Never *hear it done properly* or *the correct version*.** The target is
   * a reference, not a verdict on what the learner produced, and naming it
   * *correct* makes every attempt an implicit failure to match it.
   */
  listen: "Hear it",
  /**
   * **#366: the app could not hear the utterance at all** — Azure matched
   * nothing of the reference (`CompletenessScore` 0).
   *
   * **THE SUBJECT OF THE SENTENCE IS THE APP, DELIBERATELY.** Every natural
   * phrasing that puts it on the learner — *speak up*, *say it louder*, *try
   * again?* — makes a microphone problem read as a mouth problem, on the
   * surface most likely in this product to read as judgement. `BANNED` would
   * not catch any of them, which is why the shape is asserted in
   * `recorder.test.tsx` and not left to the scan.
   *
   * **It is NOT the same string as `trouble`.** That one is a request that did
   * not complete; this one completed and heard nothing, and the learner should
   * know which happened.
   */
  notHeard: "I didn’t catch that one. The mic may not have picked it up.",
  listening: "Listening…",
} as const;

/**
 * W13b — the conversation surface. PRD §8.6.
 *
 * **NOT ONE STRING HERE CONTAINS A NUMERAL, AND THAT IS ASSERTED BY NAME** in
 * `tests/test_web_shell.py::test_the_conversation_cap_copy_carries_no_numeral`.
 * #348 is why the regex alone is not enough: *"0 of 5 active days."* shipped to
 * a learner weekly for a year and contains no banned word. A remaining-turns
 * figure is a backlog running backwards; a tally of turns used is a score on
 * someone for talking.
 *
 * **THE CAP LINE NAMES TOMORROW, NOT A LIMIT.** The conversation closes the way
 * the End button does — corrections and all — so the learner's last message has
 * already been answered and nothing stops mid-exchange.
 */
export const CONVERSATION = {
  eyebrow: "Talk",
  title: "Have a conversation",
  /** The low-emphasis home entry point. **Never the primary call-to-action**
   * and never a count (#160: a counter that accumulates while the learner is
   * away is a backlog presented). */
  homeLink: "Or just talk for a bit",
  start: "Start talking",
  send: "Send",
  /** One swap, then the topic stands. §2c — v2's three-button picker is a
   * browsable list and is deliberately not ported. */
  another: "Something else",
  end: "That’s enough for now",
  thinking: "…",
  /** **NO SPINNER APOLOGISES FOR THE WAIT.** 2–4 seconds is what conversation
   * costs and it is not a defect (§0, cost 3). */
  recording: "Listening…",
  speak: "Hold to speak",
  /** **W13b/4 adopts the design's wording.** The shipped line was
   * *"That's the conversation for today. There's another one tomorrow."*,
   * quoted rather than deleted (#82's shape). The design's version names the
   * ACTIVITY rather than the object and promises a new topic rather than a
   * repeat, which is the more accurate description of what tomorrow holds --
   * `_topic_sources` reseeds. **Still no numeral**, so it stays under
   * `test_the_conversation_cap_copy_carries_no_numeral`. */
  capReached: "That’s the talking done for today. There’ll be a new topic tomorrow.",
  closing: "Here’s what stood out.",
  trouble: "That didn’t go through. The conversation is still here.",
  /** §C1. Three suggestions, offered once. **No count, no badge, no history of
   * skipped topics** — those would make it a backlog, which is work that
   * accumulates while you are away. These accumulate nothing. */
  pick: "What do you feel like talking about?",
  reshuffle: "Show me others",
  save: "Keep",
  saved: "Kept",
  /** **W13b/5 MOVED THE ENTRY POINT OUT OF BLOCK 4 AND ONTO THE CLOSING
   * BLOCK, AND PROMOTED IT FROM AN UNDERLINED PHRASE TO A FILLED BUTTON.**
   * Operator ruling 2026-09-07, on the design's `1i`.
   *
   * The old string is quoted rather than deleted (#82's shape):
   * *"Or have a conversation"*, rendered as
   * `text-sm text-muted-foreground underline` inside block 4.
   *
   * **HOW THIS STAYS INSIDE #160 AND INSIDE W13b/3 §A's *never the primary
   * emphasis*, WHICH IT WOULD OTHERWISE BREAK:** the button is not block 4's
   * call-to-action and does not compete with the day's task — **block 4's
   * primary action is still *Write it***. This sits on the CLOSING block,
   * after every block's own action, which is the design's own placement (its
   * card is headed *Today · to close*). **And #160's actual rule is untouched:
   * no count, no badge, no dot, no days-since.** A learner who never presses it
   * is told nothing about not having pressed it. */
  /**
   * **`entryTitle` IS GONE AND IT WAS NEVER RENDERED.** W13b/5 added
   * *"That’s the session. The rest of the English is up to you."* here and then
   * rendered only the action and the caption — **dead copy from the day it was
   * written**, found by comparing the shipped card against the design's `1i`.
   * The sentence is real and it is the design's; it now lives in
   * `BLOCKS.close.title`, which is the slot that actually paints it. **One
   * string, one home** — keeping both would have been the same sentence in two
   * places, and the one nobody rendered would have been the one edited.
   */
  entryAction: "Talk with the app",
  /** Sets the expectation before the tap. **Not a target and not a minimum** —
   * nothing measures it and nothing reports on it afterwards. */
  entryCaption: "Ten minutes, in English, about anything.",
  /** §B. The in-progress state. **The wait is the product** — this says the
   * app is working and never how long it will take. No spinner, no bar. */
  working: "Typing…",
  composerLabel: "Message",
  placeholder: "Say something…",
  micStart: "Speak",
  micStop: "Stop",
  micTrouble: "The mic didn’t start. Typing works.",
  you: "You",
  app: "App",

  // ── W13b/4, the close-out ────────────────────────────────────────────────
  //
  // **EVERY ONE OF THESE LIVES IN THIS BLOCK ON PURPOSE.** `close-out.tsx`
  // declares no copy of its own, because `test_the_conversation_copy_scan_
  // covers_every_surface` fails the moment a conversation surface holds a copy
  // block the numeral scan does not read -- #348's hole, one file to the left.

  /** The eyebrow over the close-out. Names the thing, not the learner. */
  closeEyebrow: "The conversation",
  /** Heading over the corrections. **The design's phrase, and it is the
   * point:** *worth a look* describes the sentence; *mistakes* would describe
   * the person. Never red, never a cross (CLAUDE.md §4). */
  correctionsHeading: "Worth a look",
  /** **THE LABEL SAID *"Words you asked about"* AND HE ASKED ABOUT NOTHING.**
   * Quoted rather than deleted (#82's shape). It came from the design, where
   * it describes an interaction this app does not have: the words are
   * DETECTED from his own typed turns against his ledger, never requested.
   * **A heading that tells the learner what he did is wrong about him**, and
   * being wrong about the learner is the thing this copy exists to avoid.
   *
   * **AND ITS REPLACEMENT WAS ALREADY IN THIS FILE, UNUSED.** `wordsHeading:
   * "Worth keeping"` had been dead copy since W13b/4 moved the close-out into
   * its own component — the THIRD string in three slices declared here and
   * rendered by nothing (`entryTitle` was the second). So this is a deletion,
   * not an addition: the accurate string survives and the inaccurate one goes.
   *
   * *"Worth keeping"* claims nothing about him. It does not say he asked, does
   * not say he did not know, and reads as an offer rather than a gap. */
  wordsHeading: "Worth keeping",
  /** The close-out's terminal action. Leaves for home; **never "finish" or
   * "complete"**, which imply a task with a state. */
  backToToday: "Back to today",
  /** Shown when the model returned nothing worth showing. **The close-out is
   * still a close-out** -- an empty one says so plainly rather than rendering
   * three empty headings. No apology and no blame. */
  closeNothing: "Nothing to add this time. That was a good conversation.",

  // ── W15, the two rungs on the loop: answer and retell ────────────────────
  //
  // **Same scans as every string above** (numeral, banned phrase), because they
  // live in this block. **No count, no *done today*, no *not yet*** (#160): a
  // rung answered this morning is offered again this afternoon, like a talk.

  /** Over the two rung cards on the opening screen. An offer, not a task. */
  rungsHeading: "Or try one of these",
  /** The answer card's eyebrow. The unit's task follows it, verbatim. */
  answerEyebrow: "This week’s question",
  /** The retell card's eyebrow. The video's title follows it. */
  retellEyebrow: "Today’s video",
  /** The retell card's own line. */
  retellCard: "Tell it back in your own words",
  /** The screen eyebrow while a rung is open, where `/talk` says *Talk*. */
  answerTitle: "Answer",
  retellTitle: "Retell",
  /** The composer's placeholder on a rung. */
  answerPlaceholder: "Say it your way…",
  retellPlaceholder: "What happened?",
  /** A rung's single wait is the close-out call: it is READING, not typing. */
  reading: "Reading it…",
  /** The close-out's eyebrow for each rung, where a talk says *The conversation*. */
  answerCloseEyebrow: "Your answer",
  retellCloseEyebrow: "Your retelling",
  /** A rung's close-out line under the heading (a talk's is `closing`). */
  rungClosing: "Here’s what I noticed.",
  /** A rung with nothing to show. `closeNothing` says *conversation*; a rung
   * was not one. No apology and no blame, like it. */
  rungNothing: "Nothing to add this time. That came across well.",
  /** **What the retelling got across — the video's own points, never a count
   * or a percentage of them** (the run prompt: *shown as what was covered*). */
  coveredHeading: "What you got across",
  /** The video's other points. **Content, not a shortfall**: the heading names
   * the video, never the learner, and nothing says *missed*. */
  alsoHeading: "Also in the video",
  /** A rung answered in another language. The screen says so and corrects
   * nothing. No verdict, no *wrong language*. */
  notEnglish: "That looks like it’s in another language. Try it in English next time and I’ll go through it.",
} as const;

/**
 * W16a — the writing screen, design `1d`–`1q`. **Copy in every frame is final and
 * scanned**: no score, no mark, no percentage, no numeral in any count, no
 * backlog. `tests/test_web_shell.py` holds this block to the no-numeral rule.
 *
 * **"Reading it", not the design's *"Foundgrant is reading it"*** — CLAUDE.md
 * §1a: a mock's brand name is not this product's name, and the wordmark on
 * screen is *Everyday English*. The second application of that rule; the
 * close-out import made it first.
 *
 * **The design's `1m` fixed opening line (*"This reads well the way it is. I
 * haven't changed anything."*) is NOT here.** Ruling 2 superseded it with the
 * generated, gated `did_well`, which is absent when there is nothing to say.
 */
export const WRITE = {
  eyebrow: "Write",
  leave: "Leave this",
  fieldLabel: "Your writing",
  /** W16b — `1e`. */
  paragraph: {
    eyebrow: "Write · this week",
    promptLabel: "The prompt",
    /** **The design's *"I'll correct all of it"* is not taken**: Q-D caps the
     * paragraph at eight corrections, so *all of it* would be false on a long
     * paragraph. */
    subline: "One paragraph. I’ll go through it and say something about the way it’s built.",
    placeholder: "Write your paragraph here.",
    /** `1g`: the prompt card collapses to this strip and taps to reopen. */
    strip: "The prompt",
  },
  journal: {
    title: "What happened today?",
    /** Stated once, in words, and gone once the head collapses (`1d`, `1g`). */
    length: "Five to ten sentences is about right.",
    placeholder: "Start anywhere — the dentist, the bus, dinner.",
    strip: "What happened today",
  },
  submit: "Read it over",
  /** `1h`. Above the button, never a toast; the length line is suppressed
   * beside it — restating the target next to a refusal turns guidance into a
   * mark. */
  short: "There’s not much here yet. Give me a few more sentences and I’ll read it properly.",
  /** `1i`. No spinner, no bar, no elapsed time. */
  reading: "Reading it",
  whatYouWrote: "What you wrote",
  worthALook: "Worth a look",
  /** `1k` only. Written for a pair; `1l` removes it — the first silent branch. */
  pickedTwo: "I’ve picked the two that matter most.",
  back: "Back to today",
  /** W16b — `1n`. Named in words, never dimensions; the prose is the model's. */
  structureHeading: "How it’s put together",
  /** W16b — `1o`. The intro names the number in words so one offer reads naturally. */
  keepHeading: "Worth keeping",
  keepIntroTwo: "Two phrases from the corrections. Saving one puts it in your deck with the sentence it came from.",
  keepIntroOne: "One phrase from the corrections. Saving it puts it in your deck with the sentence it came from.",
  keep: "Keep",
  inDeck: "In your deck",
  /** `1q` failure. No error code, no apology, does not blame the connection. */
  /** Named `trouble`, not `failed`: the no-guilt scan reads source, and `/talk`
   * already calls this state `trouble`. */
  trouble: "That didn’t work. Nothing’s lost — your writing is still here.",
  retry: "Try again",
  /** No design frame draws this state (D10); the W3 string is kept. */
  notEnglish: "That looks like it’s in another language — write it in English and I’ll take a look.",
  /** `1q` unavailable. `/talk`'s sentence shape exactly: no count, no reset
   * time, no come back later. */
  ceiling: "That’s the writing done for today. There’ll be a new one tomorrow.",
} as const;

/**
 * W19 — the progress screen. §1a is suspended for this run (ruling 0.3), so
 * these take the conventions `/talk` and `/write` shipped; the operator reviews
 * them from `e2e/screenshots/W19/` at the launch pass.
 *
 * **No sentence here counts what was not done.** No *missed*, no *left*, no
 * *behind*, no *keep it up*. A number is drawn only when it is above zero, and
 * each carries one line saying what it counts — the reader should never have
 * to guess whether a number is a verdict.
 */
export const PROGRESS = {
  eyebrow: "Progress",
  title: "What has actually changed.",
  subline: "Words you know, the work you’ve put in, and the units you’ve passed.",
  words: {
    eyebrow: "Words you know",
    /** The floor is never counted (W4), so the number starts small and is real. */
    about: "Words you’ve shown you know — in reviews, taps and practice. The starting list isn’t counted.",
    /** One point, no line yet. */
    firstPoint: "Each visit here adds a point, and the line starts from the second.",
    chartLabel: "Words you know over time",
  },
  xp: {
    eyebrow: "XP",
    about: "Speaking earns the most, then writing, then typing, then tapping.",
  },
  streak: {
    eyebrow: "Streak",
    days: (n: number) => (n === 1 ? "day of practice" : "days of practice"),
    about: "A day off doesn’t break it.",
    freezes: (n: number) =>
      n === 1
        ? "One freeze this month covers a day you can’t make it."
        : `${n === 2 ? "Two" : n} freezes this month cover days you can’t make it.`,
  },
  units: {
    eyebrow: "Units",
    passed: (n: number) => (n === 1 ? "unit passed" : "units passed"),
  },
  /** Week one is both learners' state: one line, no table of zeros. */
  empty: "Nothing to show yet. This fills in as you practise.",
  /**
   * **W18 turned this on (2026-09-25).** The line it replaces, kept rather than
   * deleted (#82's shape): *"Your skill profile and level history arrive with
   * the placement test."* — written while W18 was blocked; it would now be
   * untrue. What replaces it is the level card below, and before a first
   * sitting a link to take one.
   */
  level: {
    eyebrow: "Level",
    /** Before a first sitting. An offer, not a task. */
    offer: "A short check finds the level to start from. Nothing in it is marked.",
    offerLink: "Find where to start",
    /** The band, named, under the letters. */
    lead: "Where to start",
    history: "After each check",
    again: "Check where you are now",
  },
  trouble: "That didn’t load. Nothing’s lost.",
  retry: "Try again",
} as const;

/**
 * W18 — the placement check. PRD §6.
 *
 * **A placement is never a score.** Nothing here counts right or wrong answers,
 * says how many items are left (*12 of 60* is a backlog running backwards), or
 * shows a percentage. The result is a band — *where to start* — and a radar of
 * bands. **Raises are announced; a check that reads the same or lower says
 * nothing about it** (CLAUDE.md §4) — the screen shows the high-water band the
 * wire sends.
 *
 * **There are no wrong-answer words anywhere in a sitting**: no feedback is
 * shown per item at all. A placement item is a measurement, not practice, and
 * a verdict after each one would turn twelve minutes into a running tally.
 */
export const PLACEMENT = {
  eyebrow: "Where to start",
  title: "Find the level to start from.",
  subline: "About twelve minutes, in four short parts. Nothing is marked — it only finds where to begin.",
  start: "Start",
  resume: "Carry on",
  /** The operator has not built the bank yet. Plain, no date promised. */
  notReady: "The check isn’t ready yet. It will appear here when it is.",
  nextFrom: (date: string) => `The next check opens on ${date}.`,
  parts: {
    vocabulary: "Words",
    grammar: "Grammar",
    listening: "Listening",
    speaking: "Speaking",
  },
  vocabulary: {
    ask: "Do you know this word?",
    /** Said once, up front: the yes/no test only works if nobody is surprised. */
    about: "Some of these aren’t real English words. For those, “no” is the answer.",
    yes: "I know it",
    no: "Not a word I know",
  },
  grammar: {
    about: "Answer the way you would in conversation. The questions change as you go.",
  },
  listening: {
    about: "Play the sentence, then type the missing word. You can play it again.",
  },
  speaking: {
    about: "Answer out loud for about a minute and a half. Any answer is a good answer.",
    typedAbout: "Type your answer — a few sentences is plenty.",
    record: "Record",
    stop: "Stop",
    typeInstead: "Type it instead",
    send: "Send",
    placeholder: "Your answer",
    skip: "Skip this part",
    listening: "Listening…",
    unheard: "That didn’t come through. Try once more, or type it instead.",
  },
  finishing: "Working out where to start…",
  result: {
    eyebrow: "Where to start",
    raised: (from: string) => `Up from ${from}.`,
    vocab: (n: number) =>
      `You recognise about ${n.toLocaleString("en-GB")} of the most common English words.`,
    radar: "Your level in each skill",
    back: "Back to Progress",
  },
  skills: {
    vocabulary: "Words",
    grammar: "Grammar",
    listening: "Listening",
    speaking: "Speaking",
  },
  /** Under the letters, so a band reads as a place and not a grade. */
  bandName: {
    A2: "Elementary",
    B1: "Intermediate",
    B2: "Upper intermediate",
    C1: "Advanced",
  },
  unmeasured: "not measured",
  trouble: "That didn’t load. Nothing’s lost.",
  retry: "Try again",
} as const;

/**
 * W20 — the reminder control in the settings menu. PRD §10.
 *
 * **No numeral and no count, anywhere in it.** The server's ceiling, the nudge
 * ladder's hours and the last-nudge hour are real numbers, and none of them is
 * the learner's business in figures: what they need to know is that it is
 * short, that it is at their practice time, that it stops once they've
 * practised, and that it never arrives at night. `about` says exactly that and
 * no more — every clause is a rule `core.services.push` enforces.
 *
 * **Nothing here asks, pleads or warns.** No "don't forget", no "stay on
 * track": turning reminders off is as ordinary as turning them on.
 */
export const REMINDERS = {
  eyebrow: "Reminders",
  toggle: "Daily reminder",
  about:
    "A reminder at your usual practice time, and a gentle nudge later on — never late at night. Nothing once you’ve practised that day.",
  /** iOS delivers web push only to an app opened from the Home Screen. */
  install: "To get a daily reminder, add this app to your Home Screen, then open it from there.",
  /** Permission refused in the browser. Where to change it, and no verdict. */
  blocked:
    "Notifications for this app are switched off in this browser’s settings. Switch them on there to get a daily reminder.",
  /** The permission prompt was closed without an answer. (**Not `dismissed`**:
   * it contains "missed", and `test_the_progress_screen_names_no_absence`
   * scans this file from `PROGRESS` to the end, so it caught this key.) */
  closed: "Nothing changed. Turn it on whenever you like.",
  trouble: "That didn’t go through. Try again in a moment.",
  working: "Working on it",
} as const;

/**
 * W23 — the operator's panel (`/admin`), the bot's `/admin` on the web. **Read
 * by the operator alone**: the route answers 404 to anybody else. It shows
 * activity and never content (CLAUDE.md §5) — no sentence, no correction, no
 * topic. The approve/decline/revoke/pause actions stay where they are until
 * W22, and `requests` says so **without naming the other channel**:
 * `test_no_telegram_surface_in_the_web_app` (PRODUCT-PRINCIPLES §1) refused the
 * first draft, which did.
 */
export const ADMIN = {
  eyebrow: "Operator",
  title: "Who’s practising.",
  subline: "Activity only — never what anyone wrote or said.",
  requestsNone: "No access requests waiting.",
  requests: (n: number) =>
    `Access ${n === 1 ? "request" : "requests"} waiting: ${n}. This panel only reads — approve or decline ${n === 1 ? "it" : "them"} where you always have.`,
  empty: "Nobody has joined yet.",
  level: "Level",
  streak: "Streak",
  active: (lookback: number) => `Active, last ${lookback} days`,
  last: "Last practised",
  never: "Not yet",
  paused: "Paused",
  revoked: "Access revoked",
  notFound: "There’s nothing here.",
  trouble: "That didn’t load. Try again in a moment.",
  retry: "Try again",
} as const;
