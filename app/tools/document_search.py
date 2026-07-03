# app/tools/document_search.py
import structlog
from app.services.retrieval_service import RetrievalService

logger = structlog.get_logger()

class DocumentSearchTool:
    def __init__(self, retrieval_service: RetrievalService):
        self.retrieval = retrieval_service
        self.last_chunks = []  # Store structured data for the service to use later

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "search_documents",
                "description": "Search the company document database for information to answer the user's question.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The standalone search query to look up in the documents."
                        }
                    },
                    "required": ["query"]
                }
            }
        }

    async def execute(self, query: str) -> str:
        chunks = await self.retrieval.retrieve(query)
        self.last_chunks = chunks  # Save structured data to instance state
        
        if not chunks:
            return "No relevant documents found."
        
        formatted = []
        for i, chunk in enumerate(chunks, 1):
            formatted.append(
                f"[{i}] Source: {chunk['filename']} (Page: {chunk['page_number']})\n"
                f"Content: {chunk['content']}\n"
            )
        return "\n".join(formatted)