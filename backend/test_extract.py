from app.services.ingestion_service import extract_and_chunk
content = b"# Machine Learning Basics\n\nMachine learning is a branch of artificial intelligence.\n\n## Supervised Learning\nSupervised learning uses labeled training data to learn a mapping function from inputs to outputs."
result = extract_and_chunk(content, 'test.md', 'text/markdown')
print(f"Extraction successful: {len(result['chunks'])} chunks")
for chunk in result['chunks']:
    print(f"  Chunk {chunk['chunk_index']}: {len(chunk['content'])} chars")
except Exception as e:
    import traceback
    traceback.print_exc()
