-- S7a: spaced review fields on chunks (NULL next_review = never reviewed = due)
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS next_review DATE,
    ADD COLUMN IF NOT EXISTS times_right INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS times_wrong INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS streak_right INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_chunks_due ON chunks (user_id, next_review);
