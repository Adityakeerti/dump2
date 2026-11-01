"""Isolated document parsing worker. Writes extracted UTF-8 text, never credentials."""
import sys
from pathlib import Path

from src.knowledge.ingestion import read_source


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    try:
        content = read_source(Path(sys.argv[1]))
        sys.stdout.buffer.write(content.encode("utf-8"))
    except Exception:
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
