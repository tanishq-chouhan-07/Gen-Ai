# Phase 5: LLM Provider Abstraction & Prompt System

Amazing work getting through Phase 4. The hardest part (Docker, PostgreSQL, async drivers) is behind you. 

Now we build the "brain" of our application. 

In this phase, we will create the `LLMProvider` abstraction layer. This is the most important architectural pattern in the whole project. It means we write our business logic **once**, and we can switch between Gemini (development) and Amazon Bedrock (production) just by changing a single environment variable. 

We will also build a **Prompt Registry**. Prompts are essentially code—they need version control, testing, and easy updates. We will load them from YAML files at startup instead of hardcoding them in Python strings.

---

## Phase 5 Game Plan

```
Step 1 → Install pyyaml for prompt templates
Step 2 → Create LLM directory structure
Step 3 → LLM Provider Abstraction (base.py) - The interface
Step 4 → Gemini Provider Implementation - The concrete class
Step 5 → LLM Factory - How we switch providers dynamically
Step 6 → Prompt Management System (YAML templates + Registry + Builder)
Step 7 → Wire Prompt Registry into FastAPI Startup
Step 8 → Run and Verify Everything
```

---

## STEP 1 — Install pyyaml

We need YAML parsing to read our prompt template files. Open Git Bash and run:

```bash
python -m pip install pyyaml==6.0.2
```

Add it to your `requirements.txt`:

```txt
# ... existing requirements ...
# YAML for prompt templates
pyyaml==6.0.2
```

---

## STEP 2 — Create Directory Structure

We need separate folders for LLM logic, LLM providers, and Prompt management. Run this in Git Bash:

```bash
mkdir -p app/llm/providers
mkdir -p app/prompts/templates/system
mkdir -p app/prompts/templates/rag

type nul > app\llm\__init__.py
type nul > app\llm\providers\__init__.py
type nul > app\prompts\__init__.py
```

---

## STEP 3 — LLM Provider Abstraction (The Interface)

**Why we do this:** Every LLM API (Gemini, Bedrock, OpenAI) has a different SDK and requires data in different formats. If we write `import google.generativeai` inside our chat service, we can never switch to Bedrock without rewriting the service. 

Instead, we define an abstract `LLMProvider` class. Our services will only talk to this interface. The concrete implementations (GeminiProvider, BedrockProvider) handle the API-specific translations.

Create `app/llm/base.py`:

```python
# app/llm/base.py
"""
LLM Provider Abstraction

Defines the interface that ALL LLM providers must implement.
Whether we use Gemini or Bedrock, the application calls these same methods.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator
from pydantic import BaseModel


class LLMMessage(BaseModel):
    """Standard message format for all LLMs."""
    role: str  # "system", "user", "assistant"
    content: str


class LLMRequest(BaseModel):
    """Standard request format for LLM generation."""
    messages: list[LLMMessage]
    max_tokens: int = 2048
    temperature: float = 0.1
    stream: bool = False
    request_id: str | None = None


class LLMResponse(BaseModel):
    """Standard response format from LLM generation."""
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


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
```

---

## STEP 4 — Gemini Provider Implementation

**Why we do this:** This class takes our standard `LLMRequest` and translates it into the specific format Google's Gemini SDK expects. Gemini handles "system" prompts differently than OpenAI/Bedrock, so we extract it and pass it to the model configuration. 

Because the Gemini SDK is synchronous, we wrap the calls in `asyncio.to_thread` so we don't block FastAPI's async event loop.

Create `app/llm/providers/gemini_provider.py`:

```python
# app/llm/providers/gemini_provider.py
"""
Gemini LLM Provider Implementation

Uses Google's gemini-3.5-flash model.
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
        
        # Gemini handles system prompts via model config, not message history
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
```

---

## STEP 5 — LLM Factory

**Why we do this:** We don't want to scatter `if settings.llm_provider == 'gemini'` checks throughout our code. The Factory pattern reads the environment variable once and hands back the correct provider instance. When we implement Bedrock in Phase 7, we just add one `elif` block here.

Create `app/llm/factory.py`:

```python
# app/llm/factory.py
"""
LLM Provider Factory

Reads LLM_PROVIDER from settings and returns the correct provider.
To switch from Gemini to Bedrock: change LLM_PROVIDER=bedrock in .env
"""
from app.llm.base import LLMProvider
from app.config.settings import get_settings
import structlog

logger = structlog.get_logger()


def create_llm_provider() -> LLMProvider:
    """Factory function that creates the configured LLM provider."""
    settings = get_settings()
    provider_name = settings.llm_provider

    logger.info("Creating LLM provider", provider=provider_name)

    if provider_name == "gemini":
        from app.llm.providers.gemini_provider import GeminiProvider
        return GeminiProvider()

    elif provider_name == "bedrock":
        raise NotImplementedError(
            "Bedrock LLM provider will be added in Phase 7. "
            "Use LLM_PROVIDER=gemini for now."
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Supported: ['gemini', 'bedrock']"
        )
```

