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