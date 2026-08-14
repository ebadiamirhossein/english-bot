-- S24: shared content ledger + per-user delivery outcomes (fan-out)
CREATE TABLE shared_content (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN ('chunk', 'book_unit')),
    content_key     TEXT NOT NULL,
    payload         JSONB NOT NULL,
    source          TEXT,
    created_by      BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kind, content_key)
);

CREATE TABLE shared_content_deliveries (
    shared_content_id BIGINT NOT NULL REFERENCES shared_content(id) ON DELETE CASCADE,
    user_id           BIGINT NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    outcome           TEXT NOT NULL CHECK (outcome IN ('delivered', 'skipped_owned')),
    delivered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (shared_content_id, user_id)
);

CREATE INDEX idx_shared_content_deliveries_user
    ON shared_content_deliveries (user_id);