---

## STEP 6 — Prompt Management System

**Why we do this:** Hardcoding prompts in Python files is a bad practice. It requires a code redeploy just to fix a typo. By moving prompts to YAML files, we can version them (v1, v2), track changes in Git, and A/B test different prompts easily.

### 6.1 Create the System Prompt Template

Create `app/prompts/templates/system/document_agent_v1.yaml`:

```yaml
# app/prompts/templates/system/document_agent_v1.yaml
name: document_agent_system
version: "1.0"
description: "System prompt for the document AI agent"
author: "AI Team"
created_at: "2024-01-15"

template: |
  You are an expert enterprise AI assistant for {company_name}.
  Your job is to help employees find information from company documents accurately and efficiently.

  ## Response Guidelines
  1. **Always ground responses in documents**: Only state facts found in the retrieved context.
  2. **Always cite sources**: Use [1], [2], [3] notation referring to retrieved chunks.
  3. **Be concise and precise**: Answer the question directly, then provide supporting detail.
  4. **Acknowledge limitations**: If the answer is not in the documents, say so clearly.
  5. **Never hallucinate**: If you don't find relevant information, say "I could not find information about this in the company documents".

  ## Current Date
  {current_date}

variables:
  - company_name
  - current_date

changelog:
  "1.0": "Initial version"
```

### 6.2 Create the RAG Context Template

Create `app/prompts/templates/rag/rag_context_v1.yaml`:

```yaml
# app/prompts/templates/rag/rag_context_v1.yaml
name: rag_context
version: "1.0"
description: "Template for injecting retrieved context into the LLM prompt"
author: "AI Team"

template: |
  Please answer the following question based on the provided context.
  If the context does not contain enough information to answer the question, 
  state that you could not find the information.

  ## Context
  {context}

  ## Question
  {query}

variables:
  - context
  - query
```

### 6.3 Create the Prompt Registry

**Why we do this:** The registry scans the templates folder at startup, loads all YAML files into memory, and provides a `.get()` method so the app can fetch the latest version of a prompt instantly without reading files during a user request.

Create `app/prompts/registry.py`:

```python
# app/prompts/registry.py
"""
Prompt Registry

Central registry for all versioned prompt templates.
Loads from YAML files at application startup. Prompts are code - version them!
"""
import yaml
from pathlib import Path
from typing import Dict
import structlog

logger = structlog.get_logger()


class PromptRegistry:
    """Central registry for all versioned prompt templates."""
    
    _templates: Dict[str, Dict] = {}
    _templates_dir = Path(__file__).parent / "templates"
    
    @classmethod
    def load_all(cls) -> None:
        """Load all prompt templates from disk at startup."""
        count = 0
        for yaml_file in cls._templates_dir.rglob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            key = f"{data['name']}:{data['version']}"
            cls._templates[key] = data
            count += 1
            
        logger.info("Prompt registry loaded", template_count=count)
    
    @classmethod
    def get(cls, name: str, version: str = "latest") -> Dict:
        """Retrieve a prompt template by name and version."""
        if version == "latest":
            matching = [
                (k, v) for k, v in cls._templates.items() 
                if v["name"] == name
            ]
            if not matching:
                raise KeyError(f"No prompt template found with name: {name}")
            # Return the highest version available
            latest = sorted(matching, key=lambda x: x[1]["version"])[-1]
            return latest[1]
        
        key = f"{name}:{version}"
        if key not in cls._templates:
            raise KeyError(f"Prompt template not found: {name} v{version}")
        return cls._templates[key]
```

### 6.4 Create the Prompt Builder

**Why we do this:** We need a tool to take a template, inject the variables into it, assemble the list of `LLMMessage` objects, and return it ready for the LLM. This keeps our service layer clean.

Create `app/prompts/builder.py`:

```python
# app/prompts/builder.py
"""
Prompt Builder

Assembles complete prompts from registry templates.
Handles variable injection and message formatting.
"""
from datetime import datetime
from app.llm.base import LLMMessage
from app.prompts.registry import PromptRegistry


class PromptBuilder:
    """Assembles complete prompts from registry templates."""
    
    def build_rag_prompt(
        self,
        query: str,
        context_chunks: list[dict],
        conversation_history: list[LLMMessage] = [],
        company_name: str = "Our Company",
    ) -> list[LLMMessage]:
        """Build a complete RAG prompt with context and history."""
        
        # Get templates from registry
        system_template = PromptRegistry.get("document_agent_system")
        rag_template = PromptRegistry.get("rag_context")
        
        # Format system prompt with variables
        system_content = system_template["template"].format(
            company_name=company_name,
            current_date=datetime.now().strftime("%B %d, %Y"),
        )
        
        # Format context chunks for the LLM
        formatted_context = self._format_context(context_chunks)
        
        # Format user prompt with context and query
        user_content = rag_template["template"].format(
            context=formatted_context,
            query=query,
        )
        
        # Assemble standard LLM messages
        messages = [
            LLMMessage(role="system", content=system_content),
        ]
        
        # Add limited conversation history so we don't blow up token limits
        if conversation_history:
            messages.extend(conversation_history[-4:])
        
        messages.append(LLMMessage(role="user", content=user_content))
        
        return messages
    
    def _format_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks into numbered citation blocks."""
        if not chunks:
            return "No relevant documents found."
        
        formatted = []
        for i, chunk in enumerate(chunks, 1):
            formatted.append(
                f"[{i}] Source: {chunk.get('filename', 'Unknown')} "
                f"(Page {chunk.get('page_number', '?')})\n"
                f"{chunk.get('content', '')}"
            )
        
        return "\n\n---\n\n".join(formatted)
```

