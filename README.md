# Enterprise Company Document Management AI Agent
## Production-Ready 2-Day Roadmap

---

# TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Architecture Diagrams](#2-architecture-diagrams)
3. [Project Structure](#3-project-structure)
4. [Tech Stack Decisions](#4-tech-stack-decisions)
5. [Phase Roadmap](#5-phase-roadmap)
6. [API Specification](#6-api-specification)
7. [Core Engineering Patterns](#7-core-engineering-patterns)
8. [Deployment Strategy](#8-deployment-strategy)
9. [Production Readiness Checklist](#9-production-readiness-checklist)

---

# 1. SYSTEM OVERVIEW

## What We Are Building

An enterprise-grade AI Assistant that allows employees to upload company PDF documents (policies, procedures, contracts, technical documentation) and ask natural language questions. The system responds with accurate, grounded answers that include citations to the source documents, streaming output, and full observability.

## Core Design Philosophy

```
┌─────────────────────────────────────────────────────┐
│              DESIGN PRINCIPLES                       │
├─────────────────────────────────────────────────────┤
│  1. Provider Agnostic   → Gemini today, Bedrock tomorrow  │
│  2. Pipeline Separation → Ingestion ≠ Chat               │
│  3. Configuration First → No hardcoded values            │
│  4. Observable by Design→ Every operation is traced      │
│  5. Fail Gracefully     → Retry, fallback, classify      │
│  6. Clean Architecture  → Each layer has one job         │
└─────────────────────────────────────────────────────┘
```

## Two Independent Pipelines

| Pipeline | Trigger | Responsibility | Independence |
|---|---|---|---|
| **Document Ingestion** | File Upload / API | Parse → Chunk → Embed → Store | Runs without chat |
| **Chat / Retrieval** | User Query | Retrieve → Build → Generate → Stream | Runs without ingestion |

---

# 2. ARCHITECTURE DIAGRAMS

## 2.1 Overall System Architecture

```mermaid
graph TB
    subgraph CLIENT["🖥️ Client Layer"]
        UI[Web Browser / API Client]
        SDK[Internal SDK]
    end

    subgraph GATEWAY["🔀 API Gateway Layer"]
        NGINX[NGINX / Load Balancer]
        AUTH[Auth Middleware]
        RATELIMIT[Rate Limiter]
        REQID[Request ID Injector]
    end

    subgraph FASTAPI["⚡ FastAPI Application"]
        subgraph ROUTERS["API Routers"]
            DOC_API[Document Router<br/>/api/v1/documents]
            CHAT_API[Chat Router<br/>/api/v1/chat]
            HEALTH_API[Health Router<br/>/api/v1/health]
            METRICS_API[Metrics Router<br/>/api/v1/metrics]
        end

        subgraph MIDDLEWARE_LAYER["Middleware Stack"]
            CORS[CORS Middleware]
            LOGGING[Structured Logging]
            TRACING[OpenTelemetry Tracing]
            TIMING[Request Timing]
        end
    end

    subgraph PIPELINES["🔧 Business Pipelines"]
        subgraph INGESTION["📥 Document Ingestion Pipeline"]
            VALIDATOR[Document Validator]
            PARSER[PDF Parser - PyMuPDF]
            CHUNKER[Smart Chunker]
            META[Metadata Extractor]
            EMBED_SVC[Embedding Service]
            INDEX_SVC[Indexing Service]
            BG_WORKER[Background Worker]
            PROGRESS[Progress Tracker]
        end

        subgraph CHAT["💬 Chat / Retrieval Pipeline"]
            QUERY_PROC[Query Processor]
            RETRIEVER[Semantic Retriever]
            CONTEXT_BUILDER[Context Builder]
            PROMPT_BUILDER[Prompt Builder]
            AGENT[AI Agent]
            STREAM_SVC[Streaming Service]
            CITATION_SVC[Citation Service]
            MEMORY_SVC[Memory Service]
        end
    end

    subgraph PROVIDERS["🤖 Provider Abstraction Layer"]
        LLM_INTERFACE[LLMProvider Interface]
        EMBED_INTERFACE[EmbeddingProvider Interface]
        
        subgraph LLM_PROVIDERS["LLM Providers"]
            GEMINI[Gemini Provider<br/>Development]
            BEDROCK[Bedrock Provider<br/>Production]
            OPENAI[OpenAI Provider<br/>Optional]
        end

        subgraph EMBED_PROVIDERS["Embedding Providers"]
            GEMINI_EMBED[Gemini Embeddings]
            BEDROCK_EMBED[Bedrock Embeddings<br/>Titan]
            LOCAL_EMBED[Local Embeddings<br/>sentence-transformers]
        end
    end

    subgraph AGENT_LAYER["🧠 Agent & Tools"]
        AGENT_CORE[ReAct Agent Core]
        TOOL_REGISTRY[Tool Registry]
        subgraph TOOLS["Available Tools"]
            SEARCH_TOOL[DocumentSearchTool]
            CALC_TOOL[CalculatorTool]
            META_TOOL[MetadataSearchTool]
            FUTURE_TOOL[... Future Tools]
        end
    end

    subgraph PROMPT_MGMT["📝 Prompt Management"]
        PROMPT_REGISTRY[Prompt Registry]
        PROMPT_BUILDER_SVC[Prompt Builder]
        TEMPLATE_ENGINE[Template Engine]
        VERSION_CTRL[Version Controller]
    end

    subgraph STORAGE["💾 Storage Layer"]
        QDRANT[(Qdrant<br/>Vector DB)]
        REDIS[(Redis<br/>Cache + Sessions)]
        S3[(S3 / MinIO<br/>Document Storage)]
        POSTGRES[(PostgreSQL<br/>Metadata DB)]
    end

    subgraph OBSERVABILITY["📊 Observability Stack"]
        OTEL[OpenTelemetry Collector]
        JAEGER[Jaeger Tracing]
        PROMETHEUS[Prometheus Metrics]
        GRAFANA[Grafana Dashboards]
        LOKI[Loki Log Aggregation]
    end

    UI --> NGINX
    SDK --> NGINX
    NGINX --> AUTH
    AUTH --> RATELIMIT
    RATELIMIT --> REQID
    REQID --> ROUTERS

    DOC_API --> INGESTION
    CHAT_API --> CHAT
    HEALTH_API --> STORAGE
    METRICS_API --> PROMETHEUS

    INGESTION --> LLM_INTERFACE
    INGESTION --> STORAGE
    CHAT --> LLM_INTERFACE
    CHAT --> STORAGE
    CHAT --> AGENT_CORE

    LLM_INTERFACE --> GEMINI
    LLM_INTERFACE --> BEDROCK
    LLM_INTERFACE --> OPENAI
    EMBED_INTERFACE --> GEMINI_EMBED
    EMBED_INTERFACE --> BEDROCK_EMBED
    EMBED_INTERFACE --> LOCAL_EMBED

    AGENT_CORE --> TOOL_REGISTRY
    TOOL_REGISTRY --> TOOLS

    AGENT_CORE --> PROMPT_MGMT
    CHAT --> PROMPT_MGMT

    FASTAPI --> OBSERVABILITY

    style INGESTION fill:#e8f5e9,stroke:#4caf50
    style CHAT fill:#e3f2fd,stroke:#2196f3
    style PROVIDERS fill:#fff3e0,stroke:#ff9800
    style AGENT_LAYER fill:#fce4ec,stroke:#e91e63
    style OBSERVABILITY fill:#f3e5f5,stroke:#9c27b0
```

## 2.2 Document Ingestion Pipeline

```mermaid
flowchart TD
    START([📄 PDF Upload Request]) --> VALIDATE

    subgraph VALIDATION["🔍 Validation Layer"]
        VALIDATE[File Type Validator<br/>PDF only]
        SIZE_CHECK[Size Validator<br/>Max 50MB]
        CORRUPT_CHECK[Corruption Check<br/>PyMuPDF probe]
        DUPLICATE_CHECK[Duplicate Detection<br/>SHA-256 hash]
        VALIDATE --> SIZE_CHECK --> CORRUPT_CHECK --> DUPLICATE_CHECK
    end

    DUPLICATE_CHECK -->|New Document| JOB_CREATE
    DUPLICATE_CHECK -->|Duplicate Found| VERSION_CHECK

    subgraph VERSIONING["📋 Document Versioning"]
        VERSION_CHECK{Same content?}
        SKIP[Skip - Return existing]
        NEW_VERSION[Create new version<br/>v1 → v2]
        VERSION_CHECK -->|Yes| SKIP
        VERSION_CHECK -->|No, Updated| NEW_VERSION
    end

    JOB_CREATE[Create Background Job<br/>job_id + correlation_id]
    NEW_VERSION --> JOB_CREATE
    JOB_CREATE --> STORE_RAW

    subgraph STORAGE_RAW["💾 Raw Storage"]
        STORE_RAW[Store PDF in S3/MinIO<br/>with metadata]
        STORE_META[Store metadata in PostgreSQL<br/>filename, size, hash, owner]
    end

    STORE_RAW --> STORE_META --> BG_QUEUE

    subgraph BACKGROUND["⚙️ Background Processing"]
        BG_QUEUE[Background Task Queue<br/>AsyncIO + FastAPI BackgroundTasks]
        
        subgraph PARSING["📖 PDF Parsing - PyMuPDF"]
            EXTRACT_TEXT[Extract Text<br/>page by page]
            EXTRACT_IMAGES[Extract Image Metadata]
            EXTRACT_TABLES[Detect Table Structure]
            EXTRACT_META[Extract Document Metadata<br/>author, created, title, pages]
        end

        subgraph CHUNKING["✂️ Smart Chunking"]
            SEMANTIC_CHUNK[Semantic Chunker<br/>sentence boundaries]
            OVERLAP[Sliding Window Overlap<br/>128 token overlap]
            ENRICH[Chunk Enrichment<br/>page_num, section, position]
            FINAL_CHUNKS[Final Chunk Objects<br/>with full context]
        end

        subgraph EMBEDDING["🔢 Embedding Generation"]
            EMBED_PROVIDER[EmbeddingProvider<br/>abstraction call]
            BATCH_EMBED[Batch Processing<br/>32 chunks per batch]
            RETRY_EMBED[Retry with backoff<br/>on API failures]
            VECTORS[Dense Vectors<br/>768 / 1536 dimensions]
        end

        subgraph INDEXING["📂 Vector Indexing"]
            QDRANT_UPSERT[Qdrant Upsert<br/>with payload metadata]
            INDEX_TRACK[Index Progress Tracking<br/>Redis counter]
            VERIFY[Verification Query<br/>spot-check retrieval]
        end

        BG_QUEUE --> EXTRACT_TEXT
        EXTRACT_TEXT --> EXTRACT_IMAGES --> EXTRACT_TABLES --> EXTRACT_META
        EXTRACT_META --> SEMANTIC_CHUNK
        SEMANTIC_CHUNK --> OVERLAP --> ENRICH --> FINAL_CHUNKS
        FINAL_CHUNKS --> EMBED_PROVIDER
        EMBED_PROVIDER --> BATCH_EMBED --> RETRY_EMBED --> VECTORS
        VECTORS --> QDRANT_UPSERT --> INDEX_TRACK --> VERIFY
    end

    VERIFY --> UPDATE_STATUS

    subgraph STATUS["📊 Status Management"]
        UPDATE_STATUS[Update Job Status<br/>COMPLETED / FAILED]
        NOTIFY[Emit Status Event<br/>SSE / Webhook]
        ERROR_HANDLE[Error Handler<br/>classify + log + retry]
    end

    UPDATE_STATUS --> NOTIFY
    UPDATE_STATUS -->|On Error| ERROR_HANDLE
    ERROR_HANDLE -->|Retryable| BG_QUEUE
    ERROR_HANDLE -->|Fatal| DEAD_LETTER[Dead Letter Queue<br/>Manual review needed]

    NOTIFY --> DONE([✅ Document Indexed])

    style VALIDATION fill:#fff9c4,stroke:#f9a825
    style VERSIONING fill:#f3e5f5,stroke:#9c27b0
    style BACKGROUND fill:#e8f5e9,stroke:#4caf50
    style STATUS fill:#e3f2fd,stroke:#2196f3
```
## 2.3 Chat / Retrieval Pipeline

```mermaid
flowchart TD
    USER([👤 User Query]) --> RECEIVE

    subgraph REQUEST_LAYER["📨 Request Processing"]
        RECEIVE["Receive Query\nsession_id + request_id"]
        SANITIZE["Input Sanitization\nlength, injection check"]
        LOAD_SESSION["Load Session Memory\nfrom Redis"]
        RECEIVE --> SANITIZE --> LOAD_SESSION
    end

    LOAD_SESSION --> AGENT_ENTRY

    subgraph AGENT_ORCHESTRATION["🧠 AI Agent Orchestration (ReAct)"]
        AGENT_ENTRY["Agent Entry Point"]

        subgraph REASONING["🤔 ReAct Reasoning Loop"]
            THINK["THINK\nAnalyze Query\nWhat does the user need?"]
            PLAN["PLAN\nSelect Strategy\nWhich tools to use?"]
            ACT["ACT\nExecute Tool"]
            OBSERVE["OBSERVE\nProcess Result\nIs the answer complete?"]

            THINK --> PLAN --> ACT --> OBSERVE
            OBSERVE -->|Need more info| THINK
            OBSERVE -->|Complete| SYNTHESIZE
        end

        SYNTHESIZE["Synthesize Final Answer\nCombine all observations"]
    end

    AGENT_ENTRY --> THINK

    subgraph TOOLS_EXEC["🛠 Tool Execution"]

        subgraph DOC_SEARCH["📚 DocumentSearchTool"]
            QUERY_ENHANCE["Query Enhancement\nHyDE + Expansion"]
            EMBED_QUERY["Embed Query\nEmbedding Provider"]
            QDRANT_SEARCH["Qdrant Similarity Search\nTop-K = 5\nThreshold = 0.7"]
            RERANK["Cross-Encoder Reranking"]
            CONTEXT["Retrieved Context\nChunks + Metadata"]

            QUERY_ENHANCE --> EMBED_QUERY --> QDRANT_SEARCH --> RERANK --> CONTEXT
        end

        subgraph CALC["🔢 CalculatorTool"]
            MATH_PARSE["Parse Math Expression"]
            EVALUATE["Safe Evaluation\nNo Code Execution"]
            MATH_RESULT["Numeric Result"]

            MATH_PARSE --> EVALUATE --> MATH_RESULT
        end

        subgraph META_SEARCH["📋 MetadataSearchTool"]
            LIST_DOCS["List Documents"]
            FILTER["Filter\nDate / Type / Author"]
            META_RESULT["Metadata Results"]

            LIST_DOCS --> FILTER --> META_RESULT
        end

    end

    ACT --> QUERY_ENHANCE
    ACT --> MATH_PARSE
    ACT --> LIST_DOCS

    subgraph RAG_PIPELINE["🔄 RAG Pipeline"]
        CTX_BUILD["Context Builder\nRank + Deduplicate"]
        CITATION_MAP["Citation Mapper\nChunk → Source"]
        PROMPT_BUILD["Prompt Builder\nPrompt Registry"]
        TOKEN_COUNT["Token Counter\nContext Window"]
    end

    SYNTHESIZE --> CTX_BUILD
    CTX_BUILD --> CITATION_MAP --> PROMPT_BUILD --> TOKEN_COUNT

    subgraph LLM_GENERATION["🤖 LLM Generation"]
        LLM_CALL["LLMProvider.generate()"]

        subgraph STREAMING["📡 Streaming (SSE)"]
            CHUNK_STREAM["Token Streaming"]
            SSE_FORMAT["SSE Formatting"]
            CLIENT_STREAM["StreamingResponse\nFastAPI"]
        end

        VALIDATE_RESP["Response Validator\nHallucination Detection"]
    end

    TOKEN_COUNT --> LLM_CALL
    LLM_CALL --> CHUNK_STREAM --> SSE_FORMAT --> CLIENT_STREAM

    subgraph POST_PROCESS["✨ Post Processing"]
        EXTRACT_CITATIONS["Extract Citations"]
        FORMAT_RESP["Format Response\nAnswer + Citations + Metadata"]
        SAVE_MEMORY["Save Conversation\nRedis Memory"]
        LOG_INTERACTION["Analytics Logging"]
    end

    CLIENT_STREAM --> EXTRACT_CITATIONS
    LLM_CALL --> VALIDATE_RESP --> EXTRACT_CITATIONS
    EXTRACT_CITATIONS --> FORMAT_RESP --> SAVE_MEMORY --> LOG_INTERACTION

    LOG_INTERACTION --> DONE([✅ Response Delivered])

    style REQUEST_LAYER fill:#e3f2fd,stroke:#2196f3
    style AGENT_ORCHESTRATION fill:#fce4ec,stroke:#e91e63
    style TOOLS_EXEC fill:#fff3e0,stroke:#ff9800
    style RAG_PIPELINE fill:#e8f5e9,stroke:#4caf50
    style LLM_GENERATION fill:#f3e5f5,stroke:#9c27b0
```

## 2.4 RAG Pipeline Detail

```mermaid
flowchart LR

    subgraph QUERY_PROC["Query Processing"]
        Q["Raw Query"] --> QE["Query Enhancement"]
        QE --> HYDE["HyDE Generation\nHypothetical Document"]
        HYDE --> QV["Query Embedding"]
        Q --> QV
    end

    subgraph RETRIEVAL["Multi-Stage Retrieval"]
        QV --> DENSE["Dense Search\nCosine Similarity\nQdrant ANN"]
        QV --> FILTER["Metadata Filter\nDoc ID / Date / Type"]
        DENSE --> CANDIDATES["Top-20 Candidates"]
        FILTER --> CANDIDATES
        CANDIDATES --> RERANK["Cross-Encoder Rerank\nTop-5"]
    end

    subgraph CONTEXT["Context Construction"]
        RERANK --> DEDUP["Deduplicate Chunks"]
        DEDUP --> SORT["Sort\nRelevance + Page Order"]
        SORT --> WINDOW["Context Window\nToken Budget"]
        WINDOW --> CMAP["Citation Map\nChunk → Document + Page"]
    end

    subgraph PROMPT["Prompt Assembly"]
        CMAP --> SYS["System Prompt\nRegistry v2.1"]
        CMAP --> CTX_BLOCK["Context Block"]
        CMAP --> HIST["Conversation History"]
        CMAP --> QBLOCK["Question"]

        SYS --> FINAL_PROMPT["Final Prompt"]
        CTX_BLOCK --> FINAL_PROMPT
        HIST --> FINAL_PROMPT
        QBLOCK --> FINAL_PROMPT
    end

    subgraph GENERATION["LLM Generation"]
        FINAL_PROMPT --> LLM["LLMProvider"]
        LLM --> STREAM["Streaming Tokens"]
        STREAM --> PARSE["Citation Parser\nExtract References"]
        PARSE --> RESP["Structured Response\nAnswer + Citations"]
    end

    style QUERY_PROC fill:#e3f2fd
    style RETRIEVAL fill:#fff3e0
    style CONTEXT fill:#e8f5e9
    style PROMPT fill:#fce4ec
    style GENERATION fill:#f3e5f5
```

## 2.5 AI Agent Workflow

```mermaid
stateDiagram-v2
    [*] --> IDLE: New Query Received

    IDLE --> ANALYZING: Start ReAct Loop

    state ANALYZING {
        [*] --> ParseIntent
        ParseIntent --> ClassifyQuery: NLP Analysis
        
        state ClassifyQuery {
            DocumentQuestion: Needs document search
            ConversationalQuestion: Can answer from memory
            CalculationNeeded: Math required
            MultiStep: Requires multiple tools
            OutOfScope: Cannot answer
        }
    }

    ANALYZING --> PLANNING: Intent Classified

    state PLANNING {
        [*] --> SelectTools
        SelectTools --> BuildExecutionPlan
        BuildExecutionPlan --> ValidatePlan
    }

    PLANNING --> EXECUTING: Plan Ready

    state EXECUTING {
        [*] --> ToolDispatch
        
        state ToolDispatch {
            DocumentSearchTool: Search vector DB
            CalculatorTool: Math evaluation
            MetadataSearchTool: List documents
            DirectAnswer: No tool needed
        }
        
        ToolDispatch --> CollectResults
        CollectResults --> EvaluateSufficiency
        EvaluateSufficiency --> ToolDispatch: Need more info
        EvaluateSufficiency --> Synthesize: Sufficient info
    }

    EXECUTING --> GENERATING: All observations collected

    state GENERATING {
        [*] --> BuildFinalPrompt
        BuildFinalPrompt --> CallLLM
        CallLLM --> StreamTokens
        StreamTokens --> ExtractCitations
    }

    GENERATING --> RESPONDING: Generation complete

    state RESPONDING {
        [*] --> ValidateResponse
        ValidateResponse --> FormatWithCitations
        FormatWithCitations --> SaveToMemory
        SaveToMemory --> EmitToClient
    }

    RESPONDING --> [*]: Request Complete

    ANALYZING --> ERROR_STATE: Classification failed
    EXECUTING --> ERROR_STATE: Tool execution failed
    GENERATING --> ERROR_STATE: LLM call failed

    state ERROR_STATE {
        [*] --> ClassifyError
        ClassifyError --> Retryable: Transient error
        ClassifyError --> Fatal: Permanent error
        Retryable --> ANALYZING: Retry with backoff
        Fatal --> FallbackResponse: Return error message
    }
```

## 2.6 Tool Calling Flow

```mermaid
sequenceDiagram
    participant U as User
    participant A as AI Agent
    participant TR as Tool Registry
    participant DST as DocumentSearchTool
    participant CT as CalculatorTool
    participant QD as Qdrant
    participant LLM as LLMProvider
    participant SSE as SSE Stream

    U->>A: "What is the total budget in Q3 report?"
    
    Note over A: ReAct Loop - Iteration 1
    A->>LLM: Analyze query, select tools
    LLM-->>A: Use [DocumentSearchTool, CalculatorTool]
    
    A->>TR: Get DocumentSearchTool
    TR-->>A: DocumentSearchTool instance
    
    A->>DST: search("Q3 budget report")
    DST->>QD: similarity_search(query_vector, k=5)
    QD-->>DST: [chunk1, chunk2, chunk3, chunk4, chunk5]
    DST-->>A: SearchResult(chunks=[], citations=[])
    
    Note over A: ReAct Loop - Iteration 2
    A->>LLM: Observe: Found budget data "$2.5M, $1.8M, $3.2M"
    LLM-->>A: Use CalculatorTool to sum values
    
    A->>TR: Get CalculatorTool
    TR-->>A: CalculatorTool instance
    
    A->>CT: calculate("2.5 + 1.8 + 3.2")
    CT-->>A: CalculationResult(value=7.5, expression="2.5 + 1.8 + 3.2")
    
    Note over A: ReAct Loop - Complete
    A->>LLM: Synthesize final answer with citations
    LLM->>SSE: Stream token by token
    
    loop Streaming
        SSE->>U: data: {"token": "The", "type": "token"}
        SSE->>U: data: {"token": " total", "type": "token"}
        SSE->>U: data: {"token": " Q3...", "type": "token"}
    end
    
    SSE->>U: data: {"type": "citations", "data": [...]}
    SSE->>U: data: {"type": "done", "usage": {...}}
```

## 2.7 Streaming Flow (SSE)

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant PIPE as Chat Pipeline
    participant AGENT as AI Agent
    participant LLM as LLMProvider
    participant REDIS as Redis

    C->>API: POST /api/v1/chat/stream
    Note over API: Set headers:<br/>Content-Type: text/event-stream<br/>Cache-Control: no-cache<br/>X-Request-ID: uuid4

    API->>PIPE: Initialize streaming pipeline
    PIPE->>REDIS: Load conversation history
    REDIS-->>PIPE: ConversationHistory
    
    PIPE->>AGENT: Start agent with streaming=True
    
    API-->>C: SSE: {"type":"start","request_id":"..."}
    
    AGENT->>LLM: generate_stream(prompt)
    
    loop Token Streaming
        LLM-->>AGENT: AsyncGenerator[str]
        AGENT->>PIPE: Yield token
        PIPE->>API: Yield SSEEvent
        API-->>C: data: {"type":"token","content":"Hello"}
    end

    AGENT-->>PIPE: Tool call started
    PIPE->>API: Yield tool event
    API-->>C: data: {"type":"tool_start","tool":"DocumentSearch"}
    
    AGENT-->>PIPE: Tool call result
    API-->>C: data: {"type":"tool_end","result":{...}}

    AGENT-->>PIPE: Citations extracted
    API-->>C: data: {"type":"citations","data":[...]}
    
    AGENT-->>PIPE: Generation complete
    PIPE->>REDIS: Save conversation turn
    
    API-->>C: data: {"type":"done","usage":{"tokens":245}}
    API-->>C: data: [DONE]

    Note over C: Client closes connection
```

## 2.8 Deployment Architecture

```mermaid
graph TB
    subgraph INTERNET["🌐 Internet"]
        USERS[Enterprise Users]
        CICD[CI/CD Pipeline<br/>GitHub Actions]
    end

    subgraph AWS["☁️ AWS Cloud"]
        subgraph VPC["🔒 VPC - Private Network"]
            subgraph PUBLIC["Public Subnet"]
                ALB[Application Load Balancer<br/>HTTPS + SSL]
                NAT[NAT Gateway]
            end

            subgraph PRIVATE_APP["Private Subnet - Application"]
                subgraph ECS["ECS Fargate Cluster"]
                    TASK1[FastAPI Task 1<br/>2 vCPU, 4GB RAM]
                    TASK2[FastAPI Task 2<br/>2 vCPU, 4GB RAM]
                    TASK3[FastAPI Task N<br/>Auto Scaling]
                end
                
                subgraph WORKERS["Background Workers"]
                    WORKER1[Ingestion Worker 1]
                    WORKER2[Ingestion Worker 2]
                end
            end

            subgraph PRIVATE_DATA["Private Subnet - Data"]
                QDRANT_EC2[Qdrant on EC2<br/>r6i.large<br/>Vector Database]
                RDS[RDS PostgreSQL<br/>db.t3.medium<br/>Metadata]
                ELASTICACHE[ElastiCache Redis<br/>cache.t3.medium<br/>Sessions + Cache]
            end
        end

        subgraph MANAGED["🛠️ AWS Managed Services"]
            BEDROCK[Amazon Bedrock<br/>Claude 3 Sonnet<br/>Titan Embeddings]
            S3[S3 Bucket<br/>PDF Storage]
            ECR[ECR<br/>Container Registry]
            SECRETS[Secrets Manager<br/>API Keys]
            CLOUDWATCH[CloudWatch<br/>Logs + Metrics]
            XRAY[X-Ray<br/>Distributed Tracing]
            WAF[WAF<br/>Web Application Firewall]
        end

        subgraph OBSERVABILITY_AWS["📊 Observability"]
            GRAFANA_CLOUD[Grafana Cloud<br/>Dashboards]
            JAEGER_EC2[Jaeger on EC2<br/>Trace Storage]
        end
    end

    subgraph LOCAL["💻 Development"]
        DEV[Developer Machine]
        DOCKER_COMPOSE[Docker Compose<br/>Local Stack]
        GEMINI[Gemini API<br/>Development LLM]
    end

    USERS --> WAF --> ALB
    ALB --> ECS
    ECS --> PRIVATE_DATA
    ECS --> BEDROCK
    ECS --> S3
    ECS --> SECRETS
    ECS --> CLOUDWATCH
    ECS --> XRAY

    WORKERS --> QDRANT_EC2
    WORKERS --> BEDROCK
    WORKERS --> S3

    CICD --> ECR
    ECR --> ECS

    DEV --> DOCKER_COMPOSE
    DOCKER_COMPOSE --> GEMINI

    CLOUDWATCH --> GRAFANA_CLOUD
    XRAY --> JAEGER_EC2

    style AWS fill:#fff3e0,stroke:#ff9800
    style LOCAL fill:#e8f5e9,stroke:#4caf50
    style MANAGED fill:#e3f2fd,stroke:#2196f3
```

---

# 3. PROJECT STRUCTURE

```
document-ai-agent/
│
├── 📁 app/                                    # Main application package
│   │
│   ├── 📁 api/                                # API Layer - HTTP interface only
│   │   ├── __init__.py
│   │   ├── 📁 v1/                             # API version 1
│   │   │   ├── __init__.py
│   │   │   ├── 📁 routers/                    # FastAPI routers (thin controllers)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── documents.py               # Document CRUD + upload endpoints
│   │   │   │   ├── chat.py                    # Chat + streaming endpoints
│   │   │   │   ├── health.py                  # Health + readiness checks
│   │   │   │   └── metrics.py                 # Prometheus metrics endpoint
│   │   │   └── dependencies.py                # FastAPI dependency injection
│   │   └── 📁 schemas/                        # Pydantic v2 request/response models
│   │       ├── __init__.py
│   │       ├── documents.py                   # Document schemas
│   │       ├── chat.py                        # Chat schemas
│   │       ├── health.py                      # Health check schemas
│   │       └── common.py                      # Shared schemas (pagination, errors)
│   │
│   ├── 📁 services/                           # Service Layer - business orchestration
│   │   ├── __init__.py
│   │   ├── document_service.py                # Document CRUD + lifecycle management
│   │   ├── ingestion_service.py               # Orchestrates the ingestion pipeline
│   │   ├── chat_service.py                    # Orchestrates the chat pipeline
│   │   ├── embedding_service.py               # Embedding generation orchestration
│   │   ├── retrieval_service.py               # Document retrieval logic
│   │   ├── streaming_service.py               # SSE streaming management
│   │   ├── memory_service.py                  # Conversation memory management
│   │   └── citation_service.py                # Citation extraction + formatting
│   │
│   ├── 📁 repositories/                       # Repository Pattern - data access
│   │   ├── __init__.py
│   │   ├── base.py                            # Abstract base repository
│   │   ├── document_repository.py             # PostgreSQL document metadata CRUD
│   │   ├── vector_repository.py               # Qdrant vector operations
│   │   ├── job_repository.py                  # Background job tracking
│   │   └── session_repository.py              # Redis session/memory storage
│   │
│   ├── 📁 pipelines/                          # Pipeline Orchestrators
│   │   ├── __init__.py
│   │   ├── ingestion_pipeline.py              # Full ingestion flow coordinator
│   │   └── chat_pipeline.py                   # Full chat flow coordinator
│   │
│   ├── 📁 agents/                             # AI Agent Layer
│   │   ├── __init__.py
│   │   ├── base_agent.py                      # Abstract agent interface
│   │   ├── document_agent.py                  # Main ReAct document agent
│   │   └── agent_executor.py                  # Agent execution loop + state
│   │
│   ├── 📁 tools/                              # Agent Tools
│   │   ├── __init__.py
│   │   ├── base_tool.py                       # Abstract tool interface
│   │   ├── tool_registry.py                   # Tool registration + discovery
│   │   ├── document_search_tool.py            # Vector search tool
│   │   ├── calculator_tool.py                 # Safe math evaluation tool
│   │   └── metadata_search_tool.py            # Document metadata search tool
│   │
│   ├── 📁 llm/                                # LLM Provider Abstraction
│   │   ├── __init__.py
│   │   ├── base.py                            # LLMProvider abstract base class
│   │   ├── registry.py                        # Model registry + model table
│   │   ├── factory.py                         # Provider factory (config-driven)
│   │   ├── 📁 providers/                      # Concrete LLM implementations
│   │   │   ├── __init__.py
│   │   │   ├── gemini_provider.py             # Google Gemini implementation
│   │   │   ├── bedrock_provider.py            # Amazon Bedrock implementation
│   │   │   └── openai_provider.py             # OpenAI implementation (optional)
│   │   └── 📁 streaming/                      # Streaming adapters
│   │       ├── __init__.py
│   │       └── stream_adapter.py              # Normalize streaming across providers
│   │
│   ├── 📁 embeddings/                         # Embedding Provider Abstraction
│   │   ├── __init__.py
│   │   ├── base.py                            # EmbeddingProvider abstract base
│   │   ├── factory.py                         # Embedding provider factory
│   │   └── 📁 providers/                      # Concrete embedding implementations
│   │       ├── __init__.py
│   │       ├── gemini_embeddings.py           # Gemini text-embedding-004
│   │       ├── bedrock_embeddings.py          # Titan Embeddings V2
│   │       └── local_embeddings.py            # sentence-transformers (fallback)
│   │
│   ├── 📁 prompts/                            # Prompt Management System
│   │   ├── __init__.py
│   │   ├── registry.py                        # Prompt registry (load all prompts)
│   │   ├── builder.py                         # Prompt builder (assemble prompts)
│   │   ├── versioning.py                      # Version control for prompts
│   │   └── 📁 templates/                      # Versioned prompt templates
│   │       ├── __init__.py
│   │       ├── system/
│   │       │   ├── document_agent_v1.yaml     # System prompt version 1
│   │       │   └── document_agent_v2.yaml     # System prompt version 2
│   │       ├── rag/
│   │       │   ├── rag_context_v1.yaml        # RAG context prompt
│   │       │   └── rag_context_v2.yaml        # RAG context prompt v2
│   │       └── tools/
│   │           ├── tool_selection_v1.yaml     # Tool selection prompt
│   │           └── synthesis_v1.yaml          # Answer synthesis prompt
│   │
│   ├── 📁 processing/                         # Document Processing Components
│   │   ├── __init__.py
│   │   ├── pdf_parser.py                      # PyMuPDF PDF parsing
│   │   ├── chunker.py                         # Semantic text chunking
│   │   ├── metadata_extractor.py              # Document metadata extraction
│   │   └── document_validator.py              # File validation rules
│   │
│   ├── 📁 vector_db/                          # Vector Database Layer
│   │   ├── __init__.py
│   │   ├── client.py                          # Qdrant client setup + connection
│   │   ├── collections.py                     # Collection management + schema
│   │   └── operations.py                      # CRUD operations for vectors
│   │
│   ├── 📁 models/                             # Domain Models (Pydantic v2)
│   │   ├── __init__.py
│   │   ├── document.py                        # Document domain model
│   │   ├── chunk.py                           # Chunk domain model
│   │   ├── conversation.py                    # Conversation + message models
│   │   ├── job.py                             # Background job model
│   │   └── citation.py                        # Citation model
│   │
│   ├── 📁 config/                             # Configuration Management
│   │   ├── __init__.py
│   │   ├── settings.py                        # Pydantic BaseSettings (env-driven)
│   │   ├── model_table.py                     # Model registry / model table
│   │   └── feature_flags.py                   # Feature flag definitions
│   │
│   ├── 📁 middleware/                         # FastAPI Middleware
│   │   ├── __init__.py
│   │   ├── request_id.py                      # X-Request-ID injection
│   │   ├── correlation_id.py                  # Correlation ID propagation
│   │   ├── timing.py                          # Request timing middleware
│   │   ├── error_handler.py                   # Global exception handler
│   │   └── auth.py                            # Authentication middleware (stub)
│   │
│   ├── 📁 observability/                      # Observability Stack
│   │   ├── __init__.py
│   │   ├── logging.py                         # Structured JSON logging setup
│   │   ├── tracing.py                         # OpenTelemetry tracer setup
│   │   ├── metrics.py                         # Prometheus metrics definitions
│   │   └── health.py                          # Health check implementations
│   │
│   └── 📁 utils/                              # Shared Utilities
│       ├── __init__.py
│       ├── retry.py                           # Retry decorator with backoff
│       ├── timeout.py                         # Async timeout wrapper
│       ├── hashing.py                         # SHA-256 document hashing
│       ├── token_counter.py                   # Token counting utilities
│       ├── error_classifier.py                # Error classification logic
│       └── validators.py                      # Shared validation helpers
│
├── 📁 tests/                                  # Test Suite
│   ├── __init__.py
│   ├── conftest.py                            # Shared fixtures + test config
│   ├── 📁 unit/                               # Unit tests (fast, no I/O)
│   │   ├── test_chunker.py
│   │   ├── test_prompt_builder.py
│   │   ├── test_citation_service.py
│   │   ├── test_document_validator.py
│   │   └── test_calculator_tool.py
│   ├── 📁 integration/                        # Integration tests (with services)
│   │   ├── test_ingestion_pipeline.py
│   │   ├── test_chat_pipeline.py
│   │   ├── test_vector_repository.py
│   │   └── test_llm_providers.py
│   └── 📁 e2e/                               # End-to-end API tests
│       ├── test_document_api.py
│       └── test_chat_api.py
│
├── 📁 docker/                                 # Docker Configuration
│   ├── Dockerfile                             # Production multi-stage Dockerfile
│   ├── Dockerfile.dev                         # Development Dockerfile
│   └── 📁 nginx/
│       └── nginx.conf                         # NGINX reverse proxy config
│
├── 📁 deploy/                                 # Deployment Configuration
│   ├── 📁 aws/
│   │   ├── ecs-task-definition.json           # ECS task definition
│   │   ├── buildspec.yml                      # CodeBuild specification
│   │   └── cloudformation.yaml                # Infrastructure as Code
│   └── 📁 k8s/                               # Kubernetes (future)
│       └── .gitkeep
│
├── 📁 scripts/                                # Operational Scripts
│   ├── setup_qdrant_collections.py            # Initialize Qdrant collections
│   ├── migrate_db.py                          # Database migrations
│   ├── seed_data.py                           # Development seed data
│   └── health_check.sh                        # Container health check script
│
├── 📁 docs/                                   # Documentation
│   ├── architecture.md                        # Architecture decisions
│   ├── api.md                                 # API documentation
│   └── deployment.md                          # Deployment guide
│
├── docker-compose.yml                         # Full local stack
├── docker-compose.dev.yml                     # Dev override (hot reload)
├── docker-compose.test.yml                    # Test environment
├── pyproject.toml                             # Project metadata + dependencies
├── requirements.txt                           # Pinned dependencies
├── requirements-dev.txt                       # Development dependencies
├── .env.example                               # Environment template
├── .env.development                           # Development defaults
├── Makefile                                   # Developer shortcuts
└── README.md                                  # Project documentation
```

## Folder Responsibility Matrix

| Folder | Layer | Responsibility | Dependencies |
|---|---|---|---|
| `api/v1/routers/` | Interface | HTTP request handling, request validation, response formatting | `services/`, `schemas/` |
| `api/schemas/` | Interface | Pydantic v2 request/response models | `models/` |
| `services/` | Application | Business logic orchestration, pipeline coordination | `repositories/`, `providers/`, `prompts/` |
| `repositories/` | Data Access | All database operations (PostgreSQL, Qdrant, Redis) | `models/`, `vector_db/` |
| `pipelines/` | Orchestration | High-level pipeline coordination | `services/`, `agents/` |
| `agents/` | AI Logic | ReAct agent loop, tool orchestration | `tools/`, `llm/`, `prompts/` |
| `tools/` | AI Logic | Concrete agent tools with defined schemas | `repositories/`, `services/` |
| `llm/` | Provider | LLM provider abstraction + concrete implementations | External APIs |
| `embeddings/` | Provider | Embedding provider abstraction + implementations | External APIs |
| `prompts/` | AI Logic | Prompt templates, versioning, building | `config/` |
| `processing/` | Domain | PDF parsing, chunking, validation logic | PyMuPDF |
| `vector_db/` | Data Access | Qdrant client, collection management | Qdrant |
| `models/` | Domain | Core domain entities (Pydantic v2 BaseModel) | None |
| `config/` | Infrastructure | Settings, model table, feature flags | Environment |
| `middleware/` | Infrastructure | Cross-cutting concerns (IDs, timing, auth) | `observability/` |
| `observability/` | Infrastructure | Logging, tracing, metrics | OpenTelemetry |
| `utils/` | Infrastructure | Shared utilities (retry, timeout, hashing) | None |
| `tests/` | Quality | Unit, integration, e2e test suites | All |

---

# 4. TECH STACK DECISIONS

## Dependency Map

```
FastAPI ──────────────────────────────────────────────────┐
    ├── Pydantic v2          (validation + serialization)  │
    ├── AsyncIO              (async throughout)            │
    └── Uvicorn              (ASGI server)                 │
                                                           │
LangChain ───────────────────────────────────────────────┤
    ├── ReAct Agent          (reasoning loop)             │
    ├── Tool calling         (structured tool use)        │
    └── Memory               (conversation history)       │
                                                           │
Provider Layer ──────────────────────────────────────────┤
    ├── Gemini API           (development LLM)            │
    ├── Amazon Bedrock       (production LLM)             │
    └── sentence-transformers(fallback embeddings)        │
                                                           │
Storage ─────────────────────────────────────────────────┤
    ├── Qdrant               (vector search)              │
    ├── Redis                (sessions, cache, jobs)      │
    ├── PostgreSQL           (metadata, jobs)             │
    └── S3 / MinIO           (PDF files)                  │
                                                           │
Observability ───────────────────────────────────────────┘
    ├── OpenTelemetry        (tracing + metrics)
    ├── structlog             (structured logging)
    └── Prometheus           (metrics scraping)
```

---

# 5. PHASE ROADMAP

## Timeline Overview

```
DAY 1 (8 hours)                          DAY 2 (8 hours)
├── Phase 1: Foundation    (2h)          ├── Phase 4: Chat Pipeline    (2.5h)
├── Phase 2: Ingestion     (3h)          ├── Phase 5: AI Agent         (2h)
└── Phase 3: LLM Layer     (3h)          ├── Phase 6: Observability    (1.5h)
                                          └── Phase 7: Deployment       (2h)
```

---

## PHASE 1: Foundation & Infrastructure
**Duration: 2 hours | Day 1, Morning**

### Objective
Establish the complete project skeleton with configuration, observability infrastructure, and all shared utilities before writing any business logic. This prevents expensive refactoring later.

### Features Implemented
- Project structure creation
- Pydantic v2 Settings with environment variable management
- Model Registry / Model Table
- Structured JSON logging with structlog
- OpenTelemetry tracing setup
- Prometheus metrics definitions
- Request ID + Correlation ID middleware
- Global exception handler with error classification
- Health check + readiness check endpoints
- Retry utility with exponential backoff
- Async timeout wrapper
- Docker Compose with all infrastructure services

### APIs Delivered
```
GET  /api/v1/health          → Basic liveness check
GET  /api/v1/health/ready    → Readiness (checks all dependencies)
GET  /api/v1/health/detailed → Full component status
GET  /metrics                → Prometheus metrics
```

### Key Files Created

```python
# app/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    # Application
    app_name: str = "Document AI Agent"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    
    # LLM Provider Selection (the key abstraction point)
    llm_provider: Literal["gemini", "bedrock", "openai"] = "gemini"
    embedding_provider: Literal["gemini", "bedrock", "local"] = "gemini"
    
    # Gemini (Development)
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/text-embedding-004"
    
    # Amazon Bedrock (Production)
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    
    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "company_documents"
    qdrant_vector_size: int = 768
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 3600
    
    # Database
    database_url: str = "postgresql+asyncpg://user:pass@localhost/docai"
    
    # Storage
    s3_bucket: str = "company-documents"
    s3_endpoint_url: str | None = None  # None = real AWS, set for MinIO
    
    # Processing
    max_file_size_mb: int = 50
    chunk_size: int = 512
    chunk_overlap: int = 128
    max_chunks_per_doc: int = 1000
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.7
    
    # Agent
    agent_max_iterations: int = 5
    agent_timeout_seconds: int = 30
    
    # Observability
    otel_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    
    # Feature Flags
    enable_streaming: bool = True
    enable_citations: bool = True
    enable_conversation_memory: bool = True
    enable_hyde: bool = False  # Hypothetical Document Embeddings
    
    class Config:
        env_file = ".env"
        case_sensitive = False
```

```python
# app/config/model_table.py
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class ModelConfig:
    """Immutable model configuration entry."""
    model_id: str
    provider: str
    context_window: int
    max_output_tokens: int
    supports_streaming: bool
    supports_tool_calling: bool
    cost_per_1k_input_tokens: float
    cost_per_1k_output_tokens: float
    embedding_dimensions: int | None = None

# The Model Registry - single source of truth for all model configs
MODEL_TABLE: Dict[str, ModelConfig] = {
    # Gemini Models
    "gemini-2.5-flash": ModelConfig(
        model_id="gemini-2.5-flash",
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
    # Amazon Bedrock Models
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
    if model_id not in MODEL_TABLE:
        raise ValueError(f"Unknown model: {model_id}. Available: {list(MODEL_TABLE.keys())}")
    return MODEL_TABLE[model_id]
```

```python
# app/llm/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any
from pydantic import BaseModel

class LLMMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

class LLMRequest(BaseModel):
    messages: list[LLMMessage]
    max_tokens: int = 2048
    temperature: float = 0.1
    stream: bool = False
    tools: list[dict] | None = None
    request_id: str | None = None

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    tool_calls: list[dict] | None = None

class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    Swap Gemini for Bedrock by changing config - zero business logic changes.
    """
    
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def generate_stream(
        self, 
        request: LLMRequest
    ) -> AsyncGenerator[str, None]:
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

```python
# app/utils/retry.py
import asyncio
import functools
import logging
from typing import TypeVar, Callable, Type

logger = logging.getLogger(__name__)
T = TypeVar("T")

def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    exponential_base: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """
    Async retry decorator with exponential backoff.
    Production pattern: retry transient failures, propagate permanent ones.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        logger.error(
                            "Max retry attempts reached",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "error": str(e)
                            }
                        )
                        raise
                    delay = min(
                        initial_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    logger.warning(
                        "Retrying after error",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "delay": delay,
                            "error": str(e)
                        }
                    )
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
```

```yaml
# docker-compose.yml
version: '3.9'

services:
  app:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - LLM_PROVIDER=gemini
      - EMBEDDING_PROVIDER=gemini
      - QDRANT_HOST=qdrant
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql+asyncpg://user:password@postgres/docai
      - S3_ENDPOINT_URL=http://minio:9000
    depends_on:
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    volumes:
      - ./app:/app/app  # Hot reload in dev
    env_file: .env

  qdrant:
    image: qdrant/qdrant:v1.9.0
    ports:
      - "6333:6333"
      - "6334:6334"  # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: docai
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d docai"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"  # Console
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data

  jaeger:
    image: jaegertracing/all-in-one:1.56
    ports:
      - "16686:16686"   # UI
      - "4317:4317"     # OTLP gRPC
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

  prometheus:
    image: prom/prometheus:v2.51.0
    ports:
      - "9090:9090"
    volumes:
      - ./docker/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:10.4.0
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  qdrant_data:
  redis_data:
  postgres_data:
  minio_data:
  grafana_data:
```

### Deliverables
- ✅ Complete project skeleton (all folders + `__init__.py`)
- ✅ `Settings` class with full environment configuration
- ✅ Model Registry with 7 models configured
- ✅ `LLMProvider` abstract base class
- ✅ `EmbeddingProvider` abstract base class
- ✅ Structured logging with structlog
- ✅ OpenTelemetry tracer setup
- ✅ Prometheus metrics definitions
- ✅ Request ID + Correlation ID middleware
- ✅ Global exception handler
- ✅ Health check endpoints (live + ready + detailed)
- ✅ Retry + timeout utilities
- ✅ Docker Compose with all 7 services
- ✅ FastAPI app factory with middleware stack

---

## PHASE 2: Document Ingestion Pipeline
**Duration: 3 hours | Day 1, Late Morning + Afternoon**

### Objective
Build the complete, fully independent document ingestion pipeline. Users can upload PDFs, the system validates, parses, chunks, embeds, and stores them in Qdrant. The pipeline runs in background and provides real-time progress tracking.

### Features Implemented
- PDF upload endpoint with multipart form data
- File validation (type, size, corruption, duplicates)
- Document versioning with SHA-256 hash comparison
- PyMuPDF PDF parsing (text, metadata, structure)
- Semantic chunking with overlap
- Metadata extraction per chunk (page, section, position)
- Batch embedding generation with retry
- Qdrant vector storage with rich payload
- Background task processing with FastAPI BackgroundTasks
- Progress tracking via Redis
- Re-indexing endpoint for existing documents
- Document list + delete endpoints
- Incremental re-indexing (skip unchanged documents)

### APIs Delivered
```
POST   /api/v1/documents/upload              → Upload + start ingestion
POST   /api/v1/documents/{id}/reindex        → Re-index document
GET    /api/v1/documents                     → List all documents
GET    /api/v1/documents/{id}               → Get document details
DELETE /api/v1/documents/{id}               → Delete document + vectors
GET    /api/v1/documents/{id}/status        → Get ingestion job status
GET    /api/v1/documents/{id}/chunks        → List document chunks
```

### Key Files Created

```python
# app/processing/pdf_parser.py
import fitz  # PyMuPDF
from pathlib import Path
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

@dataclass
class ParsedPage:
    page_number: int
    text: str
    char_count: int
    has_images: bool
    has_tables: bool

@dataclass
class ParsedDocument:
    title: str | None
    author: str | None
    created_date: str | None
    total_pages: int
    total_chars: int
    pages: list[ParsedPage]
    raw_metadata: dict

class PDFParser:
    """
    PyMuPDF-based PDF parser.
    Extracts text page by page with structural metadata.
    """

    def parse(self, file_path: Path, document_id: str) -> ParsedDocument:
        log = logger.bind(document_id=document_id, file_path=str(file_path))
        
        try:
            doc = fitz.open(str(file_path))
            pages = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                
                # Detect tables and images
                has_images = len(page.get_images()) > 0
                blocks = page.get_text("blocks")
                has_tables = self._detect_tables(blocks)
                
                pages.append(ParsedPage(
                    page_number=page_num + 1,
                    text=text.strip(),
                    char_count=len(text),
                    has_images=has_images,
                    has_tables=has_tables,
                ))

            metadata = doc.metadata
            doc.close()
            
            log.info("PDF parsed successfully", total_pages=len(pages))
            
            return ParsedDocument(
                title=metadata.get("title"),
                author=metadata.get("author"),
                created_date=metadata.get("creationDate"),
                total_pages=len(pages),
                total_chars=sum(p.char_count for p in pages),
                pages=pages,
                raw_metadata=metadata,
            )
            
        except Exception as e:
            log.error("PDF parsing failed", error=str(e))
            raise

    def _detect_tables(self, blocks: list) -> bool:
        """Heuristic: many short blocks side-by-side indicate table structure."""
        if len(blocks) < 4:
            return False
        short_blocks = [b for b in blocks if len(b) > 4 and len(str(b[4])) < 50]
        return len(short_blocks) > len(blocks) * 0.5
```

```python
# app/processing/chunker.py
from dataclasses import dataclass
from app.processing.pdf_parser import ParsedDocument, ParsedPage
from app.config.settings import Settings

@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    content: str
    page_number: int
    chunk_index: int
    total_chunks: int
    token_count: int
    char_count: int
    metadata: dict

class SemanticChunker:
    """
    Semantic text chunker with sliding window overlap.
    Respects sentence boundaries for coherent chunks.
    """
    
    def __init__(self, settings: Settings):
        self.chunk_size = settings.chunk_size          # tokens
        self.chunk_overlap = settings.chunk_overlap    # tokens
    
    def chunk_document(
        self, 
        parsed_doc: ParsedDocument, 
        document_id: str
    ) -> list[DocumentChunk]:
        all_chunks = []
        chunk_index = 0
        
        for page in parsed_doc.pages:
            if not page.text.strip():
                continue
                
            page_chunks = self._chunk_text(
                text=page.text,
                document_id=document_id,
                page_number=page.page_number,
                start_index=chunk_index,
            )
            all_chunks.extend(page_chunks)
            chunk_index += len(page_chunks)
        
        # Update total_chunks now that we know the final count
        total = len(all_chunks)
        for chunk in all_chunks:
            chunk.total_chunks = total
            
        return all_chunks
    
    def _chunk_text(
        self, 
        text: str, 
        document_id: str, 
        page_number: int, 
        start_index: int
    ) -> list[DocumentChunk]:
        # Split into sentences (simple but effective)
        sentences = self._split_sentences(text)
        chunks = []
        current_chunk = []
        current_size = 0
        local_index = 0
        
        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)
            
            if current_size + sentence_tokens > self.chunk_size and current_chunk:
                # Finalize current chunk
                chunk_text = " ".join(current_chunk)
                chunks.append(DocumentChunk(
                    chunk_id=f"{document_id}_p{page_number}_c{start_index + local_index}",
                    document_id=document_id,
                    content=chunk_text,
                    page_number=page_number,
                    chunk_index=start_index + local_index,
                    total_chunks=0,  # Updated later
                    token_count=current_size,
                    char_count=len(chunk_text),
                    metadata={"page": page_number, "position": local_index},
                ))
                local_index += 1
                
                # Overlap: keep last N tokens worth of sentences
                overlap_sentences = self._get_overlap_sentences(current_chunk)
                current_chunk = overlap_sentences + [sentence]
                current_size = sum(self._estimate_tokens(s) for s in current_chunk)
            else:
                current_chunk.append(sentence)
                current_size += sentence_tokens
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(DocumentChunk(
                chunk_id=f"{document_id}_p{page_number}_c{start_index + local_index}",
                document_id=document_id,
                content=chunk_text,
                page_number=page_number,
                chunk_index=start_index + local_index,
                total_chunks=0,
                token_count=current_size,
                char_count=len(chunk_text),
                metadata={"page": page_number, "position": local_index},
            ))
        
        return chunks
    
    def _split_sentences(self, text: str) -> list[str]:
        """Simple sentence splitter - replace with spacy for production."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimate: 1 token ≈ 4 characters."""
        return len(text) // 4
    
    def _get_overlap_sentences(self, sentences: list[str]) -> list[str]:
        """Return the last sentences that fit within overlap budget."""
        overlap_budget = self.chunk_overlap
        overlap = []
        for sentence in reversed(sentences):
            tokens = self._estimate_tokens(sentence)
            if tokens <= overlap_budget:
                overlap.insert(0, sentence)
                overlap_budget -= tokens
            else:
                break
        return overlap
```

```python
# app/pipelines/ingestion_pipeline.py
import asyncio
import structlog
from pathlib import Path
from opentelemetry import trace

from app.processing.pdf_parser import PDFParser
from app.processing.chunker import SemanticChunker
from app.processing.document_validator import DocumentValidator
from app.embeddings.base import EmbeddingProvider
from app.repositories.vector_repository import VectorRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.models.job import JobStatus
from app.observability.metrics import ingestion_counter, ingestion_duration

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

class IngestionPipeline:
    """
    Orchestrates the complete document ingestion pipeline.
    Completely independent from the chat pipeline.
    """
    
    def __init__(
        self,
        pdf_parser: PDFParser,
        chunker: SemanticChunker,
        validator: DocumentValidator,
        embedding_provider: EmbeddingProvider,
        vector_repo: VectorRepository,
        document_repo: DocumentRepository,
        job_repo: JobRepository,
    ):
        self.pdf_parser = pdf_parser
        self.chunker = chunker
        self.validator = validator
        self.embedding_provider = embedding_provider
        self.vector_repo = vector_repo
        self.document_repo = document_repo
        self.job_repo = job_repo
    
    async def run(self, document_id: str, file_path: Path, job_id: str) -> None:
        """
        Execute the full ingestion pipeline.
        Designed to run as a background task.
        """
        log = logger.bind(document_id=document_id, job_id=job_id)
        
        with tracer.start_as_current_span("ingestion_pipeline") as span:
            span.set_attribute("document_id", document_id)
            span.set_attribute("job_id", job_id)
            
            try:
                # Step 1: Update job status
                await self.job_repo.update_status(job_id, JobStatus.PARSING, progress=10)
                log.info("Starting ingestion pipeline")
                
                # Step 2: Parse PDF
                with tracer.start_as_current_span("parse_pdf"):
                    parsed_doc = self.pdf_parser.parse(file_path, document_id)
                    log.info("PDF parsed", pages=parsed_doc.total_pages)
                
                await self.job_repo.update_status(job_id, JobStatus.CHUNKING, progress=30)
                
                # Step 3: Chunk document
                with tracer.start_as_current_span("chunk_document"):
                    chunks = self.chunker.chunk_document(parsed_doc, document_id)
                    log.info("Document chunked", chunk_count=len(chunks))
                
                await self.job_repo.update_status(job_id, JobStatus.EMBEDDING, progress=50)
                
                # Step 4: Generate embeddings in batches
                with tracer.start_as_current_span("generate_embeddings"):
                    batch_size = 32
                    all_embeddings = []
                    
                    for i in range(0, len(chunks), batch_size):
                        batch = chunks[i:i + batch_size]
                        texts = [c.content for c in batch]
                        
                        batch_embeddings = await self.embedding_provider.embed_batch(texts)
                        all_embeddings.extend(batch_embeddings)
                        
                        # Update progress (50% → 80% during embedding)
                        progress = 50 + int((i / len(chunks)) * 30)
                        await self.job_repo.update_status(
                            job_id, JobStatus.EMBEDDING, progress=progress
                        )
                    
                    log.info("Embeddings generated", count=len(all_embeddings))
                
                await self.job_repo.update_status(job_id, JobStatus.INDEXING, progress=80)
                
                # Step 5: Store in Qdrant
                with tracer.start_as_current_span("store_vectors"):
                    await self.vector_repo.upsert_chunks(
                        chunks=chunks,
                        embeddings=all_embeddings,
                        document_metadata={
                            "title": parsed_doc.title,
                            "author": parsed_doc.author,
                            "total_pages": parsed_doc.total_pages,
                        }
                    )
                    log.info("Vectors stored in Qdrant")
                
                # Step 6: Update document metadata
                await self.document_repo.update_document_status(
                    document_id=document_id,
                    status="indexed",
                    chunk_count=len(chunks),
                    total_pages=parsed_doc.total_pages,
                )
                
                await self.job_repo.update_status(job_id, JobStatus.COMPLETED, progress=100)
                
                ingestion_counter.labels(status="success").inc()
                log.info("Ingestion pipeline completed successfully")
                
            except Exception as e:
                log.error("Ingestion pipeline failed", error=str(e), exc_info=True)
                await self.job_repo.update_status(
                    job_id, JobStatus.FAILED, 
                    progress=0, 
                    error_message=str(e)
                )
                ingestion_counter.labels(status="error").inc()
                raise
```

```python
# app/api/v1/routers/documents.py
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException
from app.api.schemas.documents import (
    DocumentUploadResponse, DocumentListResponse, 
    DocumentDetailResponse, JobStatusResponse
)
from app.services.document_service import DocumentService
from app.api.v1.dependencies import get_document_service
import uuid

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/upload", response_model=DocumentUploadResponse, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
):
    """
    Upload a PDF document for indexing.
    Returns immediately with job_id for progress tracking.
    Processing happens in background.
    """
    document_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    
    result = await service.initiate_upload(
        file=file,
        document_id=document_id,
        job_id=job_id,
        background_tasks=background_tasks,
    )
    
    return DocumentUploadResponse(
        document_id=result.document_id,
        job_id=result.job_id,
        filename=file.filename,
        status="processing",
        message="Document queued for indexing. Use job_id to track progress.",
    )

@router.get("/{document_id}/status", response_model=JobStatusResponse)
async def get_ingestion_status(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
):
    """Poll ingestion progress. Frontend polls this every 2 seconds."""
    return await service.get_job_status(document_id)

@router.post("/{document_id}/reindex", status_code=202)
async def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    service: DocumentService = Depends(get_document_service),
):
    """Re-index an existing document (e.g., after model change)."""
    return await service.reindex_document(document_id, background_tasks)

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    service: DocumentService = Depends(get_document_service),
):
    """List all indexed documents with pagination."""
    return await service.list_documents(page=page, page_size=page_size)

@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
):
    """Delete document and all its vectors from Qdrant."""
    await service.delete_document(document_id)
```

### Deliverables
- ✅ Complete ingestion pipeline (validate → parse → chunk → embed → store)
- ✅ `PDFParser` with PyMuPDF
- ✅ `SemanticChunker` with overlap
- ✅ `DocumentValidator` (type, size, corruption, duplicates)
- ✅ `EmbeddingProvider` abstract base + Gemini implementation
- ✅ `VectorRepository` with Qdrant upsert/delete/search
- ✅ `DocumentRepository` with PostgreSQL CRUD
- ✅ Background processing with job tracking
- ✅ Redis progress tracking
- ✅ Document versioning with SHA-256
- ✅ All document CRUD APIs
- ✅ Ingestion status polling endpoint

---

## PHASE 3: LLM Provider Abstraction Layer
**Duration: 3 hours | Day 1, Evening**

### Objective
Implement the full provider abstraction that makes Gemini and Amazon Bedrock interchangeable. Build both providers, the embedding abstraction, the Prompt Registry, Prompt Builder, and template versioning system.

### Features Implemented
- `LLMProvider` concrete implementations (Gemini + Bedrock)
- `EmbeddingProvider` concrete implementations (Gemini + Bedrock Titan)
- LLM factory with config-driven provider selection
- Prompt Registry with YAML template loading
- Prompt versioning system
- Prompt Builder with variable injection
- Provider-specific streaming adapters
- Tool calling abstraction across providers
- Token counting per provider

### Key Files Created

```python
# app/llm/providers/gemini_provider.py
import asyncio
import google.generativeai as genai
from typing import AsyncGenerator
import structlog

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMMessage
from app.utils.retry import async_retry
from app.utils.timeout import async_timeout

logger = structlog.get_logger()

class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM Provider implementation.
    Used in development. Swap to BedrockProvider for production.
    """
    
    def __init__(self, api_key: str, model_id: str):
        genai.configure(api_key=api_key)
        self.model_id = model_id
        self._model = genai.GenerativeModel(model_id)
        self.logger = logger.bind(provider="gemini", model=model_id)
    
    @async_retry(max_attempts=3, retryable_exceptions=(Exception,))
    @async_timeout(seconds=30)
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate complete response from Gemini."""
        log = self.logger.bind(request_id=request.request_id)
        
        contents = self._format_messages(request.messages)
        
        generation_config = genai.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        
        log.debug("Calling Gemini API")
        response = await asyncio.to_thread(
            self._model.generate_content,
            contents,
            generation_config=generation_config,
        )
        
        content = response.text or ""
        usage = response.usage_metadata
        
        log.info("Gemini response received", 
                 output_tokens=usage.candidates_token_count if usage else 0)
        
        return LLMResponse(
            content=content,
            model=self.model_id,
            provider="gemini",
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "unknown",
            tool_calls=None,
        )
    
    async def generate_stream(
        self, 
        request: LLMRequest
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Gemini."""
        contents = self._format_messages(request.messages)
        
        generation_config = genai.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        
        # Gemini streaming in async context
        response = await asyncio.to_thread(
            self._model.generate_content,
            contents,
            generation_config=generation_config,
            stream=True,
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    
    def _format_messages(self, messages: list[LLMMessage]) -> list[dict]:
        """Convert standard messages to Gemini format."""
        formatted = []
        for msg in messages:
            if msg.role == "system":
                # Gemini handles system via model config, prepend to first user message
                continue
            role = "user" if msg.role == "user" else "model"
            formatted.append({"role": role, "parts": [msg.content]})
        
        # Prepend system message content to first user message
        system_msgs = [m for m in messages if m.role == "system"]
        if system_msgs and formatted:
            formatted[0]["parts"].insert(0, system_msgs[0].content + "\n\n")
        
        return formatted
    
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

```python
# app/llm/providers/bedrock_provider.py
import json
import boto3
import asyncio
from typing import AsyncGenerator
import structlog

from app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMMessage
from app.utils.retry import async_retry
from app.utils.timeout import async_timeout

logger = structlog.get_logger()

class BedrockProvider(LLMProvider):
    """
    Amazon Bedrock LLM Provider implementation.
    Production provider - zero code changes needed to switch from Gemini.
    Supports Claude 3 models via Bedrock.
    """
    
    def __init__(self, region: str, model_id: str):
        self.model_id = model_id
        self.region = region
        # Bedrock uses standard AWS credential chain
        # IAM Role in production (no explicit keys needed)
        self._client = boto3.client(
            service_name="bedrock-runtime",
            region_name=region,
        )
        self.logger = logger.bind(provider="bedrock", model=model_id)
    
    @async_retry(max_attempts=3, retryable_exceptions=(Exception,))
    @async_timeout(seconds=60)
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate complete response from Amazon Bedrock (Claude)."""
        log = self.logger.bind(request_id=request.request_id)
        
        body = self._build_request_body(request)
        
        log.debug("Calling Bedrock API")
        
        # Bedrock is synchronous; run in thread pool
        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        
        response_body = json.loads(response["body"].read())
        
        content = response_body["content"][0]["text"]
        usage = response_body.get("usage", {})
        
        log.info("Bedrock response received",
                 output_tokens=usage.get("output_tokens", 0))
        
        return LLMResponse(
            content=content,
            model=self.model_id,
            provider="bedrock",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            finish_reason=response_body.get("stop_reason", "end_turn"),
            tool_calls=None,
        )
    
    async def generate_stream(
        self, 
        request: LLMRequest
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Amazon Bedrock."""
        body = self._build_request_body(request)
        
        # Use invoke_model_with_response_stream
        response = await asyncio.to_thread(
            self._client.invoke_model_with_response_stream,
            modelId=self.model_id,
            body=json.dumps(body),
        )
        
        stream = response.get("body")
        if stream:
            for event in stream:
                chunk = event.get("chunk")
                if chunk:
                    chunk_data = json.loads(chunk.get("bytes", b"{}"))
                    if chunk_data.get("type") == "content_block_delta":
                        delta = chunk_data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
    
    def _build_request_body(self, request: LLMRequest) -> dict:
        """Build Claude API request body (Bedrock format)."""
        system_content = ""
        messages = []
        
        for msg in request.messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        
        if system_content:
            body["system"] = system_content
        
        return body
    
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

```python
# app/llm/factory.py
from app.llm.base import LLMProvider
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.bedrock_provider import BedrockProvider
from app.config.settings import Settings
from app.config.model_table import get_model_config

class LLMProviderFactory:
    """
    Factory for creating LLM provider instances.
    Configuration-driven: change LLM_PROVIDER env var to switch providers.
    Zero business logic changes required.
    """
    
    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        provider = settings.llm_provider
        
        if provider == "gemini":
            model_config = get_model_config(settings.gemini_model)
            return GeminiProvider(
                api_key=settings.gemini_api_key,
                model_id=settings.gemini_model,
            )
        
        elif provider == "bedrock":
            model_config = get_model_config(settings.bedrock_model_id)
            return BedrockProvider(
                region=settings.aws_region,
                model_id=settings.bedrock_model_id,
            )
        
        else:
            raise ValueError(
                f"Unknown LLM provider: '{provider}'. "
                f"Supported: ['gemini', 'bedrock']"
            )
```

```python
# app/prompts/registry.py
import yaml
from pathlib import Path
from typing import Dict
import structlog

logger = structlog.get_logger()

class PromptRegistry:
    """
    Central registry for all versioned prompt templates.
    Loads from YAML files. Prompts are code - version them!
    """
    
    _templates: Dict[str, Dict] = {}
    _templates_dir = Path(__file__).parent / "templates"
    
    @classmethod
    def load_all(cls) -> None:
        """Load all prompt templates from disk at startup."""
        count = 0
        for yaml_file in cls._templates_dir.rglob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            
            key = cls._make_key(data["name"], data["version"])
            cls._templates[key] = data
            count += 1
            
        logger.info("Prompt registry loaded", template_count=count)
    
    @classmethod
    def get(cls, name: str, version: str = "latest") -> Dict:
        """Retrieve a prompt template by name and version."""
        if version == "latest":
            # Find highest version
            matching = [
                (k, v) for k, v in cls._templates.items() 
                if v["name"] == name
            ]
            if not matching:
                raise KeyError(f"No prompt template found with name: {name}")
            # Sort by version and return latest
            latest = sorted(matching, key=lambda x: x[1]["version"])[-1]
            return latest[1]
        
        key = cls._make_key(name, version)
        if key not in cls._templates:
            raise KeyError(f"Prompt template not found: {name} v{version}")
        return cls._templates[key]
    
    @classmethod
    def list_all(cls) -> list[Dict]:
        """List all registered prompts with metadata."""
        return [
            {"name": v["name"], "version": v["version"], "description": v.get("description", "")}
            for v in cls._templates.values()
        ]
    
    @staticmethod
    def _make_key(name: str, version: str) -> str:
        return f"{name}:{version}"
```

```yaml
# app/prompts/templates/system/document_agent_v2.yaml
name: document_agent_system
version: "2.0"
description: "System prompt for the document AI agent - v2 with improved citation instructions"
author: "AI Team"
created_at: "2024-01-15"

template: |
  You are an expert enterprise AI assistant for {company_name}.
  Your job is to help employees find information from company documents accurately and efficiently.

  ## Your Capabilities
  You have access to the following tools:
  - **DocumentSearchTool**: Search through indexed company documents
  - **CalculatorTool**: Perform mathematical calculations  
  - **MetadataSearchTool**: Find documents by metadata (date, author, type)

  ## Response Guidelines
  1. **Always ground responses in documents**: Only state facts found in the retrieved context
  2. **Always cite sources**: Use [1], [2], [3] notation referring to retrieved chunks
  3. **Be concise and precise**: Answer the question directly, then provide supporting detail
  4. **Acknowledge limitations**: If the answer is not in the documents, say so clearly
  5. **Never hallucinate**: If you don't find relevant information, say "I could not find information about this in the company documents"

  ## Citation Format
  When referencing information, always include inline citations like:
  "The policy states that employees receive 20 days of annual leave [1, p.5]."

  ## Current Date
  {current_date}

variables:
  - company_name
  - current_date

changelog:
  "2.0": "Added explicit citation format instructions, improved tool descriptions"
  "1.0": "Initial version"
```

```python
# app/prompts/builder.py
from datetime import datetime
from app.prompts.registry import PromptRegistry
from app.llm.base import LLMMessage

class PromptBuilder:
    """
    Assembles complete prompts from registry templates.
    Handles variable injection, context insertion, and message formatting.
    """
    
    def __init__(self, registry: PromptRegistry):
        self.registry = registry
    
    def build_rag_prompt(
        self,
        query: str,
        context_chunks: list[dict],
        conversation_history: list[LLMMessage],
        company_name: str = "Our Company",
        prompt_version: str = "latest",
    ) -> list[LLMMessage]:
        """Build a complete RAG prompt with context and history."""
        
        # Get system prompt from registry
        system_template = self.registry.get("document_agent_system", prompt_version)
        system_content = system_template["template"].format(
            company_name=company_name,
            current_date=datetime.now().strftime("%B %d, %Y"),
        )
        
        # Get RAG context template
        rag_template = self.registry.get("rag_context", "latest")
        
        # Format context chunks with citation numbers
        formatted_context = self._format_context(context_chunks)
        
        context_content = rag_template["template"].format(
            context=formatted_context,
            query=query,
        )
        
        messages = [
            LLMMessage(role="system", content=system_content),
        ]
        
        # Add conversation history (last N turns)
        max_history_turns = 5
        if conversation_history:
            recent_history = conversation_history[-(max_history_turns * 2):]
            messages.extend(recent_history)
        
        # Add current query with context
        messages.append(LLMMessage(role="user", content=context_content))
        
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

### Deliverables
- ✅ `GeminiProvider` - full implementation with streaming
- ✅ `BedrockProvider` - full implementation with streaming
- ✅ `LLMProviderFactory` - config-driven provider selection
- ✅ `EmbeddingProvider` abstract base
- ✅ Gemini + Bedrock Titan embedding implementations
- ✅ Embedding factory
- ✅ `PromptRegistry` with YAML loading
- ✅ Prompt versioning system
- ✅ `PromptBuilder` with variable injection
- ✅ 5 versioned YAML prompt templates
- ✅ Stream adapter (normalize streaming across providers)
- ✅ Provider switching with **zero business logic changes**

---

## PHASE 4: Chat / Retrieval Pipeline
**Duration: 2.5 hours | Day 2, Morning**

### Objective
Build the complete chat pipeline with semantic retrieval, context construction, RAG generation, streaming SSE responses, citations, and conversation memory.

### Features Implemented
- Query processing + enhancement
- Semantic retrieval from Qdrant
- Multi-stage retrieval (dense search + reranking)
- Context construction with token budget
- Citation extraction and formatting
- Streaming SSE responses with EventSourceResponse
- Conversation memory (Redis-backed)
- Input sanitization
- Session management
- Retrieval service with configurable top-k

### APIs Delivered
```
POST  /api/v1/chat              → Single-shot chat (complete response)
POST  /api/v1/chat/stream       → Streaming chat (SSE)
GET   /api/v1/chat/sessions     → List chat sessions
DELETE /api/v1/chat/sessions/{id} → Clear session memory
GET   /api/v1/chat/sessions/{id}/history → Get conversation history
```

### Key Files Created

```python
# app/services/retrieval_service.py
import structlog
from opentelemetry import trace

from app.repositories.vector_repository import VectorRepository
from app.embeddings.base import EmbeddingProvider
from app.models.chunk import RetrievedChunk
from app.config.settings import Settings
from app.utils.retry import async_retry

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

class RetrievalService:
    """
    Handles semantic document retrieval.
    Implements multi-stage retrieval: embed → search → rerank.
    """
    
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_repo: VectorRepository,
        settings: Settings,
    ):
        self.embedding_provider = embedding_provider
        self.vector_repo = vector_repo
        self.top_k = settings.retrieval_top_k
        self.score_threshold = settings.retrieval_score_threshold
    
    @async_retry(max_attempts=2)
    async def retrieve(
        self, 
        query: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve relevant chunks for a query.
        
        Args:
            query: Natural language query
            document_ids: Optional filter to specific documents
            top_k: Override default top-k retrieval count
        """
        with tracer.start_as_current_span("retrieve_documents") as span:
            span.set_attribute("query_length", len(query))
            
            effective_top_k = top_k or self.top_k
            
            # Step 1: Embed the query
            with tracer.start_as_current_span("embed_query"):
                query_vector = await self.embedding_provider.embed(query)
            
            # Step 2: Search Qdrant
            with tracer.start_as_current_span("vector_search"):
                raw_results = await self.vector_repo.search(
                    query_vector=query_vector,
                    top_k=effective_top_k * 3,  # Over-retrieve for reranking
                    document_ids=document_ids,
                    score_threshold=self.score_threshold,
                )
            
            logger.info(
                "Retrieved candidates",
                candidate_count=len(raw_results),
                query_preview=query[:50],
            )
            
            if not raw_results:
                return []
            
            # Step 3: Rerank (simple score-based for now, 
            # plug in cross-encoder here for production)
            reranked = self._rerank(raw_results, effective_top_k)
            
            span.set_attribute("final_chunk_count", len(reranked))
            return reranked
    
    def _rerank(
        self, 
        chunks: list[RetrievedChunk], 
        top_k: int
    ) -> list[RetrievedChunk]:
        """
        Rerank retrieved chunks.
        Currently uses similarity score. 
        Production upgrade: add cross-encoder model.
        """
        # Sort by score descending, remove near-duplicates
        sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)
        
        deduplicated = self._deduplicate(sorted_chunks)
        
        return deduplicated[:top_k]
    
    def _deduplicate(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Remove chunks with >90% content overlap."""
        seen_content = []
        unique_chunks = []
        
        for chunk in chunks:
            is_duplicate = any(
                self._content_overlap(chunk.content, seen) > 0.9
                for seen in seen_content
            )
            if not is_duplicate:
                unique_chunks.append(chunk)
                seen_content.append(chunk.content)
        
        return unique_chunks
    
    @staticmethod
    def _content_overlap(text1: str, text2: str) -> float:
        """Simple Jaccard similarity for deduplication."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)
```

```python
# app/services/streaming_service.py
import json
import asyncio
from typing import AsyncGenerator
from enum import Enum
import structlog

logger = structlog.get_logger()

class SSEEventType(str, Enum):
    START = "start"
    TOKEN = "token"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    CITATIONS = "citations"
    DONE = "done"
    ERROR = "error"

class StreamingService:
    """
    Manages Server-Sent Events streaming.
    Normalizes all async generators into SSE format.
    """
    
    @staticmethod
    def format_sse_event(event_type: SSEEventType, data: dict) -> str:
        """Format a single SSE event string."""
        payload = json.dumps({"type": event_type.value, **data})
        return f"data: {payload}\n\n"
    
    @staticmethod
    async def stream_chat_response(
        token_generator: AsyncGenerator[str, None],
        citations: list[dict],
        request_id: str,
        session_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Convert token stream to SSE events.
        
        SSE Protocol:
            data: {"type": "start", "request_id": "..."}
            data: {"type": "token", "content": "Hello"}
            data: {"type": "token", "content": " World"}
            data: {"type": "citations", "data": [...]}
            data: {"type": "done", "usage": {...}}
        """
        # Send start event
        yield StreamingService.format_sse_event(
            SSEEventType.START,
            {"request_id": request_id, "session_id": session_id}
        )
        
        total_tokens = 0
        full_response = []
        
        try:
            async for token in token_generator:
                if token:
                    full_response.append(token)
                    total_tokens += 1
                    yield StreamingService.format_sse_event(
                        SSEEventType.TOKEN,
                        {"content": token}
                    )
                    # Small yield to prevent blocking event loop
                    await asyncio.sleep(0)
        
        except asyncio.CancelledError:
            logger.info("Stream cancelled by client", request_id=request_id)
            return
        
        except Exception as e:
            logger.error("Stream error", error=str(e), request_id=request_id)
            yield StreamingService.format_sse_event(
                SSEEventType.ERROR,
                {"message": "An error occurred during generation"}
            )
            return
        
        # Send citations after full response
        if citations:
            yield StreamingService.format_sse_event(
                SSEEventType.CITATIONS,
                {"data": citations}
            )
        
        # Send completion event
        yield StreamingService.format_sse_event(
            SSEEventType.DONE,
            {
                "total_tokens": total_tokens,
                "answer_length": len("".join(full_response)),
            }
        )
        
        # SSE stream terminator
        yield "data: [DONE]\n\n"
```

```python
# app/api/v1/routers/chat.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from app.api.schemas.chat import (
    ChatRequest, ChatResponse, StreamChatRequest
)
from app.services.chat_service import ChatService
from app.api.v1.dependencies import get_chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    req: Request,
    service: ChatService = Depends(get_chat_service),
):
    """
    Single-shot chat endpoint.
    Returns complete response after generation finishes.
    Use /stream for real-time token streaming.
    """
    request_id = req.headers.get("X-Request-ID", "")
    return await service.chat(request, request_id=request_id)

@router.post("/stream")
async def stream_chat(
    request: StreamChatRequest,
    req: Request,
    service: ChatService = Depends(get_chat_service),
):
    """
    Streaming chat endpoint via Server-Sent Events.
    
    Connect with EventSource in JavaScript:
        const es = new EventSource('/api/v1/chat/stream');
    
    Or with fetch + ReadableStream for POST:
        const response = await fetch('/api/v1/chat/stream', {
            method: 'POST',
            body: JSON.stringify({query: '...', session_id: '...'})
        });
    """
    request_id = req.headers.get("X-Request-ID", "")
    
    stream_generator = await service.stream_chat(request, request_id=request_id)
    
    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable NGINX buffering
            "Connection": "keep-alive",
            "X-Request-ID": request_id,
        }
    )

@router.delete("/sessions/{session_id}", status_code=204)
async def clear_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
):
    """Clear conversation memory for a session."""
    await service.clear_session(session_id)
```

```python
# app/api/schemas/chat.py
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    document_ids: list[str] | None = Field(default=None, description="Filter to specific docs")
    stream: bool = False
    
    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        # Basic injection prevention
        dangerous_patterns = ["<script>", "javascript:", "data:"]
        for pattern in dangerous_patterns:
            if pattern.lower() in v.lower():
                raise ValueError("Invalid characters in query")
        return v.strip()

class StreamChatRequest(ChatRequest):
    stream: bool = True

class CitationSource(BaseModel):
    citation_number: int
    document_id: str
    filename: str
    page_number: int
    content_preview: str
    relevance_score: float

class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    answer: str
    citations: list[CitationSource]
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    retrieval_count: int
    processing_time_ms: float
    
class ToolExecutionLog(BaseModel):
    tool_name: str
    input: dict
    output_preview: str
    execution_time_ms: float
```

### Deliverables
- ✅ `RetrievalService` with multi-stage retrieval
- ✅ `ChatService` orchestrating full pipeline
- ✅ `StreamingService` with SSE event formatting
- ✅ `CitationService` with extraction and formatting
- ✅ `MemoryService` with Redis-backed conversation history
- ✅ Chat + streaming chat endpoints
- ✅ Session management (create, list, clear)
- ✅ `ChatRequest`/`ChatResponse` Pydantic v2 schemas
- ✅ Input sanitization
- ✅ Conversation history with configurable window

---

## PHASE 5: AI Agent Implementation
**Duration: 2 hours | Day 2, Late Morning**

### Objective
Build the modular ReAct Agent with pluggable tools. The agent intelligently decides which tools to use, executes them, and synthesizes a grounded final answer.

### Features Implemented
- ReAct agent loop (Think → Plan → Act → Observe)
- Tool Registry with dynamic tool registration
- `DocumentSearchTool` (vector search)
- `CalculatorTool` (safe math evaluation)
- `MetadataSearchTool` (document metadata)
- Agent executor with state management
- Max iterations protection
- Agent timeout handling
- Tool call logging and tracing
- Easy tool extension mechanism

### Key Files Created

```python
# app/tools/base_tool.py
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any
import structlog

logger = structlog.get_logger()

class ToolInput(BaseModel):
    """Base class for tool inputs - enables schema generation for LLM."""
    pass

class ToolOutput(BaseModel):
    success: bool
    result: Any
    error: str | None = None
    execution_time_ms: float = 0.0

class BaseTool(ABC):
    """
    Abstract base for all agent tools.
    New tools: subclass this, implement name/description/schema/execute.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier."""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for LLM tool selection."""
        ...
    
    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema for tool input validation."""
        ...
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolOutput:
        """Execute the tool with given arguments."""
        ...
    
    def to_llm_tool_schema(self) -> dict:
        """Convert to LLM-compatible tool definition (OpenAI/Anthropic format)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
```

```python
# app/tools/tool_registry.py
from app.tools.base_tool import BaseTool
import structlog

logger = structlog.get_logger()

class ToolRegistry:
    """
    Central registry for all agent tools.
    Register once, use anywhere. Easy to extend.
    """
    
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises if name already taken."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.info("Tool registered", tool_name=tool.name)
    
    def get(self, name: str) -> BaseTool:
        """Get a tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found. Available: {self.list_names()}")
        return self._tools[name]
    
    def list_all(self) -> list[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def to_llm_schemas(self) -> list[dict]:
        """Get all tools as LLM-compatible schemas for tool calling."""
        return [tool.to_llm_tool_schema() for tool in self._tools.values()]
```

```python
# app/tools/document_search_tool.py
import time
from app.tools.base_tool import BaseTool, ToolOutput
from app.services.retrieval_service import RetrievalService
import structlog

logger = structlog.get_logger()

class DocumentSearchTool(BaseTool):
    """
    Searches company documents using semantic similarity.
    Primary tool for answering document-based questions.
    """
    
    def __init__(self, retrieval_service: RetrievalService):
        self._retrieval_service = retrieval_service
    
    @property
    def name(self) -> str:
        return "document_search"
    
    @property
    def description(self) -> str:
        return (
            "Search through company documents to find relevant information. "
            "Use this when the user asks about company policies, procedures, "
            "contracts, reports, or any information that would be in a document. "
            "Input: a search query as a string."
        )
    
    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant documents",
                },
                "document_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: filter to specific document IDs",
                },
            },
            "required": ["query"],
        }
    
    async def execute(self, query: str, document_ids: list[str] | None = None) -> ToolOutput:
        start_time = time.monotonic()
        
        try:
            chunks = await self._retrieval_service.retrieve(
                query=query,
                document_ids=document_ids,
            )
            
            # Format chunks for agent consumption
            results = [
                {
                    "content": chunk.content,
                    "source": chunk.filename,
                    "page": chunk.page_number,
                    "score": round(chunk.score, 3),
                    "chunk_id": chunk.chunk_id,
                }
                for chunk in chunks
            ]
            
            elapsed = (time.monotonic() - start_time) * 1000
            
            return ToolOutput(
                success=True,
                result={
                    "chunks": results,
                    "total_found": len(results),
                    "query": query,
                },
                execution_time_ms=elapsed,
            )
        
        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.error("DocumentSearchTool failed", error=str(e))
            return ToolOutput(
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=elapsed,
            )
```

```python
# app/tools/calculator_tool.py
import ast
import time
import operator
from app.tools.base_tool import BaseTool, ToolOutput

class CalculatorTool(BaseTool):
    """
    Safe mathematical calculator.
    No code execution - uses AST evaluation with whitelisted operations.
    """
    
    # Whitelist of safe operators
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }
    
    @property
    def name(self) -> str:
        return "calculator"
    
    @property
    def description(self) -> str:
        return (
            "Performs mathematical calculations safely. "
            "Use this when you need to add, subtract, multiply, divide, "
            "or perform any arithmetic on numbers found in documents. "
            "Input: a mathematical expression as a string (e.g., '2.5 + 1.8 * 3')."
        )
    
    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                }
            },
            "required": ["expression"],
        }
    
    async def execute(self, expression: str) -> ToolOutput:
        start_time = time.monotonic()
        
        try:
            result = self._safe_eval(expression)
            elapsed = (time.monotonic() - start_time) * 1000
            
            return ToolOutput(
                success=True,
                result={
                    "expression": expression,
                    "result": result,
                    "formatted": f"{expression} = {result}",
                },
                execution_time_ms=elapsed,
            )
        
        except (ValueError, ZeroDivisionError) as e:
            elapsed = (time.monotonic() - start_time) * 1000
            return ToolOutput(
                success=False,
                result=None,
                error=f"Calculation error: {str(e)}",
                execution_time_ms=elapsed,
            )
    
    def _safe_eval(self, expression: str) -> float:
        """Evaluate math expression using AST - no exec/eval."""
        try:
            tree = ast.parse(expression, mode='eval')
            return self._eval_node(tree.body)
        except Exception:
            raise ValueError(f"Invalid expression: {expression}")
    
    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self.SAFE_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._eval_node(node.operand)
        else:
            raise ValueError(f"Unsupported expression type: {type(node)}")
```

```python
# app/agents/document_agent.py
import asyncio
import json
import structlog
from opentelemetry import trace

from app.llm.base import LLMProvider, LLMRequest, LLMMessage
from app.tools.tool_registry import ToolRegistry
from app.prompts.builder import PromptBuilder
from app.models.conversation import ConversationHistory
from app.config.settings import Settings

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

class AgentState:
    """Tracks agent execution state through the ReAct loop."""
    
    def __init__(self, query: str, session_id: str):
        self.query = query
        self.session_id = session_id
        self.iterations = 0
        self.observations: list[dict] = []
        self.tool_calls_log: list[dict] = []
        self.final_answer: str | None = None
        self.citations: list[dict] = []

class DocumentAgent:
    """
    ReAct agent for company document Q&A.
    
    ReAct Loop:
    1. THINK: Analyze query, determine what's needed
    2. ACT: Select and call appropriate tool
    3. OBSERVE: Process tool result
    4. Repeat until sufficient info collected
    5. SYNTHESIZE: Generate final grounded answer
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        prompt_builder: PromptBuilder,
        settings: Settings,
    ):
        self.llm = llm_provider
        self.tools = tool_registry
        self.prompt_builder = prompt_builder
        self.max_iterations = settings.agent_max_iterations
        self.timeout = settings.agent_timeout_seconds
    
    async def run(
        self,
        query: str,
        session_id: str,
        conversation_history: list[LLMMessage],
        stream: bool = False,
    ) -> AgentState:
        """
        Execute the full agent loop.
        Returns AgentState with final answer and citations.
        """
        state = AgentState(query=query, session_id=session_id)
        log = logger.bind(session_id=session_id, query_preview=query[:50])
        
        with tracer.start_as_current_span("agent_run") as span:
            span.set_attribute("session_id", session_id)
            
            try:
                async with asyncio.timeout(self.timeout):
                    await self._react_loop(state, conversation_history, log, stream)
            
            except asyncio.TimeoutError:
                log.warning("Agent timed out", timeout_seconds=self.timeout)
                state.final_answer = (
                    "I'm sorry, I couldn't complete the research in time. "
                    "Please try a more specific question."
                )
            
            except Exception as e:
                log.error("Agent error", error=str(e), exc_info=True)
                state.final_answer = (
                    "I encountered an error while processing your question. "
                    "Please try again."
                )
        
        return state
    
    async def _react_loop(
        self,
        state: AgentState,
        history: list[LLMMessage],
        log,
        stream: bool,
    ) -> None:
        """Execute the ReAct reasoning loop."""
        
        while state.iterations < self.max_iterations:
            state.iterations += 1
            log.debug("Agent iteration", iteration=state.iterations)
            
            # Build reasoning prompt
            reasoning_messages = self._build_reasoning_prompt(state, history)
            
            # Call LLM to decide next action
            with tracer.start_as_current_span("agent_reasoning"):
                response = await self.llm.generate(LLMRequest(
                    messages=reasoning_messages,
                    max_tokens=1024,
                    temperature=0.1,
                    tools=self.tools.to_llm_schemas(),
                ))
            
            # Parse agent decision
            decision = self._parse_agent_decision(response.content)
            
            if decision["type"] == "final_answer":
                state.final_answer = decision["content"]
                state.citations = self._extract_citations(
                    decision["content"], 
                    state.observations
                )
                log.info("Agent reached final answer", iterations=state.iterations)
                return
            
            elif decision["type"] == "tool_call":
                tool_name = decision["tool"]
                tool_args = decision["args"]
                
                log.info("Agent calling tool", tool=tool_name, args=tool_args)
                
                # Execute tool
                with tracer.start_as_current_span(f"tool_{tool_name}"):
                    try:
                        tool = self.tools.get(tool_name)
                        result = await tool.execute(**tool_args)
                        
                        state.observations.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result.result,
                            "success": result.success,
                            "error": result.error,
                        })
                        
                        state.tool_calls_log.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "execution_time_ms": result.execution_time_ms,
                            "success": result.success,
                        })
                        
                    except KeyError:
                        log.warning("Unknown tool requested", tool=tool_name)
                        state.observations.append({
                            "tool": tool_name,
                            "error": f"Tool '{tool_name}' not available",
                        })
        
        # Max iterations reached - synthesize with what we have
        log.warning("Max iterations reached, synthesizing partial answer")
        state.final_answer = await self._synthesize_final_answer(state, history)
    
    def _build_reasoning_prompt(
        self, 
        state: AgentState,
        history: list[LLMMessage],
    ) -> list[LLMMessage]:
        """Build the agent reasoning prompt with all observations so far."""
        
        system_prompt = self.prompt_builder.registry.get("document_agent_system")
        
        # Build observation context
        observation_text = ""
        if state.observations:
            observation_text = "\n\n## Previous Tool Results:\n"
            for i, obs in enumerate(state.observations, 1):
                observation_text += f"\n**Observation {i}** ({obs['tool']}):\n"
                if obs.get("success"):
                    observation_text += json.dumps(obs["result"], indent=2)
                else:
                    observation_text += f"Error: {obs.get('error', 'Unknown error')}"
        
        user_content = f"""
User Question: {state.query}
{observation_text}

Based on the question and observations above, decide your next action:
- If you have enough information, provide a final answer with citations
- If you need more information, call an appropriate tool

Available tools: {', '.join(self.tools.list_names())}
        """.strip()
        
        messages = [
            LLMMessage(role="system", content=system_prompt["template"]),
        ]
        
        # Add limited history
        if history:
            messages.extend(history[-4:])  # Last 2 turns
        
        messages.append(LLMMessage(role="user", content=user_content))
        return messages
    
    def _parse_agent_decision(self, response: str) -> dict:
        """
        Parse LLM response to determine if it's a tool call or final answer.
        LangChain handles structured output; this is the simplified version.
        """
        # Look for tool call pattern
        if "TOOL_CALL:" in response:
            try:
                tool_section = response.split("TOOL_CALL:")[1].strip()
                tool_data = json.loads(tool_section)
                return {
                    "type": "tool_call",
                    "tool": tool_data["tool"],
                    "args": tool_data["args"],
                }
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Default: treat as final answer
        return {"type": "final_answer", "content": response}
    
    def _extract_citations(self, answer: str, observations: list[dict]) -> list[dict]:
        """Extract citation references from answer and map to sources."""
        import re
        citations = []
        citation_nums = re.findall(r'\[(\d+)\]', answer)
        
        # Get all document chunks from observations
        all_chunks = []
        for obs in observations:
            if obs.get("tool") == "document_search" and obs.get("success"):
                chunks = obs["result"].get("chunks", [])
                all_chunks.extend(chunks)
        
        for num_str in set(citation_nums):
            num = int(num_str) - 1
            if 0 <= num < len(all_chunks):
                chunk = all_chunks[num]
                citations.append({
                    "citation_number": int(num_str),
                    "source": chunk.get("source", "Unknown"),
                    "page": chunk.get("page", 0),
                    "content_preview": chunk.get("content", "")[:200],
                    "score": chunk.get("score", 0.0),
                })
        
        return citations
    
    async def _synthesize_final_answer(
        self, 
        state: AgentState,
        history: list[LLMMessage],
    ) -> str:
        """Synthesize final answer when max iterations reached."""
        synthesis_prompt = self.prompt_builder.registry.get("synthesis")
        messages = self._build_reasoning_prompt(state, history)
        messages[-1].content += "\n\nPlease provide your best answer with the information gathered."
        
        response = await self.llm.generate(LLMRequest(
            messages=messages,
            max_tokens=2048,
            temperature=0.1,
        ))
        return response.content
```

### Deliverables
- ✅ `DocumentAgent` with full ReAct loop
- ✅ `AgentState` for execution tracking
- ✅ `ToolRegistry` with dynamic registration
- ✅ `DocumentSearchTool` with vector retrieval
- ✅ `CalculatorTool` with safe AST evaluation
- ✅ `MetadataSearchTool` for document discovery
- ✅ Agent timeout protection
- ✅ Max iterations guard
- ✅ Tool call logging and tracing
- ✅ Citation extraction from agent observations
- ✅ Easy `BaseTool` extension pattern for future tools

---

## PHASE 6: Observability & Production Hardening
**Duration: 1.5 hours | Day 2, Afternoon**

### Objective
Add production-grade observability, error handling, and hardening. Every request must be traceable, every error classifiable, every metric measurable.

### Features Implemented
- OpenTelemetry distributed tracing across all components
- Structured JSON logging with correlation IDs
- Prometheus metrics (request count, latency, token usage, retrieval scores)
- Grafana dashboards
- Detailed health checks (liveness + readiness + deep)
- Error classification (transient vs permanent, provider vs app)
- Global exception handler
- Request ID + Correlation ID propagation
- Request timing middleware
- Circuit breaker pattern (basic)
- Rate limiting middleware

### Key Files Created

```python
# app/observability/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION

def setup_tracing(service_name: str, service_version: str, otlp_endpoint: str) -> None:
    """
    Initialize OpenTelemetry distributed tracing.
    Traces flow across all services: FastAPI → Agent → Tools → LLM → DB.
    """
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": "production",
    })
    
    provider = TracerProvider(resource=resource)
    
    # Export to Jaeger via OTLP
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    trace.set_tracer_provider(provider)
    
    # Auto-instrument FastAPI
    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
