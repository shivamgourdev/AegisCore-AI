from app.services.ingestion_service import extract_and_chunk
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore

# Simulate the upload process
content = b"# Machine Learning Basics\n\nMachine learning is a branch of artificial intelligence.\n\n## Supervised Learning\nSupervised learning uses labeled training data to learn a mapping function from inputs to outputs."

# Extract and chunk
result = extract_and_chunk(content, "test.md", "text/markdown")
print(f"Extraction: {len(result['chunks'])} chunks")

# Get embeddings
es = EmbeddingService()
embeddings = es.get_embeddings([c["content"] for c in result["chunks"]])
print(f"Embeddings: {len(embeddings)} vectors of dim {len(embeddings[0])}")

# Store in ChromaDB
vs = VectorStore()
user_id = "test_user_123"
chunk_ids = [str(uuid.uuid4()) for _ in result["chunks"]]
vs.add_vectors(
    user_id=user_id,
    ids=chunk_ids,
    embeddings=embeddings,
    documents=[c["content"] for c in result["chunks"]],
    metadatas=[{"document_id": "doc1", "chunk_index": c["chunk_index"], "filename": "test.md"} for c in result["chunks"]]
)
print(f"Stored {len(chunk_ids)} vectors for user {user_id}")

# Query
query_embedding = es.get_embedding("What is supervised learning?")
results = vs.query(user_id=user_id, query_embedding=query_embedding, top_k=5)
print(f"\nQuery results: {len(results)} chunks")
for r in results:
    print(f"  Chunk: {r['chunk_id']}, Content: {r['content'][:60]}..., Metadata: {r.get('metadata', {})}")
