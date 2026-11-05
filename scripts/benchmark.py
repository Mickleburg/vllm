"""Small streaming benchmark. TTFT starts at request send and ends at first content."""
import argparse
import json
import os
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen


def generate(prompt, max_tokens):
    body = {"model": "qwen-cpu", "messages": [{"role": "user", "content": prompt}],
            "stream": True, "stream_options": {"include_usage": True},
            "temperature": 0, "max_tokens": max_tokens, "ignore_eos": True}
    request = Request(os.environ.get("API_BASE", "http://127.0.0.1:8000") +
                      "/v1/chat/completions", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json",
                               "Authorization": "Bearer " + os.environ["VLLM_API_KEY"]})
    started = time.perf_counter()
    first = None
    usage = None
    done = False
    with urlopen(request, timeout=300) as response:
        for line in response:
            if not line.startswith(b"data: "):
                continue
            data = line[6:].strip()
            if data == b"[DONE]":
                done = True
                break
            chunk = json.loads(data)
            if first is None and any(c.get("delta", {}).get("content") for c in chunk.get("choices", [])):
                first = time.perf_counter() - started
            if chunk.get("usage"):
                usage = chunk["usage"]
    elapsed = time.perf_counter() - started
    if first is None or usage is None or not done:
        raise RuntimeError("Incomplete streaming response or missing usage")
    return {"ttft_s": first, "e2e_s": elapsed, **usage}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=32)
    args = parser.parse_args()
    if min(args.requests, args.concurrency, args.max_tokens) < 1:
        parser.error("All numeric arguments must be positive")
    # One warmup request is excluded from results.
    generate("Count from one to ten.", 8)
    results = []
    run_id = uuid.uuid4().hex
    for label, prompt in [
        ("short", "Explain why the sky is blue."),
        ("long", "Read these notes. " + "The sky scatters sunlight. " * 160 +
         "Summarize the notes in a few sentences."),
    ]:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            # A unique prefix prevents cross-request prefix-cache hits.
            samples = list(pool.map(lambda index: generate(f"{run_id}-{index}: {prompt}", args.max_tokens),
                                    range(args.requests)))
        wall = time.perf_counter() - started
        results.append({"case": label, "requests": args.requests,
                        "concurrency": args.concurrency, "max_tokens": args.max_tokens,
                        "prompt_tokens": [s["prompt_tokens"] for s in samples],
                        "ttft_p50_s": statistics.median(s["ttft_s"] for s in samples),
                        "e2e_p50_s": statistics.median(s["e2e_s"] for s in samples),
                        "output_tokens_per_s": sum(s["completion_tokens"] for s in samples) / wall,
                        "requests_per_s": len(samples) / wall, "wall_s": wall,
                        "samples": samples})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