```

```python
# app/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import time

REGISTRY = CollectorRegistry()

# Request metrics
request_counter = Counter(
    "docai_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

request_duration = Histogram(
    "docai_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

# LLM metrics
llm_token_counter = Counter(
    "docai_llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "model", "type"],  # type: input/output
    registry=REGISTRY,
)

llm_latency = Histogram(
    "docai_llm_latency_seconds",
    "LLM API call latency",
    ["provider", "model"],
    registry=REGISTRY,
)

# Ingestion metrics
ingestion_counter = Counter(
    "docai_ingestion_total",
    "Document ingestion attempts",
    ["status"],  # success/error
    registry=REGISTRY,
)

ingestion_duration = Histogram(
    "docai_ingestion_duration_seconds",
    "Document ingestion pipeline duration",
    registry=REGISTRY,
)

# Retrieval metrics
retrieval_score = Histogram(
    "docai_retrieval_score",
    "Vector similarity scores for retrieved chunks",
    buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0],
    registry=REGISTRY,
)

retrieval_count = Histogram(
    "docai_retrieval_count",
    "Number of chunks retrieved per query",
    buckets=[0, 1, 2, 3, 5, 10],
    registry=REGISTRY,
)

# Active streams
active_streams = Gauge(
    "docai_active_streams",
    "Currently active SSE streams",
    registry=REGISTRY,
)
```

```python
# app/middleware/error_handler.py
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import structlog
import uuid

logger = structlog.get_logger()

class ErrorClassifier:
    """
    Classify exceptions for appropriate handling.
    Different error types deserve different responses and retry strategies.
    """
    
    TRANSIENT_PATTERNS = [
        "timeout", "rate limit", "429", "503", "502", "connection",
        "throttling", "too many requests",
    ]
    
    PROVIDER_ERROR_PATTERNS = [
        "gemini", "bedrock", "openai", "anthropic",
        "google", "aws", "api key",
    ]
    
    @classmethod
    def classify(cls, error: Exception) -> dict:
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        is_transient = any(p in error_str for p in cls.TRANSIENT_PATTERNS)
        is_provider = any(p in error_str for p in cls.PROVIDER_ERROR_PATTERNS)
        
        return {
            "error_type": error_type,
            "is_transient": is_transient,
            "is_provider_error": is_provider,
            "is_client_error": isinstance(error, (ValueError, TypeError)),
            "retry_recommended": is_transient,
        }

async def global_exception_handler(request: Request, exc: Exception) -> Response:
    """Global exception handler - catches all unhandled exceptions."""
    
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    classification = ErrorClassifier.classify(exc)
    
    logger.error(
        "Unhandled exception",
        request_id=request_id,
        error_type=classification["error_type"],
        error_message=str(exc),
        path=str(request.url),
        is_transient=classification["is_transient"],
        exc_info=True,
    )
    
    # Determine HTTP status code
    if classification["is_client_error"]:
        status_code = 400
    elif classification["is_transient"]:
        status_code = 503
    elif classification["is_provider_error"]:
        status_code = 502
    else:
        status_code = 500
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "request_id": request_id,
                "message": "An error occurred processing your request",
                "error_type": classification["error_type"],
                "retry_recommended": classification["retry_recommended"],
                "support_reference": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )
```

```python
# app/observability/health.py
from dataclasses import dataclass
from enum import Enum
import asyncio
import time

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: float
    details: dict

class HealthChecker:
    """
    Comprehensive health checking for all system components.
    Readiness = all critical components healthy.
    Liveness = application is running (basic).
    """
    
    def __init__(self, qdrant_client, redis_client, db_session, llm_provider):
        self.qdrant = qdrant_client
        self.redis = redis_client
        self.db = db_session
        self.llm = llm_provider
    
    async def check_all(self) -> dict:
        """Run all health checks concurrently."""
        checks = await asyncio.gather(
            self._check_qdrant(),
            self._check_redis(),
            self._check_database(),
            self._check_llm_provider(),
            return_exceptions=True,
        )
        
        components = []
        all_healthy = True
        
        for check in checks:
            if isinstance(check, Exception):
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=0,
                    details={"error": str(check)},
                ))
                all_healthy = False
            else:
                components.append(check)
                if check.status != HealthStatus.HEALTHY:
                    all_healthy = False
        
        overall = HealthStatus.HEALTHY if all_healthy else HealthStatus.UNHEALTHY
        
        return {
            "status": overall.value,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "details": c.details,
                }
                for c in components
            ],
        }
    
    async def _check_qdrant(self) -> ComponentHealth:
        start = time.monotonic()
        try:
            info = await self.qdrant.get_cluster_info()
            return ComponentHealth(
                name="qdrant",
                status=HealthStatus.HEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"status": "connected"},
            )
        except Exception as e:
            return ComponentHealth(
                name="qdrant",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"error": str(e)},
            )
    
    async def _check_redis(self) -> ComponentHealth:
        start = time.monotonic()
        try:
            await self.redis.ping()
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"status": "connected"},
            )
        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"error": str(e)},
            )
    
    async def _check_database(self) -> ComponentHealth:
        start = time.monotonic()
        try:
            await self.db.execute("SELECT 1")
            return ComponentHealth(
                name="postgresql",
                status=HealthStatus.HEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"status": "connected"},
            )
        except Exception as e:
            return ComponentHealth(
                name="postgresql",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"error": str(e)},
            )
    
    async def _check_llm_provider(self) -> ComponentHealth:
        start = time.monotonic()
        try:
            is_healthy = await self.llm.health_check()
            return ComponentHealth(
                name=f"llm_provider_{self.llm.get_model_id()}",
                status=HealthStatus.HEALTHY if is_healthy else HealthStatus.DEGRADED,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"model": self.llm.get_model_id()},
            )
        except Exception as e:
            return ComponentHealth(
                name="llm_provider",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                details={"error": str(e)},
            )
