"""Celery application configuration."""

from celery import Celery
from app.config import settings

# Create Celery app
celery_app = Celery(
    "podcast_search",
    broker=settings.REDIS_URL or "redis://localhost:6379/0",
    backend=settings.REDIS_URL or "redis://localhost:6379/0",
    include=[
        "app.tasks.transcription",
        "app.tasks.embedding",
        "app.tasks.maintenance",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 min soft limit
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (prevent memory leaks)
    # Result backend
    result_expires=86400,  # Results expire after 24 hours
    # Rate limiting
    task_default_rate_limit="100/m",
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-old-audio-files": {
            "task": "app.tasks.maintenance.cleanup_audio_files",
            "schedule": 3600.0,  # Every hour
        },
        "update-channel-stats": {
            "task": "app.tasks.maintenance.update_channel_stats",
            "schedule": 300.0,  # Every 5 minutes
        },
        "refresh-embedding-cache": {
            "task": "app.tasks.maintenance.refresh_popular_embeddings",
            "schedule": 1800.0,  # Every 30 minutes
        },
    },
)

# Task routing
celery_app.conf.task_routes = {
    "app.tasks.transcription.*": {"queue": "transcription"},
    "app.tasks.embedding.*": {"queue": "embedding"},
    "app.tasks.maintenance.*": {"queue": "maintenance"},
}

# Priority queues
celery_app.conf.task_queues = {
    "transcription": {
        "exchange": "transcription",
        "routing_key": "transcription",
    },
    "embedding": {
        "exchange": "embedding",
        "routing_key": "embedding",
    },
    "maintenance": {
        "exchange": "maintenance",
        "routing_key": "maintenance",
    },
}
