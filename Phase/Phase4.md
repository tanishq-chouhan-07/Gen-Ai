# Phase 4: Document Ingestion Pipeline

This is the first real business logic phase. By the end users can upload a PDF, it gets validated, parsed, chunked, embedded with Gemini, and stored in Qdrant. Everything runs in the background with progress tracking.

---

## Phase 4 Game Plan

```
Step 1  → Install new dependencies
Step 2  → Domain models (Pydantic)
Step 3  → Document validator
Step 4  → PDF parser (PyMuPDF)
Step 5  → Smart chunker
Step 6  → Embedding provider abstraction + Gemini implementation
Step 7  → Vector repository (Qdrant operations)
Step 8  → Document repository (PostgreSQL operations)
Step 9  → Job repository (progress tracking)
Step 10 → Ingestion pipeline (orchestrates everything)
Step 11 → Document service (business logic)
Step 12 → API schemas + router
Step 13 → Wire into main
Step 14 → Run and verify
```

---

## STEP 1 — Install New Dependencies

Stop the running server with `Ctrl + C`.

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

# PDF Processing
PyMuPDF==1.24.14

# Utilities
python-multipart==0.0.12
python-dotenv==1.0.1
asgiref==3.8.1
aiofiles==24.1.0
```

Install:

```bash
pip install -r requirements.txt
```

---

## STEP 2 — Create All New Folders

Run this block all at once:

```bash
mkdir app\models
mkdir app\processing
mkdir app\embeddings
mkdir app\embeddings\providers
mkdir app\repositories
mkdir app\pipelines
mkdir app\services
mkdir app\api\v1\routers
```

Create all `__init__.py` files:

```bash
type nul > app\models\__init__.py
type nul > app\processing\__init__.py
type nul > app\embeddings\__init__.py
type nul > app\embeddings\providers\__init__.py
type nul > app\repositories\__init__.py
type nul > app\pipelines\__init__.py
type nul > app\services\__init__.py
```

---

## STEP 3 — Domain Models

These are pure Pydantic models. They represent data flowing through the system. No database logic here.

Create `app/models/document.py`:

```python
# app/models/document.py
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
```

Create `app/models/chunk.py`:

```python
# app/models/chunk.py
"""
Domain models for document chunks.

A chunk is a piece of a document that gets embedded and stored in Qdrant.
Every chunk knows exactly where it came from (document, page, position).
"""
from pydantic import BaseModel
from typing import Optional


class DocumentChunk(BaseModel):
    """
    A single chunk of text from a document.
    Created by the chunker, embedded by the embedding provider,
    stored in Qdrant by the vector repository.
    """
    chunk_id: str            # Unique ID: {document_id}_p{page}_c{index}
    document_id: str         # Which document this came from
    content: str             # The actual text content
    page_number: int         # Which page of the PDF
    chunk_index: int         # Position within the document (0-based)
    total_chunks: int        # Total chunks in this document
    token_count: int         # Estimated token count
    char_count: int          # Character count

    # Rich metadata stored alongside vector in Qdrant
    metadata: dict = {}


class RetrievedChunk(BaseModel):
    """
    A chunk returned from a Qdrant similarity search.
    Includes the similarity score and source document info.
    """
    chunk_id: str
    document_id: str
    content: str
    page_number: int
    chunk_index: int
    score: float             # Cosine similarity score (0-1)
    filename: str            # Human-readable source filename
    metadata: dict = {}
```

---

## STEP 4 — Document Validator

Create `app/processing/document_validator.py`:

```python
# app/processing/document_validator.py
"""
Document Validator

Validates uploaded files before any processing begins.
Catches problems early so we don't waste time on bad files.

Checks:
1. File extension must be .pdf
2. File size must be under the limit
3. File must not be corrupted (PyMuPDF can open it)
4. File must contain extractable text
"""
import hashlib
from pathlib import Path
from dataclasses import dataclass
import structlog
import fitz  # PyMuPDF

from app.config.settings import get_settings

logger = structlog.get_logger()


@dataclass
class ValidationResult:
    """Result of validating a document."""
    is_valid: bool
    error_message: str = ""
    file_hash: str = ""          # SHA-256 hash of file content
    file_size_bytes: int = 0
    page_count: int = 0


