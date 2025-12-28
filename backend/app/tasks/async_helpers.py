"""
Async helpers for Celery tasks.

Provides efficient async execution in sync Celery context.
Reuses event loop per worker instead of creating new loop per task.
"""

import asyncio
import threading
from typing import Coroutine, TypeVar

T = TypeVar("T")

# Thread-local storage for event loops (one per Celery worker thread)
_thread_local = threading.local()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Get or create an event loop for the current thread.

    Reuses the same loop for all tasks in a worker thread,
    avoiding the overhead of creating new loops per task.
    """
    if (
        not hasattr(_thread_local, "loop")
        or _thread_local.loop is None
        or _thread_local.loop.is_closed()
    ):
        _thread_local.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_thread_local.loop)
    return _thread_local.loop


def run_async(coro: Coroutine[None, None, T]) -> T:
    """
    Run async coroutine in sync context efficiently.

    Uses thread-local event loop instead of creating new loop each time.
    This significantly reduces overhead for Celery tasks.

    Args:
        coro: Async coroutine to run

    Returns:
        Result of the coroutine
    """
    loop = get_event_loop()
    return loop.run_until_complete(coro)


def cleanup_loop():
    """
    Cleanup the thread-local event loop.

    Call this when worker is shutting down.
    """
    if hasattr(_thread_local, "loop") and _thread_local.loop is not None:
        if not _thread_local.loop.is_closed():
            _thread_local.loop.close()
        _thread_local.loop = None
