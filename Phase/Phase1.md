# Phase 1: Foundation & Infrastructure

Perfect. Let's start from absolute zero. By the end of Phase 1 you will have a running FastAPI application with proper configuration, logging, and health checks — all verified working on your machine.

---

## Phase 1 Game Plan

We will do this in **6 steps**:

```
Step 1 → Create project folder + virtual environment
Step 2 → Install dependencies
Step 3 → Create project skeleton (folders only)
Step 4 → Configuration (Settings + Model Table)
Step 5 → FastAPI app + Health endpoint
Step 6 → Run it and verify everything works
```

After Step 6 you will see this in your browser and we move to Phase 2.

---

## STEP 1 — Project Folder + Virtual Environment

### 1.1 Open VS Code Terminal

Open VS Code. Then open the terminal:
- Press `` Ctrl + ` `` (backtick)
- Or go to **Terminal → New Terminal**

Make sure you see a PowerShell or Command Prompt at the bottom.

### 1.2 Create the project folder

Run these commands one by one. After each command press Enter and wait for it to finish before running the next.

```bash
cd C:\
```

```bash
mkdir document-ai-agent
```

```bash
cd document-ai-agent
```

```bash
code .
```

This last command opens the project folder in VS Code. A new VS Code window will open. **Switch to that new window** and open the terminal again with `` Ctrl + ` ``.

### 1.3 Create and activate virtual environment

In the new VS Code terminal (inside the `document-ai-agent` folder):

```bash
python -m venv venv
```

Wait for it to finish (about 10 seconds), then:

```bash
venv\Scripts\activate
```

You should now see `(venv)` at the start of your terminal line like this:

```
(venv) PS C:\document-ai-agent>
```

> **If you see an error about execution policy**, run this first:
> ```bash
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then try `venv\Scripts\activate` again.

---

**✋ Stop here. Tell me:**
1. Do you see `(venv)` in your terminal?
2. What does your terminal prompt look like right now?

---

## STEP 2 — Install Dependencies

Still inside the terminal with `(venv)` active.

### 2.1 Create the requirements file

In VS Code, create a new file called `requirements.txt` in the root of your project.

**Click the new file icon** in the VS Code sidebar, name it `requirements.txt`, and paste this content:

```txt
# Web Framework
fastapi==0.115.5
uvicorn[standard]==0.32.1

# Configuration
pydantic==2.10.3
pydantic-settings==2.6.1

# LLM Providers
google-generativeai==0.8.3

# Logging
structlog==24.4.0

# HTTP Client
httpx==0.28.1

# Utilities
python-multipart==0.0.12
python-dotenv==1.0.1
```

Save the file with `Ctrl + S`.

### 2.2 Install everything

In the terminal:

```bash
pip install -r requirements.txt
```

This will take 1-2 minutes. You will see a lot of output. Wait for it to finish. The last line should say something like `Successfully installed ...`

### 2.3 Verify installation

```bash
python -c "import fastapi; import pydantic; print('FastAPI:', fastapi.__version__); print('Pydantic:', pydantic.__version__)"
```

You should see:
```
FastAPI: 0.115.5
Pydantic: 2.10.3
```

---

**✋ Stop here. Tell me:**
1. Did the install finish without errors?
2. What did the verify command print?

---

## STEP 3 — Create Project Skeleton

Now we create all the folders. We are creating empty folders first. Code comes after.

### 3.1 Create folder structure

In the terminal, run this block all at once (copy the whole thing and paste it):

```bash
mkdir app
mkdir app\api
mkdir app\api\v1
mkdir app\api\v1\routers
mkdir app\api\schemas
mkdir app\config
mkdir app\middleware
mkdir app\observability
mkdir app\utils
mkdir tests
```

### 3.2 Create all `__init__.py` files

These files make Python treat each folder as a package. Run this block:

```bash
type nul > app\__init__.py
type nul > app\api\__init__.py
type nul > app\api\v1\__init__.py
type nul > app\api\v1\routers\__init__.py
type nul > app\api\schemas\__init__.py
type nul > app\config\__init__.py
type nul > app\middleware\__init__.py
type nul > app\observability\__init__.py
type nul > app\utils\__init__.py
type nul > tests\__init__.py
```

### 3.3 Verify the structure

```bash
tree /F app
```

You should see this:

```
C:\DOCUMENT-AI-AGENT\APP
│   __init__.py
│
├───api
│   │   __init__.py
│   │
│   ├───schemas
│   │       __init__.py
│   │
│   └───v1
│       │   __init__.py
│       │
│       └───routers
│               __init__.py
│
├───config
│       __init__.py
│
├───middleware
│       __init__.py
│
├───observability
│       __init__.py
│
└───utils
        __init__.py
