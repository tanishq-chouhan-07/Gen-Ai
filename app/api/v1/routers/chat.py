"""
Chat API Router

Endpoints for interacting with the Document AI Agent.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from functools import lru_cache
import structlog

from app.api.schemas.chat import ChatRequest, ChatResponse
from app.db.models import UserModel
from app.api.dependencies import get_current_user
from app.services.chat_service import ChatService
from app.services.retrieval_service import RetrievalService
from app.services.memory_service import MemoryService
from app.llm.factory import create_llm_provider
from app.embeddings.factory import create_embedding_provider
from app.prompts.builder import PromptBuilder
from app.repositories.vector_repository import VectorRepository
from app.db.qdrant_client import get_qdrant_client

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = structlog.get_logger()


@lru_cache()
def get_chat_service() -> ChatService:
    """Dependency injection for ChatService (Cached as Singleton)."""
    logger.info("Initializing ChatService and loading ML models (this only happens once)...")
    llm_provider = create_llm_provider()
    embedding_provider = create_embedding_provider()
    
    vector_repo = VectorRepository(client=get_qdrant_client())
    retrieval_service = RetrievalService(
        embedding_provider=embedding_provider,
        vector_repo=vector_repo
    )
    memory_service = MemoryService()
    prompt_builder = PromptBuilder()
    
    return ChatService(
        llm_provider=llm_provider,
        retrieval_service=retrieval_service,
        memory_service=memory_service,
        prompt_builder=prompt_builder
    )


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    current_user: UserModel = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """
    Streaming chat endpoint via Server-Sent Events (SSE).
    
    The response is a stream of tokens as they are generated.
    """
    logger.info("User streaming chat", user=current_user.username, session_id=request.session_id)
    
    async def event_generator():
        try:
            async for token in service.stream_chat(
                request.query, 
                request.session_id, 
                user_id=current_user.id, 
                is_admin=(current_user.role == "admin")
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Stream error", error=str(e), user=current_user.username)
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: UserModel = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """
    Standard chat endpoint. Returns the full response after generation.
    """
    logger.info("User chatting", user=current_user.username, session_id=request.session_id)
    
    try:
        result = await service.chat(
            request.query, 
            request.session_id, 
            user_id=current_user.id, 
            is_admin=(current_user.role == "admin")
        )
        return ChatResponse(
            request_id="",
            session_id=request.session_id,
            answer=result["answer"],
            citations=result["citations"],
            model=result["model"],
            provider=result["provider"]
        )
    except Exception as e:
        logger.error("Chat error", error=str(e), user=current_user.username)
        raise HTTPException(status_code=500, detail=str(e))