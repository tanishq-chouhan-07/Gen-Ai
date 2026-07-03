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
from app.db.database import create_all_tables, close_database
from app.db.redis_client import check_redis_connection, close_redis
from app.db.qdrant_client import ensure_collection_exists, close_qdrant
from app.api.v1.routers import health
from app.api.v1.routers import documents

setup_logging()
logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown.
    Every infrastructure connection is established here.
    """
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
    )
    logger.info("Initializing database tables...")
    try:
        await create_all_tables()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise 
    logger.info("Checking Redis connection...")
    redis_ok, redis_detail = await check_redis_connection()
    if redis_ok:
        logger.info("Redis connected", detail=redis_detail)
    else:
        logger.warning("Redis not available", detail=redis_detail)

    logger.info("Initializing Qdrant collection...")
    try:
        await ensure_collection_exists()
        logger.info("Qdrant collection ready")
    except Exception as e:
        logger.warning("Qdrant initialization failed", error=str(e))

    logger.info("=" * 50)
    logger.info("Application ready to serve requests")
    logger.info("=" * 50)

    yield  

    logger.info("Application shutting down...")
    await close_database()
    await close_redis()
    await close_qdrant()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Enterprise AI assistant for company document Q&A",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-Correlation-ID",
            "X-Process-Time-Ms",
        ],
    )

    # ── Custom Middleware (last added = first to run) ──────────
    app.add_middleware(TimingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Exception Handlers ────────────────────────────────────
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    # ── Routers ───────────────────────────────────────────────
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")   # ← NEW

    return app

app = create_app()