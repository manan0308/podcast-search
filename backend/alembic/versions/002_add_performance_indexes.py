"""Add performance indexes for search and common queries.

Revision ID: 002_add_performance_indexes
Revises: 001_initial_schema
Create Date: 2024-12-26

This migration adds:
1. Full-text search (GIN) indexes on chunk text for fast keyword search
2. Composite indexes for common query patterns
3. Partial indexes for status filtering
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add full-text search vector column and GIN index on chunks
    # This enables fast Postgres native full-text search as an alternative to BM25
    op.execute("""
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS text_search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_text_search
        ON chunks USING GIN (text_search_vector);
    """)

    # Full-text search on utterances for direct transcript search
    op.execute("""
        ALTER TABLE utterances
        ADD COLUMN IF NOT EXISTS text_search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_utterances_text_search
        ON utterances USING GIN (text_search_vector);
    """)

    # Composite index for episode queries by channel + status (very common)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_channel_status
        ON episodes (channel_id, status);
    """)

    # Composite index for episodes by channel + published date (for sorting)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_channel_published
        ON episodes (channel_id, published_at DESC NULLS LAST);
    """)

    # Partial index for pending/processing episodes (hot path for batch processing)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_pending
        ON episodes (status, created_at)
        WHERE status IN ('pending', 'queued', 'processing');
    """)

    # Composite index for chunks by episode + timing (for context retrieval)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_episode_timing
        ON chunks (episode_id, start_ms, end_ms);
    """)

    # Composite index for utterances by episode + timing (for context retrieval)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_utterances_episode_timing
        ON utterances (episode_id, start_ms);
    """)

    # Index for jobs needing retry (batch processor hot path)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_retry
        ON jobs (status, retry_count)
        WHERE status = 'failed' AND retry_count < 3;
    """)

    # Composite index for jobs by batch + status
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_batch_status
        ON jobs (batch_id, status);
    """)

    # Index for recent activity (dashboard queries)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_batches_recent
        ON batches (created_at DESC)
        WHERE status IN ('pending', 'running');
    """)


def downgrade() -> None:
    # Remove indexes
    op.execute("DROP INDEX IF EXISTS idx_batches_recent;")
    op.execute("DROP INDEX IF EXISTS idx_jobs_batch_status;")
    op.execute("DROP INDEX IF EXISTS idx_jobs_retry;")
    op.execute("DROP INDEX IF EXISTS idx_utterances_episode_timing;")
    op.execute("DROP INDEX IF EXISTS idx_chunks_episode_timing;")
    op.execute("DROP INDEX IF EXISTS idx_episodes_pending;")
    op.execute("DROP INDEX IF EXISTS idx_episodes_channel_published;")
    op.execute("DROP INDEX IF EXISTS idx_episodes_channel_status;")
    op.execute("DROP INDEX IF EXISTS idx_utterances_text_search;")
    op.execute("DROP INDEX IF EXISTS idx_chunks_text_search;")

    # Remove generated columns
    op.execute("ALTER TABLE utterances DROP COLUMN IF EXISTS text_search_vector;")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_search_vector;")
