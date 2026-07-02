"""
Global Exception Handler

This catches EVERY unhandled exception in the application and:
1. Classifies it (transient? provider? client? our bug?)
2. Logs it with full context (request ID, correlation ID, stack trace)
3. Returns a clean, safe response to the client
4. Never leaks internal details (stack traces, DB queries, etc.)

Without this, FastAPI would return a raw 500 with the exception
message - which can leak sensitive information and looks terrible.
"""
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.error_classifier import classify_error
from app.utils.context import get_request_id, get_correlation_id

logger = structlog.get_logger()


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """
    Handle known HTTP exceptions (404, 405, etc.)
    These are normal operational events, not bugs.
    """
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url.path),
        request_id=get_request_id(),
        correlation_id=get_correlation_id(),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "request_id": get_request_id(),
            }
        },
        headers={"X-Request-ID": get_request_id()},
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Handle Pydantic validation errors (bad request body, missing fields).
    These are always the client's fault → 422 Unprocessable Entity.
    """
    # Format validation errors into readable messages
    errors = []
    for error in exc.errors():
        field = " → ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })

    logger.warning(
        "Request validation failed",
        error_count=len(errors),
        path=str(request.url.path),
        request_id=get_request_id(),
        correlation_id=get_correlation_id(),
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": "Request validation failed",
                "request_id": get_request_id(),
                "details": errors,
            }
        },
        headers={"X-Request-ID": get_request_id()},
    )


async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Catch-all handler for any unhandled exception.
    This is the safety net that ensures nothing ugly reaches the client.
    """
    classification = classify_error(exc)

    # Log with appropriate level
    log_method = getattr(logger, classification.log_level, logger.error)
    log_method(
        "Unhandled exception",
        error_type=classification.error_type,
        error_message=str(exc),
        is_transient=classification.is_transient,
        is_provider_error=classification.is_provider_error,
        path=str(request.url.path),
        method=request.method,
        request_id=get_request_id(),
        correlation_id=get_correlation_id(),
        exc_info=True,  # Includes stack trace in logs
    )

    return JSONResponse(
        status_code=classification.http_status_code,
        content={
            "error": {
                "message": classification.user_message,
                "error_type": classification.error_type,
                "request_id": get_request_id(),
                "retry_recommended": classification.is_transient,
            }
        },
        headers={"X-Request-ID": get_request_id()},
    )