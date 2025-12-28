"""API Key management service."""

import secrets
import hashlib
from datetime import datetime
from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models import APIKey


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (full_key, key_prefix)

    The full key is shown once to the user.
    The key_prefix is stored for identification.
    """
    # Generate 32-byte random key
    full_key = f"ps_{secrets.token_urlsafe(32)}"
    key_prefix = full_key[:12]  # "ps_" + first 9 chars

    return full_key, key_prefix


def hash_api_key(key: str) -> str:
    """Hash API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKeyService:
    """Service for managing API keys."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_key(self, name: str) -> tuple[APIKey, str]:
        """
        Create a new API key.

        Args:
            name: Human-readable name for the key

        Returns:
            Tuple of (APIKey model, full_key)

        Note: The full_key is only returned once!
        """
        full_key, key_prefix = generate_api_key()
        key_hash = hash_api_key(full_key)

        api_key = APIKey(
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_active=True,
        )

        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        logger.info(f"Created API key: {name} ({key_prefix}...)")

        return api_key, full_key

    async def validate_key(self, key: str) -> Optional[APIKey]:
        """
        Validate an API key.

        Args:
            key: The full API key to validate

        Returns:
            APIKey model if valid, None if invalid
        """
        key_hash = hash_api_key(key)

        result = await self.db.execute(
            select(APIKey).where(
                APIKey.key_hash == key_hash,
                APIKey.is_active.is_(True),
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key:
            # Update last used timestamp
            api_key.last_used_at = datetime.utcnow()
            await self.db.commit()

            logger.debug(f"API key validated: {api_key.key_prefix}...")

        return api_key

    async def revoke_key(self, key_id: UUID) -> bool:
        """
        Revoke an API key.

        Args:
            key_id: UUID of the key to revoke

        Returns:
            True if revoked, False if not found
        """
        result = await self.db.execute(select(APIKey).where(APIKey.id == key_id))
        api_key = result.scalar_one_or_none()

        if not api_key:
            return False

        api_key.is_active = False
        await self.db.commit()

        logger.info(f"Revoked API key: {api_key.name} ({api_key.key_prefix}...)")

        return True

    async def list_keys(self) -> list[APIKey]:
        """List all API keys (active and inactive)."""
        result = await self.db.execute(
            select(APIKey).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_key(self, key_id: UUID) -> Optional[APIKey]:
        """Get API key by ID."""
        result = await self.db.execute(select(APIKey).where(APIKey.id == key_id))
        return result.scalar_one_or_none()
