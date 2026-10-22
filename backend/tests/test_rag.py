"""Tests for RAG pipeline, endpoints, and worker tasks."""

import io
import pytest
from unittest.mock import MagicMock, patch

from app.services.rag_service import RAGService
from app.workers.tasks import ingest_document, send_email


def test_rag_service_instantiation():
    """Verify RAGService instantiates with default dependencies without errors."""
    rag_service = RAGService()
    assert rag_service is not None
    assert hasattr(rag_service, "embedding_service")
    assert hasattr(rag_service, "vector_store")
    assert hasattr(rag_service, "bm25_store")
    assert hasattr(rag_service, "rerank_service")
    assert hasattr(rag_service, "generation_service")


@patch("app.services.rag_service.EmbeddingService")
@patch("app.services.rag_service.VectorStore")
@patch("app.services.rag_service.BM25Store")
@patch("app.services.rag_service.RerankService")
@patch("app.services.rag_service.GenerationService")
def test_full_rag_pipeline_execution(
    mock_gen_cls, mock_rerank_cls, mock_bm25_cls, mock_vs_cls, mock_emb_cls
):
    """Test full_rag_pipeline with mocked internal services."""
    mock_emb = mock_emb_cls.return_value
    mock_emb.get_embedding.return_value = [0.1] * 384

    mock_vs = mock_vs_cls.return_value
    mock_vs.query.return_value = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "content": "Supervised learning uses labeled training data.",
            "metadata": {"filename": "ml_basics.md"},
        }
    ]

    mock_bm25 = mock_bm25_cls.return_value
    mock_bm25.search.return_value = []

    mock_rerank = mock_rerank_cls.return_value
    mock_rerank.rerank.side_effect = lambda query, results, top_k=None: results

    mock_gen = mock_gen_cls.return_value
    mock_gen.generate.return_value = "Supervised learning uses labeled training data [[cite:c1]]."

    rag = RAGService()
    result = rag.full_rag_pipeline(user_id="user1", query="What is supervised learning?")

    assert result["abstained"] is False
    assert "Supervised learning" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["chunk_id"] == "c1"


def test_worker_tasks():
    """Verify worker tasks return expected status dictionaries."""
    res_ingest = ingest_document("doc123", "user456")
    assert res_ingest["status"] == "queued"
    assert res_ingest["document_id"] == "doc123"

    res_email = send_email("draft123", "user456")
    assert res_email["status"] == "queued"
    assert res_email["draft_id"] == "draft123"


def test_rag_ingest_and_query_endpoints(client):
    """Test /api/v1/rag/ingest and /api/v1/rag/query via TestClient."""
    # Register & Login
    client.post("/api/v1/auth/register", json={"email": "ragtest@example.com", "password": "Password123!"})
    login_resp = client.post("/api/v1/auth/login", json={"email": "ragtest@example.com", "password": "Password123!"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    file_content = b"# Machine Learning\n\nMachine learning is a subfield of artificial intelligence."
    files = {"file": ("test_doc.md", io.BytesIO(file_content), "text/markdown")}

    with patch("app.api.v1.rag.EmbeddingService") as mock_emb_cls, \
         patch("app.api.v1.rag.VectorStore") as mock_vs_cls:

        mock_emb = mock_emb_cls.return_value
        mock_emb.get_embeddings.return_value = [[0.1] * 384]

        mock_vs = mock_vs_cls.return_value
        mock_vs.add_vectors.return_value = None

        response = client.post("/api/v1/rag/ingest", headers=headers, files=files)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["status"] == "indexed"
        assert data["filename"] == "test_doc.md"

    # Query documents endpoint test
    with patch("app.services.rag_service.EmbeddingService") as mock_emb_cls, \
         patch("app.services.rag_service.VectorStore") as mock_vs_cls, \
         patch("app.services.rag_service.GenerationService") as mock_gen_cls:

        mock_emb = mock_emb_cls.return_value
        mock_emb.get_embedding.return_value = [0.1] * 384

        mock_vs = mock_vs_cls.return_value
        mock_vs.query.return_value = []

        query_resp = client.post(
            "/api/v1/rag/query",
            headers=headers,
            json={"question": "What is AI?", "top_k": 5},
        )
        assert query_resp.status_code == 200, query_resp.text
        q_data = query_resp.json()
        assert "answer" in q_data
        assert "abstained" in q_data
