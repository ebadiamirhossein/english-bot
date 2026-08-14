-- S25: first-touch presentation gate (NULL = not yet presented)
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS presented_at TIMESTAMPTZ;

-- One-off backfill: user-sourced / non-slang → presented; slang stays NULL.
-- Pre-flight on Hetzner must confirm fan-out chunks are source='slang' only.
-- Future shared sources must set presented_at NULL at insert — do not re-derive.
UPDATE chunks
   SET presented_at = created_at
 WHERE source <> 'slang' OR source IS NULL;
