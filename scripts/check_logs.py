"""Check captured server logs against a successful smoke-test response."""
import json
import os
import sys
from pathlib import Path

smoke = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
logs = Path(sys.argv[2]).read_text(encoding="utf-8-sig")
for value in (smoke["marker"], smoke["response"].strip(), os.environ["VLLM_API_KEY"]):
    if value and (value in logs or json.dumps(value, ensure_ascii=True)[1:-1] in logs):
        raise SystemExit("Privacy check failed: sensitive test content found in server logs")
events = []
for line in logs.splitlines():
    try:
        events.append(json.loads(line[line.index("{"):]))
    except (ValueError, json.JSONDecodeError):
        continue
if not any(e.get("event") == "http_request" and e.get("status") == 200
           and e.get("route") == "/v1/chat/completions" for e in events):
    raise SystemExit("No successful inference access-log event found")
print("Log privacy passed: prompt marker, response and API token absent; HTTP 200 event present")
