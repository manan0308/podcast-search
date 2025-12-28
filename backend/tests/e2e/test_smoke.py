"""
E2E Smoke Tests for Podcast Search Application.

These tests use REAL external APIs and cost money. Run sparingly.

Usage:
    # Run smoke tests only
    pytest tests/e2e/test_smoke.py -v -m smoke

    # Run with specific video (override default)
    TEST_VIDEO_ID=dQw4w9WgXcQ pytest tests/e2e/test_smoke.py -v

Requirements:
    - All services running (postgres, redis, qdrant)
    - Valid API keys in environment
    - Internet connection
"""

import os
import asyncio
import pytest
from httpx import AsyncClient

# Test configuration
# Using a short Creative Commons video for minimal cost
# Override with TEST_VIDEO_ID env var
DEFAULT_TEST_VIDEO_ID = "BaW_jenozKc"  # ~2 min test video
DEFAULT_TEST_CHANNEL = "https://www.youtube.com/@TED"  # Well-known channel

# Skip all E2E tests if not explicitly enabled
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E_TESTS") != "true",
        reason="E2E tests disabled. Set RUN_E2E_TESTS=true to enable.",
    ),
]


@pytest.fixture(scope="module")
def test_video_id():
    """Get test video ID from environment or use default."""
    return os.environ.get("TEST_VIDEO_ID", DEFAULT_TEST_VIDEO_ID)


@pytest.fixture(scope="module")
def test_channel_url():
    """Get test channel URL from environment or use default."""
    return os.environ.get("TEST_CHANNEL_URL", DEFAULT_TEST_CHANNEL)


@pytest.fixture(scope="module")
def admin_headers():
    """Get admin auth headers."""
    admin_secret = os.environ.get("ADMIN_SECRET", "change-me-in-production")
    return {"X-Admin-Secret": admin_secret}


@pytest.fixture(scope="module")
def api_base_url():
    """Get API base URL."""
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
async def async_client(api_base_url):
    """Create async HTTP client for E2E tests."""
    async with AsyncClient(base_url=api_base_url, timeout=300.0) as client:
        yield client


