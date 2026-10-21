import chromadb
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore
from app.core.config import settings

vs = VectorStore()
client = vs._get_client()
collections = client.list_collections()
print("ChromaDB collections:")
for c in collections:
    print(f"  {c.name}: {c.count()} chunks")

es = EmbeddingService()
emb = es.get_embedding("What is supervised learning?")
print(f"\nEmbedding dimension: {len(emb)}")

for c in collections:
    collection = client.get_collection(name=c.name)
    results = collection.query(
        query_embeddings=[emb],
        n_results=min(5, c.count()),
        include=["documents", "metadatas", "distances"]
    )
    ids = results.get("ids", [[]])[0]
    if ids:
        print(f"\nCollection {c.name}: {len(ids)} results")
        for i, doc_id in enumerate(ids):
            print(f"  Result {i}: id={doc_id}, doc={results['documents'][0][i][:50]}..., meta={results['metadatas'][0][i]}")
    else:
        print(f"\nCollection {c.name}: 0 results")
