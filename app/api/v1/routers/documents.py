import math
from functools import lru_cache
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
import structlog

from app.api.schemas.documents import (
    DocumentUploadResponse,
    JobStatusResponse,
    DocumentResponse,
    DocumentListResponse,
)
from app.db.models import UserModel  # Changed to use the DB model directly
from app.api.dependencies import get_current_user, require_admin
from app.utils.context import get_request_id
from app.services.document_service import DocumentService
from app.repositories.document_repository import DocumentRepository
from app.repositories.vector_repository import VectorRepository
from app.processing.document_validator import DocumentValidator
from app.processing.pdf_parser import PDFParser
from app.processing.chunker import SemanticChunker
from app.embeddings.factory import create_embedding_provider
from app.pipelines.ingestion_pipeline import IngestionPipeline
from app.db.qdrant_client import get_qdrant_client

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = structlog.get_logger()


@lru_cache() # Speed fix: Load models/clients only once
def get_document_service() -> DocumentService:
    """
    Build the DocumentService with all its dependencies.
    Cached as Singleton so we don't rebuild on every request.
    """
    embedding_provider = create_embedding_provider()
    qdrant_client = get_qdrant_client()

    document_repo = DocumentRepository()
    vector_repo = VectorRepository(client=qdrant_client)

    pipeline = IngestionPipeline(
        pdf_parser=PDFParser(),
        chunker=SemanticChunker(),
        embedding_provider=embedding_provider,
        vector_repo=vector_repo,
        document_repo=document_repo,
    )

    return DocumentService(
        validator=DocumentValidator(),
        pipeline=pipeline,
        document_repo=document_repo,
        vector_repo=vector_repo,
    )


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=202,
    summary="Upload Document",
    description=(
        "Upload a PDF document for indexing. "
        "Returns immediately with a job_id. "
        "Poll /documents/{document_id}/status to track progress."
    ),
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to upload"),
    current_user: UserModel = Depends(require_admin)  # AUTHZ: Admins only
):
    """Upload and start ingestion of a PDF document."""
    service = get_document_service()
    logger.info("User uploading document", user_id=current_user.id, username=current_user.username, filename=file.filename)

    try:
        document, job = await service.initiate_upload(
            file=file,
            background_tasks=background_tasks,
            user_id=current_user.id  # MULTI-TENANCY: Pass user UUID
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DocumentUploadResponse(
        document_id=document.id,
        job_id=job.id,
        filename=document.filename,
        status="processing",
        message=(
            "Document uploaded successfully. "
            "Indexing started in background. "
            f"Poll /api/v1/documents/{document.id}/status for progress."
        ),
        request_id=get_request_id(),
    )


@router.get(
    "/{document_id}/status",
    response_model=JobStatusResponse,
    summary="Get Ingestion Status",
    description="Poll this endpoint to track document indexing progress.",
)
async def get_document_status(
    document_id: str,
    current_user: UserModel = Depends(get_current_user) 
):
    """Get the current status of a document's ingestion job."""
    service = get_document_service()

    try:
        job = await service.get_job_status(document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return JobStatusResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List Documents",
    description="List all indexed documents with pagination.",
)
async def list_documents(
    current_user: UserModel = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
):
    """Return a paginated list of all documents."""
    service = get_document_service()
    documents, total = await service.list_documents(
        page=page,
        page_size=page_size,
    )

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=d.id,
                filename=d.filename,
                original_filename=d.original_filename,
                file_size_bytes=d.file_size_bytes,
                status=d.status,
                title=d.title,
                author=d.author,
                total_pages=d.total_pages,
                total_chunks=d.total_chunks,
                version=d.version,
                created_at=d.created_at,
                updated_at=d.updated_at,
                indexed_at=d.indexed_at,
            )
            for d in documents
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get Document",
    description="Get details of a specific document.",
)
async def get_document(
    document_id: str,
    current_user: UserModel = Depends(get_current_user)
):
    """Get a single document by ID."""
    service = get_document_service()

    try:
        doc = await service.get_document(document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        file_size_bytes=doc.file_size_bytes,
        status=doc.status,
        title=doc.title,
        author=doc.author,
        total_pages=doc.total_pages,
        total_chunks=doc.total_chunks,
        version=doc.version,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        indexed_at=doc.indexed_at,
    )


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Delete Document",
    description="Delete a document and all its vectors from the search index.",
)
async def delete_document(
    document_id: str,
    current_user: UserModel = Depends(require_admin)
):
    """Delete a document and remove all its vectors from Qdrant."""
    service = get_document_service()
    logger.info("User deleting document", user_id=current_user.id, username=current_user.username, document_id=document_id)

    try:
        await service.delete_document(document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))