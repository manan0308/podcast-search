from fastapi import APIRouter

from app.routers import channels, episodes, batches, jobs, search, chat, providers, websocket

api_router = APIRouter()

api_router.include_router(channels.router, prefix="/channels", tags=["channels"])
api_router.include_router(episodes.router, prefix="/episodes", tags=["episodes"])
api_router.include_router(batches.router, prefix="/batches", tags=["batches"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
api_router.include_router(websocket.router, tags=["websocket"])
