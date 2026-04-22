-- 003_session_question_budget.sql
-- Migration 2 (Part 5A):
--   ADD question_budget to student_sessions
--   Drives give_up_uses_remaining initialization on new sessions

ALTER TABLE student_sessions
    ADD COLUMN IF NOT EXISTS question_budget INTEGER DEFAULT 20;
