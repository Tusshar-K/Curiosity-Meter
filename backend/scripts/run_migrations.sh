#!/bin/bash
set -e

echo "=== Running database migrations ==="

psql -d "$DATABASE_URL" -f migrations/001_scoring_and_topic_updates.sql
psql -d "$DATABASE_URL" -f migrations/002_vector_store_and_topic_map.sql
psql -d "$DATABASE_URL" -f migrations/003_session_question_budget.sql
psql -d "$DATABASE_URL" -f migrations/004_questions_post_nudge.sql
psql -d "$DATABASE_URL" -f migrations/005_give_up_events.sql
psql -d "$DATABASE_URL" -f migrations/006_test_config_time_limit.sql

echo "=== Migrations complete ==="