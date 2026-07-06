# app/db/redis_client.py
"""
Redis connection manager.

Redis is used for:
1. Conversation memory (chat history per session) - String Client
2. Job progress tracking (ingestion pipeline) - String Client
3. Semantic Vector Caching - Binary Client (requires decode_responses=False)
"""
import redis.asyncio as aioredis
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger()

# Module-level clients - created once, reused everywhere
_redis_client: aioredis.Redis | None = None
_redis_binary_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """
    Get or create the standard Redis client (strings/JSON).
    Uses connection pooling automatically.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,   # Return strings, not bytes
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("Redis string client created", url=settings.redis_url)
    return _redis_client


def get_redis_binary_client() -> aioredis.Redis:
    """
    Get or create the binary Redis client (for vector search).
    Requires decode_responses=False to handle float32 byte arrays.
    """
    global _redis_binary_client
    if _redis_binary_client is None:
        settings = get_settings()
        _redis_binary_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=False, # Return bytes, not strings
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("Redis binary client created for vector search", url=settings.redis_url)
    return _redis_binary_client


async def check_redis_connection() -> tuple[bool, str]:
    """
    Test Redis connectivity.
    Returns (is_healthy, detail_message)
    """
    try:
        client = get_redis_client()
        await client.ping()
        return True, "Connected successfully"
    except Exception as e:
        logger.error("Redis connection failed", error=str(e))
        return False, str(e)


async def close_redis() -> None:
    """
    Close Redis connections gracefully.
    Called at application shutdown.
    """
    global _redis_client, _redis_binary_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis string connection closed")
    if _redis_binary_client:
        await _redis_binary_client.aclose()
        _redis_binary_client = None
        logger.info("Redis binary connection closed")