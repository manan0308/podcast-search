"""Add search optimization indexes

Revision ID: 003
Revises: 002
Create Date: 2024-12-27

This migration adds indexes to optimize:
- Episode status filtering (used in batches, jobs views)
- Utterance time-range queries (used in context fetching)
- Compound indexes for common query patterns
- Full-text search index on chunks (for BM25 replacement)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '003'
down_revision = '002_add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Episode indexes
    op.create_index(
        'idx_episodes_status',
        'episodes',
        ['status'],
        if_not_exists=True,
    )
    op.create_index(
        'idx_episodes_channel_status',
        'episodes',
        ['channel_id', 'status'],
        if_not_exists=True,
    )

    # Utterance indexes for context queries
    op.create_index(
        'idx_utterances_episode_time',
        'utterances',
        ['episode_id', 'start_ms', 'end_ms'],
        if_not_exists=True,
    )

    # Chunk indexes for keyword search
    op.create_index(
        'idx_chunks_episode_speaker',
        'chunks',
        ['episode_id', 'primary_speaker'],
        if_not_exists=True,
    )

    # Job indexes for batch monitoring
    op.create_index(
        'idx_jobs_batch_status',
        'jobs',
        ['batch_id', 'status'],
        if_not_exists=True,
    )

    # Full-text search index on chunks (for replacing in-memory BM25)
    # Uses PostgreSQL's GIN index with tsvector
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_text_search
        ON chunks USING GIN (to_tsvector('english', text));
    """)

    # Full-text search index on episodes for title search
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_title_search
        ON episodes USING GIN (to_tsvector('english', title));
    """)


def downgrade() -> None:
    op.drop_index('idx_episodes_status', table_name='episodes')
    op.drop_index('idx_episodes_channel_status', table_name='episodes')
    op.drop_index('idx_utterances_episode_time', table_name='utterances')
    op.drop_index('idx_chunks_episode_speaker', table_name='chunks')
    op.drop_index('idx_jobs_batch_status', table_name='jobs')
    op.execute("DROP INDEX IF EXISTS idx_chunks_text_search;")
    op.execute("DROP INDEX IF EXISTS idx_episodes_title_search;")
