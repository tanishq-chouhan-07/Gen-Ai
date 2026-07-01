# app/api/v1/routers/health.py
from fastapi import APIRouter
from datetime import datetime, timezone
import structlog

from app.api.schemas.health import HealthResponse, ReadinessResponse, ComponentStatus
from app.config.settings import get_settings

router = APIRouter(prefix="/health", tags=["Health"])
logger = structlog.get_logger()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness Check",
    description="Basic check that the application is running. Used by load balancers.",
)
async def health_check() -> HealthResponse:
    """
    Liveness endpoint.
    If this returns 200, the application process is alive.
    Does NOT check dependencies (database, Qdrant, etc.)
    """
    settings = get_settings()
    logger.debug("Health check requested")

    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description="Checks if the application is ready to serve traffic.",
)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness endpoint.
    Checks that all critical dependencies are reachable.
    Returns 200 only when the app can actually serve requests.
    
    In Phase 1 we only check the app itself.
    In later phases we will add Qdrant, Redis, and DB checks.
    """
    settings = get_settings()
    components = []
    all_ready = True

    # App configuration check
    config_ok = bool(settings.app_name and settings.llm_provider)
    components.append(ComponentStatus(
        name="configuration",
        status="healthy" if config_ok else "unhealthy",
        details=f"Provider: {settings.llm_provider}, Model: {settings.gemini_model}",
    ))

    if not config_ok:
        all_ready = False

    logger.info(
        "Readiness check completed",
        status="ready" if all_ready else "not_ready",
        component_count=len(components),
    )

    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        components=components,
        timestamp=datetime.now(timezone.utc),
    )