from app.services.ingestion_service import extract_and_chunk
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore

content = b"# Machine Learning\n\nMachine learning is a branch of AI.\n\n## Supervised Learning\nSupervised learning uses labeled data.\n\n## Unsupervised Learning\nUnsupervised learning finds hidden patterns."
result = extract_and_chunk(content, "test.md", "text/markdown")
print(f"Extraction: {len(result['chunks'])} chunks")

es = EmbeddingService()
embeddings = es.get_embeddings([c['content'] for c in result['chunks']])
print(f"Embeddings: {len(embeddings)} vectors of dim {len(embeddings[0])}")

vs = VectorStore()
user_id = "test_user_123"
vs.add_vectors(user_id=user_id, ids=[f"chunk_{i}" for i in range(len(result['chunks']))], embeddings=embeddings, documents=[c['content'] for c in result['chunks']], metadatas=[{'document_id': 'doc1', 'chunk_index': c['chunk_index'], 'filename': 'test.md'} for c in result['chunks']])
print(f"Stored {len(result['chunks'])} vectors")

query_emb = es.get_embedding("What is supervised learning?")
results = vs.query(user_id=user_id, query_embedding=query_emb, top_k=5)
print(f"Retrieved {len(results)} chunks")
for r in results:
    print(f"  {r['chunk_id']}: {r['content'][:60]}...")
