import hashlib
import math
from typing import Protocol

from src.config import settings


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> list[float]: ...


class DeterministicEmbedder:
    """Offline-safe fallback used in DEMO_MODE and tests."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.name = "demo-hash-v1"

    def embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        tokens = text.removeprefix("query: ").removeprefix("passage: ").lower().split()
        for token in tokens:
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            values[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


class SentenceTransformerEmbedder:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = settings.embed_model
        self.model = SentenceTransformer(
            settings.embed_model,
            local_files_only=settings.embedding_local_files_only or settings.demo_mode,
        )
        if self.model.get_sentence_embedding_dimension() != 384:
            raise ValueError("Embedding model must produce 384 dimensions")

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        if not settings.use_sentence_transformer:
            _embedder = DeterministicEmbedder(settings.embed_dimension)
        else:
            _embedder = SentenceTransformerEmbedder()
    return _embedder
