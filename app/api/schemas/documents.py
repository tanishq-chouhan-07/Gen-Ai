from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.document import DocumentStatus, JobStatus


# ── Upload Response ───────────────────────────────────────────
class DocumentUploadResponse(BaseModel):
    """Returned immediately after upload. Client polls job_id for progress."""
    document_id: str
    job_id: str
    filename: str
    status: str
    message: str
    request_id: str = ""


# ── Job Status Response ───────────────────────────────────────
class JobStatusResponse(BaseModel):
    """Current state of a background ingestion job."""
    job_id: str
    document_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


# ── Document Detail Response ──────────────────────────────────
class DocumentResponse(BaseModel):
    """Full document details."""
    id: str
    filename: str
    original_filename: str
    file_size_bytes: int
    status: DocumentStatus
    title: Optional[str] = None
    author: Optional[str] = None
    total_pages: Optional[int] = None
    total_chunks: Optional[int] = None
    version: int
    created_at: datetime
    updated_at: datetime
    indexed_at: Optional[datetime] = None


# ── Document List Response ────────────────────────────────────
class DocumentListResponse(BaseModel):
    """Paginated list of documents."""
    documents: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int