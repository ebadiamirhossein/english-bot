# CC-W4b — Identity without Telegram

Archived per CLAUDE.md: `prompts/` records the prompt each slice was given, which
documents **intent**, not state. It is never consulted for build status —
`BUILD_PROGRESS.md` is the only record of what is built and verified.

**Note on continuity:** this archive lapsed after W2. W3, W4 and W4a were run
without their prompts being committed here. W4b resumes the practice; the three
missing files are not reconstructed, because a reconstruction from memory would
be a worse record than an acknowledged gap.

W4b ran in three messages.

---

## 1. The PLAN prompt

Run in PLAN MODE, no code. The slice exists because `PRODUCT-PRINCIPLES.md` §2
requires a learner to sign up, learn and pay without a Telegram account, and
`users.telegram_user_id BIGINT PRIMARY KEY` makes that impossible — known issue
#92. It gets more expensive every slice: W5, W7 and W8 each add user-keyed
tables. Today the database holds 3 users.

The plan was required to:

- **enumerate the actual surface from the repo, not from any document** — every
  foreign key to `users(telegram_user_id)` with its nullability and `ON DELETE`,
  every view over `users` (#48's `SELECT u.*` freeze), every code site treating a
  Telegram id as identity (grouped and counted, not listed), what `tenant_id` and
  `plan` actually do, and how W2's enrolment binds a passkey. **Report anything
  that contradicts the prompt. The repo wins.**
- **adopt or reject the target shape with reasons** — surrogate `users.id`,
  nullable unique `telegram_user_id`, children repointed — and **explicitly
  reject minting synthetic Telegram ids**, so nobody proposes it later. Say what
  `user_id` means in a service signature afterwards, and **how a second
  translation path is prevented, not just discouraged**.
- **pick a migration number with reasons**, reading `db.py`'s runner before
  asserting anything about its behaviour, and distinguish renumbering an *applied*
  migration (#49's failure) from renumbering unwritten rows in a planning table.
- **specify the migration**: one transaction; row counts asserted before and
  after; `approved_onboarded_users` recreated in the same file; deferred or
  dropped-and-recreated constraints, said which and why; and **a written
  rollback** — "restore from backup" acceptable only with its cost stated.
  Rehearsal against a real restore is mandatory and is a **human-run** command.
- **size the code change**, decide the scope of web sign-up explicitly and prefer
  the smaller option, and keep `#59` the only boundary exemption.

Out of scope: multi-tenancy, payments, deleting the bot (W22), W5, any new
learner-facing feature.

Nine acceptance criteria, of which the load-bearing ones: every row survives
(per-table counts asserted); both journals intact **and attached to the right
learner, spot-checked by content**; a user creatable with `telegram_user_id NULL`
holding a passkey, a session and ledger rows; the view returning the same rows;
**every bot path re-asserted through Application-level dispatch with a correction
spy** — free correction has been silently killed three times; no orphans; the
migration rehearsed against a restored copy of production; suite green, baseline
1068.

---

## 2. The send-back — four numbered changes, item 1 blocking

1. **Blocking.** `access_requests.telegram_user_id` is the table's PRIMARY KEY, so
   `ALTER COLUMN … DROP NOT NULL` on it **errors** — the migration could not
   execute as planned. It needs its own ordered sub-sequence, with the key moved
   off the column *before* the NOT NULL is dropped. Also: confirm nothing points
   *at* `access_requests` explicitly rather than by silence; carry the
   `is_approved` signature change into the code-change table with its site count;
   and correct the claim that the migration drops one primary key — it drops two.
2. **The new foreign key on `shared_content.created_by` is scope creep with a
   stop-the-world failure mode.** Rewriting the values is necessary; adding the
   constraint is a separate act that could abort the whole identity migration over
   a column that is not identity-critical. Split it, with a pre-flight query and
   **both outcomes named in advance**.
3. **Add an acceptance criterion for session and passkey survival.** The reasoning
   says both survive; that is an "almost certainly", and an "almost certainly"
   here costs an evening of re-enrolling passkeys on two phones.
4. **Say what happens to in-flight requests during the migration**, and recommend
   whether to stop the services first.

---

## 3. The approval — two binding conditions

Approved as amended, with three resolutions singled out as having gone further
than the send-back asked and kept: the `ON CONFLICT (telegram_user_id)` finding
(without the re-added UNIQUE, two writes would have failed **at runtime, after a
green migration** — the worst failure shape available); the `is_approved` split;
and the lock-**queue** hazard, sharper than the lock itself.

- **A.** The rollback must cover **both** primary-key changes, with the guard
  extended to refuse on a web-originated `access_requests` row too. "A rollback
  that restores one key and not the other leaves the database in a state neither
  schema describes, which is worse than not rolling back at all." If any part of
  the reverse cannot be expressed exactly, say so and name restore-from-dump for
  that part rather than shipping a partial script that looks complete.
- **B.** File the silent-delivery gap as a known issue (medium, W4b → W20): a
  web-only learner receives nothing and no error is raised — the shape of #44 and
  of the S26b empty-interests incident. **W20 must alert rather than skip
  quietly**, and the issue must say so, so W20 inherits the requirement instead of
  rediscovering it. Do not build the alert now; filing it is the whole task.

Plus the standing constraints: rehearsal before production; every server step
written as an explicit command for the human; full suite green or report and
stop; W4b goes to 🟡 and only the human marks it; **#92 closes only when the
migration is live on production and both learners are verified intact**; no
production entrypoint and no live token (CLAUDE.md §5b); the stop/start touches
`english-bot` and `english-api` only, never `fonderis-worker`; nothing may
`DELETE` from a v2 table; no new SQL in `apps/bot`; `#59` stays the only boundary
exemption and the identity rule is a **second parse test, not a second
exemption**.
