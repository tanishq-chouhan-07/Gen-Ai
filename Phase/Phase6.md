# Phase 6: Chat / RAG Pipeline & AI Agent

Now we reach the climax of the application. We have documents stored in Qdrant as 1024-dimension vectors. We have an LLM Provider (Groq via httpx) and a Prompt Builder. 

In this phase, we build the **Chat Pipeline**. When a user asks a question, we will:
1. Embed their question using the local embedder.
2. Search Qdrant for the most relevant document chunks.
3. Inject those chunks into the LLM prompt.
4. Stream the LLM's answer back to the user using Server-Sent Events (SSE).

We will also introduce basic **Conversation Memory** using Redis, so the user can ask follow-up questions.

---

## Phase 6 Game Plan

```
Step 1 → Create directories for Agents and Tools
Step 2 → Pydantic Schemas for Chat
Step 3 → Retrieval Service (Search Qdrant)
Step 4 → Memory Service (Redis Chat History)
Step 5 → Chat Service (Orchestrate RAG + LLM)
Step 6 → Chat API Router (SSE Streaming Endpoint)
Step 7 → Wire Chat Router into FastAPI
Step 8 → Run and Verify Everything
```

---

## STEP 1 — Create Directories

We need folders for the Agent logic and Tools (for future expansion). Run this in Git Bash:

```bash
mkdir -p app/agents
mkdir -p app/tools

type nul > app\agents\__init__.py
type nul > app\tools\__init__.py
```

---

## STEP 2 — Pydantic Schemas for Chat

**Why we do this:** We need strict models for incoming chat requests and outgoing responses so FastAPI can auto-generate the Swagger documentation and validate inputs.

Create `app/api/schemas/chat.py`:

```python
# app/api/schemas/chat.py
from pydantic import BaseModel, Field
from typing import Optional, Any

class CitationSource(BaseModel):
    citation_number: int
    document_id: str
    filename: str
    page_number: int
    content_preview: str
    relevance_score: float

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default_factory=lambda: "default_session")
    stream: bool = True

class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    answer: str
    citations: list[CitationSource]
    model: str
    provider: str
```

---

## STEP 3 — Retrieval Service

**Why we do this:** We need a dedicated service to handle querying Qdrant. It takes a raw text query, uses our embedding provider to convert it to a vector, and searches the vector database.

Create `app/services/retrieval_service.py`:

```python
# app/services/retrieval_service.py
"""
Retrieval Service

Handles semantic document retrieval from Qdrant.
"""
import structlog
from app.repositories.vector_repository import VectorRepository
from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings

logger = structlog.get_logger()


class RetrievalService:
    """Handles querying the vector database."""
    
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_repo: VectorRepository,
    ):
        self.embedding_provider = embedding_provider
        self.vector_repo = vector_repo
        self.settings = get_settings()
    
    async def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Embed the query and search Qdrant for relevant chunks."""
        log = logger.bind(query_preview=query[:50])
        
        # 1. Embed the user query
        query_vector = await self.embedding_provider.embed(query)
        
        # 2. Search Qdrant
        chunks = await self.vector_repo.search(
            query_vector=query_vector,
            top_k=top_k,
            score_threshold=self.settings.retrieval_score_threshold,
        )
        
        log.info("Retrieved chunks", count=len(chunks))
        
        # 3. Format for the prompt builder
        results = []
        for chunk in chunks:
            results.append({
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "page_number": chunk.page_number,
                "content": chunk.content,
                "score": chunk.score,
            })
            
        return results
```

---

## STEP 4 — Memory Service

**Why we do this:** LLMs are stateless. If a user asks "What is PTO?" and then asks "How many days is it?", the LLM doesn't remember "it". We use Redis to store the last few turns of conversation and inject them into the prompt.

Create `app/services/memory_service.py`:

```python
# app/services/memory_service.py
"""
Memory Service

Manages conversation history in Redis.
Stores messages as JSON strings and enforces a TTL so old sessions expire.
"""
import json
import structlog
from app.db.redis_client import get_redis_client
from app.llm.base import LLMMessage
from app.config.settings import get_settings

logger = structlog.get_logger()


class MemoryService:
    """Handles loading and saving conversation history."""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.settings = get_settings()
    
    def _get_key(self, session_id: str) -> str:
        return f"chat_history:{session_id}"
    
    async def get_history(self, session_id: str) -> list[LLMMessage]:
        """Load conversation history for a session."""
        key = self._get_key(session_id)
        data = await self.redis.lrange(key, 0, -1)
        
        messages = []
        for item in data:
            msg_dict = json.loads(item)
            messages.append(LLMMessage(**msg_dict))
            
        return messages
    
    async def save_turn(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """Save a user query and assistant response to history."""
        key = self._get_key(session_id)
        
        user_msg_obj = LLMMessage(role="user", content=user_msg).model_dump()
        assistant_msg_obj = LLMMessage(role="assistant", content=assistant_msg).model_dump()
        
        # Push to Redis list
        await self.redis.rpush(key, json.dumps(user_msg_obj))
        await self.redis.rpush(key, json.dumps(assistant_msg_obj))
        
        # Trim list to last 10 messages (5 turns) to save memory
        await self.redis.ltrim(key, -10, -1)
        
        # Set TTL so history expires if unused
        await self.redis.expire(key, self.settings.session_ttl_seconds)
```

