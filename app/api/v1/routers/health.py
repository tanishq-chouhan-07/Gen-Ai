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
from app.db.database import check_database_connection
from app.db.redis_client import check_redis_connection
from app.db.qdrant_client import check_qdrant_connection

router = APIRouter(prefix="/health", tags=["Health"])
logger = structlog.get_logger()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness Check",
    description="Basic check that the application process is alive.",
)
async def health_check() -> HealthResponse:
    """
    Liveness endpoint - just confirms the app is running.
    No dependency checks here - those belong in /ready.
    """
    settings = get_settings()

    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc),
        request_id=get_request_id(),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description="Checks all dependencies. Returns 200 only when fully ready.",
)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness endpoint - checks every dependency the app needs.
    Load balancers use this to decide whether to send traffic here.
    """
    settings = get_settings()
    components = []
    all_ready = True

    # ── Check 1: Configuration ────────────────────────────────
    api_key_ok = bool(settings.gemini_api_key)
    components.append(ComponentStatus(
        name="configuration",
        status="healthy" if api_key_ok else "unhealthy",
        details=(
            f"Provider: {settings.llm_provider} | "
            f"API Key: {'present' if api_key_ok else 'MISSING'}"
        ),
    ))
    if not api_key_ok:
        all_ready = False

    # ── Check 2: PostgreSQL ───────────────────────────────────
    db_ok, db_detail = await check_database_connection()
    components.append(ComponentStatus(
        name="postgresql",
        status="healthy" if db_ok else "unhealthy",
        details=db_detail,
    ))
    if not db_ok:
        all_ready = False

    # ── Check 3: Redis ────────────────────────────────────────
    redis_ok, redis_detail = await check_redis_connection()
    components.append(ComponentStatus(
        name="redis",
        status="healthy" if redis_ok else "unhealthy",
        details=redis_detail,
    ))
    if not redis_ok:
        all_ready = False

    # ── Check 4: Qdrant ───────────────────────────────────────
    qdrant_ok, qdrant_detail = await check_qdrant_connection()
    components.append(ComponentStatus(
        name="qdrant",
        status="healthy" if qdrant_ok else "unhealthy",
        details=qdrant_detail,
    ))
    if not qdrant_ok:
        all_ready = False

    logger.info(
        "Readiness check completed",
        status="ready" if all_ready else "not_ready",
        request_id=get_request_id(),
    )

    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        components=components,
        timestamp=datetime.now(timezone.utc),
        request_id=get_request_id(),
    )