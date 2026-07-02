# Phase 3: Docker & Infrastructure Services

We spin up Qdrant, Redis, and PostgreSQL with Docker Compose. By the end of this phase you will have all infrastructure services running locally and the app connecting to them with proper health checks.

---

## Phase 3 Game Plan

```
Step 1 → Create Docker Compose file
Step 2 → Create environment files
Step 3 → Add database connection + models
Step 4 → Add Redis connection
Step 5 → Add Qdrant connection
Step 6 → Update readiness check (check all services)
Step 7 → Update requirements
Step 8 → Run and verify everything
```

---

## STEP 1 — Docker Compose File

Create `docker-compose.yml` in the root folder (same level as `requirements.txt`):

```yaml
# docker-compose.yml
version: '3.9'

services:

  # ── Our FastAPI Application ───────────────────────────────
  app:
    build:
      context: .
      dockerfile: docker/Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      # Hot reload - code changes reflect immediately
      - .:/app
    env_file:
      - .env
    environment:
      - QDRANT_HOST=qdrant
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql+asyncpg://docai_user:docai_password@postgres:5432/docai_db
    depends_on:
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    networks:
      - docai_network

  # ── Qdrant Vector Database ────────────────────────────────
  qdrant:
    image: qdrant/qdrant:v1.9.0
    ports:
      - "6333:6333"   # REST API
      - "6334:6334"   # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - docai_network

  # ── Redis (Sessions + Cache + Job Tracking) ───────────────
  redis:
    image: redis:7.2-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s
    networks:
      - docai_network

  # ── PostgreSQL (Document Metadata + Job Tracking) ─────────
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: docai_user
      POSTGRES_PASSWORD: docai_password
      POSTGRES_DB: docai_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U docai_user -d docai_db"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - docai_network

# ── Named Volumes (data persists between restarts) ───────────
volumes:
  qdrant_data:
  redis_data:
  postgres_data:

# ── Network ───────────────────────────────────────────────────
networks:
  docai_network:
    driver: bridge
```

---

## STEP 2 — Create Docker Folder and Dockerfile

Create the `docker` folder:

```bash
mkdir docker
```

Create `docker/Dockerfile.dev`:

```dockerfile
# docker/Dockerfile.dev
# Development Dockerfile - optimized for hot reload and fast iteration
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run with hot reload for development
CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
```

---

## STEP 3 — Update Environment Files

Update your `.env` file (replace the whole file):

```env
# ── Application ───────────────────────────────────────────────
APP_NAME="Document AI Agent"
APP_VERSION="1.0.0"
ENVIRONMENT="development"
DEBUG=true

# ── LLM Provider ──────────────────────────────────────────────
LLM_PROVIDER="gemini"
EMBEDDING_PROVIDER="gemini"

# ── Gemini ────────────────────────────────────────────────────
GEMINI_API_KEY="your-gemini-api-key-here"
GEMINI_MODEL="gemini-1.5-flash"
GEMINI_EMBEDDING_MODEL="models/text-embedding-004"

# ── Qdrant ────────────────────────────────────────────────────
QDRANT_HOST="localhost"
QDRANT_PORT=6333
QDRANT_COLLECTION="company_documents"
QDRANT_VECTOR_SIZE=768

# ── Redis ─────────────────────────────────────────────────────
REDIS_URL="redis://localhost:6379"
SESSION_TTL_SECONDS=3600

# ── PostgreSQL ────────────────────────────────────────────────
DATABASE_URL="postgresql+asyncpg://docai_user:docai_password@localhost:5432/docai_db"

# ── Logging ───────────────────────────────────────────────────
LOG_LEVEL="DEBUG"

# ── Feature Flags ─────────────────────────────────────────────
ENABLE_STREAMING=true
ENABLE_CITATIONS=true
ENABLE_CONVERSATION_MEMORY=true
```

---

## STEP 4 — Update Requirements

Update `requirements.txt` (replace the whole file):

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

# Database - PostgreSQL
sqlalchemy==2.0.36
asyncpg==0.30.0
alembic==1.14.0

# Redis
redis==5.2.1

# Qdrant Vector Database
qdrant-client==1.12.1

