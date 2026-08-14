-- S26: allow errors.source = 'conversation' for talk close-out journal writes.
ALTER TABLE errors DROP CONSTRAINT IF EXISTS errors_source_check;
ALTER TABLE errors ADD CONSTRAINT errors_source_check
    CHECK (source IN (
        'quiz', 'voice', 'text', 'reading', 'diary', 'capture', 'conversation'
    ));
