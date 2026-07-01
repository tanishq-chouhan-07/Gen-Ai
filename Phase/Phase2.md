# Phase 2: Middleware + Request IDs + Error Handling

Great work on Phase 1. Now we add the production-grade middleware layer. This is what separates a toy project from a real system — every request gets tracked, every error gets classified, every response gets timed.

---

## Phase 2 Game Plan

```
Step 1 → Request ID Middleware       (every request gets a unique ID)
Step 2 → Correlation ID Middleware   (track requests across services)
Step 3 → Request Timing Middleware   (measure every request duration)
Step 4 → Error Classification        (know what kind of error happened)
Step 5 → Global Exception Handler    (never leak raw errors to clients)
Step 6 → Wire everything into main   (plug all middleware in)
Step 7 → Update Health endpoints     (include request IDs in responses)
Step 8 → Run and verify everything   (test all middleware working)
```

---

## STEP 1 — Request ID Middleware

Every single HTTP request that enters our system gets a unique ID stamped on it immediately. This ID travels through every log line so you can trace exactly what happened for any request.

### 1.1 Install one missing dependency

Stop the running server first with `Ctrl + C`, then:

```bash
pip install asgiref==3.8.1
```

Add it to `requirements.txt` as well:

```txt
# Web Framework
fastapi==0.115.5
uvicorn[standard]==0.32.1

# Configuration
pydantic==2.10.3
pydantic-settings==2.6.1

# LLM Providers
google-generativeai==0.8.3

# Logging
structlog==24.4.0

# HTTP Client
httpx==0.28.1

# Utilities
python-multipart==0.0.12
python-dotenv==1.0.1
asgiref==3.8.1
```

### 1.2 Create context vars file

We need a way to store the request ID so any part of the code can read it without passing it as a parameter everywhere. Python's `contextvars` is perfect for this.

Create `app/utils/context.py`:

```python
# app/utils/context.py
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
```

### 1.3 Create `app/middleware/request_id.py`

```python
# app/middleware/request_id.py
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
```

---

## STEP 2 — Correlation ID Middleware

The Request ID identifies one HTTP request. The Correlation ID links a whole chain of related operations together. For example: upload a document triggers a background job — both share the same correlation ID.

Create `app/middleware/correlation_id.py`:

```python
# app/middleware/correlation_id.py
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
```

---

## STEP 3 — Request Timing Middleware

Every request gets timed. The duration appears in the response header and in the logs. This is how you spot slow endpoints in production.

Create `app/middleware/timing.py`:

```python
# app/middleware/timing.py
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
```

---

## STEP 4 — Error Classification

Before we handle errors, we need to know what kind of error we are dealing with. Different error types deserve different responses.

Create `app/utils/error_classifier.py`:

