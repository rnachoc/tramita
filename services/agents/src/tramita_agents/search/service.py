"""Policy search: find the clauses of a product's conditions that bear on a question or a claim.

Pipeline for one query:

1. **Mask** personal data in the query (same masking as documents, ADR 0011). Nothing below,
   models and logs included, sees the original text.
2. **Lexical** BM25 ranking from OpenSearch and **vector** ranking from pgvector, each limited to
   the policy's product and to ``candidates`` clauses.
3. **Fuse** both rankings by reciprocal rank (no score calibration needed).
4. **Rerank** the fused candidates with a local cross-encoder, when one is configured.

Every hit keeps its rank at each stage, so a citation can be explained and a bad answer traced
to the stage that lost the right clause. The lower stages are exposed as modes so the
evaluation can measure what each one adds.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from tramita_agents import telemetry
from tramita_agents.documents.pii import Pseudonymizer, mask
from tramita_agents.search.corpus import Clause, corpus_version
from tramita_agents.search.embeddings import Embedder
from tramita_agents.search.fusion import reciprocal_rank_fusion
from tramita_agents.search.lexical import LexicalIndex, SearchBackendError
from tramita_agents.search.rerank import Reranker
from tramita_agents.search.vectors import VectorIndex

DEFAULT_CANDIDATES = 20
MAX_QUERY_CHARS = 2000


class Mode(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"  # lexical + vector, reciprocal rank fusion
    RERANKED = "reranked"  # hybrid, then the cross-encoder


@dataclass(frozen=True)
class Hit:
    clause_id: str
    product_code: str
    article: str
    title: str
    text: str
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    fused_rank: int | None
    rerank_score: float | None


@dataclass(frozen=True)
class SearchResult:
    query: str  # masked
    masked: dict[str, int]  # kinds and counts of personal data removed, never values
    mode: Mode
    hits: list[Hit]
    timings_ms: dict[str, float] = field(default_factory=dict)


class PolicySearch:
    def __init__(
        self,
        clauses: Sequence[Clause],
        lexical: LexicalIndex,
        vectors: VectorIndex,
        embedder: Embedder,
        *,
        reranker: Reranker | None = None,
        candidates: int = DEFAULT_CANDIDATES,
    ) -> None:
        self.clauses = {c.clause_id: c for c in clauses}
        self.products = {c.product_code for c in clauses}
        self.version = corpus_version(clauses)
        self.lexical = lexical
        self.vectors = vectors
        self.embedder = embedder
        self.reranker = reranker
        self.candidates = candidates

    def check_ready(self) -> None:
        """Fails unless both indexes hold exactly the current corpus (run ``make index``)."""
        found = {
            "OpenSearch": self.lexical.version(),
            f"pgvector ({self.embedder.name})": self.vectors.version(self.embedder.name),
        }
        stale = [name for name, version in found.items() if version != self.version]
        if stale:
            raise SearchBackendError(
                f"Policy search index missing or out of date in {', '.join(stale)}: "
                "run `make index`."
            )

    def search(
        self,
        query: str,
        product_code: str | None = None,
        k: int = 5,
        mode: Mode | str = Mode.RERANKED,
    ) -> SearchResult:
        """Searches inside a ``policy_search`` span: mode, product, hits and stage timings."""
        with telemetry.span(
            "policy_search",
            **{"tramita.search.mode": str(mode), "tramita.product": product_code, "tramita.k": k},
        ) as current:
            result = self._search(query, product_code, k, mode)
            current.set_attribute("tramita.search.hits", len(result.hits))
            stage = telemetry.instruments().stage_duration
            for name, ms in result.timings_ms.items():
                current.set_attribute(f"tramita.search.{name}_ms", ms)
                stage.record(ms / 1000, {"tramita.stage": f"search.{name}"})
            return result

    def _search(
        self, query: str, product_code: str | None, k: int, mode: Mode | str
    ) -> SearchResult:
        mode = Mode(mode)
        if not query.strip():
            raise ValueError("the query is empty")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"the query is longer than {MAX_QUERY_CHARS} characters")
        if product_code is not None and product_code not in self.products:
            raise ValueError(f"unknown product code {product_code!r}")
        if mode is Mode.RERANKED and self.reranker is None:
            raise ValueError("no reranker is configured")
        timings: dict[str, float] = {}

        def timed(stage: str, started: float) -> None:
            timings[stage] = round((time.perf_counter() - started) * 1000, 2)

        started = time.perf_counter()
        masked = mask(query, Pseudonymizer())
        timed("mask", started)
        text = masked.text

        lexical: list[str] = []
        vector: list[str] = []
        if mode is not Mode.VECTOR:
            started = time.perf_counter()
            lexical = [cid for cid, _ in self.lexical.search(text, product_code, self.candidates)]
            timed("lexical", started)
        if mode is not Mode.LEXICAL:
            started = time.perf_counter()
            embedding = self.embedder.embed_query(text)
            timed("embed", started)
            started = time.perf_counter()
            vector = [
                cid
                for cid, _ in self.vectors.search(
                    self.embedder.name, embedding, product_code, self.candidates
                )
            ]
            timed("vector", started)
        lexical_rank = {cid: i for i, cid in enumerate(lexical, start=1)}
        vector_rank = {cid: i for i, cid in enumerate(vector, start=1)}

        if mode is Mode.LEXICAL:
            ranked = [(cid, 1.0 / rank) for cid, rank in lexical_rank.items()]
        elif mode is Mode.VECTOR:
            ranked = [(cid, 1.0 / rank) for cid, rank in vector_rank.items()]
        else:
            ranked = reciprocal_rank_fusion([lexical, vector])
        fused_rank = (
            {cid: i for i, (cid, _) in enumerate(ranked, start=1)}
            if mode in {Mode.HYBRID, Mode.RERANKED}
            else {}
        )

        rerank_scores: dict[str, float] = {}
        if mode is Mode.RERANKED and self.reranker is not None and ranked:
            started = time.perf_counter()
            pool = [cid for cid, _ in ranked[: self.candidates]]
            scores = self.reranker.scores(text, [self.clauses[cid].passage() for cid in pool])
            rerank_scores = dict(zip(pool, scores, strict=True))
            # Ties keep the fused order, so the reranker never shuffles equals at random.
            ranked = sorted(
                ((cid, rerank_scores[cid]) for cid in pool), key=lambda p: (-p[1], fused_rank[p[0]])
            )
            timed("rerank", started)

        hits = []
        for cid, score in ranked[:k]:
            clause = self.clauses[cid]
            hits.append(
                Hit(
                    clause_id=cid,
                    product_code=clause.product_code,
                    article=clause.article,
                    title=clause.title,
                    text=clause.text,
                    score=round(score, 6),
                    lexical_rank=lexical_rank.get(cid),
                    vector_rank=vector_rank.get(cid),
                    fused_rank=fused_rank.get(cid),
                    rerank_score=(round(rerank_scores[cid], 6) if cid in rerank_scores else None),
                )
            )
        return SearchResult(
            query=text, masked=masked.counts(), mode=mode, hits=hits, timings_ms=timings
        )


def build_indexes(
    clauses: Sequence[Clause], lexical: LexicalIndex, vectors: VectorIndex, embedder: Embedder
) -> None:
    """(Re)builds both indexes from the corpus. Idempotent."""
    lexical.rebuild(clauses)
    vectors.rebuild(embedder.name, clauses, embedder.embed_passages([c.passage() for c in clauses]))
