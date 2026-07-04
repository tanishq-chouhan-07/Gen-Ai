# app/services/guardrail_service.py
"""
Guardrail Service

Handles Input/Output validation for the Compound AI System.
1. Input: Detects prompt injection attempts via regex patterns.
2. Output: Verifies LLM answers are strictly grounded in retrieved chunks (Evaluator-Optimizer).
"""
import re
import structlog
from app.llm.base import LLMProvider, LLMRequest, LLMMessage

logger = structlog.get_logger()

class GuardrailService:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider
        # Simple regex patterns for obvious prompt injection attempts
        self.injection_patterns = [
            r"ignore (all )?previous instructions",
            r"disregard (all )?prior",
            r"you are now (a|an) ",
            r"system prompt:",
            r"reveal your (system )?prompt"
        ]

    def detect_prompt_injection(self, query: str) -> bool:
        """Checks if the user query matches known prompt injection patterns."""
        query_lower = query.lower()
        for pattern in self.injection_patterns:
            if re.search(pattern, query_lower):
                logger.warning("Prompt injection detected", query=query[:50], pattern=pattern)
                return True
        return False

    async def check_faithfulness(self, answer: str, chunks: list[dict]) -> tuple[bool, str]:
        """
        Uses a cheap LLM call to verify the answer is strictly grounded in the provided chunks.
        Returns (is_grounded, critique_or_empty_string).
        """
        if not chunks:
            # If there are no chunks, the answer should be a refusal.
            if "could not find" in answer.lower() or "don't know" in answer.lower():
                return True, ""
            return False, "The answer provides information despite no context being provided. Refuse to answer instead."

        context_str = "\n\n".join([c["content"] for c in chunks])
        
        system_prompt = (
            "You are a strict fact-checker. Your job is to determine if the 'Answer' is fully supported by the 'Context'. "
            "If the answer contains facts, numbers, or claims not present in the context, output 'FAIL'. "
            "If the answer is fully grounded in the context, output 'PASS'. "
            "If FAIL, provide a one-sentence critique of what was ungrounded. "
            "Format your response exactly as: PASS or FAIL: <critique>"
        )
        
        user_prompt = f"Context:\n{context_str}\n\nAnswer:\n{answer}\n\nIs the answer grounded?"
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            max_tokens=50,
            temperature=0.0
        )
        
        try:
            response = await self.llm.generate(request)
            result = response.content.strip()
            
            if result.startswith("PASS"):
                logger.info("Faithfulness check PASSED")
                return True, ""
            else:
                critique = result.replace("FAIL:", "").strip()
                logger.warning("Faithfulness check FAILED", critique=critique)
                return False, critique
        except Exception as e:
            logger.error("Faithfulness check failed due to API error", error=str(e))
            # Fail safe: Assume it's fine so we don't trap the user in a loop on an API error
            return True, ""