```python
# app/utils/error_classifier.py
"""
Error Classifier

Not all errors are equal. This classifier tells us:
- Is the error transient? (network blip, rate limit) → client should retry
- Is it a provider error? (Gemini/Bedrock down) → different message
- Is it a client error? (bad input) → 400, don't retry
- Is it our bug? (unhandled exception) → 500, investigate

This classification drives:
1. What HTTP status code to return
2. What message to show the client
3. Whether to suggest retrying
4. How urgently to alert the team
"""
from dataclasses import dataclass
from typing import Type


@dataclass
class ErrorClassification:
    """Result of classifying an exception."""
    error_type: str          # Class name of the exception
    http_status_code: int    # What HTTP status to return
    is_transient: bool       # Should the client retry?
    is_provider_error: bool  # Is it a LLM/external API error?
    is_client_error: bool    # Is it the client's fault?
    user_message: str        # Safe message to show the user
    log_level: str           # How urgently to log this


# Patterns that indicate a transient (temporary) error
_TRANSIENT_PATTERNS = [
    "timeout",
    "rate limit",
    "rate_limit",
    "429",
    "503",
    "502",
    "connection",
    "throttl",
    "too many requests",
    "temporarily unavailable",
    "service unavailable",
    "try again",
]

# Patterns that indicate an LLM/external API provider error
_PROVIDER_PATTERNS = [
    "gemini",
    "generativeai",
    "bedrock",
    "anthropic",
    "google",
    "aws",
    "api key",
    "invalid api",
    "quota exceeded",
]

# Exception types that are always the client's fault
_CLIENT_ERROR_TYPES: tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
)


def classify_error(exc: Exception) -> ErrorClassification:
    """
    Classify an exception and return structured information about it.

    Usage:
        try:
            result = await llm.generate(...)
        except Exception as e:
            classification = classify_error(e)
            return JSONResponse(
                status_code=classification.http_status_code,
                content={"error": classification.user_message}
            )
    """
    error_str = str(exc).lower()
    error_type = type(exc).__name__

    # Check patterns
    is_transient = any(p in error_str for p in _TRANSIENT_PATTERNS)
    is_provider = any(p in error_str for p in _PROVIDER_PATTERNS)
    is_client = isinstance(exc, _CLIENT_ERROR_TYPES)

    # Determine HTTP status code
    if is_client:
        status_code = 400
    elif is_transient:
        status_code = 503
    elif is_provider:
        status_code = 502
    else:
        status_code = 500

    # Determine log level
    if is_client:
        log_level = "warning"
    elif is_transient:
        log_level = "warning"
    else:
        log_level = "error"

    # Determine user-safe message
    if is_client:
        user_message = f"Invalid request: {str(exc)}"
    elif is_transient:
        user_message = (
            "The service is temporarily unavailable. "
            "Please try again in a few seconds."
        )
    elif is_provider:
        user_message = (
            "The AI provider is currently unavailable. "
            "Please try again shortly."
        )
    else:
        user_message = (
            "An unexpected error occurred. "
            "Please try again or contact support."
        )

    return ErrorClassification(
        error_type=error_type,
        http_status_code=status_code,
        is_transient=is_transient,
        is_provider_error=is_provider,
        is_client_error=is_client,
        user_message=user_message,
        log_level=log_level,
    )
```

---

## STEP 5 — Global Exception Handler

Now we use the classifier to build a proper global exception handler that never leaks internal details to clients.

Create `app/middleware/error_handler.py`:

```python
# app/middleware/error_handler.py
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
```

---

## STEP 6 — Update Logging to Include Request Context

Now we upgrade the logging setup so every single log line automatically includes the request ID and correlation ID — without anyone having to pass them manually.

Update `app/observability/logging.py` (replace the whole file):

```python
# app/observability/logging.py
"""
Structured Logging Setup

Every log line automatically includes:
- timestamp (ISO format)
- log level
- request_id (from context var)
- correlation_id (from context var)
- filename and line number (in development)

In development: colored, human-readable output
In production: JSON format for log aggregation (CloudWatch, Loki, etc.)
"""
import logging
import structlog
from app.config.settings import get_settings


def add_request_context(logger, method, event_dict):
    """
    Structlog processor that injects request context into every log line.
    This runs automatically on every log call.
    """
    # Import here to avoid circular imports
    from app.utils.context import get_request_id, get_correlation_id

    request_id = get_request_id()
    correlation_id = get_correlation_id()

    # Only add if they have real values
    if request_id != "no-request-id":
        event_dict["request_id"] = request_id

    if correlation_id != "no-correlation-id":
        event_dict["correlation_id"] = correlation_id

    return event_dict


def setup_logging() -> None:
    """
    Configure structured logging for the entire application.

    Call this once at application startup.
    After this, any code can do:
        logger = structlog.get_logger()
        logger.info("Something happened", key="value")
    And it will automatically include request_id, correlation_id, timestamp.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure Python's standard logging
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        force=True,
    )

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Choose renderer based on environment
    if settings.environment == "development":
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    # Build the processor chain
    # Each processor transforms the log event dict before rendering
    processors = [
        # Add log level name
        structlog.stdlib.add_log_level,
        # Add ISO timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Inject request_id and correlation_id automatically
        add_request_context,
        # Handle exceptions nicely
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        # Final rendering
        renderer,
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

---

## STEP 7 — Update Health Schemas and Endpoints

Now update the health schemas to include request IDs in responses.

Update `app/api/schemas/health.py` (replace the whole file):

```python
# app/api/schemas/health.py
from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class HealthResponse(BaseModel):
    """Response model for the basic health check endpoint."""
    status: Literal["healthy", "unhealthy"]
    app_name: str
    version: str
    environment: str
    timestamp: datetime
    request_id: str = ""


