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