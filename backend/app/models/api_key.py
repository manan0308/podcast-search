import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, JSON

from app.database import Base, GUID


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA256

    # Permissions
    permissions = Column(JSON, default=["read"])  # ["read", "write", "admin"]

    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=60)

    # Status
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<APIKey {self.name}>"

    def has_permission(self, permission: str) -> bool:
        """Check if API key has the given permission."""
        if "admin" in self.permissions:
            return True
        return permission in self.permissions