```

---

**✋ Stop here. Tell me:**
- Does your tree output match the structure above?

---

## STEP 4 — Configuration Files

Now we write real code. We start with configuration because everything else depends on it.

### 4.1 Create the `.env` file

In VS Code, create a new file in the root folder called `.env`

```
(venv) PS C:\document-ai-agent>  ← you are here
```

The `.env` file goes at this level (same level as `requirements.txt`).

Paste this content:

```env
# Application
APP_NAME="Document AI Agent"
APP_VERSION="1.0.0"
ENVIRONMENT="development"
DEBUG=true

# LLM Provider - change this one line to switch providers
LLM_PROVIDER="gemini"
EMBEDDING_PROVIDER="gemini"

# Gemini (Development)
GEMINI_API_KEY="your-gemini-api-key-here"
GEMINI_MODEL="gemini-3.5-flash"
GEMINI_EMBEDDING_MODEL="models/text-embedding-004"

# Qdrant
QDRANT_HOST="localhost"
QDRANT_PORT=6333
QDRANT_COLLECTION="company_documents"

# Redis
REDIS_URL="redis://localhost:6379"

# Logging
LOG_LEVEL="DEBUG"
```

**Replace `your-gemini-api-key-here` with your actual Gemini API key.**

### 4.2 Create `.gitignore`

Create a new file called `.gitignore` in the root folder:

```gitignore
# Virtual environment
venv/
.venv/

# Environment variables (NEVER commit this)
.env

# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd
.Python

# VS Code
.vscode/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Build
dist/
build/
*.egg-info/
```

### 4.3 Create `app/config/settings.py`

Create a new file at `app/config/settings.py`:

```python
# app/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    """
    Central configuration for the entire application.
    All values come from environment variables or the .env file.
    Nothing is hardcoded.
    """

    # ── Application ───────────────────────────────────────────
    app_name: str = "Document AI Agent"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # ── LLM Provider Selection ────────────────────────────────
    # THIS is the key abstraction point.
    # Change LLM_PROVIDER=bedrock in .env and the whole app switches.
    # Zero code changes needed.
    llm_provider: Literal["gemini", "bedrock"] = "gemini"
    embedding_provider: Literal["gemini", "bedrock", "local"] = "gemini"

    # ── Gemini (Development) ──────────────────────────────────
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "models/text-embedding-004"

    # ── Amazon Bedrock (Production) ───────────────────────────
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    # ── Qdrant ────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "company_documents"
    qdrant_vector_size: int = 768

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 3600

    # ── Document Processing ───────────────────────────────────
    max_file_size_mb: int = 50
    chunk_size: int = 512
    chunk_overlap: int = 128
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.7

    # ── Agent ─────────────────────────────────────────────────
    agent_max_iterations: int = 5
    agent_timeout_seconds: int = 30

    # ── Logging ───────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Feature Flags ─────────────────────────────────────────
    enable_streaming: bool = True
    enable_citations: bool = True
    enable_conversation_memory: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow both UPPER_CASE and lower_case env vars
        case_sensitive = False
        # Allow extra fields (useful when adding new settings)
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Use this everywhere instead of creating Settings() directly.
    lru_cache means Settings() is only created once for the whole app.
    """
    return Settings()