```

### Deliverables
- ✅ OpenTelemetry setup with OTLP exporter to Jaeger
- ✅ FastAPI + HTTPx auto-instrumentation
- ✅ Structured logging with correlation ID propagation
- ✅ 8 Prometheus metrics (request, LLM, ingestion, retrieval)
- ✅ `HealthChecker` with 4 component checks
- ✅ `ErrorClassifier` with error categorization
- ✅ Global exception handler with proper HTTP status mapping
- ✅ Rate limiting middleware
- ✅ Request timing middleware
- ✅ Detailed health endpoints

---

## PHASE 7: Containerization & AWS Deployment
**Duration: 2 hours | Day 2, Evening**

### Objective
Package the application for production deployment on AWS with Docker, configure Amazon Bedrock as the production LLM provider, and establish the deployment pipeline.

### Features Implemented
- Multi-stage production Dockerfile
- Docker Compose for local development
- Amazon Bedrock integration (Claude 3 + Titan Embeddings)
- AWS ECS Fargate task definition
- Environment-based configuration switch
- AWS Secrets Manager integration
- Production `.env` templates
- Health check scripts
- Production readiness verification

### Key Files Created

```dockerfile
# docker/Dockerfile
# ============================================
# Stage 1: Builder - install dependencies
# ============================================
FROM python:3.12-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================
# Stage 2: Production image - minimal size
# ============================================
FROM python:3.12-slim as production