# Utilities
python-multipart==0.0.12
python-dotenv==1.0.1
asgiref==3.8.1
```

Install the new dependencies:

```bash
pip install -r requirements.txt
```

Wait for it to finish. This will take 1-2 minutes.

---

## STEP 5 — Update Settings

Update `app/config/settings.py` to add the new connection settings (replace the whole file):

```python
# app/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    """
    Central configuration for the entire application.
    All values come from environment variables or the .env file.
    Nothing is hardcoded.
    """

    # ── Application ───────────────────────────────────────────
    app_name: str = "Document AI Agent"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # ── LLM Provider Selection ────────────────────────────────
    llm_provider: Literal["gemini", "bedrock"] = "gemini"
    embedding_provider: Literal["gemini", "bedrock", "local"] = "gemini"

    # ── Gemini (Development) ──────────────────────────────────
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = "gemini-1.5-flash"
    gemini_embedding_model: str = "models/text-embedding-004"

    # ── Amazon Bedrock (Production) ───────────────────────────
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    # ── Qdrant ────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "company_documents"
    qdrant_vector_size: int = 768

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 3600

    # ── PostgreSQL ────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://docai_user:docai_password@localhost:5432/docai_db",
        alias="DATABASE_URL",
    )

    # ── Document Processing ───────────────────────────────────
    max_file_size_mb: int = 50
    chunk_size: int = 512
    chunk_overlap: int = 128
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.7

    # ── Agent ─────────────────────────────────────────────────
    agent_max_iterations: int = 5
    agent_timeout_seconds: int = 30

    # ── Logging ───────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Feature Flags ─────────────────────────────────────────
    enable_streaming: bool = True
    enable_citations: bool = True
    enable_conversation_memory: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Created only once for the entire application lifetime.
    """
    return Settings()
```

---

## STEP 6 — Database Connection

Create `app/db/__init__.py`:

```bash
mkdir app\db
type nul > app\db\__init__.py
```

Create `app/db/database.py`:

```python
# app/db/database.py
"""
PostgreSQL database connection using SQLAlchemy async engine.

We use async SQLAlchemy so database queries never block the event loop.
This is critical for a FastAPI application that needs to handle
many concurrent requests.
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger()

# ── Base class for all database models ───────────────────────
class Base(DeclarativeBase):
    """
    All SQLAlchemy models inherit from this.
    Gives us .metadata for creating/dropping tables.
    """
    pass


# ── Module-level engine and session factory ───────────────────
# These are created once and reused for all requests
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            # Connection pool settings
            pool_size=5,          # Keep 5 connections ready
            max_overflow=10,      # Allow 10 more if needed
            pool_timeout=30,      # Wait max 30s for a connection
            pool_recycle=1800,    # Recycle connections every 30 min
            echo=settings.debug,  # Log SQL in debug mode
        )
        logger.info("Database engine created")
    return _engine


def get_session_factory() -> async_sessionmaker:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # Don't expire objects after commit
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def check_database_connection() -> tuple[bool, str]:
    """
    Test database connectivity.
    Returns (is_healthy, detail_message)
    Used by the readiness check endpoint.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "Connected successfully"
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False, str(e)


async def create_all_tables() -> None:
    """
    Create all database tables if they don't exist.
    Called at application startup.
    Safe to call multiple times - won't recreate existing tables.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created")


async def close_database() -> None:
    """
    Close database connections gracefully.
    Called at application shutdown.
    """
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connections closed")
```

---

## STEP 7 — Database Models

Create `app/db/models.py`:

```python
# app/db/models.py
"""
SQLAlchemy database models.

These define the actual database tables.
We keep them simple for now - just what Phase 4 (ingestion) needs.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.db.database import Base


def utc_now() -> datetime:
    """Helper to get current UTC time."""
    return datetime.now(timezone.utc)


# ── Document Status Enum ──────────────────────────────────────
class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


# ── Job Status Enum ───────────────────────────────────────────
class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Document Table ────────────────────────────────────────────
class DocumentModel(Base):
    """
    Stores metadata for every uploaded document.
    The actual PDF file goes to S3/MinIO (Phase 4).
    The vector embeddings go to Qdrant (Phase 4).
    This table is the source of truth for document metadata.
    """
    __tablename__ = "documents"

    # Primary key - we use UUID strings for portability
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # File information
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256

    # Processing status
    status: Mapped[str] = mapped_column(
        String(50),
        default=DocumentStatus.PENDING.value,
        nullable=False,
    )

    # Document metadata (extracted from PDF)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Version tracking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename} status={self.status}>"


# ── Ingestion Job Table ───────────────────────────────────────
class IngestionJobModel(Base):
    """
    Tracks background ingestion jobs.
    Every document upload creates one job.
    The frontend polls the job status to show progress.
    """
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    # Job state
    status: Mapped[str] = mapped_column(
        String(50),
        default=JobStatus.QUEUED.value,
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )  # 0-100

    # Current operation description
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<IngestionJob id={self.id} status={self.status} progress={self.progress}%>"
```

---

## STEP 8 — Redis Connection

Create `app/db/redis_client.py`:

```python
# app/db/redis_client.py
"""
Redis connection manager.

Redis is used for:
1. Conversation memory (chat history per session)
2. Job progress tracking (ingestion pipeline)
3. Response caching (future)

We use the async redis client so it never blocks the event loop.
"""
import redis.asyncio as aioredis
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger()