class DocumentValidator:
    """
    Validates PDF files before ingestion.
    All checks are fast and happen before any heavy processing.
    """

    def __init__(self):
        self.settings = get_settings()
        self.max_size_bytes = self.settings.max_file_size_mb * 1024 * 1024
        self.allowed_extensions = {".pdf"}

    def validate(self, file_path: Path, filename: str) -> ValidationResult:
        """
        Run all validation checks on a file.

        Args:
            file_path: Path to the temporary file on disk
            filename: Original filename from the upload

        Returns:
            ValidationResult with is_valid=True or error details
        """
        log = logger.bind(filename=filename)

        # ── Check 1: File extension ───────────────────────────
        suffix = Path(filename).suffix.lower()
        if suffix not in self.allowed_extensions:
            log.warning("Invalid file extension", extension=suffix)
            return ValidationResult(
                is_valid=False,
                error_message=(
                    f"Invalid file type '{suffix}'. "
                    f"Only PDF files are accepted."
                ),
            )

        # ── Check 2: File exists and is readable ──────────────
        if not file_path.exists():
            return ValidationResult(
                is_valid=False,
                error_message="File not found after upload.",
            )

        # ── Check 3: File size ────────────────────────────────
        file_size = file_path.stat().st_size

        if file_size == 0:
            return ValidationResult(
                is_valid=False,
                error_message="File is empty.",
            )

        if file_size > self.max_size_bytes:
            size_mb = file_size / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                error_message=(
                    f"File size {size_mb:.1f}MB exceeds the "
                    f"{self.settings.max_file_size_mb}MB limit."
                ),
            )

        # ── Check 4: File hash (for duplicate detection) ──────
        file_hash = self._compute_hash(file_path)

        # ── Check 5: PDF integrity (can PyMuPDF open it?) ─────
        try:
            doc = fitz.open(str(file_path))
            page_count = len(doc)
            doc.close()
        except Exception as e:
            log.warning("PDF is corrupted or unreadable", error=str(e))
            return ValidationResult(
                is_valid=False,
                error_message=(
                    "The PDF file appears to be corrupted or "
                    "is not a valid PDF."
                ),
            )

        # ── Check 6: PDF has pages ────────────────────────────
        if page_count == 0:
            return ValidationResult(
                is_valid=False,
                error_message="The PDF file has no pages.",
            )

        log.info(
            "Document validation passed",
            file_size_bytes=file_size,
            page_count=page_count,
        )

        return ValidationResult(
            is_valid=True,
            file_hash=file_hash,
            file_size_bytes=file_size,
            page_count=page_count,
        )

    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """
        Compute SHA-256 hash of file content.
        Used to detect duplicate uploads.
        If two files have the same hash, they are identical.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in 64KB chunks to handle large files
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
```

---

## STEP 5 — PDF Parser

Create `app/processing/pdf_parser.py`:

```python
# app/processing/pdf_parser.py
"""
PDF Parser using PyMuPDF (fitz)

Extracts text and metadata from PDF files page by page.
PyMuPDF is fast, handles complex PDFs well, and works offline.

