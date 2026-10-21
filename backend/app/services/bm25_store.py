"""BM25 sparse retrieval store.

In-memory per-user BM25 index. Rebuilt from PostgreSQL chunks on
application startup. Not persisted between restarts - rebuilt from
the database on each start.
"""

import logging
import re
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Store:
    """In-memory BM25 index for sparse retrieval.

    Maintains per-user indexes. Rebuilt from the database on startup
    since it's not persisted between restarts.
    """

    def __init__(self) -> None:
        # user_id -> BM25Okapi instance
        self._indexes: dict[str, BM25Okapi] = {}
        # user_id -> list of (chunk_id, document_id, content) for mapping
        self._chunk_data: dict[str, list[tuple[str, str, str]]] = {}

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization: lowercase, split on whitespace/punctuation."""
        return re.findall(r"\w+", text.lower())

    def _get_index(self, user_id: str) -> tuple[BM25Okapi, list[tuple[str, str, str]]]:
        """Get or create the BM25 index for a user."""
        if user_id not in self._indexes:
            self._indexes[user_id] = BM25Okapi([])
            self._chunk_data[user_id] = []
        return self._indexes[user_id], self._chunk_data[user_id]

    def add_chunks(
        self,
        user_id: str,
        chunks: list[tuple[str, str, str]],
    ) -> None:
        """Add chunks to the user's BM25 index.

        Args:
            chunks: List of (chunk_id, document_id, content) tuples.
        """
        index, chunk_data = self._get_index(user_id)
        chunk_data.extend(chunks)
        if chunk_data:
            texts = [c[2] for c in chunk_data]
            tokenized_texts = [self._tokenize(t) for t in texts]
            self._indexes[user_id] = BM25Okapi(tokenized_texts)
        logger.info(f"BM25 index updated for user {user_id}: {len(chunk_data)} chunks")

    def remove_document(self, user_id: str, document_id: str) -> int:
        """Remove all chunks for a document from the user's BM25 index.

        Returns the number of chunks removed.
        """
        if user_id not in self._chunk_data:
            return 0

        chunk_data = self._chunk_data[user_id]
        original_count = len(chunk_data)
        chunk_data[:] = [c for c in chunk_data if c[1] != document_id]
        removed = original_count - len(chunk_data)

        if chunk_data:
            texts = [c[2] for c in chunk_data]
            tokenized_texts = [self._tokenize(t) for t in texts]
            self._indexes[user_id] = BM25Okapi(tokenized_texts)
        else:
            self._indexes[user_id] = BM25Okapi([])

        logger.info(f"Removed {removed} chunks for document {document_id} from BM25")
        return removed

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Search BM25 index for relevant chunks.

        Args:
            user_id: User ID for isolation.
            query: Query text.
            top_k: Maximum number of results.

        Returns:
            List of dicts with keys: chunk_id, document_id, content, score.
        """
        if user_id not in self._indexes:
            return []

        index, chunk_data = self._get_index(user_id)
        if not chunk_data:
            return []

        tokenized_query = self._tokenize(query)
        scores = index.get_scores(tokenized_query)

        # Get top-k results
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
            :top_k
        ]

        results: list[dict[str, Any]] = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk_id, document_id, content = chunk_data[idx]
            results.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "content": content,
                    "score": float(scores[idx]),
                }
            )
        return results

    def count(self, user_id: str) -> int:
        """Get the number of chunks in the user's BM25 index."""
        if user_id not in self._chunk_data:
            return 0
        return len(self._chunk_data[user_id])

    def rebuild(self, user_id: str, chunks: list[tuple[str, str, str]]) -> None:
        """Rebuild the BM25 index from scratch for a user.

        Used during application startup to rebuild from PostgreSQL.
        """
        self._chunk_data[user_id] = list(chunks)
        if chunks:
            texts = [c[2] for c in chunks]
            tokenized_texts = [self._tokenize(t) for t in texts]
            self._indexes[user_id] = BM25Okapi(tokenized_texts)
        else:
            self._indexes[user_id] = BM25Okapi([])
        logger.info(f"BM25 index rebuilt for user {user_id}: {len(chunks)} chunks")

    def is_available(self) -> bool:
        """BM25 is always available (in-memory)."""
        return True