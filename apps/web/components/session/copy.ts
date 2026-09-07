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
    empty: "No video today. There\u2019ll be one on Monday, Wednesday and Friday.",
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
    eyebrow: "Output",
    title: "Say something of your own.",
    empty: "No task is set up yet.",
    action: "Write it",
  },
  close: {
    eyebrow: "Close",
    title: "That’s today.",
  },
} as const;

/** What the runner says when every block is behind you. */
export const SESSION_DONE = {
  title: "Done for today.",
  body: "Same time tomorrow — and tomorrow is its own session, not this one plus more.",
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
    unavailable: "Could not add that just now.",
  },
  /** **#335.** The transcript was purged at thirty days and the video is still
   * assigned and still watchable. It says what IS there, does not apologise,
   * does not blame, and does not use the word "expired" — nothing the learner
   * did caused this and nothing they can do fixes it. */
  noTranscript:
    "The follow-along text isn’t available for this one. The video still plays.",
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
  /** §C2. The words the learner did not know, offered to the deck. **Never a
   * count and never framed as a gap** — "words you didn't know" is a verdict;
   * "worth keeping" is an offer. */
  wordsHeading: "Worth keeping",
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
  entryTitle: "That’s the session. The rest of the English is up to you.",
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
  /** Heading over the words. **An offer, not a gap** -- "words you didn't
   * know" is a verdict. */
  closeWordsHeading: "Words you asked about",
  /** The close-out's terminal action. Leaves for home; **never "finish" or
   * "complete"**, which imply a task with a state. */
  backToToday: "Back to today",
  /** Shown when the model returned nothing worth showing. **The close-out is
   * still a close-out** -- an empty one says so plainly rather than rendering
   * three empty headings. No apology and no blame. */
  closeNothing: "Nothing to add this time. That was a good conversation.",
} as const;
