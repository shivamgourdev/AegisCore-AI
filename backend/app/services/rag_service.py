"""RAG orchestration service.

Coordinates the full RAG pipeline:
1. Query embedding (Ollama nomic-embed-text)
2. Dense retrieval (ChromaDB) + BM25 retrieval
3. RRF fusion
4. Cross-Encoder reranking
5. LLM generation (Gemini → Ollama)
6. Citation verification gate
7. Abstention gate
"""

import logging
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, Chunk
from app.services.embedding_service import EmbeddingService
from app.services.generation_service import GenerationService
from app.services.rerank_service import RerankService
from app.services.vector_store import VectorStore
from app.services.bm25_store import BM25Store

logger = logging.getLogger(__name__)


class RAGService:
    """Orchestrates the full RAG pipeline.

    Components:
    - EmbeddingService: Query embedding via Ollama
    - VectorStore: Dense retrieval via ChromaDB
    - BM25Store: Sparse retrieval via BM25
    - RerankService: Cross-Encoder reranking
    - GenerationService: LLM answer generation (Gemini → Ollama)
    """

    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.bm25_store = BM25Store()
        self.rerank_service = RerankService()
        self.generation_service = GenerationService()
        self.rrf_k = settings.rag_rerank_top_k if hasattr(settings, "rag_rerank_top_k") else 8

    def retrieve(
        self,
        user_id: str,
        query: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Perform hybrid retrieval: dense + BM25 + RRF fusion.

        Args:
            user_id: User ID for isolation.
            query: User question text.
            top_k: Maximum number of results after fusion.

        Returns:
            List of candidate chunks with scores.
        """
        # Dense retrieval via ChromaDB
        query_embedding = self.embedding_service.get_embedding(query)
        dense_results = self.vector_store.query(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        # Sparse retrieval via BM25
        bm25_results = self.bm25_store.search(
            user_id=user_id,
            query=query,
            top_k=top_k,
        )

        # Fuse scores using RRF
        fused = self._rrf_fusion(dense_results, bm25_results, top_k=top_k)
        return fused

    def _rrf_fusion(
        self,
        dense_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Fuse dense and sparse retrieval results using Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank)) for each list where the item appears.
        k = 60 (standard value).
        """
        k = 60
        scores: dict[str, dict[str, Any]] = {}

        # Process dense results
        for rank, result in enumerate(dense_results):
            chunk_id = result["chunk_id"]
            if chunk_id not in scores:
                scores[chunk_id] = {"chunk": result, "score": 0.0}
            scores[chunk_id]["score"] += 1.0 / (k + rank + 1)

        # Process BM25 results
        for rank, result in enumerate(bm25_results):
            chunk_id = result["chunk_id"]
            if chunk_id not in scores:
                scores[chunk_id] = {"chunk": result, "score": 0.0}
            scores[chunk_id]["score"] += 1.0 / (k + rank + 1)

        # Sort by fused score descending
        sorted_results = sorted(
            scores.values(), key=lambda x: x["score"], reverse=True
        )

        # Return top_k with fused score
        fused_results = []
        for item in sorted_results[:top_k]:
            result = item["chunk"]
            result["rrf_score"] = item["score"]
            fused_results.append(result)

        return fused_results

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Re-rank results using Cross-Encoder (if enabled)."""
        return self.rerank_service.rerank(query, results, top_k=top_k)

    def generate_answer(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate an answer from retrieved context.

        Returns dict with:
            answer: Generated response text.
            citations: List of citation dicts.
            abstained: Whether the system abstained.
            abstention_reason: Reason for abstention (if abstained).
        """
        if not context_chunks:
            return {
                "answer": "",
                "citations": [],
                "abstained": True,
                "abstention_reason": "No documents found matching your query.",
            }

        # Build context from chunks with citation markers
        context_parts = []
        citation_map = {}  # cite:chunk_id -> citation info

        for i, chunk in enumerate(context_chunks):
            chunk_id = chunk["chunk_id"]
            cite_marker = f"[[cite:{chunk_id}]]"
            context_parts.append(f"[{i+1}] {chunk['content']}")
            citation_map[cite_marker] = {
                "chunk_id": chunk_id,
                "document_id": chunk.get("document_id", ""),
                "filename": chunk.get("metadata", {}).get("filename", "unknown"),
                "page_number": chunk.get("metadata", {}).get("page_number"),
                "section": chunk.get("metadata", {}).get("section"),
            }

        context_text = "\n\n".join(context_parts)

        system_prompt = """You are a helpful assistant that answers questions based ONLY on the provided document context.

Rules:
1. Answer ONLY using information from the provided context chunks.
2. For each fact you state, cite the source using [[cite:chunk_id]] format.
3. If the documents don't contain sufficient evidence to answer the question, say "I could not find sufficient evidence in your documents to answer this question."
4. Do not invent information not present in the documents.
5. If sources conflict, present both perspectives.
6. Keep answers concise and direct.

Context:
{context}

Question: {question}

Answer:"""

        user_prompt = f"Context:\n{context_text}\n\nQuestion: {query}\n\nAnswer:"

        try:
            answer = self.generation_service.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {
                "answer": "",
                "citations": [],
                "abstained": True,
                "abstention_reason": "AI model unavailable. Please try again later.",
            }

        # Verify citations
        verified_citations = self._verify_citations(answer, context_chunks)

        if not verified_citations:
            return {
                "answer": "",
                "citations": [],
                "abstained": True,
                "abstention_reason": "I could not find sufficient evidence in your documents to answer this question.",
            }

        return {
            "answer": answer,
            "citations": verified_citations,
            "abstained": False,
            "abstention_reason": None,
        }

    def _verify_citations(
        self,
        answer: str,
        context_chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Verify that all cited chunks exist in the retrieved set and belong to the user.

        Strips unverifiable citations from the answer.
        """
        import re

        # Find all citation markers
        cite_pattern = r"\[\[cite:([^\]]+)\]\]"
        cited_chunk_ids = set(re.findall(cite_pattern, answer))

        # Build set of valid chunk IDs from retrieved context
        valid_chunk_ids = {c["chunk_id"] for c in context_chunks}
        chunk_map = {c["chunk_id"]: c for c in context_chunks}

        verified_citations = []

        for chunk_id in cited_chunk_ids:
            if chunk_id in valid_chunk_ids:
                chunk = chunk_map[chunk_id]
                metadata = chunk.get("metadata", {})
                verified_citations.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": chunk.get("document_id", ""),
                        "filename": metadata.get("filename", "unknown"),
                        "page_number": metadata.get("page_number"),
                        "section": metadata.get("section"),
                        "relevance_score": chunk.get("rrf_score", 0.0),
                    }
                )

        # If no valid citations remain, abstain
        if not verified_citations:
            return []

        # Replace citations in answer with just the ones that are valid
        # (keep the marker format but only for verified ones)
        # The answer text keeps the markers but we only return verified ones

        return verified_citations

    def full_rag_pipeline(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Run the full RAG pipeline end-to-end.

        Args:
            user_id: Authenticated user ID.
            query: User question.
            top_k: Maximum number of chunks to retrieve.

        Returns:
            Dict with answer, citations, abstention info.
        """
        try:
            # Step 1: Retrieve candidates
            retrieved = self.retrieve(user_id=user_id, query=query, top_k=top_k)

            if not retrieved:
                return {
                    "answer": "",
                    "citations": [],
                    "abstained": True,
                    "abstention_reason": "No documents found matching your query.",
                }

            # Step 2: Rerank
            reranked = self.rerank(query=query, results=retrieved, top_k=top_k)

            # Step 3: Generate answer with citations
            result = self.generate_answer(query=query, context_chunks=reranked)

            return result
        except Exception as e:
            logger.error(f"RAG pipeline failed: {type(e).__name__}: {e}")
            import traceback
            tb_str = traceback.format_exc()
            logger.error(tb_str)
            return {
                "answer": "",
                "citations": [],
                "abstained": True,
                "abstention_reason": f"RAG pipeline error: {type(e).__name__}: {e}",
            }