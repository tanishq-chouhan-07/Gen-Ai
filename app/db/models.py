"""
SQLAlchemy database models.

These define the actual database tables.
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
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
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


# ── User Table ────────────────────────────────────────────────
class UserModel(Base):
    """
    Stores user credentials and roles for Authentication/Authorization.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False) # 'user' or 'admin'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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

    # Relationship: A user can own many documents
    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="owner")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"


# ── Document Table ────────────────────────────────────────────
class DocumentModel(Base):
    """
    Stores metadata for every uploaded document.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Multi-tenancy: Who owns this document?
    user_id: Mapped[str | None] = mapped_column(
        String(36), 
        ForeignKey("users.id"), 
        nullable=True, # Nullable for now so existing docs don't break
        index=True
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

    # Relationship: Link back to the User
    owner: Mapped["UserModel"] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename} status={self.status}>"


# ── Ingestion Job Table ───────────────────────────────────────
class IngestionJobModel(Base):
    """
    Tracks background ingestion jobs.
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
    ) 

    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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