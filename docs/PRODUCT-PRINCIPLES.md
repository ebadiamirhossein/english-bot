# PRODUCT-PRINCIPLES.md

Standing product decisions. These are not slice decisions and are not re-argued
per slice. Anything that contradicts one of these is a bug in the plan, not a
trade-off to be weighed.

---

## 1. The product is a web app. Telegram is legacy.

The Telegram bot was v2. It exists today only because it is where the two
current learners' daily practice still lives, and it is deleted at **W22** with
its handlers and its ~209 tests.

Consequences that hold in every slice from now on:

- **No new feature is designed for Telegram.** New surfaces are web. If a slice
  proposes a bot command, that is a mistake unless the slice is explicitly about
  keeping the legacy bot alive until W22.
- **No new SQL enters `apps/bot`** (known issue #58).
- **Telegram desk-checks are not blocking.** They were deprioritised on
  2026-08-24. They remain listed because the paths are live for two learners
  until W20–W22, not because they gate anything.
- Do not propose Telegram as the delivery channel for anything new — including
  alerts, notifications, or fallbacks — without saying explicitly that it is a
  stopgap that dies at W22.

## 2. Identity must not depend on Telegram.

A user must be able to sign up, sign in, learn, and pay **without a Telegram
account**. This is a product requirement, not a preference.

Today the schema does not meet it: `users.telegram_user_id` is the primary
identity and every user-keyed table references it, including `user_lexemes`
added at W4. Web auth (W2) was hung onto that same row rather than given an
identity of its own.

- Every slice that adds a user-keyed table **enlarges the eventual migration**
  and must say so in its plan.
- No slice may add a *new* dependency on a Telegram id beyond the FK pattern
  that already exists.
- The fix is a scheduled slice, not something to improvise inside another one.

## 3. Multi-tenancy is deferred, not abandoned.

The system will have more than two users, and may become a paid or enterprise
product. Nothing is to be built *for* imagined users — but choices that are
cheap now and expensive later are called out when they are made:

- data that scales per-user × per-lemma (or similar products) is flagged if it
  materialises rows that could be computed;
- global configuration that would need to be per-user is flagged when it is
  introduced;
- **licensing is checked before any third-party data enters the repo**, and the
  answer must hold for a commercial product, not only for a private one
  (see `data/LICENCES.md`).

## 4. Implementation happens in Claude Code.

Not Cursor. Prompts are written by the planning assistant, run in Claude Code,
and delivered as downloadable `.md` files.

## 5. The record is the product's memory.

`BUILD_PROGRESS.md` is the single source of truth for what happened. Only the
human marks a slice ✅. Every prompt ends with an explicit update block, and no
unrun check is ever carried forward silently.

An untracked problem is a forgotten problem: anything found and not filed does
not exist. "It belongs to a later slice" is a reason to file it with a target,
never a reason not to file it.
