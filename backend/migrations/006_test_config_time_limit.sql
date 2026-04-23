-- 006_test_config_time_limit.sql
-- Adds optional time limit (in minutes) to test_config.
-- NULL = no time limit imposed.

ALTER TABLE test_config
    ADD COLUMN IF NOT EXISTS time_limit_minutes INTEGER DEFAULT NULL;
