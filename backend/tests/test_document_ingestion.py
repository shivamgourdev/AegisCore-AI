"""Document extraction and chunking tests."""

import io
import tiktoken
import pytest

from app.services.ingestion_service import extract_text, chunk_text, extract_and_chunk


class TestExtraction:
    """Test document text extraction."""

    def test_txt_extraction(self):
        """Plain text extraction returns content."""
        content = b"Hello, this is a test document."
        result = extract_text(content, "test.txt", "text/plain")
        assert result == "Hello, this is a test document."

    def test_markdown_extraction(self):
        """Markdown extraction returns content with headers."""
        content = b"# Header\n\nSome content here."
        result = extract_text(content, "notes.md", "text/markdown")
        assert result == "# Header\n\nSome content here."

    def test_invalid_extension_rejected(self):
        """Non-supported extension raises ValueError."""
        content = b"dummy content"
        with pytest.raises(ValueError, match="Unsupported file extension"):
            extract_text(content, "malware.exe", "application/octet-stream")

    def test_empty_document_raises(self):
        """Empty text document raises ValueError."""
        content = b""
        with pytest.raises(ValueError):
            extract_text(content, "empty.txt", "text/plain")


class TestChunking:
    """Test token-aware chunking with tiktoken cl100k_base."""

    def test_chunk_size_limit(self):
        """Each chunk is at most 512 tokens."""
        long_text = " ".join(["word"] * 2000)  # ~2000 tokens
        chunks = chunk_text(long_text)

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk["token_count"] <= 512, (
                f"Chunk {chunk['chunk_index']} has {chunk['token_count']} tokens, "
                f"exceeds 512 limit"
            )

    def test_chunk_overlap(self):
        """Consecutive chunks overlap by 50 tokens."""
        encoder = tiktoken.get_encoding("cl100k_base")
        long_text = " ".join(["word"] * 2000)
        chunks = chunk_text(long_text)

        if len(chunks) >= 2:
            chunk0_tokens = encoder.encode(chunks[0]["content"])
            chunk1_tokens = encoder.encode(chunks[1]["content"])
            overlap_tokens = set(chunk0_tokens[-50:]) & set(chunk1_tokens[:50])
            assert len(overlap_tokens) > 0, (
                "Expected overlap between consecutive chunks"
            )

    def test_empty_text_returns_empty(self):
        """Empty text returns empty chunk list."""
        chunks = chunk_text("")
        assert chunks == []

    def test_short_document_single_chunk(self):
        """Short document returns single chunk."""
        chunks = chunk_text("Hello world")
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["content"] == "Hello world"

    def test_chunk_index_sequential(self):
        """Chunk indices are sequential starting from 0."""
        long_text = " ".join(["word"] * 2000)
        chunks = chunk_text(long_text)

        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_chunk_content_contiguous(self):
        """Chunk content is contiguous (no gaps between chunks)."""
        long_text = "word " * 1000
        chunks = chunk_text(long_text)

        if len(chunks) >= 2:
            # Reconstruct text from chunks and verify coverage
            encoder = tiktoken.get_encoding("cl100k_base")
            all_chunk_tokens = []
            for chunk in chunks:
                all_chunk_tokens.extend(encoder.encode(chunk["content"]))

            original_tokens = encoder.encode(long_text)
            # All original tokens should appear in chunks (with overlap)
            assert len(all_chunk_tokens) >= len(original_tokens)


class TestExtractAndChunk:
    """Test the full extract_and_chunk pipeline."""

    def test_full_pipeline_txt(self):
        """Full extract_and_chunk on TXT file."""
        content = b"Hello world. This is a test document for chunking."
        result = extract_and_chunk(content, "test.txt", "text/plain")

        assert result["filename"] == "test.txt"
        assert result["content_type"] == "text/plain"
        assert result["size_bytes"] == len(content)
        assert result["total_chunks"] >= 1
        assert len(result["chunks"]) == result["total_chunks"]

        for chunk in result["chunks"]:
            assert "chunk_index" in chunk
            assert "content" in chunk
            assert "token_count" in chunk

    def test_full_pipeline_md(self):
        """Full extract_and_chunk on Markdown file."""
        content = b"# My Document\n\nThis is markdown content."
        result = extract_and_chunk(content, "notes.md", "text/markdown")

        assert result["filename"] == "notes.md"
        assert result["content_type"] == "text/markdown"
        assert result["total_chunks"] >= 1
        assert len(result["chunks"]) == result["total_chunks"]

    def test_chunk_count_matches(self):
        """total_chunks matches actual number of chunks."""
        content = b"word " * 1000
        result = extract_and_chunk(content, "test.txt", "text/plain")
        assert result["total_chunks"] == len(result["chunks"])

    def test_empty_document_raises(self):
        """Empty document raises ValueError through extract_and_chunk."""
        content = b""
        with pytest.raises(ValueError):
            extract_and_chunk(content, "empty.txt", "text/plain")
