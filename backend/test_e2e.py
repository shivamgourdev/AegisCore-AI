import urllib.request, json

def req(method, path, data=None, headers=None):
    url = "http://127.0.0.1:8009" + path
    req_headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=30)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return "ERR", str(e)[:200]

print("=== 1. Register ===")
status, body = req("POST", "/api/v1/auth/register", data={"email":"e2e_test@example.com","password":"securepass123"})
print("  Status:", status)

print()
print("=== 2. Login ===")
status, body = req("POST", "/api/v1/auth/login", data={"email":"e2e_test@example.com","password":"securepass123"})
print("  Status:", status)
token = None
if status == 200:
    lb = json.loads(body)
    token = lb["access_token"]
    print("  Token:", token[:30])
else:
    print("  Body:", body[:200])

print()
print("=== 3. Upload document ===")
if token:
    content = b"# Machine Learning Basics\n\nMachine learning is a branch of artificial intelligence.\n\n## Supervised Learning\nSupervised learning uses labeled training data.\n\n## Unsupervised Learning\nUnsupervised learning finds hidden patterns."
    boundary = "----WebKitFormBoundary7ma4YEU3k71Z1w6i"
    body = b"--" + boundary.encode() + b"\r\n"
    body += b'Content-Disposition: form-data; name="file"; filename="ml_basics.md"\r\n'
    body += b"Content-Type: text/markdown\r\n\r\n"
    body += content + b"\r\n"
    body += b"--" + boundary.encode() + b"--\r\n"
    req_obj = urllib.request.Request("http://127.0.0.1:8009/api/v1/rag/ingest", method="POST")
    req_obj.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    req_obj.add_header("Authorization", "Bearer " + token)
    req_obj.data = body
    try:
        resp = urllib.request.urlopen(req_obj, timeout=30)
        print("  Upload status:", resp.status)
        print(f"  Upload body: {resp.read().decode()[:200]}")
    except urllib.error.HTTPError as e:
        print(f"  Upload status: {e.code}")
        print(f"  Upload body: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"  Upload error: {e}")

print()
print("=== 4. Ask question about ML ===")
if token:
    status, body = req("POST", "/api/v1/rag/query", data={"question":"What is supervised learning?","top_k":5}, headers={"Authorization": "Bearer " + token})
    print(f"  Status: {status}")
    if status == 200:
        rb = json.loads(body)
        print(f"  Answer: {rb.get('answer', '')[:300]}")
        print(f"  Citations: {len(rb.get('citations', []))}")
        for c in rb.get('citations', []):
            print(f"    - {c.get('filename', 'unknown')} (page {c.get('page_number')}, section: {c.get('section')})")
        print(f"  Abstained: {rb.get('abstained')}")
        print(f"  Reason: {rb.get('abstention_reason')}")
    else:
        print(f"  Body: {body[:200]}")

print()
print("=== 5. Ask unrelated question ===")
if token:
    status, body = req("POST", "/api/v1/rag/query", data={"question":"What is the capital of France?","top_k":5}, headers={"Authorization": "Bearer " + token})
    print(f"  Status: {status}")
    if status == 200:
        rb = json.loads(body)
        print(f"  Answer: {rb.get('answer', '')[:200]}")
        print(f"  Abstained: {rb.get('abstained')}")
        print(f"  Reason: {rb.get('abstention_reason')}")
    else:
        print(f"  Body: {body[:200]}")

print()
print("=== ALL E2E TESTS COMPLETE ===")
