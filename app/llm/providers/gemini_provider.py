"""
Gemini LLM Provider Implementation

Uses Google's gemini-2.5-flash model.
Used in development. Replaced by BedrockProvider in production.
"""
import asyncio
import google.generativeai as genai
from typing import AsyncGenerator
import structlog

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMMessage
from app.config.settings import get_settings

logger = structlog.get_logger()


class GeminiProvider(LLMProvider):
    """Google Gemini LLM Provider implementation."""
    
    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.model_id = settings.gemini_model
        self._model = genai.GenerativeModel(self.model_id)
        self.logger = logger.bind(provider="gemini", model=self.model_id)
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate complete response from Gemini."""
        log = self.logger.bind(request_id=request.request_id)
        
        system_prompt, contents = self._format_messages(request.messages)
        
        model = self._model
        if system_prompt:
            model = genai.GenerativeModel(self.model_id, system_instruction=system_prompt)
        
        generation_config = genai.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        
        log.debug("Calling Gemini API")
        response = await asyncio.to_thread(
            model.generate_content,
            contents,
            generation_config=generation_config,
        )
        
        content = response.text or ""
        usage = response.usage_metadata
        
        log.info(
            "Gemini response received",
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
        )
        
        return LLMResponse(
            content=content,
            model=self.model_id,
            provider="gemini",
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "unknown",
        )
    
    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream tokens from Gemini."""
        system_prompt, contents = self._format_messages(request.messages)
        
        model = self._model
        if system_prompt:
            model = genai.GenerativeModel(self.model_id, system_instruction=system_prompt)
        
        generation_config = genai.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        
        response = await asyncio.to_thread(
            model.generate_content,
            contents,
            generation_config=generation_config,
            stream=True,
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    
    def _format_messages(self, messages: list[LLMMessage]) -> tuple[str | None, list[dict]]:
        """
        Convert standard messages to Gemini format.
        Gemini handles system prompts separately from user/model turns.
        """
        system_prompt = None
        contents = []
        
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({"role": role, "parts": [msg.content]})
        
        return system_prompt, contents
    
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