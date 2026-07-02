"""
Context variables for request-scoped data.

contextvars work like thread-local storage but for async code.
Set a value at the start of a request, read it anywhere in that
request's call chain - even deep inside services and repositories.

This is how we get request_id into every log line automatically.
"""
from contextvars import ContextVar

# Stores the unique ID for the current request
request_id_var: ContextVar[str] = ContextVar(
    "request_id",
    default="no-request-id"
)

# Stores the correlation ID (links related requests together)
correlation_id_var: ContextVar[str] = ContextVar(
    "correlation_id",
    default="no-correlation-id"
)


def get_request_id() -> str:
    """Get the current request ID. Safe to call from anywhere."""
    return request_id_var.get()


def get_correlation_id() -> str:
    """Get the current correlation ID. Safe to call from anywhere."""
    return correlation_id_var.get()