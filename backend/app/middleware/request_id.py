"""Request ID middleware for tracking requests across services."""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable for request ID (accessible from any async code)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique ID to each request.

    The request ID is:
    - Stored in context variable for logging
    - Added to response headers (X-Request-ID)
    - Can be provided by client (X-Request-ID header)

    Usage:
        from app.middleware.request_id import get_request_id

        logger.info(f"Processing request {get_request_id()}")
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID or generate new one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Set in context for logging
        token = request_id_ctx.set(request_id)

        try:
            # Add to request state for easy access
            request.state.request_id = request_id

            # Process request
            response = await call_next(request)

            # Add to response headers
            response.headers["X-Request-ID"] = request_id

            return response
        finally:
            # Reset context
            request_id_ctx.reset(token)
