"""
Document Repository

All PostgreSQL operations for documents and ingestion jobs.
No SQL lives outside this file.
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
import structlog

from app.db.models import DocumentModel, IngestionJobModel
from app.db.database import get_session_factory
from app.models.document import Document, IngestionJob, DocumentStatus, JobStatus

logger = structlog.get_logger()


class DocumentRepository:
    """
    Data access for documents and ingestion jobs.

    Every method is async and uses SQLAlchemy async sessions.
    Returns domain models, not SQLAlchemy models.
    """

    def _get_session(self) -> AsyncSession:
        """Create a new database session."""
        factory = get_session_factory()
        return factory()

    # ── Document Operations ───────────────────────────────────

    async def create_document(
        self,
        document_id: str,
        filename: str,
        original_filename: str,
        file_size_bytes: int,
        file_hash: str,
        user_id: str,  # MULTI-TENANCY: Added user_id
    ) -> Document:
        """Create a new document record."""
        async with self._get_session() as session:
            async with session.begin():
                now = datetime.now(timezone.utc)
                db_doc = DocumentModel(
                    id=document_id,
                    filename=filename,
                    original_filename=original_filename,
                    file_size_bytes=file_size_bytes,
                    file_hash=file_hash,
                    status=DocumentStatus.PENDING.value,
                    user_id=user_id,  # MULTI-TENANCY: Save user_id
                    created_at=now,
                    updated_at=now,
                )
                session.add(db_doc)

            logger.info("Document record created", document_id=document_id, user_id=user_id)
            return self._to_domain(db_doc)

    async def get_document(self, document_id: str) -> Document | None:
        """Get a document by ID."""
        async with self._get_session() as session:
            result = await session.execute(
                select(DocumentModel).where(DocumentModel.id == document_id)
            )
            db_doc = result.scalar_one_or_none()
            return self._to_domain(db_doc) if db_doc else None

    async def get_document_by_hash(self, file_hash: str) -> Document | None:
        """Find a document by its file hash (for duplicate detection)."""
        async with self._get_session() as session:
            result = await session.execute(
                select(DocumentModel)
                .where(DocumentModel.file_hash == file_hash)
                .where(DocumentModel.status != DocumentStatus.DELETED.value)
            )
            db_doc = result.scalar_one_or_none()
            return self._to_domain(db_doc) if db_doc else None

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        user_id: str | None = None,  # MULTI-TENANCY: Optional filter by user
    ) -> tuple[list[Document], int]:
        """
        List all documents with pagination.
        If user_id is provided, filters by that user.
        Returns (documents, total_count).
        """
        async with self._get_session() as session:
            # Base query conditions
            conditions = [DocumentModel.status != DocumentStatus.DELETED.value]
            if user_id:
                conditions.append(DocumentModel.user_id == user_id)

            # Count total
            count_result = await session.execute(
                select(func.count(DocumentModel.id)).where(*conditions)
            )
            total = count_result.scalar() or 0

            # Get page
            offset = (page - 1) * page_size
            result = await session.execute(
                select(DocumentModel)
                .where(*conditions)
                .order_by(DocumentModel.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            db_docs = result.scalars().all()
            documents = [self._to_domain(d) for d in db_docs]

            return documents, total

    async def update_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        total_pages: int | None = None,
        total_chunks: int | None = None,
        title: str | None = None,
        author: str | None = None,
    ) -> None:
        """Update document processing status and metadata."""
        async with self._get_session() as session:
            async with session.begin():
                values: dict = {
                    "status": status.value,
                    "updated_at": datetime.now(timezone.utc),
                }
                if total_pages is not None:
                    values["total_pages"] = total_pages
                if total_chunks is not None:
                    values["total_chunks"] = total_chunks
                if title is not None:
                    values["title"] = title
                if author is not None:
                    values["author"] = author
                if status == DocumentStatus.INDEXED:
                    values["indexed_at"] = datetime.now(timezone.utc)

                await session.execute(
                    update(DocumentModel)
                    .where(DocumentModel.id == document_id)
                    .values(**values)
                )

    async def delete_document(self, document_id: str) -> None:
        """Soft delete a document (marks as deleted, doesn't remove row)."""
        async with self._get_session() as session:
            async with session.begin():
                await session.execute(
                    update(DocumentModel)
                    .where(DocumentModel.id == document_id)
                    .values(
                        status=DocumentStatus.DELETED.value,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
        logger.info("Document soft deleted", document_id=document_id)

    # ── Job Operations ────────────────────────────────────────

    async def create_job(
        self,
        job_id: str,
        document_id: str,
    ) -> IngestionJob:
        """Create a new ingestion job."""
        async with self._get_session() as session:
            async with session.begin():
                now = datetime.now(timezone.utc)
                db_job = IngestionJobModel(
                    id=job_id,
                    document_id=document_id,
                    status=JobStatus.QUEUED.value,
                    progress=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(db_job)

            logger.info("Ingestion job created", job_id=job_id)
            return self._job_to_domain(db_job)

    async def get_job(self, job_id: str) -> IngestionJob | None:
        """Get a job by ID."""
        async with self._get_session() as session:
            result = await session.execute(
                select(IngestionJobModel)
                .where(IngestionJobModel.id == job_id)
            )
            db_job = result.scalar_one_or_none()
            return self._job_to_domain(db_job) if db_job else None

    async def get_job_by_document(
        self, document_id: str
    ) -> IngestionJob | None:
        """Get the latest job for a document."""
        async with self._get_session() as session:
            result = await session.execute(
                select(IngestionJobModel)
                .where(IngestionJobModel.document_id == document_id)
                .order_by(IngestionJobModel.created_at.desc())
                .limit(1)
            )
            db_job = result.scalar_one_or_none()
            return self._job_to_domain(db_job) if db_job else None

    async def update_job_progress(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update job progress during ingestion."""
        async with self._get_session() as session:
            async with session.begin():
                values: dict = {
                    "status": status.value,
                    "progress": progress,
                    "updated_at": datetime.now(timezone.utc),
                }
                if current_step is not None:
                    values["current_step"] = current_step
                if error_message is not None:
                    values["error_message"] = error_message
                if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    values["completed_at"] = datetime.now(timezone.utc)

                await session.execute(
                    update(IngestionJobModel)
                    .where(IngestionJobModel.id == job_id)
                    .values(**values)
                )

    # ── Converters ────────────────────────────────────────────

    @staticmethod
    def _to_domain(db_doc: DocumentModel) -> Document:
        """Convert SQLAlchemy model to domain model."""
        return Document(
            id=db_doc.id,
            filename=db_doc.filename,
            original_filename=db_doc.original_filename,
            file_size_bytes=db_doc.file_size_bytes,
            file_hash=db_doc.file_hash,
            status=DocumentStatus(db_doc.status),
            title=db_doc.title,
            author=db_doc.author,
            total_pages=db_doc.total_pages,
            total_chunks=db_doc.total_chunks,
            version=db_doc.version,
            created_at=db_doc.created_at,
            updated_at=db_doc.updated_at,
            indexed_at=db_doc.indexed_at,
            user_id=db_doc.user_id,  # MULTI-TENANCY: Map user_id
        )

    @staticmethod
    def _job_to_domain(db_job: IngestionJobModel) -> IngestionJob:
        """Convert SQLAlchemy model to domain model."""
        return IngestionJob(
            id=db_job.id,
            document_id=db_job.document_id,
            status=JobStatus(db_job.status),
            progress=db_job.progress,
            current_step=db_job.current_step,
            error_message=db_job.error_message,
            retry_count=db_job.retry_count,
            created_at=db_job.created_at,
            updated_at=db_job.updated_at,
            completed_at=db_job.completed_at,
        )