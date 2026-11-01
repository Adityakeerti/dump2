import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    index: int
    section: str | None
    text: str


HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
ATOMIC = re.compile(r"^\s*(?:\||\d+[.)]\s|[-*+]\s)")


def chunk_text(
    text: str,
    target_tokens: int = 400,
    overlap_tokens: int = 50,
    token_count: Callable[[str], int] | None = None,
) -> list[Chunk]:
    if target_tokens < 1 or overlap_tokens < 0:
        raise ValueError("Invalid chunk sizes")
    count = token_count or (lambda value: len(value.split()))
    result: list[Chunk] = []
    section: str | None = None
    buffer: list[str] = []

    def flush(overlap: bool = True) -> None:
        nonlocal buffer
        if not buffer:
            return
        result.append(Chunk(len(result), section, "\n".join(buffer)))
        tail: list[str] = []
        if overlap:
            for unit in reversed(buffer):
                if count("\n".join([unit, *tail])) > overlap_tokens:
                    if not ATOMIC.match(unit):
                        suffix: list[str] = []
                        for word in reversed(unit.split()):
                            if (
                                count(" ".join([word, *suffix]) + "\n" + "\n".join(tail))
                                > overlap_tokens
                            ):
                                break
                            suffix.insert(0, word)
                        if suffix:
                            tail.insert(0, " ".join(suffix))
                    break
                tail.insert(0, unit)
        buffer = tail

    for line in text.replace("\r\n", "\n").splitlines():
        line = line.strip()
        heading = HEADING.match(line)
        if heading:
            flush(False)
            section = heading.group(1)[:500]
            continue
        if not line:
            continue
        if ATOMIC.match(line):
            if count(line) > target_tokens:
                raise ValueError(
                    "A table row or list item exceeds the token budget; split the source item"
                )
            units = [line]
        else:
            units = []
            words: list[str] = []
            prose_budget = target_tokens - min(overlap_tokens, target_tokens // 2)
            for word in line.split():
                if count(word) > prose_budget:
                    raise ValueError("A single token sequence exceeds the chunk budget")
                if words and count(" ".join([*words, word])) > prose_budget:
                    units.append(" ".join(words))
                    words = []
                words.append(word)
            if words:
                units.append(" ".join(words))
        for unit in units:
            if buffer and count("\n".join([*buffer, unit])) > target_tokens:
                flush()
                if buffer and count("\n".join([*buffer, unit])) > target_tokens:
                    buffer = []
            buffer.append(unit)
    flush(False)
    return result
