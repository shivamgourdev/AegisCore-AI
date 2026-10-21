"""Embedding service using Ollama.

Provides dense vector embeddings for document chunks and query text using
Ollama's nomic-embed-text model. Includes model compatibility checks and
batching for CPU-constrained environments.
"""

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Client for Ollama embedding model (nomic-embed-text).

    Provides embedding generation for document chunks and queries.
    Validates model compatibility by checking vector dimensions.
    """

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.rag_embedding_model
        self._dimension: Optional[int] = None

    def _client(self) -> httpx.Client:
        """Create an httpx client with appropriate timeout."""
        return httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(60.0))

    def get_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.

        Raises:
            RuntimeError: If Ollama is unavailable or embedding fails.
        """
        response = self._client().post(
            "/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Embedding failed: HTTP {response.status_code}: {response.text[:200]}"
            )
        data = response.json()
        embedding = data.get("embedding")
        if embedding is None:
            raise RuntimeError(f"Embedding response missing 'embedding' field: {data}")
        embedding_list = list(embedding)
        if self._dimension is None:
            self._dimension = len(embedding_list)
            logger.info(f"Embedding dimension set to {self._dimension}")
        elif len(embedding_list) != self._dimension:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self._dimension}, "
                f"got {len(embedding_list)}. Model may have changed."
            )
        return embedding_list

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts sequentially.

        Processes one text at a time to keep memory usage bounded
        on CPU-constrained hardware.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        results: list[list[float]] = []
        for text in texts:
            results.append(self.get_embedding(text))
        return results

    @property
    def dimension(self) -> Optional[int]:
        """Return the embedding dimension, or None if not yet initialized."""
        return self._dimension

    def is_available(self) -> bool:
        """Check if the embedding model is available via Ollama."""
        try:
            response = self._client().post(
                "/api/embeddings",
                json={"model": self.model, "prompt": "test"},
            )
            return response.status_code == 200
        except Exception:
            return False