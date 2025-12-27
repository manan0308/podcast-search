from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Integer, Index
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class ActivityLog(Base):
    __tablename__ = "activity_log"

    # Use Integer for SQLite compatibility (autoincrement only works with INTEGER PRIMARY KEY)
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Context
    batch_id = Column(GUID(), ForeignKey("batches.id", ondelete="CASCADE"), nullable=True)
    job_id = Column(GUID(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    episode_id = Column(GUID(), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True)

    # Log data
    level = Column(String(10), default="info", nullable=False)
    # Valid levels: debug, info, warn, error
    message = Column(Text, nullable=False)
    log_metadata = Column("metadata", JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    batch = relationship("Batch", back_populates="activity_logs")
    job = relationship("Job", back_populates="activity_logs")

    # Indexes
    __table_args__ = (
        Index("idx_activity_batch", "batch_id"),
        Index("idx_activity_job", "job_id"),
        Index("idx_activity_created", "created_at"),
    )

    def __repr__(self):
        return f"<ActivityLog [{self.level}] {self.message[:50]}>"
