"""
Ingestion Pipeline Orchestrator

This is the heart of Phase 4.
It coordinates every step of turning a PDF into searchable vectors.

Steps:
1. Parse PDF        → extract text per page
2. Chunk document   → split into overlapping pieces
3. Embed chunks     → generate vectors via Gemini
4. Store vectors    → upsert into Qdrant
5. Update metadata  → mark document as indexed in PostgreSQL

Completely independent from the chat pipeline.
Runs entirely in the background after the upload API returns.
"""
import asyncio
from pathlib import Path
import structlog

from app.processing.pdf_parser import PDFParser
from app.processing.chunker import SemanticChunker
from app.embeddings.base import EmbeddingProvider
from app.repositories.vector_repository import VectorRepository
from app.repositories.document_repository import DocumentRepository
from app.models.document import DocumentStatus, JobStatus
from app.config.settings import get_settings
logger = structlog.get_logger()

settings = get_settings()
class IngestionPipeline:
    """
    Orchestrates the complete document ingestion pipeline.

    This class only coordinates. Each step is handled
    by a dedicated component (parser, chunker, embedder, repository).
    """

    # Batch size for embedding generation
    EMBEDDING_BATCH_SIZE = settings.EMBEDDING_BATCH_SIZE

    def __init__(
        self,
        pdf_parser: PDFParser,
        chunker: SemanticChunker,
        embedding_provider: EmbeddingProvider,
        vector_repo: VectorRepository,
        document_repo: DocumentRepository,
    ):
        self.pdf_parser = pdf_parser
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.vector_repo = vector_repo
        self.document_repo = document_repo

    async def run(
        self,
        document_id: str,
        job_id: str,
        file_path: Path,
        original_filename: str,
    ) -> None:
        """
        Execute the full ingestion pipeline for one document.

        This method is called as a background task.
        It updates job progress at each step so the client can poll.

        Args:
            document_id: UUID of the document record
            job_id: UUID of the ingestion job
            file_path: Path to the uploaded PDF on disk
            original_filename: Original name of the uploaded file
        """
        log = logger.bind(
            document_id=document_id,
            job_id=job_id,
            filename=original_filename,
        )
        log.info("Ingestion pipeline started")

        try:
            # ══════════════════════════════════════════════════
            # STEP 1: Parse PDF
            # ══════════════════════════════════════════════════
            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.PARSING,
                progress=10,
                current_step="Parsing PDF document",
            )
            await self.document_repo.update_document_status(
                document_id=document_id,
                status=DocumentStatus.PROCESSING,
            )

            log.info("Step 1/4: Parsing PDF")
            parsed_doc = self.pdf_parser.parse(file_path, document_id)

            log.info(
                "PDF parsed successfully",
                total_pages=parsed_doc.total_pages,
                total_chars=parsed_doc.total_chars,
            )

            # ══════════════════════════════════════════════════
            # STEP 2: Chunk Document
            # ══════════════════════════════════════════════════
            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.CHUNKING,
                progress=25,
                current_step="Splitting document into chunks",
            )

            log.info("Step 2/4: Chunking document")
            chunks = self.chunker.chunk_document(parsed_doc, document_id)

            if not chunks:
                raise ValueError(
                    "No text could be extracted from this PDF. "
                    "The document may be scanned or image-only."
                )

            log.info("Document chunked", chunk_count=len(chunks))

            # ══════════════════════════════════════════════════
            # STEP 3: Generate Embeddings
            # ══════════════════════════════════════════════════
            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.EMBEDDING,
                progress=40,
                current_step=f"Generating embeddings for {len(chunks)} chunks",
            )

            log.info("Step 3/4: Generating embeddings", total_chunks=len(chunks))
            all_embeddings = await self._embed_in_batches(
                chunks=chunks,
                job_id=job_id,
                log=log,
            )

            log.info("Embeddings generated", count=len(all_embeddings))

            # ══════════════════════════════════════════════════
            # STEP 4: Store in Qdrant
            # ══════════════════════════════════════════════════
            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.INDEXING,
                progress=80,
                current_step="Storing vectors in search index",
            )

            log.info("Step 4/4: Storing vectors in Qdrant")
            stored_count = await self.vector_repo.upsert_chunks(
                chunks=chunks,
                embeddings=all_embeddings,
                document_filename=original_filename,
            )

            log.info("Vectors stored", count=stored_count)

            # ══════════════════════════════════════════════════
            # COMPLETE: Update status to indexed
            # ══════════════════════════════════════════════════
            await self.document_repo.update_document_status(
                document_id=document_id,
                status=DocumentStatus.INDEXED,
                total_pages=parsed_doc.total_pages,
                total_chunks=len(chunks),
                title=parsed_doc.title,
                author=parsed_doc.author,
            )

            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                current_step="Indexing complete",
            )

            log.info(
                "Ingestion pipeline completed successfully",
                total_pages=parsed_doc.total_pages,
                total_chunks=len(chunks),
                vectors_stored=stored_count,
            )

        except Exception as e:
            log.error(
                "Ingestion pipeline failed",
                error=str(e),
                exc_info=True,
            )
            # Mark document and job as failed
            await self.document_repo.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
            )
            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.FAILED,
                progress=0,
                current_step="Pipeline failed",
                error_message=str(e),
            )
            # Don't re-raise - this runs in background,
            # no one is waiting for the return value

    async def _embed_in_batches(
        self,
        chunks,
        job_id: str,
        log,
    ) -> list[list[float]]:
        """
        Generate embeddings in batches with progress updates.
        Splits chunks into batches to avoid overwhelming the API.
        """
        all_embeddings = []
        total = len(chunks)

        for batch_start in range(0, total, self.EMBEDDING_BATCH_SIZE):
            batch_end = min(batch_start + self.EMBEDDING_BATCH_SIZE, total)
            batch = chunks[batch_start:batch_end]
            texts = [chunk.content for chunk in batch]

            log.debug(
                "Embedding batch",
                batch_start=batch_start,
                batch_end=batch_end,
                total=total,
            )

            batch_embeddings = await self.embedding_provider.embed_batch(texts)
            all_embeddings.extend(batch_embeddings)

            # Update progress: 40% → 80% during embedding phase
            embedding_progress = int(
                40 + ((batch_end / total) * 40)
            )
            await self.document_repo.update_job_progress(
                job_id=job_id,
                status=JobStatus.EMBEDDING,
                progress=embedding_progress,
                current_step=(
                    f"Embedding chunk {batch_end} of {total}"
                ),
            )

            # Small delay to avoid rate limits
            if batch_end < total:
                await asyncio.sleep(0.5)

        return all_embeddings