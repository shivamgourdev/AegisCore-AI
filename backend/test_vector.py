from app.services.vector_store import VectorStore
vs = VectorStore()
print("Vector store created")
vs.add_vectors("user_test", ["chunk1"], [[0.1]*768], ["test content"], [{"document_id": "doc1", "chunk_index": 0, "filename": "test.md"}])
print("Vector added")
results = vs.query("user_test", [0.1]*768, top_k=5)
print(f"Found {len(results)} results")
for r in results:
    print(f"  Chunk: {r['chunk_id']}, Content: {r['content'][:50]}...")
print("Vector store works!")
