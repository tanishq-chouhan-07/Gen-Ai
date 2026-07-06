# app/observability/tracing.py
"""
OpenTelemetry Tracing Setup

Configures tracing to export spans to an OTLP collector (Jaeger).
Uses HTTP protocol to avoid Windows gRPC compilation issues.
"""
import logging
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

def setup_tracing(app):
    """Initialize OpenTelemetry and instrument FastAPI."""
    settings = get_settings()
    
    resource = Resource.create({
        "service.name": "gen-ai-rag-api",
        "service.version": settings.app_version,
        "deployment.environment": settings.environment
    })
    
    provider = TracerProvider(resource=resource)
    
    # Export spans to Jaeger via OTLP HTTP
    # Docker maps localhost:4318 to the Jaeger container
    otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    trace.set_tracer_provider(provider)
    
    # Auto-instrument FastAPI routes
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry tracing initialized and FastAPI instrumented")