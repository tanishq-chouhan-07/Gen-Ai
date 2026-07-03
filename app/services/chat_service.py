"""
Chat Service

Orchestrates the full RAG pipeline:
1. Load history
2. Retrieve context
3. Build prompt
4. Generate/stream LLM response
5. Save history
"""
from typing import AsyncGenerator
import structlog

from app.llm.base import LLMProvider, LLMRequest, LLMMessage
from app.services.retrieval_service import RetrievalService
from app.services.memory_service import MemoryService
from app.prompts.builder import PromptBuilder

logger = structlog.get_logger()


class ChatService:
    """Main business logic for chat interactions."""
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        retrieval_service: RetrievalService,
        memory_service: MemoryService,
        prompt_builder: PromptBuilder,
    ):
        self.llm = llm_provider
        self.retrieval = retrieval_service
        self.memory = memory_service
        self.prompt_builder = prompt_builder
    
    async def stream_chat(self, query: str, session_id: str) -> AsyncGenerator[str, None]:
        """Stream a chat response token by token."""
        log = logger.bind(session_id=session_id, query_preview=query[:50])
        log.info("Starting streaming chat")
        
        # 1. Load history
        history = await self.memory.get_history(session_id)
        
        # 2. Retrieve context from Qdrant
        context_chunks = await self.retrieval.retrieve(query)
        
        # 3. Build prompt
        messages = self.prompt_builder.build_rag_prompt(
            query=query,
            context_chunks=context_chunks,
            conversation_history=history
        )
        
        # 4. Generate streaming response
        request = LLMRequest(
            messages=messages,
            max_tokens=2048,  # Give reasoning models room to think + answer
            temperature=0.1,
            stream=True
        )
        
        full_response = []
        async for token in self.llm.generate_stream(request):
            full_response.append(token)
            yield token
            
        # 5. Save turn to memory
        full_text = "".join(full_response)
        await self.memory.save_turn(session_id, query, full_text)
        
        log.info("Streaming chat completed", response_length=len(full_text))
    
    async def chat(self, query: str, session_id: str) -> dict:
        """Non-streaming chat response."""
        log = logger.bind(session_id=session_id, query_preview=query[:50])
        log.info("Starting chat")
        
        # 1. Load history
        history = await self.memory.get_history(session_id)
        
        # 2. Retrieve context
        context_chunks = await self.retrieval.retrieve(query)
        
        # 3. Build prompt
        messages = self.prompt_builder.build_rag_prompt(
            query=query,
            context_chunks=context_chunks,
            conversation_history=history
        )
        
        # 4. Generate response
        request = LLMRequest(messages=messages, max_tokens=2048, temperature=0.1)
        response = await self.llm.generate(request)
        
        # 5. Save turn to memory
        await self.memory.save_turn(session_id, query, response.content)
        
        # 6. Extract citations from chunks
        citations = []
        for i, chunk in enumerate(context_chunks, 1):
            citations.append({
                "citation_number": i,
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "page_number": chunk["page_number"],
                "content_preview": chunk["content"][:200],
                "relevance_score": chunk["score"]
            })
        
        return {
            "answer": response.content,
            "citations": citations,
            "model": response.model,
            "provider": response.provider
        }