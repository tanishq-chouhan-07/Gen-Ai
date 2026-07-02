"""
Request ID Middleware

Every incoming HTTP request gets a unique ID.
If the client sends X-Request-ID header, we use that.
If not, we generate a new UUID4.

The ID is:
  - Stored in context var (accessible everywhere in this request)
  - Added to response headers (client can use it for support)
  - Injected into all log lines for this request
"""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.context import request_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique ID to every request.

    Priority order for request ID:
    1. X-Request-ID header from client (if provided)
    2. Generate a new UUID4

    The request ID is added to:
    - Response header X-Request-ID
    - Context variable (so logs can include it automatically)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Check if client sent a request ID
        print("RequestIDMiddleware: Checking for X-Request-ID header...")
        request_id = request.headers.get("X-Request-ID")

        # If not, generate one
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in context var - now any code in this request can read it
        token = request_id_var.set(request_id)

        try:
            # Process the request
            response = await call_next(request)
        finally:
            # Always reset context var after request (even on errors)
            request_id_var.reset(token)

        # Add request ID to response so client gets it back
        response.headers["X-Request-ID"] = request_id

        return response