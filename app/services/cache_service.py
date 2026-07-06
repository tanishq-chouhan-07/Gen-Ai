# app/services/cache_service.py
"""
Semantic Cache Service (Multi-Tenant)

Uses Redis Stack's vector search capabilities to cache RAG results.
Filters cache hits by user_id to prevent cross-tenant data leakage.
"""
import json
import structlog
import numpy as np
from app.db.redis_client import get_redis_binary_client, get_redis_client
from app.embeddings.base import EmbeddingProvider

logger = structlog.get_logger()

class CacheService:
    def __init__(self, embedding_provider: EmbeddingProvider):
        self.redis_bytes = get_redis_binary_client()
        self.redis_str = get_redis_client()
        self.embedding_provider = embedding_provider
        self.index_name = "semantic_cache_idx"
        self.prefix = "cache:"
        self.threshold = 0.95 # 95% cosine similarity required for a hit
        self.vector_dim = 1024 # BGE-large dimension

    async def init_index(self):
        """Create the vector index in Redis if it doesn't exist."""
        try:
            await self.redis_bytes.ft(self.index_name).info()
        except Exception:
            # Index does not exist, create it
            from redis.commands.search.field import TextField, VectorField, TagField
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType
            
            schema = (
                TagField("user_id"), # MULTI-TENANCY: Tag field for fast user filtering
                TextField("query_text"),
                TextField("result_json"),
                VectorField("query_vector", "FLAT", {"TYPE": "FLOAT32", "DIM": self.vector_dim, "DISTANCE_METRIC": "COSINE"})
            )
            definition = IndexDefinition(prefix=[self.prefix], index_type=IndexType.HASH)
            await self.redis_bytes.ft(self.index_name).create_index(schema, definition=definition)
            logger.info("Redis multi-tenant semantic cache index created")

    async def check_cache(self, query: str, user_id: str | None) -> dict | None:
        """
        Embeds the query and checks for a similar past query.
        Filters by user_id (or searches all if admin/user_id is None).
        """
        await self.init_index()
        
        query_vector = await self.embedding_provider.embed(query)
        vec_bytes = np.array(query_vector, dtype=np.float32).tobytes()

        from redis.commands.search.query import Query
        
        # MULTI-TENANCY: Filter by user_id tag. 
        # If user_id is None (Admin), search all caches using "*"
        filter_str = f"@user_id:{{{user_id}}}" if user_id else "*"
        
        q = (
            Query(f"{filter_str}=>[KNN 1 @query_vector $vec AS score]")
            .return_fields("result_json", "score")
            .dialect(2)
        )

        try:
            # Search using the binary client because we are passing vector bytes
            results = await self.redis_bytes.ft(self.index_name).search(q, query_params={"vec": vec_bytes})
            if results.docs:
                doc = results.docs[0]
                # Redis returns distance (0 = identical, 2 = opposite). Convert to similarity 0-1
                similarity = 1 - float(doc.score)
                
                if similarity >= self.threshold:
                    logger.info("Semantic cache HIT", similarity=similarity, user_id=user_id or "ALL")
                    # result_json is returned as bytes, need to decode it
                    result_str = doc.result_json.decode('utf-8') if isinstance(doc.result_json, bytes) else doc.result_json
                    return json.loads(result_str)
        except Exception as e:
            logger.warning("Cache search failed", error=str(e))
        
        logger.info("Semantic cache MISS", user_id=user_id or "ALL")
        return None

    async def add_to_cache(self, query: str, result: dict, user_id: str | None):
        """Stores a query and its result in the Redis vector cache."""
        query_vector = await self.embedding_provider.embed(query)
        vec_bytes = np.array(query_vector, dtype=np.float32).tobytes()

        cache_key = f"{self.prefix}{abs(hash(query + str(user_id)))}"
        
        await self.redis_bytes.hset(cache_key, mapping={
            "user_id": user_id if user_id else "admin", # MULTI-TENANCY: Tag the cache entry
            "query_text": query,
            "result_json": json.dumps(result),
            "query_vector": vec_bytes
        })
        await self.redis_bytes.expire(cache_key, 86400)
        logger.info("Added result to semantic cache", user_id=user_id or "ALL")