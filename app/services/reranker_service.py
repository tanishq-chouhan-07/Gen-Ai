# app/services/reranker_service.py
"""
Cross-Encoder Reranker Service

Takes a query and a list of retrieved chunks, and reranks them 
using a Cross-Encoder model for higher precision.
"""
import structlog
from sentence_transformers import CrossEncoder
from app.config.settings import get_settings

logger = structlog.get_logger()

class RerankerService:
    def __init__(self):
        settings = get_settings()
        # BGE reranker base is fast and accurate enough for CPU/GPU
        self.model = CrossEncoder('BAAI/bge-reranker-base', max_length=512)
        logger.info("CrossEncoder reranker loaded", model="BAAI/bge-reranker-base")

    def rerank(self, query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
        if not chunks:
            return []

        log = logger.bind(query_preview=query[:50], initial_chunks=len(chunks))
        
        # 1. Create pairs of (query, chunk_content) for the CrossEncoder
        pairs = [[query, chunk["content"]] for chunk in chunks]
        
        # 2. Score the pairs
        scores = self.model.predict(pairs)
        
        # 3. Attach new scores to chunks
        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)
            
        # 4. Sort by new rerank score (descending)
        reranked_chunks = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        
        # 5. Slice top K
        top_chunks = reranked_chunks[:top_k]
        
        log.info("Reranking complete", returned_chunks=len(top_chunks), 
                 top_rerank_score=top_chunks[0]["rerank_score"] if top_chunks else 0)
        
        return top_chunks