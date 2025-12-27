import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class Utterance(Base):
    __tablename__ = "utterances"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    episode_id = Column(GUID(), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)

    # Speaker info
    speaker = Column(String(200), nullable=False, index=True)  # "Sam Parr", "Guest"
    speaker_raw = Column(String(50), nullable=True)  # "A", "B", "C"

    # Content
    text = Column(Text, nullable=False)

    # Timing
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)

    # Metadata
    confidence = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    episode = relationship("Episode", back_populates="utterances")

    # Indexes
    __table_args__ = (
        Index("idx_utterances_episode", "episode_id"),
        Index("idx_utterances_speaker", "speaker"),
    )

    def __repr__(self):
        return f"<Utterance {self.speaker}: {self.text[:30]}...>"

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def timestamp(self) -> str:
        """Return formatted timestamp like '14:30'."""
        total_seconds = self.start_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
