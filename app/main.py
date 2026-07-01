# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

from app.config.settings import get_settings
from app.observability.logging import setup_logging
from app.api.v1.routers import health

# ── Setup logging before anything else ───────────────────────
setup_logging()
logger = structlog.get_logger()
settings = get_settings()


# ── Application Lifespan ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.
    This replaces the old @app.on_event("startup") pattern.
    """
    # ── STARTUP ──────────────────────────────────────────────
    logger.info(
        "Starting application",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        model=settings.gemini_model,
    )

    yield  # Application runs here

    # ── SHUTDOWN ─────────────────────────────────────────────
    logger.info("Shutting down application")


# ── Create FastAPI App ────────────────────────────────────────
def create_app() -> FastAPI:
    """
    Application factory pattern.
    Creates and configures the FastAPI application.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Enterprise AI assistant for company document Q&A",
        docs_url="/docs",      # Swagger UI
        redoc_url="/redoc",    # ReDoc UI
        lifespan=lifespan,
    )

    # ── Register Routers ─────────────────────────────────────
    app.include_router(health.router, prefix="/api/v1")

    # ── Global Exception Handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            error=str(exc),
            path=str(request.url),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "An internal error occurred",
                    "type": type(exc).__name__,
                }
            },
        )

    logger.info("Application created successfully")
    return app


# ── App Instance ─────────────────────────────────────────────
app = create_app()