What we extract:
- Text content per page
- Document metadata (title, author, creation date)
- Page count
- Basic structure detection (has images, has tables)
"""
from pathlib import Path
from dataclasses import dataclass, field
import structlog
import fitz  # PyMuPDF

logger = structlog.get_logger()


@dataclass
class ParsedPage:
    """Text and metadata extracted from a single PDF page."""
    page_number: int      # 1-based page number
    text: str             # Extracted text content
    char_count: int       # Number of characters
    has_images: bool      # Page contains images
    has_tables: bool      # Page likely contains tables (heuristic)


@dataclass
class ParsedDocument:
    """Complete parsed content of a PDF document."""
    # Document metadata from PDF properties
    title: str | None
    author: str | None
    created_date: str | None
    total_pages: int
    total_chars: int

    # Per-page content
    pages: list[ParsedPage] = field(default_factory=list)

    # Raw metadata dict from PyMuPDF
    raw_metadata: dict = field(default_factory=dict)


class PDFParser:
    """
    Parses PDF files using PyMuPDF.

    Usage:
        parser = PDFParser()
        result = parser.parse(Path("document.pdf"), document_id="doc-123")
        for page in result.pages:
            print(f"Page {page.page_number}: {len(page.text)} chars")
    """

    def parse(self, file_path: Path, document_id: str) -> ParsedDocument:
        """
        Parse a PDF file and extract all text content.

        Args:
            file_path: Path to the PDF file
            document_id: Document ID for logging context

        Returns:
            ParsedDocument with all extracted content
        """
        log = logger.bind(document_id=document_id, file_path=str(file_path))
        log.info("Starting PDF parsing")

        try:
            doc = fitz.open(str(file_path))
            pages = []

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_number = page_idx + 1  # Convert to 1-based

                # Extract text - "text" mode gives clean plain text
                text = page.get_text("text")
                text = text.strip()

                # Detect images
                has_images = len(page.get_images()) > 0

                # Detect tables using heuristic
                # Many short text blocks side by side usually means a table
                blocks = page.get_text("blocks")
                has_tables = self._detect_tables(blocks)

                pages.append(ParsedPage(
                    page_number=page_number,
                    text=text,
                    char_count=len(text),
                    has_images=has_images,
                    has_tables=has_tables,
                ))

                log.debug(
                    "Page parsed",
                    page=page_number,
                    chars=len(text),
                    has_images=has_images,
                )

            # Extract document-level metadata
            metadata = doc.metadata or {}
            doc.close()

            total_chars = sum(p.char_count for p in pages)
            non_empty_pages = [p for p in pages if p.text]

            log.info(
                "PDF parsing complete",
                total_pages=len(pages),
                non_empty_pages=len(non_empty_pages),
                total_chars=total_chars,
            )

            return ParsedDocument(
                title=metadata.get("title") or None,
                author=metadata.get("author") or None,
                created_date=metadata.get("creationDate") or None,
                total_pages=len(pages),
                total_chars=total_chars,
                pages=pages,
                raw_metadata=metadata,
            )

        except Exception as e:
            log.error("PDF parsing failed", error=str(e))
            raise

    def _detect_tables(self, blocks: list) -> bool:
        """
        Heuristic table detection.
        Tables tend to have many small blocks arranged in a grid.
        This is not perfect but good enough for metadata purposes.
        """
        if len(blocks) < 6:
            return False

        # Count blocks with short text (typical of table cells)
        short_blocks = [
            b for b in blocks
            if len(b) > 4 and isinstance(b[4], str) and len(b[4].strip()) < 60
        ]

        # If more than 60% of blocks are short → likely a table
        return len(short_blocks) > len(blocks) * 0.6
```

---

## STEP 6 — Smart Chunker

Create `app/processing/chunker.py`:

```python
# app/processing/chunker.py
"""
Semantic Text Chunker

Splits parsed document pages into overlapping chunks.

Why chunking matters:
- LLMs have context window limits
- Smaller chunks give more precise retrieval
- Overlap ensures context is not lost at chunk boundaries

