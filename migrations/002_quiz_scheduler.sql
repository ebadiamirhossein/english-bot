-- S3: quiz payload persistence + bot-initiated message ceiling
ALTER TABLE sessions ADD COLUMN payload JSONB;

CREATE TABLE bot_message_counts (
    user_id     BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    local_date  DATE NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
    PRIMARY KEY (user_id, local_date)
);