# Security: create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add user's local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# Production: use gunicorn with uvicorn workers
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

```python
# app/main.py - Application factory
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import Settings
from app.observability.logging import setup_logging
from app.observability.tracing import setup_tracing
from app.observability.metrics import REGISTRY
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.correlation_id import CorrelationIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.middleware.error_handler import global_exception_handler
from app.api.v1.routers import documents, chat, health, metrics
from app.prompts.registry import PromptRegistry
from app.vector_db.client import init_qdrant_client
from app.vector_db.collections import ensure_collections_exist

settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    
    # ── Startup ──────────────────────────────────────
    setup_logging(level=settings.log_level)
    setup_tracing(
        service_name=settings.app_name,
        service_version=settings.app_version,
        otlp_endpoint=settings.otel_endpoint,
    )
    
    # Load all prompt templates
    PromptRegistry.load_all()
    
    # Initialize vector DB
    qdrant_client = await init_qdrant_client(settings)
    await ensure_collections_exist(qdrant_client, settings)
    
    # Store in app state for dependency injection
    app.state.settings = settings
    app.state.qdrant_client = qdrant_client
    
    yield
    
    # ── Shutdown ─────────────────────────────────────
    await qdrant_client.close()

def create_app() -> FastAPI:
    app = FastAPI(
        title="Company Document AI Agent",
        version=settings.app_version,
        description="Enterprise AI assistant for company document Q&A",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    
    # Middleware (order matters - outer → inner)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TimingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(RequestIDMiddleware)
    
    # Exception handler
    app.add_exception_handler(Exception, global_exception_handler)
    
    # Routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(metrics.router)
    
    return app

app = create_app()
```

