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