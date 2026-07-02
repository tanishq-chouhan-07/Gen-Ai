"""
Qdrant vector database connection manager.

Qdrant stores:
- Document chunk embeddings (dense vectors)
- Chunk metadata (filename, page number, document_id, etc.)

We use the async Qdrant client for non-blocking operations.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    CollectionInfo,
)
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger()

# Module-level client
_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """
    Get or create the Qdrant client.
    """
    global _qdrant_client
    if _qdrant_client is None:
        settings = get_settings()
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=30,
        )
        logger.info(
            "Qdrant client created",
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
    return _qdrant_client


async def check_qdrant_connection() -> tuple[bool, str]:
    """
    Test Qdrant connectivity.
    Returns (is_healthy, detail_message)
    """
    try:
        client = get_qdrant_client()
        # get_collections is a lightweight call that confirms connectivity
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]
        return True, f"Connected. Collections: {collection_names}"
    except Exception as e:
        logger.error("Qdrant connection failed", error=str(e))
        return False, str(e)


async def ensure_collection_exists() -> None:
    """
    Create the documents collection in Qdrant if it doesn't exist.
    Safe to call multiple times - won't recreate if already exists.

    Called at application startup.
    """
    settings = get_settings()
    client = get_qdrant_client()

    try:
        # Check if collection already exists
        existing = await client.get_collections()
        existing_names = [c.name for c in existing.collections]

        if settings.qdrant_collection in existing_names:
            logger.info(
                "Qdrant collection already exists",
                collection=settings.qdrant_collection,
            )
            return

        # Create the collection
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,  # 768 for Gemini embeddings
                distance=Distance.COSINE,           # Cosine similarity
            ),
        )

        logger.info(
            "Qdrant collection created",
            collection=settings.qdrant_collection,
            vector_size=settings.qdrant_vector_size,
        )

    except Exception as e:
        logger.error(
            "Failed to ensure Qdrant collection",
            error=str(e),
            collection=settings.qdrant_collection,
        )
        raise


async def close_qdrant() -> None:
    """
    Close Qdrant connection gracefully.
    Called at application shutdown.
    """
    global _qdrant_client
    if _qdrant_client:
        await _qdrant_client.close()
        _qdrant_client = None
        logger.info("Qdrant connection closed")