class ComponentStatus(BaseModel):
    """Status of a single system component."""
    name: str
    status: Literal["healthy", "degraded", "unhealthy"]
    details: str = ""


class ReadinessResponse(BaseModel):
    """Response model for the readiness check endpoint."""
    status: Literal["ready", "not_ready"]
    components: list[ComponentStatus]
    timestamp: datetime
    request_id: str = ""


class ErrorDetail(BaseModel):
    """Structured error response."""
    message: str
    error_type: str = ""
    request_id: str = ""
    retry_recommended: bool = False
    details: list[dict] = []


class ErrorResponse(BaseModel):
    """Top-level error response wrapper."""
    error: ErrorDetail
```

Update `app/api/v1/routers/health.py` (replace the whole file):

```python
# app/api/v1/routers/health.py
from fastapi import APIRouter
from datetime import datetime, timezone
import structlog

from app.api.schemas.health import (
    HealthResponse,
    ReadinessResponse,
    ComponentStatus,
)
from app.config.settings import get_settings
from app.utils.context import get_request_id, get_correlation_id

router = APIRouter(prefix="/health", tags=["Health"])
logger = structlog.get_logger()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness Check",
    description=(
        "Basic check that the application process is alive. "
        "Used by load balancers and container orchestration. "
        "Does NOT check external dependencies."
    ),
)
async def health_check() -> HealthResponse:
    """
    Liveness endpoint.
    Returns 200 as long as the app process is running.
    """
    settings = get_settings()
    request_id = get_request_id()

    logger.debug(
        "Health check requested",
        request_id=request_id,
    )

    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc),
        request_id=request_id,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description=(
        "Checks if the application is ready to serve traffic. "
        "Verifies configuration is valid. "
        "In later phases: will check Qdrant, Redis, and Database."
    ),
)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness endpoint.
    Currently checks configuration only.
    Will be expanded in Phase 3 to check all dependencies.
    """
    settings = get_settings()
    request_id = get_request_id()
    components = []
    all_ready = True

    # ── Check 1: Configuration ────────────────────────────────
    api_key_present = bool(settings.gemini_api_key)
    config_healthy = bool(settings.app_name and settings.llm_provider)

    components.append(ComponentStatus(
        name="configuration",
        status="healthy" if config_healthy else "unhealthy",
        details=(
            f"Provider: {settings.llm_provider} | "
            f"Model: {settings.gemini_model} | "
            f"API Key: {'present' if api_key_present else 'MISSING'}"
        ),
    ))

    if not config_healthy:
        all_ready = False

    # ── Log the readiness check ───────────────────────────────
    logger.info(
        "Readiness check completed",
        status="ready" if all_ready else "not_ready",
        component_count=len(components),
        request_id=request_id,
        correlation_id=get_correlation_id(),
    )

    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        components=components,
        timestamp=datetime.now(timezone.utc),
        request_id=request_id,
    )
```

---

## STEP 8 — Wire Everything into `app/main.py`

Now update `app/main.py` to plug in all the middleware (replace the whole file):

```python
# app/main.py
"""
Application Entry Point

This file:
1. Creates the FastAPI application
2. Registers all middleware (in the correct order)
3. Registers all exception handlers
4. Registers all routers
5. Handles startup and shutdown

