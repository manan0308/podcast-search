"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # Channels table
    op.create_table(
        "channels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("youtube_channel_id", sa.String(100), nullable=True),
        sa.Column("youtube_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column(
            "speakers",
            postgresql.JSON(astext_type=sa.Text()),
            server_default="[]",
            nullable=True,
        ),
        sa.Column(
            "default_unknown_speaker_label",
            sa.String(100),
            server_default="Guest",
            nullable=True,
        ),
        sa.Column("episode_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("transcribed_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column(
            "total_duration_seconds", sa.Integer(), server_default="0", nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("youtube_channel_id"),
    )
    op.create_index("idx_channels_slug", "channels", ["slug"])

    # Episodes table
    op.create_table(
        "episodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("youtube_id", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "transcript_raw", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("youtube_id"),
    )
    op.create_index("idx_episodes_channel", "episodes", ["channel_id"])
    op.create_index("idx_episodes_status", "episodes", ["status"])
    op.create_index("idx_episodes_published", "episodes", ["published_at"])
    op.create_index("idx_episodes_youtube_id", "episodes", ["youtube_id"])

    # Utterances table
    op.create_table(
        "utterances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("speaker", sa.String(200), nullable=False),
        sa.Column("speaker_raw", sa.String(50), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_utterances_episode", "utterances", ["episode_id"])
    op.create_index("idx_utterances_speaker", "utterances", ["speaker"])

    # Chunks table
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("primary_speaker", sa.String(200), nullable=True),
        sa.Column(
            "speakers",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chunks_episode", "chunks", ["episode_id"])
    op.create_index("idx_chunks_speaker", "chunks", ["primary_speaker"])
    op.create_index("idx_chunks_qdrant", "chunks", ["qdrant_point_id"])

    # Batches table
    op.create_table(
        "batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("concurrency", sa.Integer(), server_default="10", nullable=True),
        sa.Column(
            "config",
            postgresql.JSON(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column("total_episodes", sa.Integer(), server_default="0", nullable=True),
        sa.Column(
            "completed_episodes", sa.Integer(), server_default="0", nullable=True
        ),
        sa.Column("failed_episodes", sa.Integer(), server_default="0", nullable=True),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=True),
        sa.Column("actual_cost_cents", sa.Integer(), server_default="0", nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_batches_status", "batches", ["status"])
    op.create_index("idx_batches_channel", "batches", ["channel_id"])

    # Jobs table
    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_job_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=True),
        sa.Column("current_step", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("cost_cents", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "episode_id", name="uq_jobs_batch_episode"),
    )
    op.create_index("idx_jobs_batch", "jobs", ["batch_id"])
    op.create_index("idx_jobs_episode", "jobs", ["episode_id"])
    op.create_index("idx_jobs_status", "jobs", ["status"])

    # Activity log table
    op.create_table(
        "activity_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.String(10), server_default="info", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSON(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_activity_batch", "activity_log", ["batch_id"])
    op.create_index("idx_activity_job", "activity_log", ["job_id"])
    op.create_index("idx_activity_created", "activity_log", ["created_at"])

    # API keys table
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSON(astext_type=sa.Text()),
            server_default='["read"]',
            nullable=True,
        ),
        sa.Column(
            "rate_limit_per_minute", sa.Integer(), server_default="60", nullable=True
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("idx_api_keys_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("activity_log")
    op.drop_table("jobs")
    op.drop_table("batches")
    op.drop_table("chunks")
    op.drop_table("utterances")
    op.drop_table("episodes")
    op.drop_table("channels")
