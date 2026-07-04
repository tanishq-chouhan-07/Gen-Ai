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
        user_id: str,  # MULTI-TENANCY: Added user_id
    ) -> int:
        """
        Store chunk vectors in Qdrant.

        Args:
            chunks: List of DocumentChunk objects
            embeddings: Corresponding embedding vectors (same order as chunks)
            document_filename: Original filename for search results
            user_id: The UUID of the user uploading the document

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
            user_id=user_id,
        )

        # Build Qdrant point objects
        points = []
        for chunk, vector in zip(chunks, embeddings):
            # The payload is stored alongside the vector in Qdrant
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "user_id": user_id,  # MULTI-TENANCY: Save user_id in payload
                "content": chunk.content,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "token_count": chunk.token_count,
                "filename": document_filename,
                **chunk.metadata,
            }

            points.append(PointStruct(
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
        user_id: str | None = None,  # MULTI-TENANCY: Added user_id filter
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        """
        Find the most similar chunks to a query vector.

        Args:
            query_vector: The embedded query
            top_k: Maximum number of results to return
            document_ids: Optional filter to specific documents
            user_id: Optional filter to restrict search to a specific user's documents
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of RetrievedChunk sorted by similarity (highest first)
        """
        must_conditions = []
        
        if document_ids:
            must_conditions.extend([
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=doc_id),
                )
                for doc_id in document_ids
            ])
            
        if user_id:  # MULTI-TENANCY: Apply user filter
            must_conditions.append(
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            )

        search_filter = Filter(must=must_conditions) if must_conditions else None

        results = await self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=search_filter,
            score_threshold=score_threshold,
            with_payload=True,
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

    async def delete_by_document_id(self, document_id: str) -> None:
        """Delete all chunks associated with a document ID from Qdrant."""
        await self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            )
        )

    @staticmethod
    def _chunk_id_to_int(chunk_id: str) -> int:
        """
        Convert a string chunk ID to a stable integer for Qdrant.
        Qdrant requires integer or UUID point IDs.
        We use abs(hash()) for a stable integer from any string.
        """
        return abs(hash(chunk_id)) % (2**53)