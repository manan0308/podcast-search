import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    channel_id = Column(
        GUID(), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )

    # YouTube data
    youtube_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Processing status
    status = Column(String(20), default="pending", nullable=False, index=True)
    # Valid statuses: pending, queued, processing, done, failed, skipped

    # Transcript data
    transcript_raw = Column(JSON, nullable=True)
    word_count = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    channel = relationship("Channel", back_populates="episodes")
    utterances = relationship(
        "Utterance", back_populates="episode", cascade="all, delete-orphan"
    )
    chunks = relationship(
        "Chunk", back_populates="episode", cascade="all, delete-orphan"
    )
    jobs = relationship("Job", back_populates="episode", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_episodes_channel", "channel_id"),
        Index("idx_episodes_published", "published_at"),
    )

    def __repr__(self):
        return f"<Episode {self.title[:50]}>"
