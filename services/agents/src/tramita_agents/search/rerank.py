"""Second stage of the policy search: a cross-encoder that reads the query and each candidate
clause together and scores how well the clause answers the query.

It is slower than the first stage (one model pass per candidate), so it only reorders the few
candidates that the fused lexical and vector rankings return. It runs locally on CPU.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class Reranker(Protocol):
    @property
    def name(self) -> str: ...

    def scores(self, query: str, passages: Sequence[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, model: str, cache_dir: Path | None = None) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # noqa: PLC0415

        self._model = TextCrossEncoder(model, cache_dir=str(cache_dir) if cache_dir else None)
        self._name = model

    @property
    def name(self) -> str:
        return self._name

    def scores(self, query: str, passages: Sequence[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, list(passages))]
