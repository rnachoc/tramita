"""Reciprocal rank fusion (Cormack, Clarke and Büttcher, SIGIR 2009).

Lexical and vector scores live on different scales (BM25 is unbounded, cosine similarity is not),
so the rankings are fused by position instead: ``score(d) = sum(1 / (k + rank_i(d)))`` over the
rankings that contain ``d``, with ranks starting at 1. ``k = 60`` is the value from the paper; it
damps the advantage of the very first positions so that agreement between rankings counts more.
"""

from __future__ import annotations

from collections.abc import Sequence

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = RRF_K
) -> list[tuple[str, float]]:
    """Fuses rankings of ids, best first. Ties go to the better single rank, then to the id."""
    if k < 1:
        raise ValueError("k must be at least 1")
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        if len(set(ranking)) != len(ranking):
            raise ValueError("a ranking repeats an id")
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best_rank[item] = min(rank, best_rank.get(item, rank))
    return sorted(scores.items(), key=lambda pair: (-pair[1], best_rank[pair[0]], pair[0]))
