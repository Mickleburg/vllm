"""HTTP smoke checks; print a synthetic response for comparison with server logs."""
import json
import os
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


base = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
key = os.environ["VLLM_API_KEY"]
marker = "privacy_probe_" + uuid.uuid4().hex


def request(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers)
    try:
        with urlopen(req, timeout=600) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, None


body = {"model": "qwen-cpu", "messages": [{"role": "user", "content":
        "Reply with exactly this word: " + marker}], "max_tokens": 32, "temperature": 0}
for token in (None, "incorrect-token"):
    status, _ = request("/v1/chat/completions", body, token)
    assert status == 401, f"Expected 401, got {status}"
status, models = request("/v1/models", token=key)
assert status == 200 and any(m["id"] == "qwen-cpu" for m in models["data"])
status, _ = request("/v1/chat/completions", {**body, "model": marker}, key)
assert status == 404, f"Expected 404 for an unknown model, got {status}"
status, answer = request("/v1/chat/completions?private=" + marker, body, key)
assert status == 200, f"Expected 200, got {status}"
content = answer["choices"][0]["message"]["content"]
assert content.strip(), "Empty model response"
print(json.dumps({"auth": "passed", "inference": "passed", "marker": marker,
                  "response": content, "usage": answer.get("usage")}, ensure_ascii=True))
