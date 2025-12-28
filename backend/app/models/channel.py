import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class Channel(Base):
    __tablename__ = "channels"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    youtube_channel_id = Column(String(100), unique=True, nullable=True)
    youtube_url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)

    # Speaker configuration
    speakers = Column(JSON, default=list)  # ["Sam Parr", "Shaan Puri"]
    default_unknown_speaker_label = Column(String(100), default="Guest")

    # Denormalized stats
    episode_count = Column(Integer, default=0)
    transcribed_count = Column(Integer, default=0)
    total_duration_seconds = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    episodes = relationship(
        "Episode", back_populates="channel", cascade="all, delete-orphan"
    )
    batches = relationship("Batch", back_populates="channel")

    def __repr__(self):
        return f"<Channel {self.name}>"
