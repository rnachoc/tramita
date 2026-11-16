"""Stand-ins for the search backends and local models, so the search runs without the stack."""

from collections.abc import Sequence

from tramita_agents.search.corpus import corpus_version, load_clauses
from tramita_agents.search.lexical import LexicalIndex
from tramita_agents.search.vectors import VectorIndex

CLAUSES = load_clauses()
VERSION = corpus_version(CLAUSES)


class FakeLexical(LexicalIndex):
    def __init__(self, ranking: list[str], version: str | None = VERSION) -> None:
        self.ranking = ranking
        self._version = version
        self.queries: list[tuple[str, str | None]] = []

    def version(self) -> str | None:
        return self._version

    def search(self, query: str, product_code: str | None, size: int) -> list[tuple[str, float]]:
        self.queries.append((query, product_code))
        return [(cid, 10.0 - i) for i, cid in enumerate(self.ranking[:size])]


class FakeVectors(VectorIndex):
    def __init__(self, ranking: list[str], version: str | None = VERSION) -> None:
        self.ranking = ranking
        self._version = version

    def version(self, model: str) -> str | None:
        return self._version

    def search(
        self, model: str, vector: Sequence[float], product_code: str | None, size: int
    ) -> list[tuple[str, float]]:
        return [(cid, 0.9 - i / 100) for i, cid in enumerate(self.ranking[:size])]


class FakeEmbedder:
    name = "fake-embedder"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [1.0, 0.0]


class FakeReranker:
    name = "fake-reranker"

    def __init__(self, favourite: str) -> None:
        self.favourite = favourite
        self.queries: list[str] = []

    def scores(self, query: str, passages: Sequence[str]) -> list[float]:
        self.queries.append(query)
        return [1.0 if self.favourite in p else 0.0 for p in passages]