Strategy:
- Split text into sentences first (respect natural boundaries)
- Fill chunks up to chunk_size tokens
- Add overlap from the previous chunk
- Enrich every chunk with metadata (page, position, etc.)
"""
import re
import uuid
from app.processing.pdf_parser import ParsedDocument, ParsedPage
from app.models.chunk import DocumentChunk
from app.config.settings import get_settings
import structlog

logger = structlog.get_logger()


class SemanticChunker:
    """
    Splits document text into overlapping chunks.

    Each chunk is self-contained with enough context to be understood
    on its own, plus metadata linking it back to the source.
    """

    def __init__(self):
        settings = get_settings()
        # chunk_size is in approximate tokens (1 token ≈ 4 chars)
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap

    def chunk_document(
        self,
        parsed_doc: ParsedDocument,
        document_id: str,
    ) -> list[DocumentChunk]:
        """
        Chunk an entire parsed document.

        Args:
            parsed_doc: Output from PDFParser.parse()
            document_id: Used to build chunk IDs and metadata

        Returns:
            List of DocumentChunk objects ready for embedding
        """
        log = logger.bind(document_id=document_id)
        all_chunks: list[DocumentChunk] = []
        chunk_index = 0

        for page in parsed_doc.pages:
            # Skip empty pages
            if not page.text.strip():
                log.debug("Skipping empty page", page=page.page_number)
                continue

            page_chunks = self._chunk_page(
                page=page,
                document_id=document_id,
                start_index=chunk_index,
            )

            all_chunks.extend(page_chunks)
            chunk_index += len(page_chunks)

        # Now that we know the total, update total_chunks on every chunk
        total = len(all_chunks)
        for chunk in all_chunks:
            chunk.total_chunks = total

        log.info(
            "Document chunking complete",
            total_chunks=total,
            pages_processed=parsed_doc.total_pages,
        )

        return all_chunks

    def _chunk_page(
        self,
        page: ParsedPage,
        document_id: str,
        start_index: int,
    ) -> list[DocumentChunk]:
        """Split a single page into chunks."""
        sentences = self._split_into_sentences(page.text)

        if not sentences:
            return []

        chunks = []
        current_sentences: list[str] = []
        current_token_count = 0
        local_index = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)

            # If adding this sentence would exceed chunk_size
            # AND we already have content → finalize current chunk
            if (
                current_token_count + sentence_tokens > self.chunk_size
                and current_sentences
            ):
                # Build and save the chunk
                chunk = self._build_chunk(
                    sentences=current_sentences,
                    document_id=document_id,
                    page_number=page.page_number,
                    chunk_index=start_index + local_index,
                )
                chunks.append(chunk)
                local_index += 1

                # Start next chunk with overlap from the current one
                overlap_sentences = self._get_overlap(current_sentences)
                current_sentences = overlap_sentences + [sentence]
                current_token_count = sum(
                    self._estimate_tokens(s) for s in current_sentences
                )
            else:
                current_sentences.append(sentence)
                current_token_count += sentence_tokens

        # Don't forget the last chunk
        if current_sentences:
            chunk = self._build_chunk(
                sentences=current_sentences,
                document_id=document_id,
                page_number=page.page_number,
                chunk_index=start_index + local_index,
            )
            chunks.append(chunk)

        return chunks

    def _build_chunk(
        self,
        sentences: list[str],
        document_id: str,
        page_number: int,
        chunk_index: int,
    ) -> DocumentChunk:
        """Create a DocumentChunk from a list of sentences."""
        content = " ".join(sentences).strip()
        token_count = self._estimate_tokens(content)

        return DocumentChunk(
            chunk_id=f"{document_id}_p{page_number}_c{chunk_index}",
            document_id=document_id,
            content=content,
            page_number=page_number,
            chunk_index=chunk_index,
            total_chunks=0,  # Will be updated after all chunks are created
            token_count=token_count,
            char_count=len(content),
            metadata={
                "page_number": page_number,
                "chunk_index": chunk_index,
                "document_id": document_id,
            },
        )

    def _split_into_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences.
        Uses regex to split on sentence-ending punctuation.
        Filters out very short fragments.
        """
        # Split on . ! ? followed by whitespace
        raw = re.split(r'(?<=[.!?])\s+', text)

        sentences = []
        for s in raw:
            s = s.strip()
            # Skip very short fragments (less than 20 chars)
            if len(s) >= 20:
                sentences.append(s)

        return sentences

    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token estimate: 1 token ≈ 4 characters.
        Good enough for chunking purposes without loading a tokenizer.
        """
        return max(1, len(text) // 4)

    def _get_overlap(self, sentences: list[str]) -> list[str]:
        """
        Get the tail sentences that fit within the overlap budget.
        These become the start of the next chunk for context continuity.
        """
        budget = self.chunk_overlap
        overlap = []

        # Walk backwards through sentences
        for sentence in reversed(sentences):
            tokens = self._estimate_tokens(sentence)
            if tokens <= budget:
                overlap.insert(0, sentence)
                budget -= tokens
            else:
                break

        return overlap
```

---

## STEP 7 — Embedding Provider Abstraction

Create `app/embeddings/base.py`:

```python
# app/embeddings/base.py
"""
Embedding Provider Abstraction

