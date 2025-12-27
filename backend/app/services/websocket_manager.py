"""
WebSocket Manager for real-time updates.

Manages WebSocket connections and broadcasts job/batch updates
via Redis PubSub for cross-process communication.
"""
import asyncio
import json
from typing import Dict, Set, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from fastapi import WebSocket
from loguru import logger
import redis.asyncio as redis

from app.config import settings


@dataclass
class JobUpdate:
    """Job progress update message."""
    type: str = "job_update"
    job_id: str = ""
    batch_id: str = ""
    episode_id: str = ""
    status: str = ""
    progress: int = 0
    current_step: str = ""
    error_message: str | None = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class BatchUpdate:
    """Batch progress update message."""
    type: str = "batch_update"
    batch_id: str = ""
    status: str = ""
    completed_episodes: int = 0
    failed_episodes: int = 0
    total_episodes: int = 0
    progress_percent: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class ConnectionManager:
    """Manages WebSocket connections and subscriptions."""

    def __init__(self):
        # Active connections: websocket -> set of subscribed channels
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # Channel to connections mapping for efficient broadcasting
        self.channel_connections: Dict[str, Set[WebSocket]] = {}
        # Redis pubsub for cross-process communication
        self._redis: redis.Redis | None = None
        self._pubsub_task: asyncio.Task | None = None

    async def get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection."""
        if not settings.REDIS_URL:
            return None
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                logger.info("WebSocket manager connected to Redis")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._redis = None
        return self._redis

    async def start_pubsub_listener(self):
        """Start listening for Redis pubsub messages."""
        redis_client = await self.get_redis()
        if not redis_client:
            logger.warning("Redis not available, WebSocket updates will be local only")
            return

        async def listener():
            try:
                pubsub = redis_client.pubsub()
                await pubsub.psubscribe("ws:*")
                logger.info("Started Redis pubsub listener for WebSocket updates")

                async for message in pubsub.listen():
                    if message["type"] == "pmessage":
                        channel = message["channel"]
                        data = message["data"]
                        try:
                            # Extract the actual channel name (remove ws: prefix)
                            ws_channel = channel.replace("ws:", "", 1)
                            await self._broadcast_to_channel(ws_channel, data)
                        except Exception as e:
                            logger.error(f"Error broadcasting message: {e}")
            except asyncio.CancelledError:
                logger.info("Pubsub listener cancelled")
            except Exception as e:
                logger.error(f"Pubsub listener error: {e}")

        self._pubsub_task = asyncio.create_task(listener())

    async def stop_pubsub_listener(self):
        """Stop the Redis pubsub listener."""
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()

    async def connect(self, websocket: WebSocket, channels: list[str] | None = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[websocket] = set()

        # Subscribe to requested channels
        if channels:
            for channel in channels:
                await self.subscribe(websocket, channel)

        logger.info(f"WebSocket connected, total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            # Unsubscribe from all channels
            for channel in list(self.active_connections[websocket]):
                self._unsubscribe_internal(websocket, channel)
            del self.active_connections[websocket]

        logger.info(f"WebSocket disconnected, remaining: {len(self.active_connections)}")

    async def subscribe(self, websocket: WebSocket, channel: str):
        """Subscribe a connection to a channel."""
        if websocket not in self.active_connections:
            return

        self.active_connections[websocket].add(channel)

        if channel not in self.channel_connections:
            self.channel_connections[channel] = set()
        self.channel_connections[channel].add(websocket)

        logger.debug(f"Subscribed to channel: {channel}")

    def _unsubscribe_internal(self, websocket: WebSocket, channel: str):
        """Internal unsubscribe without async."""
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(channel)

        if channel in self.channel_connections:
            self.channel_connections[channel].discard(websocket)
            if not self.channel_connections[channel]:
                del self.channel_connections[channel]

    async def unsubscribe(self, websocket: WebSocket, channel: str):
        """Unsubscribe a connection from a channel."""
        self._unsubscribe_internal(websocket, channel)

    async def _broadcast_to_channel(self, channel: str, message: str):
        """Broadcast message to all connections subscribed to a channel."""
        if channel not in self.channel_connections:
            return

        dead_connections = []
        for websocket in self.channel_connections[channel]:
            try:
                await websocket.send_text(message)
            except Exception:
                dead_connections.append(websocket)

        # Clean up dead connections
        for websocket in dead_connections:
            self.disconnect(websocket)

    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected clients."""
        message_str = json.dumps(message)
        dead_connections = []

        for websocket in self.active_connections:
            try:
                await websocket.send_text(message_str)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


# Global connection manager instance
manager = ConnectionManager()


async def publish_job_update(
    job_id: str,
    batch_id: str | None,
    episode_id: str,
    status: str,
    progress: int = 0,
    current_step: str = "",
    error_message: str | None = None,
):
    """
    Publish a job update to Redis for broadcasting.

    This can be called from Celery tasks or anywhere else.
    """
    update = JobUpdate(
        job_id=job_id,
        batch_id=batch_id or "",
        episode_id=episode_id,
        status=status,
        progress=progress,
        current_step=current_step,
        error_message=error_message,
        timestamp=datetime.utcnow().isoformat(),
    )

    message = json.dumps(update.to_dict())

    # Publish to Redis for cross-process broadcasting
    redis_client = await manager.get_redis()
    if redis_client:
        try:
            # Publish to job-specific channel
            await redis_client.publish(f"ws:job:{job_id}", message)
            # Also publish to batch channel if applicable
            if batch_id:
                await redis_client.publish(f"ws:batch:{batch_id}", message)
            # Publish to global updates channel
            await redis_client.publish("ws:updates", message)
        except Exception as e:
            logger.error(f"Failed to publish job update to Redis: {e}")
    else:
        # Fallback to direct broadcast if Redis not available
        await manager._broadcast_to_channel(f"job:{job_id}", message)
        if batch_id:
            await manager._broadcast_to_channel(f"batch:{batch_id}", message)
        await manager._broadcast_to_channel("updates", message)


async def publish_batch_update(
    batch_id: str,
    status: str,
    completed_episodes: int = 0,
    failed_episodes: int = 0,
    total_episodes: int = 0,
):
    """Publish a batch update to Redis for broadcasting."""
    progress_percent = 0.0
    if total_episodes > 0:
        progress_percent = ((completed_episodes + failed_episodes) / total_episodes) * 100

    update = BatchUpdate(
        batch_id=batch_id,
        status=status,
        completed_episodes=completed_episodes,
        failed_episodes=failed_episodes,
        total_episodes=total_episodes,
        progress_percent=progress_percent,
        timestamp=datetime.utcnow().isoformat(),
    )

    message = json.dumps(update.to_dict())

    redis_client = await manager.get_redis()
    if redis_client:
        try:
            await redis_client.publish(f"ws:batch:{batch_id}", message)
            await redis_client.publish("ws:updates", message)
        except Exception as e:
            logger.error(f"Failed to publish batch update to Redis: {e}")
    else:
        await manager._broadcast_to_channel(f"batch:{batch_id}", message)
        await manager._broadcast_to_channel("updates", message)
