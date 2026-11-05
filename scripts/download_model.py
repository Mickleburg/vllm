"""Download a pinned HF snapshot once; a valid local snapshot needs no network."""
import json
import os
import re
from pathlib import Path

from huggingface_hub import snapshot_download


def main():
    model_id = os.environ["MODEL_ID"]
    revision = os.environ["MODEL_REVISION"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("MODEL_REVISION must be a full commit SHA")
    target = Path(os.environ.get("MODEL_PATH", "/models/model"))
    target.mkdir(parents=True, exist_ok=True)
    marker = target / ".complete.json"
    if marker.exists():
        manifest = json.loads(marker.read_text())
        if manifest["model_id"] != model_id or manifest["revision"] != revision:
            raise ValueError("Use a new PVC when changing the model or revision")
        if (manifest["model_id"] == model_id and manifest["revision"] == revision
                and all((target / name).is_file()
                        and (target / name).stat().st_size == size
                        for name, size in manifest["files"].items())):
            print("model_cache_hit", flush=True)
            return
    # Never log exception text: remote errors may contain credentials/URLs.
    snapshot_download(
        repo_id=model_id, revision=revision, local_dir=target,
        token=os.environ.get("HF_TOKEN") or False,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.jinja"],
        max_workers=2,
    )
    files = {str(p.relative_to(target)): p.stat().st_size
             for p in target.rglob("*")
             if p.is_file() and ".cache" not in p.relative_to(target).parts
             and p.name not in {".complete.json", ".complete.tmp"}}
    if "config.json" not in files or not any(n.endswith(".safetensors") for n in files):
        raise ValueError("Incomplete model snapshot")
    temporary = target / ".complete.tmp"
    temporary.write_text(json.dumps({"model_id": model_id, "revision": revision,
                                     "files": files}, sort_keys=True))
    temporary.replace(marker)
    print("model_download_complete", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("model_download_failed: check connectivity, HF_TOKEN and storage", flush=True)
        raise SystemExit(1) from None