Defines the interface that ALL embedding providers must implement.
Whether we use Gemini, Bedrock Titan, or a local model,
the rest of the application calls the same methods.
"""
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.

    Implementations:
    - GeminiEmbeddingProvider (development)
    - BedrockEmbeddingProvider (production)
    - LocalEmbeddingProvider (offline fallback)
    """

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """
        Embed a single piece of text.
        Returns a list of floats (the embedding vector).
        """
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts at once.
        More efficient than calling embed() in a loop.
        Returns a list of vectors, one per input text.
        """
        ...

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the dimension of vectors this provider produces."""
        ...

    @abstractmethod
    def get_model_id(self) -> str:
        """Return the model identifier string."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Test that the provider is reachable and working."""
        ...
```

Create `app/embeddings/providers/gemini_embeddings.py`:

```python
# app/embeddings/providers/gemini_embeddings.py
"""
Gemini Embedding Provider

Uses Google's text-embedding-004 model.
768-dimensional embeddings, great quality, fast.
Used in development. Replaced by Bedrock Titan in production.
"""
import asyncio
import structlog
import google.generativeai as genai

from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings

logger = structlog.get_logger()


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using Google Gemini text-embedding-004.
    Produces 768-dimensional vectors.
    """

    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.model_id = settings.gemini_embedding_model
        self._dimension = 768
        logger.info(
            "Gemini embedding provider initialized",
            model=self.model_id,
            dimension=self._dimension,
        )

    async def embed(self, text: str) -> list[float]:
        """
        Embed a single text string.
        Runs the synchronous Gemini API in a thread pool
        so it doesn't block the async event loop.
        """
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        result = await asyncio.to_thread(
            genai.embed_content,
            model=self.model_id,
            content=text,
            task_type="retrieval_document",
        )

        return result["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts.
        Gemini doesn't have a native batch endpoint so we
        call embed() concurrently with asyncio.gather.
        Limit concurrency to avoid rate limits.
        """
        if not texts:
            return []

        # Filter out empty strings
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return []

        logger.debug(
            "Embedding batch",
            batch_size=len(valid_texts),
            model=self.model_id,
        )

        # Process in parallel but limit to 5 concurrent requests
        # to stay within Gemini rate limits
        semaphore = asyncio.Semaphore(5)

        async def embed_with_semaphore(text: str) -> list[float]:
            async with semaphore:
                return await self.embed(text)

        embeddings = await asyncio.gather(
            *[embed_with_semaphore(text) for text in valid_texts]
        )

        logger.debug(
            "Batch embedding complete",
            count=len(embeddings),
        )

        return list(embeddings)

    def get_dimension(self) -> int:
        return self._dimension

    def get_model_id(self) -> str:
        return self.model_id

    async def health_check(self) -> bool:
        """Test embedding with a short string."""
        try:
            vector = await self.embed("health check")
            return len(vector) == self._dimension
        except Exception as e:
            logger.error("Gemini embedding health check failed", error=str(e))
            return False
```

Create `app/embeddings/factory.py`:

```python
# app/embeddings/factory.py
"""
Embedding Provider Factory

Reads EMBEDDING_PROVIDER from settings and returns
the correct provider implementation.

To switch from Gemini to Bedrock Titan:
  Change EMBEDDING_PROVIDER=bedrock in .env
  Zero code changes needed.
"""
from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings
import structlog

logger = structlog.get_logger()


def create_embedding_provider() -> EmbeddingProvider:
    """
    Factory function that creates the configured embedding provider.
    Called once at application startup.
    """
    settings = get_settings()
    provider_name = settings.embedding_provider

    logger.info("Creating embedding provider", provider=provider_name)

    if provider_name == "gemini":
        from app.embeddings.providers.gemini_embeddings import (
            GeminiEmbeddingProvider,
        )
        return GeminiEmbeddingProvider()

    elif provider_name == "bedrock":
        # Will be implemented in Phase 7 (AWS deployment)
        raise NotImplementedError(
            "Bedrock embedding provider will be added in Phase 7. "
            "Use EMBEDDING_PROVIDER=gemini for now."
        )

    else:
        raise ValueError(
            f"Unknown embedding provider: '{provider_name}'. "
            f"Supported: ['gemini', 'bedrock']"
        )
