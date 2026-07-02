"""
Correlation ID Middleware

A Correlation ID links multiple operations that belong together.
Example: User uploads a PDF → background job starts → embeddings generated.
All three operations share the same correlation_id so you can find
them all in your logs with a single search.

How it works:
- Client can send X-Correlation-ID header (useful when calling from another service)
- If not provided, we use the request_id as the correlation_id
- This gets added to every log line and response header
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.context import correlation_id_var, get_request_id


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a correlation ID to every request.

    The correlation ID:
    - Links related requests and background jobs together
    - Is returned in X-Correlation-ID response header
    - Is stored in context var for logging
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Check if client or upstream service sent a correlation ID
        print("CorrelationIDMiddleware: Checking for X-Correlation-ID header...")
        correlation_id = request.headers.get("X-Correlation-ID")

        # If not, use the request ID (already set by RequestIDMiddleware)
        if not correlation_id:
            correlation_id = get_request_id()

        # Store in context var
        token = correlation_id_var.set(correlation_id)

        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)

        # Add to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response