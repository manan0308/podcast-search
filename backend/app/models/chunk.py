import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship

from app.database import Base, GUID


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    episode_id = Column(GUID(), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)

    # Link to vector store
    qdrant_point_id = Column(GUID(), nullable=False, index=True)

    # Content
    text = Column(Text, nullable=False)

    # Speaker info
    primary_speaker = Column(String(200), nullable=True, index=True)
    speakers = Column(JSON, default=list)  # List of speaker names

    # Position
    start_ms = Column(Integer, nullable=True)
    end_ms = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=True)

    # Metadata
    word_count = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    episode = relationship("Episode", back_populates="chunks")

    # Indexes
    __table_args__ = (
        Index("idx_chunks_episode", "episode_id"),
        Index("idx_chunks_speaker", "primary_speaker"),
        Index("idx_chunks_qdrant", "qdrant_point_id"),
    )

    def __repr__(self):
        return f"<Chunk {self.chunk_index} of episode {self.episode_id}>"

    @property
    def timestamp(self) -> str:
        """Return formatted timestamp like '14:30'."""
        if self.start_ms is None:
            return "0:00"
        total_seconds = self.start_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
