-- S4: streak rollover idempotency + monthly freeze reset + freeze notice flag
ALTER TABLE streaks
    ADD COLUMN last_evaluated_date DATE,
    ADD COLUMN freeze_reset_on DATE,
    ADD COLUMN pending_freeze_notice BOOLEAN NOT NULL DEFAULT FALSE;
