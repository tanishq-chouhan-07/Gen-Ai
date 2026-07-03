"""
OpenAI Compatible LLM Provider (via httpx)

Works with any OpenAI-compatible API (Groq, Together, Anyscale, etc.)
by overriding the base_url. Uses httpx directly to avoid SDK DLL issues.
"""
import httpx
import json
from typing import AsyncGenerator
import structlog

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMMessage
from app.config.settings import get_settings

logger = structlog.get_logger()


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM Provider implementation using httpx."""
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_url.rstrip('/')
        self.model_id = settings.openai_chat_model
        self.logger = logger.bind(provider="groq_httpx", model=self.model_id)
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate complete response."""
        log = self.logger.bind(request_id=request.request_id)
        
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        log.debug("Calling Groq API via httpx")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        log.info(
            "Response received",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
        
        return LLMResponse(
            content=content,
            model=self.model_id,
            provider="openai",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=data["choices"][0].get("finish_reason", "unknown"),
        )
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream tokens from API via httpx."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            # print(f"DEBUG: Received data: {data}")  # Debugging line
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
    
    def get_model_id(self) -> str:
        return self.model_id
    
    async def health_check(self) -> bool:
        try:
            test_request = LLMRequest(
                messages=[LLMMessage(role="user", content="Reply with: OK")],
                max_tokens=10,
            )
            response = await self.generate(test_request)
            return len(response.content) > 0
        except Exception:
            return False