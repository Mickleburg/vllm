"""Create a local ignored env file without printing credentials."""
import os
import secrets

fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
    stream.write("HF_TOKEN=" + os.environ.get("HF_TOKEN", "") + "\n")
    stream.write("VLLM_API_KEY=" + secrets.token_urlsafe(32) + "\n")
print("Created .env; keep it local. Existing files are never overwritten.")
