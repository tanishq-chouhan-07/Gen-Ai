"""
Semantic Text Chunker

Splits parsed document pages into overlapping chunks.

Why chunking matters:
- LLMs have context window limits
- Smaller chunks give more precise retrieval
- Overlap ensures context is not lost at chunk boundaries

Strategy:
- Split text into sentences first (respect natural boundaries)
- Fill chunks up to chunk_size tokens
- Add overlap from the previous chunk
- Enrich every chunk with metadata (page, position, etc.)
"""
import re
import uuid
from app.processing.pdf_parser import ParsedDocument, ParsedPage
from app.models.chunk import DocumentChunk
from app.config.settings import get_settings
import structlog

logger = structlog.get_logger()


class SemanticChunker:
    """
    Splits document text into overlapping chunks.

    Each chunk is self-contained with enough context to be understood
    on its own, plus metadata linking it back to the source.
    """

    def __init__(self):
        settings = get_settings()
        # chunk_size is in approximate tokens (1 token ≈ 4 chars)
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap

    def chunk_document(
        self,
        parsed_doc: ParsedDocument,
        document_id: str,
    ) -> list[DocumentChunk]:
        """
        Chunk an entire parsed document.

        Args:
            parsed_doc: Output from PDFParser.parse()
            document_id: Used to build chunk IDs and metadata

        Returns:
            List of DocumentChunk objects ready for embedding
        """
        log = logger.bind(document_id=document_id)
        all_chunks: list[DocumentChunk] = []
        chunk_index = 0

        for page in parsed_doc.pages:
            # Skip empty pages
            if not page.text.strip():
                log.debug("Skipping empty page", page=page.page_number)
                continue

            page_chunks = self._chunk_page(
                page=page,
                document_id=document_id,
                start_index=chunk_index,
            )

            all_chunks.extend(page_chunks)
            chunk_index += len(page_chunks)

        # Now that we know the total, update total_chunks on every chunk
        total = len(all_chunks)
        for chunk in all_chunks:
            chunk.total_chunks = total

        log.info(
            "Document chunking complete",
            total_chunks=total,
            pages_processed=parsed_doc.total_pages,
        )

        return all_chunks

    def _chunk_page(
        self,
        page: ParsedPage,
        document_id: str,
        start_index: int,
    ) -> list[DocumentChunk]:
        """Split a single page into chunks."""
        sentences = self._split_into_sentences(page.text)

        if not sentences:
            return []

        chunks = []
        current_sentences: list[str] = []
        current_token_count = 0
        local_index = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)

            # If adding this sentence would exceed chunk_size
            # AND we already have content → finalize current chunk
            if (
                current_token_count + sentence_tokens > self.chunk_size
                and current_sentences
            ):
                # Build and save the chunk
                chunk = self._build_chunk(
                    sentences=current_sentences,
                    document_id=document_id,
                    page_number=page.page_number,
                    chunk_index=start_index + local_index,
                )
                chunks.append(chunk)
                local_index += 1

                # Start next chunk with overlap from the current one
                overlap_sentences = self._get_overlap(current_sentences)
                current_sentences = overlap_sentences + [sentence]
                current_token_count = sum(
                    self._estimate_tokens(s) for s in current_sentences
                )
            else:
                current_sentences.append(sentence)
                current_token_count += sentence_tokens

        # Don't forget the last chunk
        if current_sentences:
            chunk = self._build_chunk(
                sentences=current_sentences,
                document_id=document_id,
                page_number=page.page_number,
                chunk_index=start_index + local_index,
            )
            chunks.append(chunk)

        return chunks

    def _build_chunk(
        self,
        sentences: list[str],
        document_id: str,
        page_number: int,
        chunk_index: int,
    ) -> DocumentChunk:
        """Create a DocumentChunk from a list of sentences."""
        content = " ".join(sentences).strip()
        token_count = self._estimate_tokens(content)

        return DocumentChunk(
            chunk_id=f"{document_id}_p{page_number}_c{chunk_index}",
            document_id=document_id,
            content=content,
            page_number=page_number,
            chunk_index=chunk_index,
            total_chunks=0,  # Will be updated after all chunks are created
            token_count=token_count,
            char_count=len(content),
            metadata={
                "page_number": page_number,
                "chunk_index": chunk_index,
                "document_id": document_id,
            },
        )

    def _split_into_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences.
        Uses regex to split on sentence-ending punctuation.
        Filters out very short fragments.
        """
        # Split on . ! ? followed by whitespace
        raw = re.split(r'(?<=[.!?])\s+', text)

        sentences = []
        for s in raw:
            s = s.strip()
            # Skip very short fragments (less than 20 chars)
            if len(s) >= 20:
                sentences.append(s)

        return sentences

    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token estimate: 1 token ≈ 4 characters.
        Good enough for chunking purposes without loading a tokenizer.
        """
        return max(1, len(text) // 4)

    def _get_overlap(self, sentences: list[str]) -> list[str]:
        """
        Get the tail sentences that fit within the overlap budget.
        These become the start of the next chunk for context continuity.
        """
        budget = self.chunk_overlap
        overlap = []

        # Walk backwards through sentences
        for sentence in reversed(sentences):
            tokens = self._estimate_tokens(sentence)
            if tokens <= budget:
                overlap.insert(0, sentence)
                budget -= tokens
            else:
                break

        return overlap