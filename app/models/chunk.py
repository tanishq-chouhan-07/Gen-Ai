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