Middleware execution order (outermost to innermost):
    Request  → TimingMiddleware → CorrelationIDMiddleware → RequestIDMiddleware → Router
    Response ← TimingMiddleware ← CorrelationIDMiddleware ← RequestIDMiddleware ← Router

IMPORTANT: Middleware added LAST runs FIRST on requests.
So we add RequestIDMiddleware last → it runs first → sets the ID
before CorrelationIDMiddleware and TimingMiddleware need it.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from app.config.settings import get_settings
from app.observability.logging import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.correlation_id import CorrelationIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.middleware.error_handler import (
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.api.v1.routers import health

# ── Setup logging before anything else ───────────────────────
# This must be the first thing that runs
setup_logging()
logger = structlog.get_logger()
settings = get_settings()


# ── Application Lifespan ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown lifecycle manager.
    Add startup checks here as we build more phases.
    """
    # ── STARTUP ──────────────────────────────────────────────
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        model=settings.gemini_model,
    )

    # Future phases will add:
    # - Qdrant connection check
    # - Redis connection check
    # - Database connection + migrations
    # - Prompt registry loading

    logger.info("All startup checks passed. Ready to serve requests.")

    yield  # ← Application runs here

    # ── SHUTDOWN ─────────────────────────────────────────────
    logger.info("Application shutting down gracefully")


# ── Application Factory ───────────────────────────────────────
def create_app() -> FastAPI:
    """
    Creates and fully configures the FastAPI application.

    Using a factory function (instead of module-level app = FastAPI())
    makes testing easier - tests can call create_app() to get a fresh instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Enterprise AI assistant for company document Q&A. "
            "Upload PDFs, ask questions, get grounded answers with citations."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS Middleware ───────────────────────────────────────
    # Must be added before our custom middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],      # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[          # These headers are visible to browser JS
            "X-Request-ID",
            "X-Correlation-ID",
            "X-Process-Time-Ms",
        ],
    )

    # ── Custom Middleware ─────────────────────────────────────
    # Remember: LAST added = FIRST to run on incoming requests
    #
    # Execution order on REQUEST:
    #   1. RequestIDMiddleware   (sets request_id first - others need it)
    #   2. CorrelationIDMiddleware (uses request_id as fallback)
    #   3. TimingMiddleware      (starts timer, logs at end with IDs)
    #
    app.add_middleware(TimingMiddleware)           # runs 3rd on request
    app.add_middleware(CorrelationIDMiddleware)    # runs 2nd on request
    app.add_middleware(RequestIDMiddleware)        # runs 1st on request

    # ── Exception Handlers ────────────────────────────────────
    # Order matters: more specific handlers first
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )
    app.add_exception_handler(
        Exception,
        global_exception_handler,
    )

    # ── API Routers ───────────────────────────────────────────
    app.include_router(health.router, prefix="/api/v1")

    logger.info("Application factory complete")
    return app


# ── App Instance ─────────────────────────────────────────────
# uvicorn app.main:app uses this
app = create_app()
```

---

## STEP 9 — Verify Final File Structure

Before running, make sure your structure looks like this:

```bash
tree /F
```

Expected output:
```
C:\DOCUMENT-AI-AGENT
│   .env
│   .gitignore
│   requirements.txt
│
├───app
│   │   __init__.py
│   │   main.py
│   │
│   ├───api
│   │   │   __init__.py
│   │   │
│   │   ├───schemas
│   │   │       __init__.py
│   │   │       health.py
│   │   │
│   │   └───v1
│   │       │   __init__.py
│   │       │
│   │       └───routers
│   │               __init__.py
│   │               health.py
│   │
│   ├───config
│   │       __init__.py
│   │       model_table.py
│   │       settings.py
│   │
│   ├───middleware
│   │       __init__.py
│   │       correlation_id.py
│   │       error_handler.py
│   │       request_id.py
│   │       timing.py
│   │
│   ├───observability
│   │       __init__.py
│   │       logging.py
│   │
│   └───utils
│           __init__.py
│           context.py
│           error_classifier.py
│
└───tests
        __init__.py
