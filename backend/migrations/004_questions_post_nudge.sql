-- 004_questions_post_nudge.sql
-- Migration 3 (Part 5D):
--   ADD post_nudge boolean to questions
--   Ensure composite_score is numeric(4,2)

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS post_nudge BOOLEAN DEFAULT false;

-- Ensure composite_score precision (safe no-op if already correct type)
ALTER TABLE questions
    ALTER COLUMN composite_score TYPE NUMERIC(4,2)
    USING composite_score::NUMERIC(4,2);