```bash
# .env.development
# Development environment - uses Gemini

ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# LLM Provider: gemini for development
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=models/text-embedding-004

# Infrastructure (Docker Compose defaults)
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql+asyncpg://user:password@localhost/docai

# Storage (MinIO local)
S3_BUCKET=company-documents
S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin

# Observability
OTEL_ENDPOINT=http://localhost:4317

# Feature Flags
ENABLE_STREAMING=true
ENABLE_CITATIONS=true
ENABLE_CONVERSATION_MEMORY=true
ENABLE_HYDE=false
```

```bash
# .env.production
# Production environment - uses Amazon Bedrock

ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# LLM Provider: bedrock for production
# Just change these two lines - ZERO code changes!
LLM_PROVIDER=bedrock
EMBEDDING_PROVIDER=bedrock
BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
AWS_REGION=us-east-1
# No API keys needed! Uses IAM Role attached to ECS Task

# Infrastructure (AWS managed)
QDRANT_HOST=qdrant.internal.company.com
QDRANT_PORT=6333
REDIS_URL=redis://docai-cache.xxx.cache.amazonaws.com:6379
DATABASE_URL=postgresql+asyncpg://user:${DB_PASSWORD}@docai-db.xxx.rds.amazonaws.com/docai

# Storage (Real S3)
S3_BUCKET=company-ai-documents-prod
# S3_ENDPOINT_URL not set = use real AWS S3

# Observability
OTEL_ENDPOINT=http://otel-collector.internal:4317

# Feature Flags
ENABLE_STREAMING=true
ENABLE_CITATIONS=true
ENABLE_CONVERSATION_MEMORY=true
ENABLE_HYDE=true  # Enable in production

# Processing
RETRIEVAL_TOP_K=5
RETRIEVAL_SCORE_THRESHOLD=0.72
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT_SECONDS=45
```