```

---

## STEP 8 — Vector Repository

Create `app/repositories/vector_repository.py`:

```python
# app/repositories/vector_repository.py
"""
Vector Repository

All Qdrant operations live here.
No other part of the application touches Qdrant directly.

Responsibilities:
- Store chunk vectors with metadata (upsert)
- Search for similar chunks (similarity search)
- Delete all vectors for a document
- Check if a document is already indexed
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
)
import structlog

from app.models.chunk import DocumentChunk, RetrievedChunk
from app.config.settings import get_settings

logger = structlog.get_logger()


class VectorRepository:
    """
    Handles all vector database operations with Qdrant.

    Uses the repository pattern: callers never touch
    the Qdrant client directly, only this class does.
    """

    def __init__(self, client: AsyncQdrantClient):
        self.client = client
        self.settings = get_settings()
        self.collection = self.settings.qdrant_collection

    async def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        document_filename: str,
    ) -> int:
        """
        Store chunk vectors in Qdrant.

        Args:
            chunks: List of DocumentChunk objects
            embeddings: Corresponding embedding vectors (same order as chunks)
            document_filename: Original filename for search results

        Returns:
            Number of chunks stored
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks count ({len(chunks)}) != "
                f"embeddings count ({len(embeddings)})"
            )

        if not chunks:
            return 0

        log = logger.bind(
            document_id=chunks[0].document_id,
            chunk_count=len(chunks),
        )

        # Build Qdrant point objects
        points = []
        for chunk, vector in zip(chunks, embeddings):
            # The payload is stored alongside the vector in Qdrant
            # We can filter and return these fields in search results
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "token_count": chunk.token_count,
                "filename": document_filename,
                **chunk.metadata,
            }

            points.append(PointStruct(
                # Qdrant needs a numeric or UUID point ID
                # We hash the chunk_id to get a stable integer
                id=self._chunk_id_to_int(chunk.chunk_id),
                vector=vector,
                payload=payload,
            ))

        # Upsert in batches of 100 to avoid timeout
        batch_size = 100
        total_upserted = 0

        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await self.client.upsert(
                collection_name=self.collection,
                points=batch,
                wait=True,  # Wait for indexing to complete
            )
            total_upserted += len(batch)
            log.debug("Batch upserted", batch=i // batch_size + 1)

        log.info("All chunks stored in Qdrant", total=total_upserted)
        return total_upserted

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        document_ids: list[str] | None = None,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        """
        Find the most similar chunks to a query vector.

        Args:
            query_vector: The embedded query
            top_k: Maximum number of results to return
            document_ids: Optional filter to specific documents
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of RetrievedChunk sorted by similarity (highest first)
        """
        # Build optional filter for specific documents
        search_filter = None
        if document_ids:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=doc_id),
                    )
                    for doc_id in document_ids
                ]
            )

        results = await self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=search_filter,
            score_threshold=score_threshold,
            with_payload=True,  # Include metadata in results
        )

        # Convert Qdrant results to our domain model
        chunks = []
        for result in results:
            payload = result.payload or {}
            chunks.append(RetrievedChunk(
                chunk_id=payload.get("chunk_id", ""),
                document_id=payload.get("document_id", ""),
                content=payload.get("content", ""),
                page_number=payload.get("page_number", 0),
                chunk_index=payload.get("chunk_index", 0),
                score=result.score,
                filename=payload.get("filename", "Unknown"),
                metadata=payload,
            ))

        return chunks

    async def delete_document_chunks(self, document_id: str) -> int:
        """
        Delete all vectors for a specific document from Qdrant.
        Called when a document is deleted.

        Returns:
            Approximate number of deleted points
        """
        log = logger.bind(document_id=document_id)

        # First count how many points exist for this document
        count_result = await self.client.count(
            collection_name=self.collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            exact=True,
        )
        count = count_result.count

        if count == 0:
            log.info("No vectors found for document")
            return 0

        # Delete by filter
        await self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            wait=True,
        )

        log.info("Document vectors deleted", count=count)
        return count

    async def document_exists(self, document_id: str) -> bool:
        """Check if any vectors exist for a document."""
        result = await self.client.count(
            collection_name=self.collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
        )
        return result.count > 0

    @staticmethod
    def _chunk_id_to_int(chunk_id: str) -> int:
        """
        Convert a string chunk ID to a stable integer for Qdrant.
        Qdrant requires integer or UUID point IDs.
        We use abs(hash()) for a stable integer from any string.
        """
        return abs(hash(chunk_id)) % (2**53)
