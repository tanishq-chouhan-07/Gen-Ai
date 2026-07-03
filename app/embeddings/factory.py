"""
Embedding Provider Factory

Reads EMBEDDING_PROVIDER from settings and returns the correct provider.
"""
from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings
import structlog

logger = structlog.get_logger()


def create_embedding_provider() -> EmbeddingProvider:
    """Factory function that creates the configured embedding provider."""
    settings = get_settings()
    provider_name = settings.embedding_provider

    logger.info("Creating embedding provider", provider=provider_name)

    if provider_name == "gemini":
        from app.embeddings.providers.gemini_embeddings import GeminiEmbeddingProvider
        return GeminiEmbeddingProvider()

    elif provider_name == "local":
        from app.embeddings.providers.local_embeddings import LocalEmbeddingProvider
        return LocalEmbeddingProvider()

    elif provider_name == "bedrock":
        raise NotImplementedError(
            "Bedrock embedding provider will be added in Phase 7. "
            "Use EMBEDDING_PROVIDER=gemini or local for now."
        )

    else:
        raise ValueError(
            f"Unknown embedding provider: '{provider_name}'. "
            f"Supported: ['gemini', 'local', 'bedrock']"
        )