class TestHealthCheck:
    """Test that all services are running."""

    @pytest.mark.asyncio
    async def test_api_health(self, async_client):
        """API should be healthy."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_detailed_health(self, async_client):
        """All components should be healthy."""
        response = await async_client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()

        # Check all components
        assert data["status"] in ["healthy", "degraded"]
        components = data.get("components", {})

        # Database should be healthy
        assert components.get("database", {}).get("status") == "healthy"

        # Qdrant should be healthy
        assert components.get("qdrant", {}).get("status") == "healthy"

        # Redis might not be configured, that's ok
        redis_status = components.get("redis", {}).get("status")
        assert redis_status in ["healthy", "not_configured"]


class TestYouTubeIntegration:
    """Test YouTube fetching functionality."""

    @pytest.mark.asyncio
    async def test_fetch_channel_preview(
        self, async_client, admin_headers, test_channel_url
    ):
        """Should fetch channel info from YouTube."""
        response = await async_client.post(
            "/api/channels/fetch",
            json={"youtube_url": test_channel_url},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Should have channel info
        assert "name" in data
        assert "youtube_channel_id" in data
        assert "episodes" in data
        assert data["total_episodes"] > 0

        print(
            f"\n✓ Found channel: {data['name']} with {data['total_episodes']} episodes"
        )


class TestFullPipeline:
    """
    Test the complete transcription pipeline.

    WARNING: This test costs money (~$0.02-0.10) and takes 2-5 minutes.
    """

    @pytest.fixture(scope="class")
    async def created_channel(self, async_client, admin_headers):
        """Create a test channel for pipeline testing."""
        # Create channel
        response = await async_client.post(
            "/api/channels",
            json={
                "name": "E2E Test Channel",
                "youtube_channel_id": "UC_E2E_TEST",
                "youtube_url": "https://www.youtube.com/@test",
                "speakers": ["Speaker 1", "Speaker 2"],
            },
            headers=admin_headers,
        )

        if response.status_code == 201:
            channel = response.json()
            yield channel

            # Cleanup: Delete channel after tests
            await async_client.delete(
                f"/api/channels/{channel['id']}",
                headers=admin_headers,
            )
        else:
            # Channel might already exist, try to find it
            channels_response = await async_client.get("/api/channels")
            channels = channels_response.json().get("channels", [])
            for ch in channels:
                if ch.get("name") == "E2E Test Channel":
                    yield ch
                    return
            pytest.fail(f"Failed to create test channel: {response.text}")

    @pytest.fixture(scope="class")
    async def created_episode(
        self, async_client, admin_headers, created_channel, test_video_id
    ):
        """Create a test episode."""
        response = await async_client.post(
            "/api/episodes",
            json={
                "channel_id": created_channel["id"],
                "youtube_id": test_video_id,
                "title": "E2E Test Episode",
                "url": f"https://www.youtube.com/watch?v={test_video_id}",
            },
            headers=admin_headers,
        )

        if response.status_code == 201:
            episode = response.json()
            yield episode
        else:
            # Episode might already exist
            episodes_response = await async_client.get(
                f"/api/episodes?channel_id={created_channel['id']}"
            )
            episodes = episodes_response.json().get("episodes", [])
            for ep in episodes:
                if ep.get("youtube_id") == test_video_id:
                    yield ep
                    return
            pytest.fail(f"Failed to create test episode: {response.text}")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_create_and_start_batch(
        self, async_client, admin_headers, created_channel, created_episode
    ):
        """
        Create a batch and start transcription.

        This is the main E2E test - it actually transcribes a video.
        """
        print(f"\n📝 Creating batch for episode: {created_episode['title']}")

        # Create batch
        batch_response = await async_client.post(
            "/api/batches",
            json={
                "channel_id": created_channel["id"],
                "name": "E2E Test Batch",
                "provider": os.environ.get("TEST_PROVIDER", "deepgram"),
                "episode_ids": [created_episode["id"]],
            },
            headers=admin_headers,
        )

        assert batch_response.status_code == 201
        batch = batch_response.json()
        batch_id = batch["id"]

        print(f"✓ Created batch: {batch_id}")

        # Start batch
        start_response = await async_client.post(
            f"/api/batches/{batch_id}/start",
            headers=admin_headers,
        )

        assert start_response.status_code == 200
        print("✓ Batch started")

        # Wait for completion (poll every 10 seconds, max 5 minutes)
        max_wait = 300  # 5 minutes
        poll_interval = 10
        waited = 0

        while waited < max_wait:
            status_response = await async_client.get(
                f"/api/batches/{batch_id}",
                headers=admin_headers,
            )

            assert status_response.status_code == 200
            status = status_response.json()

            print(
                f"  Status: {status['status']}, Progress: {status.get('progress_percent', 0):.0f}%"
            )

            if status["status"] == "completed":
                print(f"✓ Batch completed in {waited}s")
                break
            elif status["status"] == "failed":
                pytest.fail(f"Batch failed: {status}")

            await asyncio.sleep(poll_interval)
            waited += poll_interval

        if waited >= max_wait:
            pytest.fail(f"Batch did not complete within {max_wait}s")

        # Verify episode is transcribed
        episode_response = await async_client.get(
            f"/api/episodes/{created_episode['id']}"
        )
        assert episode_response.status_code == 200
        episode = episode_response.json()
        assert episode["status"] == "done"
        print(f"✓ Episode transcribed: {episode.get('word_count', 0)} words")

        return batch_id


class TestSearchAfterTranscription:
    """Test search functionality after transcription."""

    @pytest.mark.asyncio
    async def test_semantic_search(self, async_client):
        """Semantic search should return results."""
        response = await async_client.post(
            "/api/search",
            json={
                "query": "test",
                "limit": 5,
                "use_hybrid": False,
            },
        )

        assert response.status_code == 200
        data = response.json()

        print(
            f"\n🔍 Semantic search found {data['total']} results in {data['processing_time_ms']}ms"
        )

    @pytest.mark.asyncio
    async def test_hybrid_search(self, async_client):
        """Hybrid search should return results."""
        response = await async_client.post(
            "/api/search",
            json={
                "query": "test",
                "limit": 5,
                "use_hybrid": True,
                "use_reranking": True,
            },
        )

        assert response.status_code == 200
        data = response.json()

        print(
            f"🔍 Hybrid search found {data['total']} results in {data['processing_time_ms']}ms"
        )

    @pytest.mark.asyncio
    async def test_search_with_filters(self, async_client):
        """Search with filters should work."""
        response = await async_client.post(
            "/api/search",
            json={
                "query": "test",
                "limit": 5,
                "filters": {
                    "speaker": "Speaker 1",
                },
            },
        )

        assert response.status_code == 200


class TestChatAfterTranscription:
    """Test RAG chat functionality after transcription."""

    @pytest.mark.asyncio
    async def test_rag_chat(self, async_client):
        """RAG chat should return answers with citations."""
        response = await async_client.post(
            "/api/chat",
            json={
                "message": "What was discussed?",
                "max_context_chunks": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert "citations" in data
        assert "conversation_id" in data

        print(f"\n💬 Chat response ({data['processing_time_ms']}ms):")
        print(f"   Answer: {data['answer'][:200]}...")
        print(f"   Citations: {len(data['citations'])}")


class TestAPIValidation:
    """Test API input validation."""

    @pytest.mark.asyncio
    async def test_search_query_validation(self, async_client):
        """Search should validate query length."""
        # Empty query
        response = await async_client.post(
            "/api/search",
            json={"query": ""},
        )
        assert response.status_code == 422

        # Too long query
        response = await async_client.post(
            "/api/search",
            json={"query": "a" * 1000},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_limit_validation(self, async_client):
        """Search should validate limit parameter."""
        # Too high
        response = await async_client.post(
            "/api/search",
            json={"query": "test", "limit": 1000},
        )
        assert response.status_code == 422

        # Too low
        response = await async_client.post(
            "/api/search",
            json={"query": "test", "limit": 0},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_admin_auth_required(self, async_client):
        """Admin endpoints should require authentication."""
        response = await async_client.post(
            "/api/channels",
            json={"name": "Test", "youtube_channel_id": "UC123"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_youtube_url(self, async_client, admin_headers):
        """Should reject invalid YouTube URLs."""
        response = await async_client.post(
            "/api/channels/fetch",
            json={"youtube_url": "not-a-youtube-url"},
            headers=admin_headers,
        )
        assert response.status_code == 400


# Standalone runner for quick testing
if __name__ == "__main__":
    import subprocess
    import sys

    print("🚀 Running E2E Smoke Tests")
    print("=" * 50)
    print("⚠️  WARNING: These tests use real APIs and cost money!")
    print("=" * 50)

    # Set environment variable to enable tests
    os.environ["RUN_E2E_TESTS"] = "true"

    # Run pytest
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            __file__,
            "-v",
            "--tb=short",
            "-x",  # Stop on first failure
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )

    sys.exit(result.returncode)
