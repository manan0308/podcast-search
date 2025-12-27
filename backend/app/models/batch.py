import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class Batch(Base):
    __tablename__ = "batches"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    channel_id = Column(GUID(), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)

    # Configuration
    name = Column(String(255), nullable=True)
    provider = Column(String(50), nullable=False)  # assemblyai, deepgram, whisper
    concurrency = Column(Integer, default=10)
    config = Column(JSON, default=dict)  # Provider-specific config

    # Stats
    total_episodes = Column(Integer, default=0)
    completed_episodes = Column(Integer, default=0)
    failed_episodes = Column(Integer, default=0)

    # Cost tracking (in cents)
    estimated_cost_cents = Column(Integer, nullable=True)
    actual_cost_cents = Column(Integer, default=0)

    # Status
    status = Column(String(20), default="pending", nullable=False, index=True)
    # Valid statuses: pending, running, paused, completed, cancelled, failed

    # Timing
    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    channel = relationship("Channel", back_populates="batches")
    jobs = relationship("Job", back_populates="batch", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="batch", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_batches_status", "status"),
        Index("idx_batches_channel", "channel_id"),
    )

    def __repr__(self):
        return f"<Batch {self.id} - {self.status}>"

    @property
    def progress_percent(self) -> float:
        if self.total_episodes == 0:
            return 0
        return (self.completed_episodes / self.total_episodes) * 100

    @property
    def pending_episodes(self) -> int:
        return self.total_episodes - self.completed_episodes - self.failed_episodes
