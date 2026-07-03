"""
Local Embedding Provider

Uses sentence-transformers to run embedding models locally.
Zero API costs, completely private.
"""
import asyncio
import structlog
from sentence_transformers import SentenceTransformer

from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings

logger = structlog.get_logger()


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.
    Downloads the model on first use, then runs entirely offline.
    """
    
    def __init__(self):
        settings = get_settings()
        self.model_id = settings.embedding_model_name
        self._dimension = settings.embedding_dimensions
        
        self.logger = logger.bind(provider="local", model=self.model_id)
        self.logger.info("Loading local embedding model (this may take a minute on first run)...")
        
        # Load the model into memory
        self._model = SentenceTransformer(self.model_id)
        
        self.logger.info("Local embedding model loaded successfully")
    
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        
        # Run synchronous inference in a thread to avoid blocking event loop
        # FIX: Use keyword arguments for sentence-transformers v3.x compatibility
        vector = await asyncio.to_thread(
            self._model.encode,
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return vector.tolist()
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts at once."""
        if not texts:
            return []
        
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return []
        
        self.logger.debug("Embedding batch", batch_size=len(valid_texts))
        
        # FIX: Use keyword arguments for sentence-transformers v3.x compatibility
        vectors = await asyncio.to_thread(
            self._model.encode,
            valid_texts,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        
        return vectors.tolist()
    
    def get_dimension(self) -> int:
        return self._dimension
    
    def get_model_id(self) -> str:
        return self.model_id
    
    async def health_check(self) -> bool:
        try:
            vector = await self.embed("health check")
            return len(vector) == self._dimension
        except Exception as e:
            self.logger.error("Local embedding health check failed", error=str(e))
            return False