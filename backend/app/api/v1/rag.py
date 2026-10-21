"""RAG API routes.

Endpoints:
- POST /api/v1/rag/ingest - Upload and index a document
- POST /api/v1/rag/query - Ask a question over uploaded documents
- GET /api/v1/rag/documents - List user's documents
- DELETE /api/v1/rag/documents/{document_id} - Delete a document
- GET /api/v1/rag/documents/{document_id} - Get document metadata
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.models.document import Chunk
from app.services.embedding_service import EmbeddingService
from app.services.generation_service import GenerationService
from app.services.ingestion_service import extract_and_chunk
from app.services.rag_service import RAGService
from app.services.upload_service import validate_upload
from app.services.vector_store import VectorStore

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_rag_service() -> RAGService:
    """Create a RAG service instance with all dependencies."""
    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    bm25_store = None  # Will be initialized with chunks from DB
    rerank_service = None  # Will be initialized conditionally
    generation_service = GenerationService()

    return RAGService()


@router.post("/ingest", status_code=201)
async def ingest_document(
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    """Upload and index a document.

    Extracts text, chunks it, generates embeddings, and stores everything
    for RAG retrieval.
    """
    import traceback

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {type(e).__name__}: {e}")
        raise HTTPException(status_code=415, detail=f"Failed to read file: {str(e)}")

    # Validate upload
    try:
        extension = validate_upload(file.filename, file.content_type, file)
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        logger.error(f"Upload validation error: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=415, detail=f"Upload validation error: {str(e)}")

    # Re-read content (validate_upload consumed it)
    content = await file.read()

    # Extract and chunk
    try:
        result = extract_and_chunk(content, file.filename, file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f"Extraction error: {type(e).__name__}: {e}"
        logger.error(error_msg)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

    # Store document record in PostgreSQL
    import uuid

    document_id = str(uuid.uuid4())
    user_id = str(current_user.id)

    from app.models.document import Document

    db_document = Document(
        id=document_id,
        user_id=user_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        storage_path=f"data/uploads/{user_id}/{document_id}",
        status="indexing",
        chunk_count=len(result["chunks"]),
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # Process chunks: embed + store in ChromaDB + add to BM25
    embedding_service = EmbeddingService()
    vector_store = VectorStore()

    chunk_records = []
    embeddings = []
    embedding_texts = []
    embedding_ids = []

    for chunk in result["chunks"]:
        chunk_id = str(uuid.uuid4())
        chunk_records.append(
            {
                "id": chunk_id,
                "document_id": document_id,
                "user_id": user_id,
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "page_number": None,  # Could be extracted from PDF metadata
                "section": None,
                "metadata": {"filename": file.filename},
                "embedding_id": chunk_id,
            }
        )
        embedding_texts.append(chunk["content"])
        embedding_ids.append(chunk_id)

    # Generate embeddings
    try:
        embeddings = embedding_service.get_embeddings(embedding_texts)
        logger.info(f"Generated {len(embeddings)} embeddings")
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"Embedding failed: {type(e).__name__}: {e}\n{tb_str}")
        db_document.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=f"Embedding service unavailable: {type(e).__name__}: {e}\n{tb_str}",
        )

    # Store vectors in ChromaDB
    try:
        vector_store.add_vectors(
            user_id=user_id,
            ids=embedding_ids,
            embeddings=embeddings,
            documents=[c["content"] for c in chunk_records],
            metadatas=[
                {
                    "document_id": cr["document_id"],
                    "chunk_index": cr["chunk_index"],
                    "filename": file.filename,
                }
                for cr in chunk_records
            ],
        )
    except Exception as e:
        logger.error(f"Vector store error: {e}")
        db_document.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=503, detail=f"Vector store error: {e}"
        )

    # Store chunks in PostgreSQL
    for chunk_record in chunk_records:
        db_chunk = Chunk(
            id=chunk_record["id"],
            document_id=chunk_record["document_id"],
            user_id=chunk_record["user_id"],
            chunk_index=chunk_record["chunk_index"],
            content=chunk_record["content"],
            page_number=chunk_record["page_number"],
            section=chunk_record["section"],
            metadata_=chunk_record["metadata"],
            embedding_id=chunk_record["embedding_id"],
        )
        db.add(db_chunk)

    # Update document status
    db_document.status = "indexed"
    db.commit()

    logger.info(
        f"Ingested document {document_id} for user {user_id}: "
        f"{len(chunk_records)} chunks"
    )

    return {
        "document_id": document_id,
        "filename": file.filename,
        "chunk_count": len(chunk_records),
        "status": "indexed",
    }


@router.post("/query")
async def query_documents(
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    """Ask a question over uploaded documents.

    Uses hybrid retrieval (dense + BM25 + RRF), Cross-Encoder reranking,
    and LLM generation with citation verification.
    """
    try:
        question = body.get("question", "").strip()
        if not question:
            raise HTTPException(status_code=422, detail="Question is required")

        top_k = body.get("top_k", 5)
        user_id = str(current_user.id)

        rag_service = _get_rag_service()
        result = rag_service.full_rag_pipeline(
            user_id=user_id,
            query=question,
            top_k=top_k,
        )

        return result
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"RAG query failed: {type(e).__name__}: {e}\n{tb_str}")
        return {
            "answer": "",
            "citations": [],
            "abstained": True,
            "abstention_reason": f"Query processing error: {type(e).__name__}: {e}",
        }


@router.get("/documents")
async def list_documents(
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> list[dict[str, Any]]:
    """List all documents for the current user."""
    from app.models.document import Document

    docs = (
        db.query(Document)
        .filter(Document.user_id == str(current_user.id))
        .all()
    )

    return [
        {
            "id": d.id,
            "filename": d.filename,
            "content_type": d.content_type,
            "size_bytes": d.size_bytes,
            "status": d.status,
            "chunk_count": d.chunk_count,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> None:
    """Delete a document and all its chunks/vectors.

    Only the document owner can delete it.
    """
    from app.models.document import Document, Chunk

    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .filter(Document.user_id == str(current_user.id))
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    user_id = str(current_user.id)

    # Delete from ChromaDB
    vector_store = VectorStore()
    vector_store.delete_document(user_id=user_id, document_id=document_id)

    # Delete chunks from PostgreSQL
    db.query(Chunk).filter(Chunk.document_id == document_id).delete()

    # Delete document
    db.delete(document)
    db.commit()

    logger.info(f"Deleted document {document_id} for user {user_id}")


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    """Get document metadata."""
    from app.models.document import Document

    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .filter(Document.user_id == str(current_user.id))
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "filename": document.filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "status": document.status,
        "chunk_count": document.chunk_count,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }
