"""
Document Validator

Validates uploaded files before any processing begins.
Catches problems early so we don't waste time on bad files.

Checks:
1. File extension must be .pdf
2. File size must be under the limit
3. File must not be corrupted (PyMuPDF can open it)
4. File must contain extractable text
"""
import hashlib
from pathlib import Path
from dataclasses import dataclass
import structlog
import fitz  

from app.config.settings import get_settings

logger = structlog.get_logger()


@dataclass
class ValidationResult:
    """Result of validating a document."""
    is_valid: bool
    error_message: str = ""
    file_hash: str = ""          
    file_size_bytes: int = 0
    page_count: int = 0


class DocumentValidator:
    """
    Validates PDF files before ingestion.
    All checks are fast and happen before any heavy processing.
    """

    def __init__(self):
        self.settings = get_settings()
        self.max_size_bytes = self.settings.max_file_size_mb * 1024 * 1024
        self.allowed_extensions = {".pdf"}

    def validate(self, file_path: Path, filename: str) -> ValidationResult:
        """
        Run all validation checks on a file.

        Args:
            file_path: Path to the temporary file on disk
            filename: Original filename from the upload

        Returns:
            ValidationResult with is_valid=True or error details
        """
        log = logger.bind(filename=filename)

        # ── Check 1: File extension ───────────────────────────
        suffix = Path(filename).suffix.lower()
        if suffix not in self.allowed_extensions:
            log.warning("Invalid file extension", extension=suffix)
            return ValidationResult(
                is_valid=False,
                error_message=(
                    f"Invalid file type '{suffix}'. "
                    f"Only PDF files are accepted."
                ),
            )

        # ── Check 2: File exists and is readable ──────────────
        if not file_path.exists():
            return ValidationResult(
                is_valid=False,
                error_message="File not found after upload.",
            )

        # ── Check 3: File size ────────────────────────────────
        file_size = file_path.stat().st_size

        if file_size == 0:
            return ValidationResult(
                is_valid=False,
                error_message="File is empty.",
            )

        if file_size > self.max_size_bytes:
            size_mb = file_size / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                error_message=(
                    f"File size {size_mb:.1f}MB exceeds the "
                    f"{self.settings.max_file_size_mb}MB limit."
                ),
            )

        # ── Check 4: File hash (for duplicate detection) ──────
        file_hash = self._compute_hash(file_path)

        # ── Check 5: PDF integrity (can PyMuPDF open it?) ─────
        try:
            doc = fitz.open(str(file_path))
            page_count = len(doc)
            doc.close()
        except Exception as e:
            log.warning("PDF is corrupted or unreadable", error=str(e))
            return ValidationResult(
                is_valid=False,
                error_message=(
                    "The PDF file appears to be corrupted or "
                    "is not a valid PDF."
                ),
            )

        # ── Check 6: PDF has pages ────────────────────────────
        if page_count == 0:
            return ValidationResult(
                is_valid=False,
                error_message="The PDF file has no pages.",
            )

        log.info(
            "Document validation passed",
            file_size_bytes=file_size,
            page_count=page_count,
        )

        return ValidationResult(
            is_valid=True,
            file_hash=file_hash,
            file_size_bytes=file_size,
            page_count=page_count,
        )

    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """
        Compute SHA-256 hash of file content.
        Used to detect duplicate uploads.
        If two files have the same hash, they are identical.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in 64KB chunks to handle large files
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()