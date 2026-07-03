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