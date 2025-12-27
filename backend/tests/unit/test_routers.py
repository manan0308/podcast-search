"""
Unit tests for API routers.

Tests router logic with mocked dependencies.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from httpx import AsyncClient
from fastapi import FastAPI

from app.main import app
from app.models import Channel, Episode, Batch, Job
from app.dependencies import get_db
from app.config import settings


class TestChannelRouter:
    """Tests for channel endpoints."""

    @pytest.mark.asyncio
    async def test_list_channels_empty(self, client):
        """Should return empty list when no channels exist."""
        response = await client.get("/api/channels")
        assert response.status_code == 200
        data = response.json()
        assert data["channels"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_channels_with_data(self, db_session, client):
        """Should return list of channels."""
        channel = Channel(
            id=uuid4(),
            slug="test-channel",
            name="Test Channel",
            youtube_channel_id="UC123",
        )
        db_session.add(channel)
        await db_session.commit()

        response = await client.get("/api/channels")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["channels"][0]["slug"] == "test-channel"

    @pytest.mark.asyncio
    async def test_get_channel_by_slug(self, db_session, client):
        """Should return channel by slug."""
        channel = Channel(
            id=uuid4(),
            slug="my-podcast",
            name="My Podcast",
            youtube_channel_id="UC456",
            episode_count=5,
            transcribed_count=3,
        )
        db_session.add(channel)
        await db_session.commit()

        response = await client.get("/api/channels/slug/my-podcast")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Podcast"
        assert data["episode_count"] == 5

    @pytest.mark.asyncio
    async def test_get_channel_not_found(self, client):
        """Should return 404 for non-existent channel."""
        response = await client.get("/api/channels/slug/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_channel_requires_auth(self, client):
        """Creating channel should require admin auth."""
        response = await client.post("/api/channels", json={
            "slug": "new-channel",
            "name": "New Channel",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_channel_with_auth(self, db_session, client, admin_headers):
        """Should create channel with valid auth."""
        response = await client.post(
            "/api/channels",
            json={
                "slug": "new-channel",
                "name": "New Channel",
                "speakers": ["Host", "Guest"],
            },
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "new-channel"
        assert data["speakers"] == ["Host", "Guest"]

    @pytest.mark.asyncio
    async def test_create_channel_auto_increments_slug(self, db_session, client, admin_headers):
        """Should auto-increment slug when duplicate exists."""
        channel = Channel(
            id=uuid4(),
            slug="existing-channel",
            name="Existing Channel",
        )
        db_session.add(channel)
        await db_session.commit()

        response = await client.post(
            "/api/channels",
            json={"name": "Existing Channel"},  # Same name, should get slug "existing-channel-1"
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "existing-channel-1"


class TestEpisodeRouter:
    """Tests for episode endpoints."""

    @pytest.mark.asyncio
    async def test_list_episodes_empty(self, client):
        """Should return empty list when no episodes exist."""
        response = await client.get("/api/episodes")
        assert response.status_code == 200
        data = response.json()
        assert data["episodes"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_episodes_with_channel_filter(self, db_session, client):
        """Should filter episodes by channel."""
        channel1 = Channel(id=uuid4(), slug="channel1", name="Channel 1")
        channel2 = Channel(id=uuid4(), slug="channel2", name="Channel 2")
        db_session.add_all([channel1, channel2])

        ep1 = Episode(
            id=uuid4(),
            channel_id=channel1.id,
            youtube_id="vid1",
            title="Episode 1",
            status="done",
        )
        ep2 = Episode(
            id=uuid4(),
            channel_id=channel2.id,
            youtube_id="vid2",
            title="Episode 2",
            status="done",
        )
        db_session.add_all([ep1, ep2])
        await db_session.commit()

        response = await client.get(f"/api/episodes?channel_id={channel1.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["episodes"][0]["title"] == "Episode 1"

    @pytest.mark.asyncio
    async def test_list_episodes_with_status_filter(self, db_session, client):
        """Should filter episodes by status."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)

        ep1 = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid1",
            title="Done Episode",
            status="done",
        )
        ep2 = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid2",
            title="Pending Episode",
            status="pending",
        )
        db_session.add_all([ep1, ep2])
        await db_session.commit()

        response = await client.get("/api/episodes?status=done")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["episodes"][0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_list_episodes_with_search(self, db_session, client):
        """Should search episodes by title."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)

        ep1 = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid1",
            title="Interview with CEO",
            status="done",
        )
        ep2 = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid2",
            title="Product Review",
            status="done",
        )
        db_session.add_all([ep1, ep2])
        await db_session.commit()

        response = await client.get("/api/episodes?search=CEO")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "CEO" in data["episodes"][0]["title"]

    @pytest.mark.asyncio
    async def test_get_episode_detail(self, db_session, client):
        """Should return episode with utterances."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)

        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid123",
            title="Test Episode",
            status="done",
            word_count=1000,
        )
        db_session.add(episode)
        await db_session.commit()

        response = await client.get(f"/api/episodes/{episode.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Episode"
        assert data["word_count"] == 1000
        assert "utterances" in data

    @pytest.mark.asyncio
    async def test_get_episode_not_found(self, client):
        """Should return 404 for non-existent episode."""
        fake_id = uuid4()
        response = await client.get(f"/api/episodes/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_episode_requires_auth(self, db_session, client):
        """Creating episode should require admin auth."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)
        await db_session.commit()

        response = await client.post("/api/episodes", json={
            "channel_id": str(channel.id),
            "youtube_id": "newvid",
            "title": "New Episode",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_episode_requires_auth(self, db_session, client):
        """Deleting episode should require admin auth."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid",
            title="To Delete",
            status="pending",
        )
        db_session.add_all([channel, episode])
        await db_session.commit()

        response = await client.delete(f"/api/episodes/{episode.id}")
        assert response.status_code == 401


class TestBatchRouter:
    """Tests for batch endpoints."""

    @pytest.mark.asyncio
    async def test_list_batches_empty(self, client):
        """Should return empty list when no batches exist."""
        response = await client.get("/api/batches")
        assert response.status_code == 200
        data = response.json()
        assert data["batches"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_batches_with_status_filter(self, db_session, client):
        """Should filter batches by status."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)

        batch1 = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Batch 1",
            provider="deepgram",
            status="running",
            total_episodes=5,
        )
        batch2 = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Batch 2",
            provider="deepgram",
            status="completed",
            total_episodes=3,
        )
        db_session.add_all([batch1, batch2])
        await db_session.commit()

        response = await client.get("/api/batches?status=running")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["batches"][0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_batch_detail(self, db_session, client):
        """Should return batch with jobs."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)

        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid",
            title="Test Episode",
            status="queued",
        )
        db_session.add(episode)

        batch = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Test Batch",
            provider="deepgram",
            status="running",
            total_episodes=1,
        )
        db_session.add(batch)

        job = Job(
            id=uuid4(),
            batch_id=batch.id,
            episode_id=episode.id,
            provider="deepgram",
            status="pending",
        )
        db_session.add(job)
        await db_session.commit()

        response = await client.get(f"/api/batches/{batch.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Batch"
        assert len(data["jobs"]) == 1

    @pytest.mark.asyncio
    async def test_get_batch_not_found(self, client):
        """Should return 404 for non-existent batch."""
        fake_id = uuid4()
        response = await client.get(f"/api/batches/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_batch_requires_auth(self, client):
        """Creating batch should require admin auth."""
        response = await client.post("/api/batches", json={
            "provider": "deepgram",
            "channel_id": str(uuid4()),
            "episode_ids": [str(uuid4())],
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_start_batch_requires_auth(self, db_session, client):
        """Starting batch should require admin auth."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        batch = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Test Batch",
            provider="deepgram",
            status="pending",
            total_episodes=1,
        )
        db_session.add_all([channel, batch])
        await db_session.commit()

        response = await client.post(f"/api/batches/{batch.id}/start")
        assert response.status_code == 401


class TestSearchRouter:
    """Tests for search endpoints."""

    @pytest.mark.asyncio
    async def test_search_requires_query(self, client):
        """Search should require query in body."""
        response = await client.post("/api/search", json={})
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_accepts_short_query(self, client):
        """Search should accept short queries."""
        # Mock the search service to avoid Qdrant connection
        mock_service = AsyncMock()
        mock_service.search.return_value = ([], 10)  # processing_time_ms must be int
        with patch('app.routers.search.HybridSearchService', return_value=mock_service):
            response = await client.post("/api/search", json={"query": "ai"})
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_validates_limit(self, client):
        """Search should validate limit parameter."""
        response = await client.post("/api/search", json={"query": "test", "limit": 500})
        assert response.status_code == 422


class TestJobRouter:
    """Tests for job endpoints."""

    @pytest.mark.asyncio
    async def test_list_jobs_with_batch_filter(self, db_session, client):
        """Should filter jobs by batch."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        db_session.add(channel)

        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid",
            title="Test",
            status="queued",
        )
        db_session.add(episode)

        batch = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Batch",
            provider="deepgram",
            status="running",
            total_episodes=1,
        )
        db_session.add(batch)

        job = Job(
            id=uuid4(),
            batch_id=batch.id,
            episode_id=episode.id,
            provider="deepgram",
            status="pending",
        )
        db_session.add(job)
        await db_session.commit()

        response = await client.get(f"/api/jobs?batch_id={batch.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1

    @pytest.mark.asyncio
    async def test_get_job_detail(self, db_session, client):
        """Should return job details."""
        channel = Channel(id=uuid4(), slug="test", name="Test")
        episode = Episode(
            id=uuid4(),
            channel_id=channel.id,
            youtube_id="vid",
            title="Test Episode",
            status="queued",
        )
        batch = Batch(
            id=uuid4(),
            channel_id=channel.id,
            name="Batch",
            provider="deepgram",
            status="running",
            total_episodes=1,
        )
        job = Job(
            id=uuid4(),
            batch_id=batch.id,
            episode_id=episode.id,
            provider="deepgram",
            status="transcribing",
            progress=50,
            current_step="Transcribing audio",
        )
        db_session.add_all([channel, episode, batch, job])
        await db_session.commit()

        response = await client.get(f"/api/jobs/{job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "transcribing"
        assert data["progress"] == 50


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_root_returns_info(self, client):
        """Root endpoint should return API info."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Health endpoint should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
