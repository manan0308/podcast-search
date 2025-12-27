import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class Job(Base):
    __tablename__ = "jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    batch_id = Column(GUID(), ForeignKey("batches.id", ondelete="CASCADE"), nullable=True)
    episode_id = Column(GUID(), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)

    # Provider info
    provider = Column(String(50), nullable=False)
    provider_job_id = Column(String(255), nullable=True)

    # Status tracking
    status = Column(String(20), default="pending", nullable=False, index=True)
    # Valid statuses: pending, downloading, uploading, transcribing, labeling, chunking, embedding, done, failed, cancelled

    progress = Column(Integer, default=0)  # 0-100
    current_step = Column(String(100), nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0)

    # Cost (in cents)
    cost_cents = Column(Integer, nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    batch = relationship("Batch", back_populates="jobs")
    episode = relationship("Episode", back_populates="jobs")
    activity_logs = relationship("ActivityLog", back_populates="job", cascade="all, delete-orphan")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_jobs_batch", "batch_id"),
        Index("idx_jobs_episode", "episode_id"),
        Index("idx_jobs_status", "status"),
        UniqueConstraint("batch_id", "episode_id", name="uq_jobs_batch_episode"),
    )

    def __repr__(self):
        return f"<Job {self.id} - {self.status}>"

    @property
    def duration_seconds(self) -> int | None:
        """Return job duration in seconds."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None
