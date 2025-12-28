"""Pytest configuration and fixtures for podcast search backend tests."""

import asyncio
import pytest
from typing import AsyncGenerator
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.config import settings


# Test database URL (in-memory SQLite for fast tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (require running services)"
    )
    config.addinivalue_line("markers", "smoke: Smoke tests (quick sanity checks)")
    config.addinivalue_line("markers", "slow: Slow tests (transcription, etc.)")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with mocked database."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service that returns fixed-dimension vectors."""
    mock = AsyncMock()
    mock.embed_query.return_value = [0.1] * 1536
    mock.embed_texts.return_value = [[0.1] * 1536]
    return mock


@pytest.fixture
def mock_vector_store():
    """Mock vector store service."""
    mock = AsyncMock()
    mock.search.return_value = []
    mock.upsert_chunks.return_value = [str(uuid4())]
    mock.get_collection_stats.return_value = {"points_count": 0}
    return mock


@pytest.fixture
def mock_cache_service():
    """Mock cache service."""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.exists.return_value = False
    mock.delete.return_value = True
    return mock


@pytest.fixture
def sample_channel_data():
    """Sample channel data for tests."""
    return {
        "id": uuid4(),
        "slug": "test-channel",
        "name": "Test Channel",
        "youtube_channel_id": "UC123456789",
        "youtube_url": "https://www.youtube.com/@testchannel",
        "speakers": ["Host", "Guest"],
        "created_at": datetime.utcnow(),
    }


@pytest.fixture
def sample_episode_data(sample_channel_data):
    """Sample episode data for tests."""
    return {
        "id": uuid4(),
        "channel_id": sample_channel_data["id"],
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Test Episode",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "status": "done",
        "published_at": datetime.utcnow(),
    }


@pytest.fixture
def sample_chunk_data(sample_episode_data, sample_channel_data):
    """Sample chunk data for tests."""
    return {
        "id": uuid4(),
        "episode_id": sample_episode_data["id"],
        "channel_id": sample_channel_data["id"],
        "text": "This is a sample chunk of text for testing purposes.",
        "primary_speaker": "Host",
        "speakers": ["Host"],
        "start_ms": 0,
        "end_ms": 5000,
        "chunk_index": 0,
    }


@pytest.fixture
def sample_search_result(sample_chunk_data, sample_episode_data, sample_channel_data):
    """Sample search result for tests."""
    return {
        "chunk_id": str(sample_chunk_data["id"]),
        "episode_id": str(sample_episode_data["id"]),
        "channel_id": str(sample_channel_data["id"]),
        "text": sample_chunk_data["text"],
        "speaker": "Host",
        "speakers": ["Host"],
        "start_ms": 0,
        "end_ms": 5000,
        "score": 0.95,
    }


# Admin auth fixture
@pytest.fixture
def admin_headers():
    """Headers with admin authentication."""
    return {"X-Admin-Secret": settings.ADMIN_SECRET}
