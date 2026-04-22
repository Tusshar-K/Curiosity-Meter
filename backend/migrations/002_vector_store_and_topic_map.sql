-- 002_vector_store_and_topic_map.sql
-- Migration 1 (Part 2A & 2B Step 5):
--   ADD vector_store_id to test_materials
--   ADD topic_map (JSONB) to test_materials

ALTER TABLE test_materials
    ADD COLUMN IF NOT EXISTS vector_store_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS topic_map JSONB DEFAULT '[]'::JSONB;
