from app.services.ingestion_service import extract_and_chunk

content = b"# Test Document 5\n\nThis is test document 5 for ingestion."
result = extract_and_chunk(content, 'test5.md', 'text/markdown')
print(f"Chunks 5: {len(result['chunks'])}")
