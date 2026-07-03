"""
Retrieval Service

Handles semantic document retrieval from Qdrant using Two-Stage Retrieval:
1. Bi-Encoder (Qdrant + BGE) for broad recall.
2. Cross-Encoder (BGE-Reranker) for high precision.
"""
import structlog
from app.repositories.vector_repository import VectorRepository
from app.embeddings.base import EmbeddingProvider
from app.config.settings import get_settings
from app.services.reranker_service import RerankerService

logger = structlog.get_logger()


class RetrievalService:
    """Handles querying the vector database and reranking results."""
    
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_repo: VectorRepository,
    ):
        self.embedding_provider = embedding_provider
        self.vector_repo = vector_repo
        self.settings = get_settings()
        self.reranker = RerankerService()  # Initialize the Cross-Encoder reranker
    
    async def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Embed the query, search Qdrant, and rerank relevant chunks."""
        log = logger.bind(query_preview=query[:50])
        
        # 1. Embed the user query
        query_vector = await self.embedding_provider.embed(query)
        
        # 2. Search Qdrant (Stage 1: Broad Recall)
        # We over-fetch (e.g., 4x the requested amount) and use a lower threshold.
        # The Cross-Encoder will handle filtering out the garbage later.
        fetch_k = top_k * 4 
        chunks = await self.vector_repo.search(
            query_vector=query_vector,
            top_k=fetch_k,
            score_threshold=0.3,  # Lowered from 0.5 to cast a wider net
        )
        
        log.info("Initial retrieval from Qdrant", count=len(chunks))
        
        # 3. Format for the reranker
        results = []
        for chunk in chunks:
            results.append({
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "page_number": chunk.page_number,
                "content": chunk.content,
                "score": chunk.score,  # Original Qdrant cosine similarity score
            })
            
        # 4. Rerank using Cross-Encoder (Stage 2: High Precision)
        # This scores the (query, chunk) pairs together and returns only the top_k
        reranked_results = self.reranker.rerank(query, results, top_k=top_k)
        
        log.info("Reranking complete", final_count=len(reranked_results))
        
        return reranked_results