```

---

## STEP 9 — Document Repository

Create `app/repositories/document_repository.py`:

```python
# app/repositories/document_repository.py
"""
Document Repository

All PostgreSQL operations for documents and ingestion jobs.
No SQL lives outside this file.
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
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
                    created_at=now,
                    updated_at=now,
                )
                session.add(db_doc)

            logger.info("Document record created", document_id=document_id)
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
    ) -> tuple[list[Document], int]:
        """
        List all documents with pagination.
        Returns (documents, total_count).
        """
        async with self._get_session() as session:
            # Count total
            from sqlalchemy import func
            count_result = await session.execute(
                select(func.count(DocumentModel.id))
                .where(DocumentModel.status != DocumentStatus.DELETED.value)
            )
            total = count_result.scalar() or 0

            # Get page
            offset = (page - 1) * page_size
            result = await session.execute(
                select(DocumentModel)
                .where(DocumentModel.status != DocumentStatus.DELETED.value)
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
```

---

## STEP 10 — Ingestion Pipeline

Create `app/pipelines/ingestion_pipeline.py`:

```python
# app/pipelines/ingestion_pipeline.py
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

logger = structlog.get_logger()


class IngestionPipeline:
    """
    Orchestrates the complete document ingestion pipeline.

    This class only coordinates. Each step is handled
    by a dedicated component (parser, chunker, embedder, repository).
    """

    # Batch size for embedding generation
    EMBEDDING_BATCH_SIZE = 10

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
```

---

## STEP 11 — Document Service

Create `app/services/document_service.py`:

```python
# app/services/document_service.py
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
        log = logger.bind(filename=file.filename)
        log.info("Upload initiated")

        # ── Save to temp file ─────────────────────────────────
        # We need it on disk for PyMuPDF
        tmp_path = await self._save_to_temp(file)

        try:
            # ── Validate ──────────────────────────────────────
            log.info("Validating document")
            validation = self.validator.validate(
                file_path=tmp_path,
                filename=file.filename or "upload.pdf",
            )

            if not validation.is_valid:
                # Clean up temp file
                tmp_path.unlink(missing_ok=True)
                raise ValueError(validation.error_message)

            # ── Duplicate check ───────────────────────────────
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

            # ── Create DB records ─────────────────────────────
            document_id = str(uuid.uuid4())
            job_id = str(uuid.uuid4())

            document = await self.document_repo.create_document(
                document_id=document_id,
                filename=file.filename or "upload.pdf",
                original_filename=file.filename or "upload.pdf",
                file_size_bytes=validation.file_size_bytes,
                file_hash=validation.file_hash,
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

            # ── Schedule background processing ────────────────
            # This returns immediately - pipeline runs in background
            background_tasks.add_task(
                self.pipeline.run,
                document_id=document_id,
                job_id=job_id,
                file_path=tmp_path,
                original_filename=file.filename or "upload.pdf",
            )

            log.info("Background ingestion scheduled")
            return document, job

        except Exception:
            # Clean up temp file on any error
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

        # Verify it exists
        doc = await self.document_repo.get_document(document_id)
        if not doc:
            raise ValueError(f"Document not found: {document_id}")

        # Delete vectors from Qdrant
        deleted_vectors = await self.vector_repo.delete_document_chunks(
            document_id
        )
        log.info("Vectors deleted", count=deleted_vectors)

        # Soft delete in PostgreSQL
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
            os.close(tmp_fd)  # Close the file descriptor

            # Read and write in chunks to handle large files
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
```

---

## STEP 12 — API Schemas

Create `app/api/schemas/documents.py`:

```python
# app/api/schemas/documents.py
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
```

---

## STEP 13 — Documents Router

Create `app/api/v1/routers/documents.py`:

```python
# app/api/v1/routers/documents.py
import math
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
import structlog

from app.api.schemas.documents import (
    DocumentUploadResponse,
    JobStatusResponse,
    DocumentResponse,
    DocumentListResponse,
)
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


def get_document_service() -> DocumentService:
    """
    Build the DocumentService with all its dependencies.
    In a larger app this would use FastAPI Depends properly.
    For now, we construct it here.
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
):
    """Upload and start ingestion of a PDF document."""
    service = get_document_service()

    try:
        document, job = await service.initiate_upload(
            file=file,
            background_tasks=background_tasks,
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
async def get_document_status(document_id: str):
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
async def get_document(document_id: str):
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
async def delete_document(document_id: str):
    """Delete a document and remove all its vectors from Qdrant."""
    service = get_document_service()

    try:
        await service.delete_document(document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

---

## STEP 14 — Wire Documents Router into Main

Update `app/main.py` — just add one import and one `include_router` line:

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
from app.api.v1.routers import documents   # ← NEW

setup_logging()
logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
    )

    logger.info("Initializing database tables...")
    try:
        await create_all_tables()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise

    logger.info("Checking Redis connection...")
    redis_ok, redis_detail = await check_redis_connection()
    if redis_ok:
        logger.info("Redis connected", detail=redis_detail)
    else:
        logger.warning("Redis not available", detail=redis_detail)

    logger.info("Initializing Qdrant collection...")
    try:
        await ensure_collection_exists()
        logger.info("Qdrant collection ready")
    except Exception as e:
        logger.warning("Qdrant initialization failed", error=str(e))

    logger.info("=" * 50)
    logger.info("Application ready to serve requests")
    logger.info("=" * 50)

    yield

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

    app.add_middleware(TimingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")   # ← NEW

    return app


app = create_app()
```

---

## STEP 15 — Run and Verify Everything

### 15.1 Make sure Docker services are running

```bash
docker compose ps
```

All three should show `running (healthy)`. If not:

```bash
docker compose up -d qdrant redis postgres
```

### 15.2 Start the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Watch for these lines in the startup output:
```
Database tables ready
Redis connected
Qdrant collection ready
Application ready to serve requests
```

### 15.3 Open Swagger UI

Go to `http://localhost:8000/docs`

You should now see a **Documents** section with 5 endpoints.

### 15.4 Upload a real PDF

Find any PDF on your computer. Then in a second terminal:

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@C:\path\to\your\document.pdf"
```

Replace the path with a real PDF on your machine.

Expected response:
```json
{
  "document_id": "abc-123",
  "job_id": "xyz-789",
  "filename": "your-document.pdf",
  "status": "processing",
  "message": "Document uploaded successfully. Indexing started in background..."
}
```

### 15.5 Poll job status

```bash
curl http://localhost:8000/api/v1/documents/{document_id}/status
```

Replace `{document_id}` with the ID from the upload response. Run this a few times and watch progress go from 10 → 25 → 40 → 80 → 100.

Final state should be:
```json
{
  "status": "completed",
  "progress": 100,
  "current_step": "Indexing complete"
}
```

### 15.6 List documents

```bash
curl http://localhost:8000/api/v1/documents
```

Expected:
```json
{
  "documents": [
    {
      "id": "abc-123",
      "filename": "your-document.pdf",
      "status": "indexed",
      "total_pages": 5,
      "total_chunks": 23
    }
  ],
  "total": 1,
  "page": 1
}
```

### 15.7 Verify vectors in Qdrant

```bash
curl http://localhost:6333/collections/company_documents
```

Look for `vectors_count` — it should be greater than 0.

---

## Phase 4 Complete — What We Built

```
PDF Upload Request
      │
      ▼
DocumentValidator          ← Is it a valid PDF? Right size?
      │
      ▼
DocumentRepository         ← Create document + job record in PostgreSQL
      │
      ▼
BackgroundTask             ← Return 202 to client immediately
      │
      ▼ (runs in background)
IngestionPipeline
      │
      ├─ PDFParser          ← Extract text page by page (PyMuPDF)
      │
      ├─ SemanticChunker    ← Split into overlapping chunks
      │
      ├─ GeminiEmbeddings   ← Generate 768-dim vectors
      │
      ├─ VectorRepository   ← Store in Qdrant
      │
      └─ DocumentRepository ← Update status to INDEXED

Client polls /status      ← Sees progress 10→25→40→80→100
```

---

**Tell me:**

1. Did the server start with all 4 success messages?
2. Did the PDF upload return a `document_id` and `job_id`?
3. Did the job status eventually reach `completed` with `progress: 100`?
4. Did the Qdrant collection show vectors stored?
5. Any errors anywhere?

Once confirmed we move to **Phase 5: LLM Provider Abstraction and Prompt System.**