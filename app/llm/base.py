# app/llm/base.py
"""
LLM Provider Abstraction

Defines the interface that ALL LLM providers must implement.
Whether we use Gemini or Bedrock, the application calls these same methods.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional
from pydantic import BaseModel


class LLMMessage(BaseModel):
    """Standard message format for all LLMs."""
    role: str
    content: Optional[str] = None  # Optional because tool calls have no content
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None  # Used when role is "tool"

class ToolDefinition(BaseModel):
    type: str = "function"
    function: dict

class LLMRequest(BaseModel):
    """Standard request format for LLM generation."""
    messages: list[LLMMessage]
    max_tokens: int = 2048
    temperature: float = 0.1
    stream: bool = False
    request_id: Optional[str] = None
    tools: Optional[list[ToolDefinition]] = None
    tool_choice: Optional[str] = None  # "auto", "required", or specific tool

class LLMResponse(BaseModel):
    """Standard response format from LLM generation."""
    content: Optional[str] = None
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: Optional[str] = None
    tool_calls: Optional[list[dict]] = None


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