```json
// deploy/aws/ecs-task-definition.json
{
  "family": "document-ai-agent",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/docAITaskRole",
  "containerDefinitions": [
    {
      "name": "document-ai-agent",
      "image": "ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/document-ai-agent:latest",
      "portMappings": [
        {"containerPort": 8000, "protocol": "tcp"}
      ],
      "environment": [
        {"name": "ENVIRONMENT", "value": "production"},
        {"name": "LLM_PROVIDER", "value": "bedrock"},
        {"name": "EMBEDDING_PROVIDER", "value": "bedrock"},
        {"name": "AWS_REGION", "value": "us-east-1"}
      ],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:docai/database-url"
        },
        {
          "name": "REDIS_URL", 
          "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:docai/redis-url"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/document-ai-agent",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

```yaml
# deploy/aws/iam-bedrock-policy.yaml
# IAM Policy to attach to ECS Task Role
# This grants the application access to Bedrock - no API keys needed!

PolicyDocument:
  Version: "2012-10-17"
  Statement:
    - Effect: Allow
      Action:
        - bedrock:InvokeModel
        - bedrock:InvokeModelWithResponseStream
      Resource:
        - "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
        - "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
        - "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    - Effect: Allow
      Action:
        - s3:GetObject
        - s3:PutObject
        - s3:DeleteObject
        - s3:ListBucket
      Resource:
        - "arn:aws:s3:::company-ai-documents-prod"
        - "arn:aws:s3:::company-ai-documents-prod/*"
    - Effect: Allow
      Action:
        - secretsmanager:GetSecretValue
      Resource:
        - "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:docai/*"
