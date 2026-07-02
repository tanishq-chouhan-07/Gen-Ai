"""
Request Timing Middleware

Measures how long every request takes and adds the duration to:
- Response header X-Process-Time-Ms (client can see it)
- Log line (for monitoring and alerting)

This helps answer: "Which endpoints are slow?"
"""
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.context import get_request_id, get_correlation_id

logger = structlog.get_logger()


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that times every HTTP request.

    Adds X-Process-Time-Ms to every response.
    Logs request method, path, status code, and duration.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.monotonic()

        # Process the request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.monotonic() - start_time) * 1000

        # Add timing to response header
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"

        # Log every request with full context
        logger.info(
            "Request completed",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            request_id=get_request_id(),
            correlation_id=get_correlation_id(),
        )

        return response