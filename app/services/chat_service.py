# app/services/chat_service.py
"""
Chat Service (Compound AI System)

Orchestrates an agentic loop with 4-Tier Caching:
1. Prompt-Prefix: System prompt kept at start for Groq API native caching.
2. Embedding Cache: Handled in EmbeddingProvider.
3. Response Cache: Handled in LLMProvider.
4. Semantic Cache: Handled in ChatService before Agent loop starts.
"""
from typing import AsyncGenerator
import structlog
import json

from app.llm.base import LLMProvider, LLMRequest, LLMMessage, ToolDefinition
from app.services.retrieval_service import RetrievalService
from app.services.memory_service import MemoryService
from app.services.guardrail_service import GuardrailService
from app.services.cache_service import CacheService
from app.tools.document_search import DocumentSearchTool
from app.prompts.builder import PromptBuilder

logger = structlog.get_logger()


class ChatService:
    """Main business logic for agentic chat interactions."""
    
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
        
        self.search_tool = DocumentSearchTool(retrieval_service)
        self.guardrails = GuardrailService(llm_provider)
        self.cache = CacheService(retrieval_service.embedding_provider)
        
        self.tools = [
            ToolDefinition(**self.search_tool.schema),
            ToolDefinition(
                type="function",
                function={
                    "name": "finish_answer",
                    "description": "Use this to deliver the final answer to the user. You must cite sources used.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "answer": {"type": "string", "description": "The final answer text"},
                            "citations_used": {
                                "type": "array", 
                                "items": {"type": "integer"},
                                "description": "List of citation numbers [1, 2] actually used in the answer"
                            }
                        },
                        "required": ["answer", "citations_used"]
                    }
                }
            )
        ]
    
    async def stream_chat(self, query: str, session_id: str, user_id: str, is_admin: bool) -> AsyncGenerator[str, None]:
        """
        Streaming chat response.
        NOTE: True streaming with tool-calling requires parsing tool-call deltas.
        To keep this stable for the SSE endpoint, we run the bounded agent loop,
        then stream the final assembled answer back to the client.
        """
        log = logger.bind(session_id=session_id, query_preview=query[:50])
        log.info("Starting streaming agent chat")
        
        result = await self.chat(query, session_id, user_id, is_admin)
        final_answer = result.get("answer", "")
        
        words = final_answer.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            
        log.info("Streaming agent chat completed")
    
    async def chat(self, query: str, session_id: str, user_id: str, is_admin: bool) -> dict:
        """Non-streaming agentic chat response."""
        log = logger.bind(session_id=session_id, query_preview=query[:50])
        log.info("Starting agent chat loop")

        # MULTI-TENANCY: Admins search all caches (user_id=None), Users search their own
        cache_user_scope = None if is_admin else user_id

        # TIER 4 CACHE: Semantic Cache check
        cached_result = await self.cache.check_cache(query, user_id=cache_user_scope)
        if cached_result:
            log.info("Returning cached result bypassing Agent loop")
            return cached_result

        # INPUT GUARDRAIL: Check for prompt injection
        if self.guardrails.detect_prompt_injection(query):
            log.warning("Request blocked by input guardrail")
            return {
                "answer": "I cannot process requests that attempt to override my instructions.",
                "citations": [],
                "model": "guardrail",
                "provider": "system"
            }

        history = await self.memory.get_history(session_id)

        from app.prompts.registry import PromptRegistry
        from datetime import datetime
        
        system_template = PromptRegistry.get("system_agent_v1")
        system_content = system_template["template"].format(
            company_name="Our Company",
            current_date=datetime.now().strftime("%B %d, %Y"),
        )

        # TIER 1 CACHE: Prompt-Prefix Structure
        # System prompt is FIRST, followed by history, then the new query.
        # This allows the LLM API (Groq) to cache the system prompt prefix natively.
        messages = [
            LLMMessage(role="system", content=system_content),
        ]
        
        if history:
            messages.extend(history[-4:])
            
        messages.append(LLMMessage(role="user", content=query))

        # AGENT LOOP (Bounded to 5 steps)
        for step in range(5):
            request = LLMRequest(
                messages=messages,
                # max_tokens=2048,
                max_tokens=8192,
                temperature=0.1,
                tools=self.tools,
                tool_choice="auto"
            )

            # TIER 3 CACHE happens inside self.llm.generate()
            response = await self.llm.generate(request)
            assistant_msg = LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls
            )
            messages.append(assistant_msg)

            if not response.tool_calls:
                log.warning("Agent did not call a tool, forcing fallback finish")
                final_text = response.content or "I could not process that request."
                await self.memory.save_turn(session_id, query, final_text)
                return {
                    "answer": final_text,
                    "citations": [],
                    "model": response.model,
                    "provider": response.provider
                }

            for tool_call in response.tool_calls:
                func_name = tool_call["function"]["name"]
                args = json.loads(tool_call["function"]["arguments"])

                if func_name == "search_documents":
                    search_query = args.get("query", query)
                    
                    # MULTI-TENANCY: Admins see all, Users only see their own
                    target_user_id = None if is_admin else user_id
                    
                    # TIER 2 CACHE happens inside self.search_tool.execute() -> retrieve() -> embed()
                    chunks = await self.search_tool.execute(search_query, user_id=target_user_id)
                    messages.append(LLMMessage(
                        role="tool",
                        tool_call_id=tool_call["id"],
                        content=chunks
                    ))
                    log.info("Agent used search tool", agent_query=search_query, scoped_user=target_user_id or "ALL (Admin)")

                elif func_name == "finish_answer":
                    final_answer = args.get("answer", "")
                    citations_used = args.get("citations_used", [])
                    
                    # OUTPUT GUARDRAIL (Evaluator-Optimizer)
                    is_grounded, critique = await self.guardrails.check_faithfulness(
                        final_answer, self.search_tool.last_chunks
                    )
                    
                    if not is_grounded and step < 4:
                        log.warning("Agent answer failed faithfulness check, requesting revision", critique=critique)
                        messages.append(LLMMessage(
                            role="user",
                            content=f"Your previous answer was not grounded in the provided context. Critique: {critique}. Please revise your answer using ONLY the provided context and call finish_answer again."
                        ))
                        continue

                    citations = []
                    for cite_num in citations_used:
                        idx = int(cite_num) - 1
                        if 0 <= idx < len(self.search_tool.last_chunks):
                            chunk = self.search_tool.last_chunks[idx]
                            citations.append({
                                "citation_number": cite_num,
                                "document_id": chunk["document_id"],
                                "filename": chunk["filename"],
                                "page_number": chunk["page_number"],
                                "content_preview": chunk["content"][:200],
                                "relevance_score": chunk.get("rerank_score", chunk.get("score", 0.0))
                            })
                    
                    await self.memory.save_turn(session_id, query, final_answer)
                    log.info("Agent finished with structured output", citation_count=len(citations))
                    
                    result = {
                        "answer": final_answer,
                        "citations": citations,
                        "model": response.model,
                        "provider": response.provider
                    }

                    # TIER 4 CACHE: Add to Semantic Cache (scoped to user)
                    if citations:
                        await self.cache.add_to_cache(query, result, user_id=cache_user_scope)

                    return result

        return {
            "answer": "I was unable to complete the request within the allowed steps.", 
            "citations": [],
            "model": "unknown",
            "provider": "unknown"
        }