---

## STEP 7 — Wire Prompt Registry into FastAPI Startup

**Why we do this:** We must load the YAML files into memory *before* any user tries to chat. We add it to the FastAPI `lifespan` so it runs exactly once when the server boots.

Open `app/main.py` and make two changes:

1. Add the import at the top:
```python
from app.prompts.registry import PromptRegistry
```

2. Inside the `lifespan` async function, add the loading call right after the database initialization:

```python
    # ... database init code ...

    # ── Load Prompt Templates ────────────────────────────────
    logger.info("Loading prompt templates...")
    PromptRegistry.load_all()

    # ... redis/qdrant init code ...
```

Your final `lifespan` function should look like this:

```python
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

    # ── Load Prompt Templates ────────────────────────────────
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
```

---

## STEP 8 — Run and Verify Everything

### 8.1 Start the server

Make sure your docker containers are running, then start the server:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Look at the startup logs. You should see:
```
Loading prompt templates...
Prompt registry loaded template_count=2
Database tables ready
Redis connected
Qdrant collection ready
Application ready to serve requests
```

### 8.2 Test LLM Provider & Prompt Builder End-to-End

Open a second Git Bash terminal and run this script. It simulates the full RAG flow: creating the provider, loading prompts, injecting context, and calling Gemini.

```bash
source /c/Users/HP/Desktop/Gen-Ai/venv/Scripts/activate

python -c "
import asyncio
from app.llm.factory import create_llm_provider
from app.llm.base import LLMRequest
from app.prompts.builder import PromptBuilder
from app.prompts.registry import PromptRegistry

# Load prompts manually for this script test
PromptRegistry.load_all()

async def test_llm():
    # 1. Create provider using our factory
    llm = create_llm_provider()
    print(f'Created LLM Provider: {llm.get_model_id()}')
    
    # 2. Build prompt using our YAML templates
    builder = PromptBuilder()
    fake_chunks = [
        {'filename': 'policy.pdf', 'page_number': 5, 'content': 'Employees get 20 days of paid leave annually.'}
    ]
    messages = builder.build_rag_prompt(
        query='How many days of leave do I get?',
        context_chunks=fake_chunks
    )
    print(f'Built {len(messages)} messages')
    print(f'System prompt length: {len(messages[0].content)} chars')
    
    # 3. Generate response from Gemini
    request = LLMRequest(messages=messages, max_tokens=100)
    response = await llm.generate(request)
    
    print('\n--- LLM RESPONSE ---')
    print(response.content)
    print('--------------------')
    print(f'Tokens used: {response.input_tokens} in, {response.output_tokens} out')

asyncio.run(test_llm())
"
```

Expected Output:
```
Created LLM Provider: gemini-3.5-flash
Built 2 messages
System prompt length: 4XX chars

--- LLM RESPONSE ---
Employees get 20 days of paid leave annually [1].
--------------------
Tokens used: XXX in, XX out
```

### 8.3 Test LLM Streaming

Run this to verify the streaming generator works (we will use this heavily in Phase 6 for Server-Sent Events):

```bash
python -c "
import asyncio
from app.llm.factory import create_llm_provider
from app.llm.base import LLMRequest, LLMMessage

async def test_stream():
    llm = create_llm_provider()
    request = LLMRequest(
        messages=[LLMMessage(role='user', content='Count from 1 to 5.')],
        max_tokens=50,
        stream=True
    )
    
    print('Streaming response:')
    async for token in llm.generate_stream(request):
        print(token, end='', flush=True)
    print('\nDone.')

asyncio.run(test_stream())
"
```

Expected Output:
```
Streaming response:
1
2
3
4
5

Done.
```

---

**Tell me:**

1. Did the server startup show `Prompt registry loaded template_count=2`?
2. Did the LLM Response test successfully answer the question and cite `[1]`?
3. Did the Streaming test output numbers one by one?
4. Any errors anywhere?

Once confirmed, we move to **Phase 6: Chat / RAG Pipeline & AI Agent**, where we connect this LLM to the Qdrant database and build the actual chat endpoints with Server-Sent Events!