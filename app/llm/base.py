"""
LLM Provider Abstraction

Defines the interface that ALL LLM providers must implement.
Whether we use Gemini or Bedrock, the application calls these same methods.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator
from pydantic import BaseModel


class LLMMessage(BaseModel):
    """Standard message format for all LLMs."""
    role: str
    content: str


class LLMRequest(BaseModel):
    """Standard request format for LLM generation."""
    messages: list[LLMMessage]
    max_tokens: int = 2048
    temperature: float = 0.1
    stream: bool = False
    request_id: str | None = None


class LLMResponse(BaseModel):
    """Standard response format from LLM generation."""
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Swap Gemini for Bedrock by changing config - zero business logic changes.
    """

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Generate a streaming response token by token."""
        ...

    @abstractmethod
    def get_model_id(self) -> str:
        """Return the model identifier."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify provider connectivity."""
        ...