# Module-level client - created once, reused everywhere
_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """
    Get or create the Redis client.
    Uses connection pooling automatically.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,   # Return strings, not bytes
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("Redis client created", url=settings.redis_url)
    return _redis_client


async def check_redis_connection() -> tuple[bool, str]:
    """
    Test Redis connectivity.
    Returns (is_healthy, detail_message)
    """
    try:
        client = get_redis_client()
        await client.ping()
        return True, "Connected successfully"
    except Exception as e:
        logger.error("Redis connection failed", error=str(e))
        return False, str(e)


async def close_redis() -> None:
    """
    Close Redis connections gracefully.
    Called at application shutdown.
    """
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")
```

---

## STEP 9 — Qdrant Connection

Create `app/db/qdrant_client.py`:

```python
# app/db/qdrant_client.py
"""
Qdrant vector database connection manager.

Qdrant stores:
- Document chunk embeddings (dense vectors)
- Chunk metadata (filename, page number, document_id, etc.)

We use the async Qdrant client for non-blocking operations.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    CollectionInfo,
)
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger()

# Module-level client
_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """
    Get or create the Qdrant client.
    """
    global _qdrant_client
    if _qdrant_client is None:
        settings = get_settings()
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=30,
        )
        logger.info(
            "Qdrant client created",
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
    return _qdrant_client


async def check_qdrant_connection() -> tuple[bool, str]:
    """
    Test Qdrant connectivity.
    Returns (is_healthy, detail_message)
    """
    try:
        client = get_qdrant_client()
        # get_collections is a lightweight call that confirms connectivity
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]
        return True, f"Connected. Collections: {collection_names}"
    except Exception as e:
        logger.error("Qdrant connection failed", error=str(e))
        return False, str(e)


async def ensure_collection_exists() -> None:
    """
    Create the documents collection in Qdrant if it doesn't exist.
    Safe to call multiple times - won't recreate if already exists.

    Called at application startup.
    """
    settings = get_settings()
    client = get_qdrant_client()

    try:
        # Check if collection already exists
        existing = await client.get_collections()
        existing_names = [c.name for c in existing.collections]

        if settings.qdrant_collection in existing_names:
            logger.info(
                "Qdrant collection already exists",
                collection=settings.qdrant_collection,
            )
            return

        # Create the collection
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,  # 768 for Gemini embeddings
                distance=Distance.COSINE,           # Cosine similarity
            ),
        )

        logger.info(
            "Qdrant collection created",
            collection=settings.qdrant_collection,
            vector_size=settings.qdrant_vector_size,
        )

    except Exception as e:
        logger.error(
            "Failed to ensure Qdrant collection",
            error=str(e),
            collection=settings.qdrant_collection,
        )
        raise


async def close_qdrant() -> None:
    """
    Close Qdrant connection gracefully.
    Called at application shutdown.
    """
    global _qdrant_client
    if _qdrant_client:
        await _qdrant_client.close()
        _qdrant_client = None
        logger.info("Qdrant connection closed")
```

---

## STEP 10 — Update Health Router with Real Checks

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
```

---

## STEP 11 — Update `app/main.py` with Full Startup

Replace `app/main.py` completely:

```python
# app/main.py
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

# ── Logging first ─────────────────────────────────────────────
setup_logging()
logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown.
    Every infrastructure connection is established here.
    """

    # ══════════════════════════════════════════════════════════
    # STARTUP
    # ══════════════════════════════════════════════════════════
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
    )

    # ── Step 1: Database tables ───────────────────────────────
    logger.info("Initializing database tables...")
    try:
        await create_all_tables()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise  # Cannot start without database

    # ── Step 2: Redis connectivity ────────────────────────────
    logger.info("Checking Redis connection...")
    redis_ok, redis_detail = await check_redis_connection()
    if redis_ok:
        logger.info("Redis connected", detail=redis_detail)
    else:
        logger.warning("Redis not available", detail=redis_detail)

    # ── Step 3: Qdrant collection ─────────────────────────────
    logger.info("Initializing Qdrant collection...")
    try:
        await ensure_collection_exists()
        logger.info("Qdrant collection ready")
    except Exception as e:
        logger.warning("Qdrant initialization failed", error=str(e))

    logger.info("=" * 50)
    logger.info("Application ready to serve requests")
    logger.info("=" * 50)

    yield  # ← Application runs here

    # ══════════════════════════════════════════════════════════
    # SHUTDOWN
    # ══════════════════════════════════════════════════════════
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

    return app


app = create_app()
```

---

## STEP 12 — Verify File Structure

```bash
tree /F
```

