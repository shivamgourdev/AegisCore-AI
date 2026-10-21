from app.services.ingestion_service import extract_and_chunk

content = b"# Test Document\n\nThis is a test document for ingestion."
result = extract_and_chunk(content, 'test.md', 'text/markdown')
print(f"Chunks: {len(result['chunks'])}")
