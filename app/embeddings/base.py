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