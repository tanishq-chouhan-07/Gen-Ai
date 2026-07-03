"""
Domain models for documents.
These are Pydantic models used throughout the application.
They are NOT database models (those live in app/db/models.py).

Think of domain models as the language the application speaks internally.
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(BaseModel):
    """Represents a document in the system."""
    id: str
    filename: str
    original_filename: str
    file_size_bytes: int
    file_hash: str
    status: DocumentStatus
    title: Optional[str] = None
    author: Optional[str] = None
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    indexed_at: Optional[datetime] = None


class IngestionJob(BaseModel):
    """Represents a background ingestion job."""
    id: str
    document_id: str
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100)
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None