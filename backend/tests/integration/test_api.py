"""Integration tests for API endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Root endpoint should return API info."""
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """Health endpoint should return healthy status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestSearchEndpoints:
    """Tests for search API endpoints."""

    @pytest.mark.asyncio
    async def test_search_requires_query(self, client: AsyncClient):
        """Search should require a query parameter."""
        response = await client.post("/api/search", json={})

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_validates_limit(self, client: AsyncClient):
        """Search should validate limit parameter."""
        # Too high
        response = await client.post(
            "/api/search",
            json={
                "query": "test",
                "limit": 1000,
            },
        )
        assert response.status_code == 422

        # Too low
        response = await client.post(
            "/api/search",
            json={
                "query": "test",
                "limit": 0,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_validates_query_length(self, client: AsyncClient):
        """Search should validate query length."""
        # Empty query
        response = await client.post(
            "/api/search",
            json={
                "query": "",
            },
        )
        assert response.status_code == 422

        # Too long query
        response = await client.post(
            "/api/search",
            json={
                "query": "a" * 1000,
            },
        )
        assert response.status_code == 422


class TestChannelEndpoints:
    """Tests for channel API endpoints."""

    @pytest.mark.asyncio
    async def test_list_channels(self, client: AsyncClient):
        """List channels should return empty list initially."""
        response = await client.get("/api/channels")

        assert response.status_code == 200
        data = response.json()
        assert "channels" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_channel_requires_auth(self, client: AsyncClient):
        """Create channel should require admin auth."""
        response = await client.post(
            "/api/channels",
            json={
                "name": "Test Channel",
                "youtube_channel_id": "UC123",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_fetch_channel_validates_url(
        self, client: AsyncClient, admin_headers
    ):
        """Fetch channel should validate YouTube URL."""
        response = await client.post(
            "/api/channels/fetch",
            json={"youtube_url": "not-a-valid-url"},
            headers=admin_headers,
        )

        # Should fail validation or return error
        assert response.status_code in [400, 422]


class TestAdminAuth:
    """Tests for admin authentication."""

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self, client: AsyncClient):
        """Missing auth should return 401."""
        response = await client.post(
            "/api/channels",
            json={
                "name": "Test",
                "youtube_channel_id": "UC123",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_auth_returns_401(self, client: AsyncClient):
        """Invalid auth should return 401."""
        response = await client.post(
            "/api/channels",
            json={"name": "Test", "youtube_channel_id": "UC123"},
            headers={"X-Admin-Secret": "wrong-secret"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_auth_works(self, client: AsyncClient, admin_headers):
        """Bearer token auth should work."""
        from app.config import settings

        response = await client.get(
            "/api/channels",
            headers={"Authorization": f"Bearer {settings.ADMIN_SECRET}"},
        )

        assert response.status_code == 200
