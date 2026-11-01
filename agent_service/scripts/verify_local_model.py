"""Probe local OpenAI-compatible models, optionally reporting completion throughput."""

import argparse
import json
import time

import httpx

from src.config import settings


def main(base_url: str, model: str) -> None:
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=60) as client:
            models = client.get(base_url.rstrip("/") + "/models")
            models.raise_for_status()
            result = client.post(
                base_url.rstrip("/") + "/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say hello in Hindi."}],
                    "max_tokens": 32,
                },
            )
            result.raise_for_status()
            payload = result.json()
            duration = time.perf_counter() - start
            tokens = payload.get("usage", {}).get("completion_tokens")
            print(
                json.dumps(
                    {
                        "ok": bool(payload["choices"]),
                        "elapsed_seconds": round(duration, 2),
                        "completion_tokens": tokens,
                        "tokens_per_second_including_request": tokens / duration
                        if tokens
                        else None,
                    }
                )
            )
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=settings.local_llm_base_url)
    parser.add_argument("--model", default=settings.local_llm_model)
    args = parser.parse_args()
    main(args.base_url, args.model)
