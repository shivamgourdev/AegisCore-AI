from app.services.ingestion_service import extract_and_chunk
content = b"# Machine Learning Basics\n\nThis is a test document about machine learning."
result = extract_and_chunk(content, "test.md", "text/markdown")
print("Extraction successful:", len(result["chunks"]), "chunks")
for chunk in result["chunks"]:
    print("  Chunk", chunk["chunk_index"], ":", len(chunk["content"]), "chars")
except Exception as e:
    import traceback
    traceback.print_exc()
