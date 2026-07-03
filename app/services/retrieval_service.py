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