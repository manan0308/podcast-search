"""
WebSocket router for real-time updates.

Provides WebSocket endpoints for:
- Job progress updates
- Batch status updates
- Global activity feed
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger

from app.services.websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channels: str = Query(
        default="updates",
        description="Comma-separated list of channels to subscribe to",
    ),
):
    """
    WebSocket endpoint for real-time updates.

    Query Parameters:
        channels: Comma-separated list of channels to subscribe to.
                  Examples:
                  - "updates" - All updates (default)
                  - "batch:abc123" - Updates for specific batch
                  - "job:xyz789" - Updates for specific job
                  - "batch:abc123,updates" - Multiple channels

    Message Types Received:
        - job_update: Job progress update
        - batch_update: Batch status update

    Client Commands (send as JSON):
        - {"action": "subscribe", "channel": "batch:abc123"}
        - {"action": "unsubscribe", "channel": "batch:abc123"}
        - {"action": "ping"} -> responds with {"type": "pong"}
    """
    # Parse initial channels
    channel_list = [c.strip() for c in channels.split(",") if c.strip()]

    await manager.connect(websocket, channel_list)

    try:
        while True:
            # Wait for client messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    channel = message.get("channel")
                    if channel:
                        await manager.subscribe(websocket, channel)
                        await websocket.send_json(
                            {
                                "type": "subscribed",
                                "channel": channel,
                            }
                        )

                elif action == "unsubscribe":
                    channel = message.get("channel")
                    if channel:
                        await manager.unsubscribe(websocket, channel)
                        await websocket.send_json(
                            {
                                "type": "unsubscribed",
                                "channel": channel,
                            }
                        )

                elif action == "ping":
                    await websocket.send_json({"type": "pong"})

                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Unknown action: {action}",
                        }
                    )

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                    }
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.debug("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/ws/batch/{batch_id}")
async def batch_websocket(websocket: WebSocket, batch_id: str):
    """
    WebSocket endpoint for a specific batch's updates.

    Automatically subscribes to the batch channel and global updates.
    """
    channels = [f"batch:{batch_id}", "updates"]
    await manager.connect(websocket, channels)

    try:
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong
            try:
                message = json.loads(data)
                if message.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Batch WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/ws/job/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for a specific job's updates.

    Automatically subscribes to the job channel.
    """
    channels = [f"job:{job_id}"]
    await manager.connect(websocket, channels)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Job WebSocket error: {e}")
        manager.disconnect(websocket)
