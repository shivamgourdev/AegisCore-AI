"""Cross-Encoder reranking service.

Uses sentence-transformers Cross-Encoder to re-rank retrieved chunks
by relevance to the query. Configurable and can be disabled if CPU/
memory constraints require it.
"""

import logging
from typing import Any

from sentence_transformers import CrossEncoder

from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankService:
    """Cross-Encoder reranking for RAG retrieval results.

    Re-ranks top-k retrieved chunks based on query-document relevance
    using a Cross-Encoder model. Configurable via settings.
    """

    def __init__(self) -> None:
        self.enabled = settings.rag_enable_reranking
        self._encoder: Optional[Any] = None
        self._model_name = "cross-encoder/ms-marco-MiniLM-L-12-v2"

    def _get_encoder(self) -> Any:
        """Lazy-load the Cross-Encoder model."""
        if self._encoder is None:
            logger.info(f"Loading Cross-Encoder model: {self._model_name}")
            self._encoder = CrossEncoder(self._model_name)
        return self._encoder

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Re-rank retrieved chunks by relevance to the query.

        Args:
            query: User query text.
            results: List of retrieval results with 'content' key.
            top_k: Maximum number of results to return (uses config default if None).

        Returns:
            Re-ranked list of results with added 'rerank_score' field.
        """
        if not self.enabled or not results:
            return results[: top_k] if top_k else results

        try:
            encoder = self._get_encoder()
        except Exception as e:
            logger.warning(f"Cross-Encoder model unavailable: {e}. Skipping reranking.")
            return results[: top_k] if top_k else results

        # Prepare query-document pairs
        pairs = [(query, r["content"]) for r in results]

        # Get relevance scores
        try:
            scores = encoder.predict(pairs)
        except Exception as e:
            logger.warning(f"Cross-Encoder inference failed: {e}. Skipping reranking.")
            return results[: top_k] if top_k else results

        # Attach scores and sort
        for i, result in enumerate(results):
            result["rerank_score"] = float(scores[i])

        results.sort(key=lambda r: r.get("rerank_score", 0.0), reverse=True)

        if top_k is not None:
            results = results[:top_k]

        return results

    def is_available(self) -> bool:
        """Check if the reranker is enabled and model loads."""
        if not self.enabled:
            return False
        try:
            self._get_encoder()
            return True
        except Exception:
            return False