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