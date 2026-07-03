"""
PDF Parser using PyMuPDF (fitz)

Extracts text and metadata from PDF files page by page.
PyMuPDF is fast, handles complex PDFs well, and works offline.

What we extract:
- Text content per page
- Document metadata (title, author, creation date)
- Page count
- Basic structure detection (has images, has tables)
"""
from pathlib import Path
from dataclasses import dataclass, field
import structlog
import fitz  # PyMuPDF

logger = structlog.get_logger()


@dataclass
class ParsedPage:
    """Text and metadata extracted from a single PDF page."""
    page_number: int      # 1-based page number
    text: str             # Extracted text content
    char_count: int       # Number of characters
    has_images: bool      # Page contains images
    has_tables: bool      # Page likely contains tables (heuristic)


@dataclass
class ParsedDocument:
    """Complete parsed content of a PDF document."""
    # Document metadata from PDF properties
    title: str | None
    author: str | None
    created_date: str | None
    total_pages: int
    total_chars: int

    # Per-page content
    pages: list[ParsedPage] = field(default_factory=list)

    # Raw metadata dict from PyMuPDF
    raw_metadata: dict = field(default_factory=dict)


class PDFParser:
    """
    Parses PDF files using PyMuPDF.

    Usage:
        parser = PDFParser()
        result = parser.parse(Path("document.pdf"), document_id="doc-123")
        for page in result.pages:
            print(f"Page {page.page_number}: {len(page.text)} chars")
    """

    def parse(self, file_path: Path, document_id: str) -> ParsedDocument:
        """
        Parse a PDF file and extract all text content.

        Args:
            file_path: Path to the PDF file
            document_id: Document ID for logging context

        Returns:
            ParsedDocument with all extracted content
        """
        log = logger.bind(document_id=document_id, file_path=str(file_path))
        log.info("Starting PDF parsing")

        try:
            doc = fitz.open(str(file_path))
            pages = []

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_number = page_idx + 1  # Convert to 1-based

                # Extract text - "text" mode gives clean plain text
                text = page.get_text("text")
                text = text.strip()

                # Detect images
                has_images = len(page.get_images()) > 0

                # Detect tables using heuristic
                # Many short text blocks side by side usually means a table
                blocks = page.get_text("blocks")
                has_tables = self._detect_tables(blocks)

                pages.append(ParsedPage(
                    page_number=page_number,
                    text=text,
                    char_count=len(text),
                    has_images=has_images,
                    has_tables=has_tables,
                ))

                log.debug(
                    "Page parsed",
                    page=page_number,
                    chars=len(text),
                    has_images=has_images,
                )

            # Extract document-level metadata
            metadata = doc.metadata or {}
            doc.close()

            total_chars = sum(p.char_count for p in pages)
            non_empty_pages = [p for p in pages if p.text]

            log.info(
                "PDF parsing complete",
                total_pages=len(pages),
                non_empty_pages=len(non_empty_pages),
                total_chars=total_chars,
            )

            return ParsedDocument(
                title=metadata.get("title") or None,
                author=metadata.get("author") or None,
                created_date=metadata.get("creationDate") or None,
                total_pages=len(pages),
                total_chars=total_chars,
                pages=pages,
                raw_metadata=metadata,
            )

        except Exception as e:
            log.error("PDF parsing failed", error=str(e))
            raise

    def _detect_tables(self, blocks: list) -> bool:
        """
        Heuristic table detection.
        Tables tend to have many small blocks arranged in a grid.
        This is not perfect but good enough for metadata purposes.
        """
        if len(blocks) < 6:
            return False

        # Count blocks with short text (typical of table cells)
        short_blocks = [
            b for b in blocks
            if len(b) > 4 and isinstance(b[4], str) and len(b[4].strip()) < 60
        ]

        # If more than 60% of blocks are short → likely a table
        return len(short_blocks) > len(blocks) * 0.6