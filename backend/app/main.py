from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from app.config import settings
from app.database import init_db
from app.routers import api_router
from app.services.vector_store import VectorStoreService
from app.services.websocket_manager import manager as ws_manager
from app.middleware.request_id import RequestIDMiddleware


# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.ENVIRONMENT == "development" else "INFO",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting Podcast Search API...")

    # Validate production secrets
    validation_errors = settings.validate_production_secrets()
    if validation_errors:
        for error in validation_errors:
            logger.error(f"Configuration error: {error}")
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                f"Production configuration invalid: {'; '.join(validation_errors)}"
            )
        else:
            logger.warning("Configuration issues detected (non-fatal in development)")

    # Initialize database tables
    # Note: In production, use Alembic migrations instead
    if settings.ENVIRONMENT == "development":
        await init_db()
        logger.info("Database initialized")

    # Ensure Qdrant collection exists
    vector_store = VectorStoreService()
    await vector_store.ensure_collection()
    logger.info("Vector store initialized")

    # Start WebSocket pubsub listener
    await ws_manager.start_pubsub_listener()
    logger.info("WebSocket manager initialized")

    yield

    # Stop WebSocket pubsub listener
    await ws_manager.stop_pubsub_listener()
    logger.info("Shutting down Podcast Search API...")


app = FastAPI(
    title="Podcast Search API",
    description="API for searching and chatting with podcast transcripts",
    version="1.0.0",
    lifespan=lifespan,
)

# Request ID middleware - must be added first (outermost)
app.add_middleware(RequestIDMiddleware)

# CORS middleware - uses settings for production safety
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Podcast Search API",
        "version": "1.0.0",
        "docs": "/docs",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/detailed")
async def health_detailed():
    """
    Detailed health check with component status.

    Includes:
    - Database connection pool stats
    - Redis connectivity
    - Qdrant connectivity
    """
    from app.database import async_engine
    from app.services.cache import CacheService
    from app.services.vector_store import VectorStoreService

    health_status = {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "components": {},
    }

    # Database pool status
    pool = async_engine.pool
    health_status["components"]["database"] = {
        "status": "healthy",
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalidatedcount() if hasattr(pool, 'invalidatedcount') else 0,
    }

    # Check if pool is near exhaustion
    available = pool.size() - pool.checkedout() + (10 - pool.overflow())  # max_overflow=10
    if available < 3:
        health_status["components"]["database"]["status"] = "degraded"
        health_status["components"]["database"]["warning"] = "Connection pool nearly exhausted"

    # Redis status
    try:
        cache = CacheService()
        redis = await cache._get_redis()
        if redis:
            await redis.ping()
            health_status["components"]["redis"] = {"status": "healthy"}
        else:
            health_status["components"]["redis"] = {"status": "not_configured"}
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Qdrant status
    try:
        vector_store = VectorStoreService()
        collections = await vector_store.client.get_collections()
        health_status["components"]["qdrant"] = {
            "status": "healthy",
            "collections": len(collections.collections),
        }
    except Exception as e:
        health_status["components"]["qdrant"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Overall status
    component_statuses = [c.get("status") for c in health_status["components"].values()]
    if "unhealthy" in component_statuses:
        health_status["status"] = "unhealthy"
    elif "degraded" in component_statuses:
        health_status["status"] = "degraded"

    return health_status
