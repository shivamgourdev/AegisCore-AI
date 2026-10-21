"""Document extraction and chunking service.

Handles PDF, TXT, and Markdown file extraction, token-aware chunking
with 512-token chunks and 50-token overlap using tiktoken cl100k_base
as a sizing convention.
"""

import io
from pathlib import Path
from typing import Optional

import tiktoken

from app.core.config import settings


CHUNK_SIZE = settings.rag_chunk_size  # 512 tokens
CHUNK_OVERLAP = settings.rag_chunk_overlap  # 50 tokens


def extract_text(file_content: bytes, filename: str, content_type: str) -> str:
    """Extract text content from an uploaded file.

    Supports PDF, TXT, and Markdown files. For PDFs without extractable
    text (e.g., scanned images), raises ValueError.

    Args:
        file_content: Raw file bytes.
        filename: Original filename (used to determine extension).
        content_type: MIME type from upload.

    Returns:
        Extracted text string.

    Raises:
        ValueError: If file type is unsupported or PDF has no extractable text.
    """
    extension = Path(filename).suffix.lower()

    if extension == ".pdf":
        return _extract_pdf_text(file_content)
    elif extension in (".txt", ".md", ".markdown"):
        text = file_content.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError(
                "Document contains no extractable text. "
                "The file is empty or contains only whitespace."
            )
        return text
    else:
        raise ValueError(f"Unsupported file extension: {extension}")


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text_parts = []

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text()
        if page_text and page_text.strip():
            text_parts.append(f"[Page {page_num}]\n{page_text}")

    if not text_parts:
        raise ValueError(
            "No extractable text found in PDF. "
            "This may be a scanned or image-only PDF. OCR is not supported."
        )

    return "\n".join(text_parts)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Split text into overlapping chunks using tiktoken cl100k_base.

    Args:
        text: Raw text to chunk.
        chunk_size: Maximum tokens per chunk.
        overlap: Number of overlapping tokens between consecutive chunks.

    Returns:
        List of dicts with keys: chunk_index, content, token_count.
    """
    encoder = tiktoken.get_encoding("cl100k_base")
    tokens = encoder.encode(text)

    if len(tokens) == 0:
        return []

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text_str = encoder.decode(chunk_tokens)

        chunks.append(
            {
                "chunk_index": chunk_index,
                "content": chunk_text_str,
                "token_count": len(chunk_tokens),
            }
        )

        if end >= len(tokens):
            break

        start = end - overlap
        chunk_index += 1

    return chunks


def extract_and_chunk(
    file_content: bytes, filename: str, content_type: str
) -> dict:
    """Extract text from file and chunk it into token-aware segments.

    Args:
        file_content: Raw file bytes.
        filename: Original filename.
        content_type: MIME type from upload.

    Returns:
        Dict with:
            filename: Original filename.
            content_type: MIME type.
            size_bytes: File size in bytes.
            total_chunks: Number of chunks produced.
            chunks: List of dicts with chunk_index, content, token_count.

    Raises:
        ValueError: If file type unsupported or PDF has no extractable text.
    """
    text = extract_text(file_content, filename, content_type)
    chunks = chunk_text(text)

    return {
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(file_content),
        "total_chunks": len(chunks),
        "chunks": chunks,
    }
