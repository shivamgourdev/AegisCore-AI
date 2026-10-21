"""Vector store service using ChromaDB (persistent, embedded mode).

Provides vector storage and retrieval for document chunks.
Persisted to disk via CHROMA_PERSIST_DIRECTORY.
"""

import logging
from typing import Any

import chromadb
from chromadb.errors import NotFoundError
from chromadb.api.models.Collection import Collection

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB wrapper for dense vector storage and retrieval.

    Uses ChromaDB in embedded/persistent mode, storing vectors on disk.
    Collections are keyed by user_id for isolation.
    """

    def __init__(self) -> None:
        self.persist_directory = settings.chroma_persist_directory
        self._client: Optional[chromadb.PersistentClient] = None
        self._collections: dict[str, Collection] = {}

    def _get_client(self) -> chromadb.PersistentClient:
        """Get or create the ChromaDB client."""
        if self._client is None:
            self._client = chromadb.PersistentClient(path=self.persist_directory)
        return self._client

    def _get_collection(self, user_id: str) -> Collection:
        """Get or create a ChromaDB collection for a specific user.

        Each user gets their own collection for data isolation.
        """
        client = self._get_client()
        collection_name = f"user_{user_id.replace('-', '_')}"
        try:
            return client.get_collection(name=collection_name)
        except NotFoundError:
            # Collection doesn't exist yet - create it
            return client.create_collection(name=collection_name)

    def add_vectors(
        self,
        user_id: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Add vectors to the user's collection.

        Args:
            ids: Unique IDs for each vector.
            embeddings: Vector embeddings.
            documents: Original text content (for ChromaDB storage).
            metadatas: Metadata dicts for each vector (must include document_id, chunk_index).
        """
        collection = self._get_collection(user_id)
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"Added {len(ids)} vectors for user {user_id}")

    def query(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Query the vector store for similar documents.

        Args:
            user_id: User ID for isolation.
            query_embedding: Query vector embedding.
            top_k: Maximum number of results to return.

        Returns:
            List of dicts with keys: id, document (content), metadata, distance.
        """
        try:
            collection = self._get_collection(user_id)
        except ValueError:
            # No collection exists for this user yet
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        results_list: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            results_list.append(
                {
                    "chunk_id": ids[i],
                    "content": documents[i] if documents else "",
                    "metadata": metadatas[i] if metadatas else {},
                    "distance": distances[i] if distances else 1.0,
                }
            )
        return results_list

    def delete_document(self, user_id: str, document_id: str) -> int:
        """Delete all vectors for a document from the user's collection.

        Returns the number of vectors deleted.
        """
        try:
            collection = self._get_collection(user_id)
        except ValueError:
            return 0

        # ChromaDB doesn't support direct delete by metadata filter in all versions,
        # so we query first to get IDs, then delete.
        results = collection.get(where={"document_id": document_id})
        ids = results.get("ids", [])
        if ids:
            collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} vectors for document {document_id}")
        return len(ids)

    def count(self, user_id: str) -> int:
        """Get the number of vectors stored for a user."""
        try:
            collection = self._get_collection(user_id)
            return collection.count()
        except ValueError:
            return 0

    def is_available(self) -> bool:
        """Check if ChromaDB is accessible."""
        try:
            self._get_client()
            return True
        except Exception:
            return False