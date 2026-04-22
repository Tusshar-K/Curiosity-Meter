-- 001_scoring_and_topic_updates.sql

-- 1. Safely rename the table if it's still named question_logs
DO $$ 
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'question_logs') 
    AND NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'questions') THEN
        ALTER TABLE question_logs RENAME TO questions;
    END IF;
END $$;

-- 2. Clean up deprecated columns from previous phases safely if they exist
ALTER TABLE questions
DROP COLUMN IF EXISTS momentum_bonus CASCADE,
DROP COLUMN IF EXISTS echo_penalty CASCADE,
DROP COLUMN IF EXISTS topic_fixation_penalty CASCADE,
DROP COLUMN IF EXISTS penalties_applied CASCADE,
DROP COLUMN IF EXISTS final_question_score CASCADE;

-- 3. Rename old score columns to the new names so we don't lose data
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.columns WHERE table_name='questions' AND column_name='r_score') THEN
        ALTER TABLE questions RENAME COLUMN r_score TO relevance_r;
    END IF;
    IF EXISTS (SELECT FROM information_schema.columns WHERE table_name='questions' AND column_name='b_score') THEN
        ALTER TABLE questions RENAME COLUMN b_score TO bloom_b;
    END IF;
    IF EXISTS (SELECT FROM information_schema.columns WHERE table_name='questions' AND column_name='d_score') THEN
        ALTER TABLE questions RENAME COLUMN d_score TO depth_d;
    END IF;
    IF EXISTS (SELECT FROM information_schema.columns WHERE table_name='questions' AND column_name='feedback') THEN
        ALTER TABLE questions RENAME COLUMN feedback TO feedback_text;
    END IF;
END $$;

-- 4. Create Students Table so the Foreign Keys won't fail
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

-- 5. Add new columns to Questions
ALTER TABLE questions
ADD COLUMN IF NOT EXISTS student_id UUID references students(id) NULL,
ADD COLUMN IF NOT EXISTS dedup_status VARCHAR(50) DEFAULT 'unique',
ADD COLUMN IF NOT EXISTS bridging_bonus INTEGER,
ADD COLUMN IF NOT EXISTS composite_score NUMERIC(4,2),
ADD COLUMN IF NOT EXISTS current_topic VARCHAR(60),
ADD COLUMN IF NOT EXISTS scaffold_strategy VARCHAR(40),
ADD COLUMN IF NOT EXISTS scaffold_parameters JSON DEFAULT '[]'::JSON,
ADD COLUMN IF NOT EXISTS chain_of_thought JSON DEFAULT '{}'::JSON;

-- 6. Add student_id to sessions as well safely
ALTER TABLE student_sessions
ADD COLUMN IF NOT EXISTS student_id UUID references students(id) NULL;

-- 7. Modify composite_score format safely for existing columns (if it already existed but was float)
ALTER TABLE questions ALTER COLUMN composite_score TYPE numeric(4,2) USING composite_score::numeric(4,2);

-- Note: student_id is kept NULLABLE at the DB level for existing rows without migration scripts needing to drop data! Sqlalchemy will force NOT NULL functionally later.
