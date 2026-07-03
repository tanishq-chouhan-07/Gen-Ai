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