```

---

## STEP 10 — Run and Verify Everything

### 10.1 Start the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see startup logs like this:
```
2024-01-15T10:30:00Z [info] Application starting app_name='Document AI Agent' ...
2024-01-15T10:30:00Z [info] All startup checks passed. Ready to serve requests.
2024-01-15T10:30:00Z [info] Application factory complete
```

### 10.2 Open a second terminal and run these tests one by one

Activate venv in the second terminal:
```bash
cd C:\document-ai-agent
venv\Scripts\activate
```

---

**Test 1 — Basic health check (check response headers):**

```bash
curl -v http://localhost:8000/api/v1/health
```

Look for these headers in the response:
```
X-Request-ID: some-uuid-here
X-Correlation-ID: same-uuid-here
X-Process-Time-Ms: 1.23
```

And the body:
```json
{
  "status": "healthy",
  "app_name": "Document AI Agent",
  "version": "1.0.0",
  "environment": "development",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "some-uuid-here"
}
```

---

**Test 2 — Send your own Request ID:**

```bash
curl -v -H "X-Request-ID: my-custom-id-12345" http://localhost:8000/api/v1/health
```

The response should echo back YOUR id:
```
X-Request-ID: my-custom-id-12345
```

And the body should contain:
```json
{
  "request_id": "my-custom-id-12345"
}
```

---

**Test 3 — Test error handling (hit a route that doesn't exist):**

```bash
curl -v http://localhost:8000/api/v1/nonexistent
```

Expected — a clean error, not a raw Python traceback:
```json
{
  "error": {
    "message": "Not Found",
    "request_id": "some-uuid"
  }
}
```

---

**Test 4 — Test validation error handling:**

```bash
curl -v -X POST http://localhost:8000/api/v1/health -H "Content-Type: application/json" -d "{\"invalid\": \"data\"}"
```

Expected — a structured validation error:
```json
{
  "error": {
    "message": "Not Found",
    "request_id": "some-uuid"
  }
}
```

---

**Test 5 — Check the server logs in terminal 1**

After running all the curl commands, look at the first terminal (where uvicorn is running). You should see structured log lines like:

```
2024-01-15T10:30:05Z [info] Request completed method='GET' path='/api/v1/health' status_code=200 duration_ms=1.23 request_id='abc-123' correlation_id='abc-123'
```

Notice: `request_id` and `correlation_id` appear automatically in every log line.

---

**Test 6 — Check Swagger UI**

Open your browser: `http://localhost:8000/docs`

You should see both health endpoints documented with proper request/response schemas.

---

## Phase 2 Complete — What We Built

```
Every HTTP request now goes through this pipeline:

  Incoming Request
       │
       ▼
  RequestIDMiddleware        ← Stamps every request with unique ID
       │
       ▼
  CorrelationIDMiddleware    ← Links related operations together
       │
       ▼
  TimingMiddleware           ← Starts the clock
       │
       ▼
  Your Router / Handler      ← Business logic runs here
       │
       ▼
  TimingMiddleware           ← Stops clock, logs full request details
       │
       ▼
  CorrelationIDMiddleware    ← Adds X-Correlation-ID to response
       │
       ▼
  RequestIDMiddleware        ← Adds X-Request-ID to response
       │
       ▼
  Client gets response with:
    - X-Request-ID header
    - X-Correlation-ID header
    - X-Process-Time-Ms header
    - Clean JSON error (if something went wrong)
```

---

**Tell me:**

1. Did the server start without errors?
2. Did Test 2 (custom request ID) echo your ID back?
3. Did Test 3 (404) return a clean JSON error?
4. Do the server logs show `request_id` in every line?

Once confirmed, we move to **Phase 3: Docker + Infrastructure Services** where we spin up Qdrant, Redis, and PostgreSQL with Docker Compose so Phase 4 (ingestion pipeline) has everything it needs.