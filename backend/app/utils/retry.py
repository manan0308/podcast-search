"""Retry and circuit breaker utilities for external API calls."""

import asyncio
import time
from functools import wraps
from typing import Callable, TypeVar, Any
from enum import Enum
from dataclasses import dataclass, field
from loguru import logger

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for external API calls.

    Prevents cascading failures by temporarily blocking calls
    to failing services.

    Usage:
        breaker = CircuitBreaker(name="openai", failure_threshold=5)

        @breaker
        async def call_openai():
            ...
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds
    half_open_max_calls: int = 3

    # State
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for recovery."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN")
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (test failed)")
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit {self.name}: CLOSED -> OPEN "
                f"(failures: {self._failure_count})"
            )

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap function with circuit breaker."""

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if self.state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit {self.name} is open. "
                    f"Retry after {self.recovery_timeout}s"
                )

            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure()
                raise

        return wrapper


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


def retry_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Async retry decorator with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exceptions to retry on

    Usage:
        @retry_async(max_retries=3, exceptions=(APIError,))
        async def call_api():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Add jitter (10% random variation)
                        import random

                        jitter = delay * 0.1 * (random.random() * 2 - 1)
                        sleep_time = min(delay + jitter, max_delay)

                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: "
                            f"{e}. Waiting {sleep_time:.2f}s"
                        )
                        await asyncio.sleep(sleep_time)
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        logger.error(
                            f"All {max_retries} retries failed for {func.__name__}: {e}"
                        )

            raise last_exception

        return wrapper

    return decorator


# Pre-configured circuit breakers for common services
openai_circuit = CircuitBreaker(name="openai", failure_threshold=5, recovery_timeout=60)
anthropic_circuit = CircuitBreaker(
    name="anthropic", failure_threshold=5, recovery_timeout=60
)
qdrant_circuit = CircuitBreaker(name="qdrant", failure_threshold=3, recovery_timeout=30)
