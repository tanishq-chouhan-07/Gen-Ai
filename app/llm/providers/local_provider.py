# app/llm/providers/openai_provider.py
"""
OpenAI Compatible LLM Provider (via httpx)

Works with any OpenAI-compatible API (Groq, Together, Anyscale, etc.)
Implements Tier 3 Caching: Identical API requests return cached responses.
"""
import httpx
import json
import hashlib
from typing import AsyncGenerator
import structlog

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMMessage
from app.config.settings import get_settings
from app.db.redis_client import get_redis_client

logger = structlog.get_logger()


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM Provider implementation using httpx."""
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_url.rstrip('/')
        self.model_id = settings.openai_chat_model
        self.redis = get_redis_client()
        self.logger = logger.bind(provider="groq_httpx", model=self.model_id)
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming generation with Tier 3 Response Cache."""
        
        # TIER 3 CACHE: Exact-match response cache
        req_dict = {
            "model": self.get_model_id(),
            "messages": [msg.model_dump(exclude_none=True) for msg in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "tools": [t.model_dump() for t in request.tools] if request.tools else None,
            "tool_choice": request.tool_choice
        }
        req_hash = hashlib.md5(json.dumps(req_dict, sort_keys=True).encode()).hexdigest()
        cache_key = f"llm_cache:{req_hash}"

        cached_resp = await self.redis.get(cache_key)
        if cached_resp:
            self.logger.info("LLM Response cache HIT")
            return LLMResponse.model_validate_json(cached_resp)

        # Cache Miss: Build payload and call API
        payload = req_dict.copy()
        if not payload["tools"]:
            del payload["tools"]
            del payload["tool_choice"]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Create httpx client on the fly
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            response_json = response.json()
            
            choice = response_json["choices"][0]
            message = choice["message"]
            
            llm_response = LLMResponse(
                content=message.get("content"),
                model=self.get_model_id(),
                provider="openai",
                tool_calls=message.get("tool_calls"),
                finish_reason=choice.get("finish_reason"),
                input_tokens=response_json.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=response_json.get("usage", {}).get("completion_tokens", 0)
            )
            
            # Save to cache (1h TTL for LLM responses)
            await self.redis.setex(cache_key, 3600, llm_response.model_dump_json())
            return llm_response
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream tokens from API via httpx. (No caching applied to streams)."""
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