---

## STEP 5 — Chat Service

**Why we do this:** This is the orchestrator. It ties together Memory, Retrieval, Prompt Building, and LLM Generation. It provides two methods: `chat` (single response) and `stream_chat` (yields tokens for SSE).

*Note: I've set `max_tokens=2048` here because Groq's `gpt-oss-120b` is a reasoning model and uses tokens for hidden chain-of-thought before answering.*

Create `app/services/chat_service.py`:

```python
# app/services/chat_service.py
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
```

---

## STEP 6 — Chat API Router

**Why we do this:** We need HTTP endpoints. We will create a standard `POST /chat` and a streaming `POST /chat/stream`. 

The streaming endpoint uses FastAPI's `StreamingResponse` with `media_type="text/event-stream"` to keep the HTTP connection open and push tokens to the client as they arrive from Groq.

Create `app/api/v1/routers/chat.py`:

```python
# app/api/v1/routers/chat.py
"""
Chat API Router

Endpoints for interacting with the Document AI Agent.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import structlog

from app.api.schemas.chat import ChatRequest, ChatResponse
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


def get_chat_service() -> ChatService:
    """Dependency injection for ChatService."""
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
    service: ChatService = Depends(get_chat_service),
):
    """
    Streaming chat endpoint via Server-Sent Events (SSE).
    
    The response is a stream of tokens as they are generated.
    """
    async def event_generator():
        try:
            async for token in service.stream_chat(request.query, request.session_id):
                # SSE format: data: <json>\n\n
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no", # Disable Nginx buffering
        }
    )


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
):
    """
    Standard chat endpoint. Returns the full response after generation.
    """
    try:
        result = await service.chat(request.query, request.session_id)
        return ChatResponse(
            request_id="",
            session_id=request.session_id,
            answer=result["answer"],
            citations=result["citations"],
            model=result["model"],
            provider=result["provider"]
        )
    except Exception as e:
        logger.error("Chat error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

---

## STEP 7 — Wire Chat Router into FastAPI

**Why we do this:** We must register the new router with the main FastAPI app so it can route `/chat` requests to our new code. (This fixes the 404 errors you saw earlier).

Open `app/main.py` and replace the **entire file** with this:

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from app.config.settings import get_settings
from app.observability.logging import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.correlation_id import CorrelationIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.middleware.error_handler import (
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.db.database import create_all_tables, close_database
from app.db.redis_client import check_redis_connection, close_redis
from app.db.qdrant_client import ensure_collection_exists, close_qdrant
from app.api.v1.routers import health, documents, chat
from app.prompts.registry import PromptRegistry

setup_logging()
logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
    )

    logger.info("Initializing database tables...")
    try:
        await create_all_tables()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise

    logger.info("Loading prompt templates...")
    PromptRegistry.load_all()

    logger.info("Checking Redis connection...")
    redis_ok, redis_detail = await check_redis_connection()
    if redis_ok:
        logger.info("Redis connected", detail=redis_detail)
    else:
        logger.warning("Redis not available", detail=redis_detail)

    logger.info("Initializing Qdrant collection...")
    try:
        await ensure_collection_exists()
        logger.info("Qdrant collection ready")
    except Exception as e:
        logger.warning("Qdrant initialization failed", error=str(e))

    logger.info("=" * 50)
    logger.info("Application ready to serve requests")
    logger.info("=" * 50)

    yield

    logger.info("Application shutting down...")
    await close_database()
    await close_redis()
    await close_qdrant()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Enterprise AI assistant for company document Q&A",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-Correlation-ID",
            "X-Process-Time-Ms",
        ],
    )

    app.add_middleware(TimingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    # ── Routers ───────────────────────────────────────────────
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")

    return app


app = create_app()
```

---

## STEP 8 — Run and Verify Everything

### 8.1 Start the server

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 8.2 Test non-streaming chat

Open a second Git Bash terminal. Ask a question about the PDF you uploaded earlier:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What is this document about?", "stream": false}'
```

You should get a JSON response with an `answer` and `citations` pointing to your uploaded document.

### 8.3 Test streaming chat (SSE)

Now let's test the streaming endpoint. As tokens are generated, they will print to your terminal one by one:

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Summarize the key points in 3 bullets", "stream": true}'
```

You will see output like this (arriving progressively):
```
data: -
data:  Point 1
data: ...
data: [DONE]
```

### 8.4 Test Conversation Memory

Because we implemented Redis memory, the LLM should remember the context of the conversation. Let's ask a follow-up question using the *same* `session_id`:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Can you expand on the second point?", "session_id": "my-test-session", "stream": false}'
```

The LLM should understand that "the second point" refers to the summary it just generated, proving that memory is working!

---

**Tell me:**

1. Did the non-streaming chat return an answer and citations successfully?
2. Did the streaming chat print tokens progressively?
3. Did the memory test work (did it understand "the second point")?
4. Any errors in the server logs?

Once confirmed, we have a fully working, end-to-end RAG application. The final step will be **Phase 7: Observability, Production Hardening & AWS Deployment**.