```

```makefile
# Makefile - Developer shortcuts
.PHONY: dev test build deploy

# Development
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-down:
	docker compose down -v

# Testing
test:
	pytest tests/unit/ -v --tb=short

test-integration:
	docker compose -f docker-compose.test.yml up -d
	pytest tests/integration/ -v
	docker compose -f docker-compose.test.yml down

test-e2e:
	pytest tests/e2e/ -v

# Build
build:
	docker build -f docker/Dockerfile -t document-ai-agent:latest .

# Setup
setup-qdrant:
	python scripts/setup_qdrant_collections.py

migrate:
	python scripts/migrate_db.py

seed:
	python scripts/seed_data.py

# AWS Deployment
push-ecr:
	aws ecr get-login-password --region us-east-1 | \
	docker login --username AWS --password-stdin $(ECR_URI)
	docker tag document-ai-agent:latest $(ECR_URI)/document-ai-agent:latest
	docker push $(ECR_URI)/document-ai-agent:latest

deploy-ecs:
	aws ecs update-service \
	--cluster docai-cluster \
	--service document-ai-agent \
	--force-new-deployment

# Health check
health:
	curl -s http://localhost:8000/api/v1/health | python -m json.tool

health-ready:
	curl -s http://localhost:8000/api/v1/health/ready | python -m json.tool

# Logs
logs:
	docker compose logs -f app
```

### Deliverables
- ✅ Multi-stage production Dockerfile (< 200MB image)
- ✅ Complete Docker Compose stack (7 services)
- ✅ `.env.development` with Gemini config
- ✅ `.env.production` with Bedrock config (2-line switch)
- ✅ ECS Fargate task definition
- ✅ IAM policy for Bedrock + S3 + Secrets Manager
- ✅ FastAPI application factory with lifespan
- ✅ AWS Secrets Manager integration
- ✅ Makefile with developer shortcuts
- ✅ Production startup verification

---

# 6. API SPECIFICATION

## Complete API Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT ENDPOINTS                            │
├────────────────────────────────────┬────────────┬──────────────┤
│ POST /api/v1/documents/upload      │ 202        │ Upload PDF   │
│ GET  /api/v1/documents             │ 200        │ List docs    │
│ GET  /api/v1/documents/{id}        │ 200        │ Doc details  │
│ DELETE /api/v1/documents/{id}      │ 204        │ Delete doc   │
│ POST /api/v1/documents/{id}/reindex│ 202        │ Re-index     │
│ GET  /api/v1/documents/{id}/status │ 200        │ Job status   │
│ GET  /api/v1/documents/{id}/chunks │ 200        │ List chunks  │
├────────────────────────────────────┼────────────┼──────────────┤
│                    CHAT ENDPOINTS                                │
├────────────────────────────────────┼────────────┼──────────────┤
│ POST /api/v1/chat                  │ 200        │ Chat         │
│ POST /api/v1/chat/stream           │ 200 (SSE)  │ Stream chat  │
│ GET  /api/v1/chat/sessions         │ 200        │ List sessions│
│ GET  /api/v1/chat/sessions/{id}    │ 200        │ Session info │
│ DELETE /api/v1/chat/sessions/{id}  │ 204        │ Clear memory │
│ GET  /api/v1/chat/sessions/{id}/history│ 200   │ History      │
├────────────────────────────────────┼────────────┼──────────────┤
│                 OBSERVABILITY ENDPOINTS                          │
├────────────────────────────────────┼────────────┼──────────────┤
│ GET  /api/v1/health                │ 200        │ Liveness     │
│ GET  /api/v1/health/ready          │ 200/503    │ Readiness    │
│ GET  /api/v1/health/detailed       │ 200        │ Full status  │
│ GET  /metrics                      │ 200        │ Prometheus   │
└────────────────────────────────────┴────────────┴──────────────┘
```

## Request/Response Examples

### Upload Document
```http
POST /api/v1/documents/upload
Content-Type: multipart/form-data
X-Request-ID: req-550e8400-e29b
X-Correlation-ID: corr-f47ac10b

Form:
  file: [Q3_Financial_Report.pdf]

Response 202:
{
  "document_id": "doc-550e8400-e29b-41d4",
  "job_id": "job-f47ac10b-58a2-4e24",
  "filename": "Q3_Financial_Report.pdf",
  "status": "processing",
  "message": "Document queued for indexing. Use job_id to track progress.",
  "estimated_time_seconds": 30,
  "_links": {
    "status": "/api/v1/documents/doc-550e8400/status",
    "document": "/api/v1/documents/doc-550e8400"
  }
}
```

### Job Status Polling
```http
GET /api/v1/documents/doc-550e8400/status

Response 200:
{
  "job_id": "job-f47ac10b",
  "document_id": "doc-550e8400",
  "status": "embedding",
  "progress": 65,
  "current_step": "Generating embeddings for chunks 45-60 of 92",
  "steps_completed": ["validation", "parsing", "chunking"],
  "steps_remaining": ["embedding", "indexing"],
  "started_at": "2024-01-15T10:30:00Z",
  "estimated_completion": "2024-01-15T10:30:45Z"
}
```

### Chat Request
```http
POST /api/v1/chat
Content-Type: application/json
X-Request-ID: req-abc123

{
  "query": "What is our vacation policy for new employees?",
  "session_id": "session-xyz789",
  "document_ids": null,
  "stream": false
}

Response 200:
{
  "request_id": "req-abc123",
  "session_id": "session-xyz789",
  "answer": "According to the Employee Handbook, new employees receive 10 days of annual leave during their first year [1, p.12]. After completing one year of service, this increases to 15 days [1, p.13]. Additionally, all employees receive 5 sick days per year [2, p.3].",
  "citations": [
    {
      "citation_number": 1,
      "document_id": "doc-550e8400",
      "filename": "Employee_Handbook_2024.pdf",
      "page_number": 12,
      "content_preview": "New employees are entitled to 10 days of annual leave...",
      "relevance_score": 0.94
    },
    {
      "citation_number": 2,
      "document_id": "doc-661f9511",
      "filename": "HR_Policies_v3.pdf",
      "page_number": 3,
      "content_preview": "All full-time employees receive 5 sick days...",
      "relevance_score": 0.87
    }
  ],
  "model": "gemini-2.5-flash",
  "provider": "gemini",
  "input_tokens": 1245,
  "output_tokens": 89,
  "retrieval_count": 5,
  "processing_time_ms": 1834.2,
  "tool_calls": [
    {
      "tool_name": "document_search",
      "execution_time_ms": 243.1,
      "success": true
    }
  ]
}
```

### Streaming Chat (SSE)
```http
POST /api/v1/chat/stream
Content-Type: application/json

{
  "query": "Summarize the Q3 financial results",
  "session_id": "session-xyz789",
  "stream": true
}

Response (SSE Stream):
Content-Type: text/event-stream

data: {"type": "start", "request_id": "req-abc123", "session_id": "session-xyz789"}

data: {"type": "tool_start", "tool": "document_search", "query": "Q3 financial results"}

data: {"type": "tool_end", "tool": "document_search", "chunks_found": 5}

data: {"type": "token", "content": "The"}

data: {"type": "token", "content": " Q3"}

data: {"type": "token", "content": " financial"}

data: {"type": "token", "content": " results"}

data: {"type": "token", "content": " show"}

... (more tokens)

data: {"type": "citations", "data": [{"citation_number": 1, "filename": "Q3_Report.pdf", "page": 4}]}

data: {"type": "done", "total_tokens": 312, "processing_time_ms": 2103.5}

data: [DONE]
```

---

# 7. CORE ENGINEERING PATTERNS

## The LLMProvider Switch (The Most Important Pattern)

```
Development Environment:          Production Environment:
┌──────────────────────┐         ┌──────────────────────┐
│ LLM_PROVIDER=gemini  │         │ LLM_PROVIDER=bedrock  │
│ GEMINI_API_KEY=sk-.. │    →    │ AWS_REGION=us-east-1  │
└──────────────────────┘         │ (IAM Role handles auth)│
         ↓                       └──────────────────────┘
  GeminiProvider                          ↓
         ↓                        BedrockProvider
  Both implement LLMProvider              ↓
  Business logic is IDENTICAL    Business logic is IDENTICAL
```

## Dependency Injection Pattern

```python
# app/api/v1/dependencies.py
from functools import lru_cache
from fastapi import Depends, Request
from app.config.settings import Settings
from app.llm.factory import LLMProviderFactory
from app.embeddings.factory import EmbeddingProviderFactory
from app.services.chat_service import ChatService
from app.services.ingestion_service import IngestionService
from app.tools.tool_registry import ToolRegistry
from app.tools.document_search_tool import DocumentSearchTool
from app.tools.calculator_tool import CalculatorTool

# ── Settings (singleton) ──────────────────────────────────────
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

# ── Providers (singleton, expensive to create) ────────────────
@lru_cache(maxsize=1)
def get_llm_provider(settings: Settings = Depends(get_settings)):
    """
    Returns the configured LLM provider.
    Change LLM_PROVIDER env var to switch. No code changes needed.
    """
    return LLMProviderFactory.create(settings)

@lru_cache(maxsize=1)
def get_embedding_provider(settings: Settings = Depends(get_settings)):
    return EmbeddingProviderFactory.create(settings)

# ── Tool Registry ─────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_tool_registry(
    retrieval_service=Depends(get_retrieval_service),
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(DocumentSearchTool(retrieval_service))
    registry.register(CalculatorTool())
    registry.register(MetadataSearchTool(document_repository))
    # Future: registry.register(WebSearchTool())
    # Future: registry.register(CalendarTool())
    return registry

# ── Services (per-request) ────────────────────────────────────
def get_chat_service(
    request: Request,
    llm_provider=Depends(get_llm_provider),
    tool_registry=Depends(get_tool_registry),
    settings=Depends(get_settings),
) -> ChatService:
    """
    Chat service is created per-request with request-scoped dependencies.
    """
    return ChatService(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        qdrant_client=request.app.state.qdrant_client,
        settings=settings,
    )
```

## Prompt Versioning System

```
prompts/templates/
├── system/
│   ├── document_agent_v1.yaml    ← Old version (kept for rollback)
│   └── document_agent_v2.yaml    ← Current version
├── rag/
│   ├── rag_context_v1.yaml       
│   └── rag_context_v2.yaml       ← Improved context format
└── tools/
    ├── tool_selection_v1.yaml
    └── synthesis_v1.yaml

Deployment: Run v1 and v2 simultaneously, A/B test, promote winner
Rollback: Change PROMPT_VERSION=v1 in env, instant rollback
```

---

# 8. DEPLOYMENT STRATEGY

## The Two-Line Environment Switch

```bash
# Development (Friday evening - everything works locally)
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini

# Production (Monday morning - AWS deployment)
LLM_PROVIDER=bedrock          # ← Change this
EMBEDDING_PROVIDER=bedrock    # ← And this
# That's it. Zero code changes.
```

## AWS Deployment Sequence

```bash
# Step 1: Build and push to ECR
make build
make push-ecr ECR_URI=123456789.dkr.ecr.us-east-1.amazonaws.com

# Step 2: Initialize Qdrant collection on EC2
ssh ec2-user@qdrant.internal "python /app/scripts/setup_qdrant_collections.py"

# Step 3: Run database migrations
aws ecs run-task \
  --cluster docai-cluster \
  --task-definition docai-migrate \
  --overrides '{"containerOverrides":[{"name":"app","command":["python","scripts/migrate_db.py"]}]}'

# Step 4: Deploy ECS service
make deploy-ecs

# Step 5: Verify deployment
curl https://api.company.internal/api/v1/health/ready
```

## Bedrock Model Access Setup

```bash
# Request Bedrock model access (one-time setup in AWS Console)
# Navigate to: Amazon Bedrock → Model Access → Request Access
# Models needed:
# - anthropic.claude-3-sonnet-20240229-v1:0
# - anthropic.claude-3-haiku-20240307-v1:0  
# - amazon.titan-embed-text-v2:0

# Verify access via CLI
aws bedrock list-foundation-models \
  --by-provider anthropic \
  --region us-east-1 \
  --query 'modelSummaries[?modelId==`anthropic.claude-3-sonnet-20240229-v1:0`]'
```

---

# 9. PRODUCTION READINESS CHECKLIST

```
✅ ARCHITECTURE
  □ LLMProvider abstraction implemented
  □ EmbeddingProvider abstraction implemented  
  □ Provider switch requires only env var change
  □ Document ingestion pipeline independent from chat
  □ Repository pattern separates data access
  □ Service layer handles all business logic
  □ Dependency injection throughout
  □ No hardcoded configuration values

✅ RELIABILITY
  □ Retry logic with exponential backoff on all external calls
  □ Timeout handling on all async operations
  □ Circuit breaker for LLM provider calls
  □ Background job error recovery + dead letter
  □ Graceful degradation when retrieval returns 0 results
  □ Agent max iterations guard
  □ Agent timeout guard
  □ Input validation on all endpoints
  □ File type + size + corruption validation

✅ OBSERVABILITY
  □ OpenTelemetry traces on all operations
  □ Request ID on every request
  □ Correlation ID propagated across services
  □ Structured JSON logging everywhere
  □ Prometheus metrics exported
  □ Health check (liveness) endpoint
  □ Readiness check (all deps) endpoint
  □ Detailed component health endpoint
  □ Request timing logged

✅ SECURITY
  □ Non-root Docker user
  □ Secrets in AWS Secrets Manager (not env files)
  □ IAM Role for Bedrock (no API keys in production)
  □ Input sanitization on chat queries
  □ File upload validation
  □ CORS configured
  □ Rate limiting middleware
  □ No sensitive data in logs

✅ PERFORMANCE
  □ Async throughout (FastAPI + asyncio)
  □ Batch embedding generation (32 chunks/batch)
  □ Connection pooling for PostgreSQL
  □ Redis caching for session memory
  □ Streaming responses via SSE (no timeout on slow queries)
  □ NGINX buffering disabled for SSE streams
  □ ECS Fargate auto-scaling configured

✅ DEPLOYMENT
  □ Multi-stage Docker build (production image < 200MB)
  □ Docker Compose for local development
  □ ECS task definition with resource limits
  □ CloudWatch log groups configured
  □ Health check in task definition
  □ Secrets Manager integration
  □ ECR image versioning
  □ Rollback procedure documented
  □ Environment-specific .env files

✅ CODE QUALITY
  □ Pydantic v2 for all data models
  □ Type hints throughout
  □ Abstract base classes for all providers
  □ Unit tests for business logic
  □ Integration tests for pipelines
  □ E2E tests for critical paths
  □ No circular imports
  □ Single responsibility per module
```

---

## Final Architecture Summary

```
What We Built in 2 Days:

GEMINI (Dev)  ←→  LLMProvider  ←→  BEDROCK (Prod)
                       ↑
              Single abstraction point
              Change 1 env var to switch
                       
    PDF → Validate → Parse → Chunk → Embed → Qdrant
              (Ingestion Pipeline - runs independently)
              
    Query → Agent → Tools → RAG → Stream → Citations
              (Chat Pipeline - runs independently)
              
    Logging + Tracing + Metrics → Grafana + Jaeger
              (Observability - on every operation)
              
    Docker → ECR → ECS Fargate → Bedrock + Qdrant
              (Deployment - production on AWS)
```