```

### 4.4 Create `app/config/model_table.py`

Create `app/config/model_table.py`:

```python
# app/config/model_table.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """
    Immutable configuration for a single model.
    frozen=True means no one can accidentally change these values.
    """
    model_id: str
    provider: str
    context_window: int
    max_output_tokens: int
    supports_streaming: bool
    supports_tool_calling: bool
    cost_per_1k_input_tokens: float
    cost_per_1k_output_tokens: float
    embedding_dimensions: int | None = None


# ─────────────────────────────────────────────────────────────
# THE MODEL REGISTRY
# Single source of truth for every model in the system.
# Add a new model here and it's available everywhere.
# ─────────────────────────────────────────────────────────────
MODEL_TABLE: dict[str, ModelConfig] = {

    # ── Gemini Models (Development) ───────────────────────────
    "gemini-3.5-flash": ModelConfig(
        model_id="gemini-3.5-flash",
        provider="gemini",
        context_window=1_000_000,
        max_output_tokens=8192,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.000075,
        cost_per_1k_output_tokens=0.0003,
    ),
    "gemini-1.5-pro": ModelConfig(
        model_id="gemini-1.5-pro",
        provider="gemini",
        context_window=2_000_000,
        max_output_tokens=8192,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.00125,
        cost_per_1k_output_tokens=0.005,
    ),
    "models/text-embedding-004": ModelConfig(
        model_id="models/text-embedding-004",
        provider="gemini",
        context_window=2048,
        max_output_tokens=0,
        supports_streaming=False,
        supports_tool_calling=False,
        cost_per_1k_input_tokens=0.00001,
        cost_per_1k_output_tokens=0.0,
        embedding_dimensions=768,
    ),

    # ── Amazon Bedrock Models (Production) ────────────────────
    "anthropic.claude-3-sonnet-20240229-v1:0": ModelConfig(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        provider="bedrock",
        context_window=200_000,
        max_output_tokens=4096,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.003,
        cost_per_1k_output_tokens=0.015,
    ),
    "anthropic.claude-3-haiku-20240307-v1:0": ModelConfig(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        provider="bedrock",
        context_window=200_000,
        max_output_tokens=4096,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.00025,
        cost_per_1k_output_tokens=0.00125,
    ),
    "amazon.titan-embed-text-v2:0": ModelConfig(
        model_id="amazon.titan-embed-text-v2:0",
        provider="bedrock",
        context_window=8192,
        max_output_tokens=0,
        supports_streaming=False,
        supports_tool_calling=False,
        cost_per_1k_input_tokens=0.00002,
        cost_per_1k_output_tokens=0.0,
        embedding_dimensions=1024,
    ),
}


def get_model_config(model_id: str) -> ModelConfig:
    """
    Look up a model by ID.
    Raises a clear error if the model doesn't exist.
    """
    if model_id not in MODEL_TABLE:
        available = list(MODEL_TABLE.keys())
        raise ValueError(
            f"Unknown model: '{model_id}'.\n"
            f"Available models: {available}"
        )
    return MODEL_TABLE[model_id]
```

### 4.5 Quick test — verify settings work

In the terminal:

```bash
python -c "from app.config.settings import get_settings; s = get_settings(); print('App:', s.app_name); print('Provider:', s.llm_provider); print('Model:', s.gemini_model)"
```

Expected output:
```
App: Document AI Agent
Provider: gemini
Model: gemini-3.5-flash
```

---

**✋ Stop here. Tell me:**
1. Did the settings test print the expected output?
2. Any errors?

---

## STEP 5 — Logging + FastAPI App + Health Endpoint

### 5.1 Create `app/observability/logging.py`

```python
# app/observability/logging.py
import logging
import structlog
from app.config.settings import get_settings


def setup_logging() -> None:
    """
    Configure structured JSON logging for the entire application.
    
    In development: pretty colored output for readability.
    In production: JSON format for log aggregation tools.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
    )

    # Choose renderer based on environment
    if settings.environment == "development":
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            # Add log level to every log entry
            structlog.stdlib.add_log_level,
            # Add timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Add caller info in development
            structlog.processors.CallsiteParameterAdder(
                [structlog.processors.CallsiteParameter.FILENAME,
                 structlog.processors.CallsiteParameter.LINENO]
            ) if settings.debug else structlog.processors.StackInfoRenderer(),
            # Final renderer
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

### 5.2 Create `app/api/schemas/health.py`

```python
# app/api/schemas/health.py
from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class HealthResponse(BaseModel):
    """Response model for the basic health check endpoint."""
    status: Literal["healthy", "unhealthy"]
    app_name: str
    version: str
    environment: str
    timestamp: datetime


class ComponentStatus(BaseModel):
    """Status of a single system component."""
    name: str
    status: Literal["healthy", "degraded", "unhealthy"]
    details: str = ""


class ReadinessResponse(BaseModel):
    """Response model for the readiness check endpoint."""
    status: Literal["ready", "not_ready"]
    components: list[ComponentStatus]
    timestamp: datetime
```

### 5.3 Create `app/api/v1/routers/health.py`

```python
# app/api/v1/routers/health.py
from fastapi import APIRouter
from datetime import datetime, timezone
import structlog

from app.api.schemas.health import HealthResponse, ReadinessResponse, ComponentStatus
from app.config.settings import get_settings

router = APIRouter(prefix="/health", tags=["Health"])
logger = structlog.get_logger()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness Check",
    description="Basic check that the application is running. Used by load balancers.",
)
async def health_check() -> HealthResponse:
    """
    Liveness endpoint.
    If this returns 200, the application process is alive.
    Does NOT check dependencies (database, Qdrant, etc.)
    """
    settings = get_settings()
    logger.debug("Health check requested")

    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description="Checks if the application is ready to serve traffic.",
)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness endpoint.
    Checks that all critical dependencies are reachable.
    Returns 200 only when the app can actually serve requests.
    
    In Phase 1 we only check the app itself.
    In later phases we will add Qdrant, Redis, and DB checks.
    """
    settings = get_settings()
    components = []
    all_ready = True

    # App configuration check
    config_ok = bool(settings.app_name and settings.llm_provider)
    components.append(ComponentStatus(
        name="configuration",
        status="healthy" if config_ok else "unhealthy",
        details=f"Provider: {settings.llm_provider}, Model: {settings.gemini_model}",
    ))

    if not config_ok:
        all_ready = False

    logger.info(
        "Readiness check completed",
        status="ready" if all_ready else "not_ready",
        component_count=len(components),
    )

    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        components=components,
        timestamp=datetime.now(timezone.utc),
    )
```

