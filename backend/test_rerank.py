from app.services.rerank_service import RerankService
rs = RerankService()
print("Rerank service created, enabled:", rs.enabled)
results = [{"content": "Machine learning is a subset of AI", "score": 0.5}, {"content": "Python is a programming language", "score": 0.3}]
reranked = rs.rerank("What is machine learning?", results)
print(f"Reranked {len(reranked)} results")
for r in reranked:
    print(f"  Score: {r.get('rerank_score', 0):.3f}, Content: {r['content'][:50]}")
