"""Live, opt-in provider probe. Reports protocol success without printing payloads/keys."""

import argparse
import asyncio
import json
import time

from src.providers.hosted import configured_providers


async def main(name: str, tools: bool) -> None:
    provider = configured_providers().get(name)
    if not provider:
        raise SystemExit(f"{name} is not configured")
    schema = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo the request",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]
    start = time.perf_counter()
    try:
        result = await provider.generate(
            system="For a tool test call echo with text='hello'. Otherwise answer briefly.",
            user="Call echo" if tools else "What does the passage say?",
            context=["The city office opens at 10 AM."],
            language="en",
            tools=schema if tools else None,
        )
        print(
            json.dumps(
                {
                    "provider": name,
                    "ok": True,
                    "tool_calls_received": len(result.tool_calls),
                    "elapsed_seconds": round(time.perf_counter() - start, 2),
                    "model": provider.model,
                }
            )
        )
    except Exception as exc:
        print(json.dumps({"provider": name, "ok": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=["local", "groq", "sarvam"])
    parser.add_argument("--tools", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.provider, args.tools))
