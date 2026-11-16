"""Sentence embeddings computed locally, so the vector search runs without any API key.

Models run on CPU through fastembed (ONNX Runtime, no PyTorch) and are downloaded once from
Hugging Face into the models cache. Which model is used is configuration; the policy search
measures the candidates with ``make eval-retrieval`` (ADR 0012).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

# Models trained with instruction prefixes lose quality without them.
PREFIXES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model: str, cache_dir: Path | None = None) -> None:
        # Imported here: loading ONNX Runtime is slow and most commands never embed anything.
        from fastembed import TextEmbedding  # noqa: PLC0415

        self._model = TextEmbedding(model, cache_dir=str(cache_dir) if cache_dir else None)
        self._query_prefix, self._passage_prefix = PREFIXES.get(model, ("", ""))
        self._name = model

    @property
    def name(self) -> str:
        return self._name

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [self._passage_prefix + t for t in texts]
        return [vector.tolist() for vector in self._model.embed(prefixed)]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.embed([self._query_prefix + text])))
        result: list[float] = vector.tolist()
        return result
