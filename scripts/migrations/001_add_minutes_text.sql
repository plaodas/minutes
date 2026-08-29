-- Migration: add minutes_text column and full-text indexes to tasks
-- Run this against your Postgres database (via psql or the helper script).

BEGIN;

-- add plain text column for storing minutes body
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS minutes_text TEXT;

-- create pg_trgm extension if available for efficient substring search (may require superuser)
DO $$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
       BEGIN
           CREATE EXTENSION pg_trgm;
       EXCEPTION WHEN OTHERS THEN
           -- ignore if not permitted
           RAISE NOTICE 'pg_trgm extension creation skipped or not permitted';
       END;
   END IF;
END$$;

-- GIN index for trigram substring search (useful for LIKE / similarity searches)
CREATE INDEX IF NOT EXISTS idx_tasks_minutes_text_trgm ON tasks USING GIN (minutes_text gin_trgm_ops);

-- Full-text search index using to_tsvector (language: simple by default)
CREATE INDEX IF NOT EXISTS idx_tasks_minutes_text_tsv ON tasks USING GIN (to_tsvector('simple', coalesce(minutes_text, '')));

COMMIT;
