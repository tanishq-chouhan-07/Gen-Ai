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