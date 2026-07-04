"""
Document Service

Orchestrates all document operations.
This is the bridge between the API layer and the pipeline/repository layer.

The API router calls the service.
The service calls repositories and pipelines.
The API router never talks to repositories directly.
"""
import uuid
import tempfile
import aiofiles
import os
from pathlib import Path
from fastapi import UploadFile, BackgroundTasks
import structlog

from app.processing.document_validator import DocumentValidator
from app.pipelines.ingestion_pipeline import IngestionPipeline
from app.repositories.document_repository import DocumentRepository
from app.repositories.vector_repository import VectorRepository
from app.models.document import Document, IngestionJob, DocumentStatus

logger = structlog.get_logger()


class DocumentService:
    """
    Business logic for document management.

    Handles:
    - Upload validation and initiation
    - Background pipeline triggering
    - Status queries
    - Document deletion (DB + Qdrant)
    """

    def __init__(
        self,
        validator: DocumentValidator,
        pipeline: IngestionPipeline,
        document_repo: DocumentRepository,
        vector_repo: VectorRepository,
    ):
        self.validator = validator
        self.pipeline = pipeline
        self.document_repo = document_repo
        self.vector_repo = vector_repo

    async def initiate_upload(
        self,
        file: UploadFile,
        background_tasks: BackgroundTasks,
        user_id: str  # MULTI-TENANCY: Added user_id parameter
    ) -> tuple[Document, IngestionJob]:
        """
        Handle a new document upload.

        Steps:
        1. Save uploaded file to temp location
        2. Validate the file
        3. Check for duplicates
        4. Create DB records (document + job)
        5. Schedule background ingestion
        6. Return immediately with job ID

        Returns:
            (document, job) tuple for the API response
        """
        log = logger.bind(filename=file.filename, user_id=user_id)
        log.info("Upload initiated")

        tmp_path = await self._save_to_temp(file)

        try:
            log.info("Validating document")
            validation = self.validator.validate(
                file_path=tmp_path,
                filename=file.filename or "upload.pdf",
            )

            if not validation.is_valid:
                tmp_path.unlink(missing_ok=True)
                raise ValueError(validation.error_message)

            existing = await self.document_repo.get_document_by_hash(
                validation.file_hash
            )
            if existing:
                tmp_path.unlink(missing_ok=True)
                log.info(
                    "Duplicate document detected",
                    existing_id=existing.id,
                )
                raise ValueError(
                    f"This document was already uploaded. "
                    f"Document ID: {existing.id}"
                )

            document_id = str(uuid.uuid4())
            job_id = str(uuid.uuid4())

            document = await self.document_repo.create_document(
                document_id=document_id,
                filename=file.filename or "upload.pdf",
                original_filename=file.filename or "upload.pdf",
                file_size_bytes=validation.file_size_bytes,
                file_hash=validation.file_hash,
                user_id=user_id  # MULTI-TENANCY: Save the user_id
            )

            job = await self.document_repo.create_job(
                job_id=job_id,
                document_id=document_id,
            )

            log.info(
                "Document record created",
                document_id=document_id,
                job_id=job_id,
            )

            background_tasks.add_task(
                self.pipeline.run,
                document_id=document_id,
                job_id=job_id,
                file_path=tmp_path,
                original_filename=file.filename or "upload.pdf",
                user_id=user_id  # MULTI-TENANCY: Pass to pipeline
            )

            log.info("Background ingestion scheduled")
            return document, job

        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    async def get_document(self, document_id: str) -> Document:
        """Get a document by ID. Raises ValueError if not found."""
        doc = await self.document_repo.get_document(document_id)
        if not doc:
            raise ValueError(f"Document not found: {document_id}")
        return doc

    async def get_job_status(self, document_id: str) -> IngestionJob:
        """Get the ingestion job status for a document."""
        job = await self.document_repo.get_job_by_document(document_id)
        if not job:
            raise ValueError(
                f"No ingestion job found for document: {document_id}"
            )
        return job

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Document], int]:
        """List documents with pagination."""
        return await self.document_repo.list_documents(
            page=page,
            page_size=page_size,
        )

    async def delete_document(self, document_id: str) -> None:
        """
        Delete a document and all its data.
        1. Delete vectors from Qdrant
        2. Soft-delete from PostgreSQL
        """
        log = logger.bind(document_id=document_id)

        doc = await self.document_repo.get_document(document_id)
        if not doc:
            raise ValueError(f"Document not found: {document_id}")

        deleted_vectors = await self.vector_repo.delete_document_chunks(
            document_id
        )
        log.info("Vectors deleted", count=deleted_vectors)

        await self.document_repo.delete_document(document_id)
        log.info("Document deleted")

    @staticmethod
    async def _save_to_temp(file: UploadFile) -> Path:
        """
        Save uploaded file to a temporary path on disk.
        Returns the path to the temp file.
        """
        suffix = Path(file.filename or "upload.pdf").suffix
        tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=suffix)
        tmp_path = Path(tmp_path_str)

        try:
            os.close(tmp_fd)

            async with aiofiles.open(tmp_path, "wb") as tmp_file:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    await tmp_file.write(chunk)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        return tmp_path