Expected:
```
C:\DOCUMENT-AI-AGENT
│   .env
│   .gitignore
│   docker-compose.yml
│   requirements.txt
│
├───app
│   │   __init__.py
│   │   main.py
│   │
│   ├───api
│   │   │   __init__.py
│   │   ├───schemas
│   │   │       __init__.py
│   │   │       health.py
│   │   └───v1
│   │       │   __init__.py
│   │       └───routers
│   │               __init__.py
│   │               health.py
│   │
│   ├───config
│   │       __init__.py
│   │       model_table.py
│   │       settings.py
│   │
│   ├───db
│   │       __init__.py
│   │       database.py
│   │       models.py
│   │       qdrant_client.py
│   │       redis_client.py
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
├───docker
│       Dockerfile.dev
│
└───tests
        __init__.py
```

---

## STEP 13 — Start Docker Services and Run

### 13.1 Start all infrastructure services

Make sure Docker Desktop is running. Then in your terminal:

```bash
docker compose up -d qdrant redis postgres
```

You will see Docker pulling images the first time. Wait until all three say `Started` or `Running`.

Check they are all healthy:

```bash
docker compose ps
```

You should see:
```
NAME                        STATUS
document-ai-agent-qdrant-1  running (healthy)
document-ai-agent-redis-1   running (healthy)
document-ai-agent-postgres-1 running (healthy)
```

> **If any show `starting` wait 20 seconds and run `docker compose ps` again.**

### 13.2 Start the FastAPI app locally

In your terminal (with venv active):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Watch the startup logs. You should see:

```
Application starting ...
Initializing database tables...
Database tables ready
Checking Redis connection...
Redis connected detail='Connected successfully'
Initializing Qdrant collection...
Qdrant collection ready
==================================================
Application ready to serve requests
==================================================
```

### 13.3 Test all endpoints

Open a second terminal with venv active and run:

**Test 1 — Liveness:**
```bash
curl http://localhost:8000/api/v1/health
```

Expected:
```json
{
  "status": "healthy",
  "app_name": "Document AI Agent",
  "version": "1.0.0",
  "environment": "development",
  "request_id": "some-uuid"
}
```

**Test 2 — Readiness (all 4 components):**
```bash
curl http://localhost:8000/api/v1/health/ready
```

Expected — all four components healthy:
```json
{
  "status": "ready",
  "components": [
    {"name": "configuration", "status": "healthy", "details": "Provider: gemini | API Key: present"},
    {"name": "postgresql",    "status": "healthy", "details": "Connected successfully"},
    {"name": "redis",         "status": "healthy", "details": "Connected successfully"},
    {"name": "qdrant",        "status": "healthy", "details": "Connected. Collections: ['company_documents']"}
  ],
  "request_id": "some-uuid"
}
```

**Test 3 — Verify Qdrant collection was created:**
```bash
curl http://localhost:6333/collections
```

Expected:
```json
{
  "result": {
    "collections": [
      {"name": "company_documents"}
    ]
  }
}
```

**Test 4 — Verify PostgreSQL tables were created:**
```bash
docker compose exec postgres psql -U docai_user -d docai_db -c "\dt"
```

Expected:
```
          List of relations
 Schema |      Name       | Type  |   Owner
--------+-----------------+-------+-----------
 public | documents       | table | docai_user
 public | ingestion_jobs  | table | docai_user
```

**Test 5 — Verify Redis:**
```bash
docker compose exec redis redis-cli ping
```

Expected:
```
PONG
```

---

## Useful Docker Commands

Save these for later:

```bash
# See all running containers
docker compose ps

# See logs for a specific service
docker compose logs qdrant
docker compose logs redis
docker compose logs postgres

# Stop all services (keeps data)
docker compose down

# Stop all services AND delete all data (fresh start)
docker compose down -v

# Restart a single service
docker compose restart qdrant
```

---

## Phase 3 Complete — What We Built

```
Local Development Stack:

  Your Terminal
  (uvicorn --reload)
       │
       ▼
  FastAPI App :8000
       │
       ├──→ PostgreSQL :5432  (document metadata, job tracking)
       │         └── tables: documents, ingestion_jobs
       │
       ├──→ Redis :6379       (sessions, cache, progress)
       │
       └──→ Qdrant :6333      (vector embeddings)
                 └── collection: company_documents

  All connected. All health-checked. All verified.
```

---

**Tell me:**

1. Did `docker compose ps` show all 3 services as healthy?
2. Did the FastAPI startup logs show all 4 success messages?
3. Did the `/ready` endpoint show all 4 components as healthy?
4. Did the PostgreSQL table check show both tables?

Once confirmed we move to **Phase 4: Document Ingestion Pipeline** — the first real business logic where users upload PDFs and they get parsed, chunked, embedded, and stored in Qdrant.