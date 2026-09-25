-- ============================================================================
-- 031 — W20. Web Push: where a learner's browser can be reached, and what the
-- worker decided about each push on each local day.
--
-- **NUMBER READ FREE BEFORE IT WAS TAKEN:** `migrations/` ran 001–030 with no
-- gaps and the development database reported `schema_version` 30. **031 IS
-- WHAT THE AUTHORITATIVE TABLE RESERVED FOR W18**, and W18 is unwritten
-- (blocked on its item bank), so **W18 SHIFTS 031 → 032 IN BOTH HALVES OF
-- `docs/TASKS-v3-web.md` IN THIS SAME COMMIT.** #185's rule: take the next
-- number when the file is written.
--
-- PRODUCT-PRINCIPLES §2: both tables key on `users(id)` and cascade. Neither
-- carries a Telegram id, and a learner with no Telegram account can subscribe.
--
-- **NO LEARNER TEXT IN EITHER TABLE** (CLAUDE.md §5). A subscription is three
-- strings the browser minted; a decision is a date, a kind and an outcome. The
-- message a push carried is `core/copy.py`'s and is not stored.
-- ============================================================================

-- One row per browser that said yes. A learner with a phone and a laptop has
-- two. **The endpoint is a capability URL** — with the two keys, anyone holding
-- it can put a notification on that phone — so it is never logged whole
-- (`core.push.endpoint_host`) and never leaves this table except to the push
-- service it names.
CREATE TABLE push_subscriptions (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- UNIQUE, not (user_id, endpoint): one browser is one endpoint, and a shared
    -- device that signs in as the other learner MOVES the row to them rather
    -- than leaving it reachable by both (`core.services.push.save_subscription`).
    endpoint    TEXT        NOT NULL UNIQUE CHECK (endpoint LIKE 'https://%'),

    -- `PushSubscription.toJSON().keys`, base64url, exactly as the browser gave
    -- them: the P-256 point (65 bytes → 87 characters) and the 16-byte secret
    -- (→ 22). Lengths checked here so a malformed body fails at the route, not
    -- at 08:00 inside the worker.
    p256dh      TEXT        NOT NULL CHECK (length(p256dh) = 87),
    auth        TEXT        NOT NULL CHECK (length(auth) = 22),

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX push_subscriptions_user_idx ON push_subscriptions (user_id);

COMMENT ON TABLE push_subscriptions IS
    'W20: one row per browser a learner allowed to receive reminders. Deleted '
    'when the push service answers 404/410, or when the learner turns reminders '
    'off. The endpoint is a capability URL: never logged whole.';

-- One row per learner, per LOCAL day, per push the ladder could send. **Written
-- BEFORE the send and inside the same transaction as the ceiling reservation**,
-- so a crash between the two can lose a reminder but never send one twice —
-- a reminder sent twice is worse than one not sent.
CREATE TABLE push_deliveries (
    user_id     BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_date  DATE        NOT NULL,

    -- v2's ladder, ported: the reminder at `users.morning_time`, then two
    -- nudges at +3h and +6h (`core.services.motivation`'s NUDGE_FIRST_HOURS
    -- and NUDGE_SECOND_HOURS).
    kind        TEXT        NOT NULL CHECK (kind IN ('reminder', 'nudge_1', 'nudge_2')),

    -- What happened, and — for everything but `sent` — why nothing did:
    --   sending          reserved and in flight (a row left here is a crash)
    --   sent             at least one of the learner's browsers accepted it
    --   failed           every browser's push service refused or timed out
    --   practised        the learner already practised today: never nudged
    --   ceiling          the day's 3 messages, bot and push together, were spent
    --   bot_ladder       the Telegram bot's own nudge ladder owns today
    --   no_subscription  reachable on Telegram, but no browser subscribed
    --   no_channel       no browser AND no Telegram: #95's loud case
    --   late             a nudge that fell due after 21:00 local, dropped
    outcome     TEXT        NOT NULL CHECK (outcome IN (
                    'sending', 'sent', 'failed', 'practised', 'ceiling',
                    'bot_ladder', 'no_subscription', 'no_channel', 'late')),

    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, local_date, kind)
);

COMMENT ON TABLE push_deliveries IS
    'W20: the worker''s decision about each push, one row per learner per local '
    'day per kind, written before the send. No text. The message is core/copy.py''s.';
