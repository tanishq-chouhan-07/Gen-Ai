# app/embeddings/providers/local_provider.py
"""
Local Embedding Provider

Uses SentenceTransformers BGE model locally.
Implements Tier 2 Caching: Identical text strings return cached vectors instantly.
"""
import asyncio
import hashlib
import json
import structlog
from sentence_transformers import SentenceTransformer

from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings
from app.db.redis_client import get_redis_client

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
        
        self._model = SentenceTransformer(self.model_id)
        self.redis = get_redis_client()
        
        self.logger.info("Local embedding model loaded successfully")
    
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string, using cache if available."""
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        
        # TIER 2 CACHE: Exact-match embedding cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"embed_cache:{text_hash}"
        
        cached_vec = await self.redis.get(cache_key)
        if cached_vec:
            return json.loads(cached_vec)

        # Compute embedding (normalize for cosine similarity)
        vector = await asyncio.to_thread(
            self._model.encode,
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        vec_list = vector.tolist()

        # Save to Redis (24h TTL)
        await self.redis.setex(cache_key, 86400, json.dumps(vec_list))
        return vec_list
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts at once."""
        if not texts:
            return []
        
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return []
        
        self.logger.debug("Embedding batch", batch_size=len(valid_texts))
        
        # For batch, we skip individual caching for simplicity and compute together
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