### 5.4 Create the main FastAPI app `app/main.py`

Create `app/main.py` (directly inside the `app` folder):

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

from app.config.settings import get_settings
from app.observability.logging import setup_logging
from app.api.v1.routers import health

# ── Setup logging before anything else ───────────────────────
setup_logging()
logger = structlog.get_logger()
settings = get_settings()


# ── Application Lifespan ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.
    This replaces the old @app.on_event("startup") pattern.
    """
    # ── STARTUP ──────────────────────────────────────────────
    logger.info(
        "Starting application",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        model=settings.gemini_model,
    )

    yield  # Application runs here

    # ── SHUTDOWN ─────────────────────────────────────────────
    logger.info("Shutting down application")


# ── Create FastAPI App ────────────────────────────────────────
def create_app() -> FastAPI:
    """
    Application factory pattern.
    Creates and configures the FastAPI application.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Enterprise AI assistant for company document Q&A",
        docs_url="/docs",      # Swagger UI
        redoc_url="/redoc",    # ReDoc UI
        lifespan=lifespan,
    )

    # ── Register Routers ─────────────────────────────────────
    app.include_router(health.router, prefix="/api/v1")

    # ── Global Exception Handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            error=str(exc),
            path=str(request.url),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "An internal error occurred",
                    "type": type(exc).__name__,
                }
            },
        )

    logger.info("Application created successfully")
    return app


# ── App Instance ─────────────────────────────────────────────
app = create_app()
```

---

**✋ Stop here. Tell me if you have any errors creating these files before we run.**

---

## STEP 6 — Run and Verify

### 6.1 Run the application

In the terminal (make sure `(venv)` is still active):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see output like this:

```
INFO     Starting application app_name='Document AI Agent' ...
INFO     Application created successfully
INFO     Started server process
INFO     Waiting for application startup.
INFO     Application startup complete.
INFO     Uvicorn running on http://0.0.0.0:8000
```

### 6.2 Test the endpoints

Open a **new terminal** (keep uvicorn running in the first one). In the new terminal, activate venv again:

```bash
venv\Scripts\activate
```

Then test each endpoint:

**Test 1 — Health check:**
```bash
curl http://localhost:8000/api/v1/health
```

Expected:
```json
{
  "status": "healthy",
  "app_name": "Document AI Agent",
  "version": "1.0.0",
  "environment": "development",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Test 2 — Readiness check:**
```bash
curl http://localhost:8000/api/v1/health/ready
```

Expected:
```json
{
  "status": "ready",
  "components": [
    {
      "name": "configuration",
      "status": "healthy",
      "details": "Provider: gemini, Model: gemini-3.5-flash"
    }
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Test 3 — Open Swagger UI in your browser:**

Go to: `http://localhost:8000/docs`

You should see a nice Swagger UI with your endpoints listed.

### 6.3 Your final folder structure

Run this to verify:
```bash
tree /F
```

It should look like this:
```
C:\DOCUMENT-AI-AGENT
│   .env
│   .gitignore
│   requirements.txt
│
├───app
│   │   __init__.py
│   │   main.py
│   │
│   ├───api
│   │   │   __init__.py
│   │   │
│   │   ├───schemas
│   │   │       __init__.py
│   │   │       health.py
│   │   │
│   │   └───v1
│   │       │   __init__.py
│   │       │
│   │       └───routers
│   │               __init__.py
│   │               health.py
│   │
│   ├───config
│   │       __init__.py
│   │       model_table.py
│   │       settings.py
│   │
│   ├───middleware
│   │       __init__.py
│   │
│   ├───observability
│   │       __init__.py
│   │       logging.py
│   │
│   └───utils
│           __init__.py
│
└───tests
        __init__.py
```

---

## Phase 1 Complete ✅

**Tell me:**

1. Did `uvicorn` start without errors?
2. Did both `curl` commands return the expected JSON?
3. Did the Swagger UI open at `http://localhost:8000/docs`?
4. Any errors anywhere?

Once you confirm everything is working, we move to **Phase 2: Middleware + Request IDs + Error Handling** — we will add the production-grade middleware layer before touching any business logic.