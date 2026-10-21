from app.services.ingestion_service import extract_and_chunk
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.rerank_service import RerankService
from app.services.generation_service import GenerationService
import uuid

content = b"# Machine Learning\n\nMachine learning is a branch of AI.\n\n## Supervised Learning\nSupervised learning uses labeled data.\n\n## Unsupervised Learning\nUnsupervised learning finds patterns."
result = extract_and_chunk(content, "test.md", "text/markdown")
print(f"Extraction: {len(result['chunks'])} chunks")

es = EmbeddingService()
embeddings = es.get_embeddings([c["content"] for c in result['chunks']])
print(f"Embeddings: {len(embeddings)} vectors of dim {len(embeddings[0])}")

vs = VectorStore()
user_id = "test_user"
chunk_ids = [str(uuid.uuid4()) for _ in result['chunks']]
vs.add_vectors(user_id=user_id, ids=chunk_ids, embeddings=embeddings, documents=[c["content"] for c in result["chunks"]], metadatas=[{"document_id": "doc1"} for c in result["chunks"]])
print(f"Stored {len(chunk_ids)} vectors")

query_emb = es.get_embedding("What is supervised learning?")
results = vs.query(user_id=user_id, query_embedding=query_emb, top_k=5)
print(f"Retrieved {len(results)} chunks")
for r in results:
    print(f"  {r['chunk_id']}: {r['content'][:60]}...")

rs = RerankService()
reranked = rs.rerank(query="What is supervised learning?", results=results, top_k=3)
print(f"Reranked: {len(reranked)} results")
for r in reranked:
    print(f"  Score: {r.get('rerank_score', 0):.3f}, Content: {r['content'][:50]}...")

gs = GenerationService()
context_text = "\n\n".join([f"[{i+1}] {c['content']}" for i, c in enumerate(reranked)])
print(f"\nContext for generation: {context_text[:100]}...")
answer = gs.generate(prompt=f"Answer based on context: {context_text}\n\nQuestion: What is supervised learning?", system_prompt="You are a helpful assistant.")
print(f"\nGenerated answer: {answer[:200]}...")
