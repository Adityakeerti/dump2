"""Probe real recordings without printing their transcripts."""

import argparse
import asyncio
import json
from pathlib import Path

from src.config import settings
from src.providers.speech import transcribe_with_fallback


async def main(paths: list[Path], provider: str) -> None:
    if settings.demo_mode:
        raise SystemExit("Disable DEMO_MODE for live STT verification")
    settings.stt_provider_order = provider
    failures = 0
    for path in paths:
        try:
            data = path.read_bytes()
            if len(data) > settings.max_upload_bytes:
                raise ValueError("Recording exceeds upload cap")
            transcript, language, served = await transcribe_with_fallback(data, path.name, "hi")
            print(
                json.dumps(
                    {
                        "file": path.name,
                        "ok": True,
                        "transcript_chars": len(transcript),
                        "language": language,
                        "provider": served,
                    }
                )
            )
        except Exception as exc:
            failures += 1
            print(json.dumps({"file": path.name, "ok": False, "error_type": type(exc).__name__}))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=["local", "groq", "sarvam"])
    parser.add_argument("recordings", type=Path, nargs="+")
    args = parser.parse_args()
    asyncio.run(main(args.recordings, args.provider))
