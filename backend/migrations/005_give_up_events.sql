-- 005_give_up_events.sql
-- Migration 4 (Part 5C step 8):
--   CREATE give_up_events table

CREATE TABLE IF NOT EXISTS give_up_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID NOT NULL REFERENCES student_sessions(id) ON DELETE CASCADE,
    student_id       UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    covered_topics   JSONB NOT NULL DEFAULT '[]'::JSONB,
    uncovered_topics JSONB NOT NULL DEFAULT '[]'::JSONB,
    nudge_text       TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_give_up_events_session_id ON give_up_events(session_id);
