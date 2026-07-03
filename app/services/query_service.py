# app/services/query_service.py
"""
Query Service

Handles rewriting conversational queries into standalone queries
for the vector database, preventing retrieval misses on pronouns/references.
"""
import structlog
from app.llm.base import LLMProvider, LLMRequest, LLMMessage
from app.services.memory_service import MemoryService

logger = structlog.get_logger()

class QueryService:
    def __init__(self, llm_provider: LLMProvider, memory_service: MemoryService):
        self.llm = llm_provider
        self.memory = memory_service

    async def rewrite_query(self, query: str, session_id: str) -> str:
        history = await self.memory.get_history(session_id)
        if not history:
            return query

        log = logger.bind(original_query=query[:50], session_id=session_id)
        history_str = "\n".join([f"{msg.role}: {msg.content}" for msg in history[-4:]])
        
        messages = [
            LLMMessage(role="system", content=(
                "You are a query rewriter. Given a conversation history and a follow-up question, "
                "rewrite the follow-up question to be a standalone question. "
                "Do not answer the question, just rewrite it. Output ONLY the rewritten question."
            )),
            LLMMessage(role="user", content=f"Conversation history:\n{history_str}\n\nFollow-up question: {query}\n\nStandalone question:")
        ]
        
        request = LLMRequest(messages=messages, max_tokens=100, temperature=0.0)
        
        try:
            response = await self.llm.generate(request)
            rewritten = response.content.strip().strip('"')
            log.info("Query rewritten", rewritten_query=rewritten[:50])
            return rewritten
        except Exception as e:
            log.warning("Query rewrite failed, using original", error=str(e))
            return query