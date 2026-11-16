"""Builds the policy search from configuration, and the ``tramita-index-policies`` command.

Usage: ``make index`` with the stack up. It (re)builds the OpenSearch index and the pgvector rows
of the configured embedding model from ``data/policies/clauses.json``; running it again is
harmless. The first run downloads the models into ``models-cache/``.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence

from tramita_agents.search.corpus import corpus_version, load_clauses
from tramita_agents.search.embeddings import FastEmbedEmbedder
from tramita_agents.search.lexical import LexicalIndex
from tramita_agents.search.rerank import FastEmbedReranker
from tramita_agents.search.service import PolicySearch, build_indexes
from tramita_agents.search.vectors import VectorIndex
from tramita_agents.settings import Settings


def build_policy_search(
    settings: Settings,
    embedding_model: str | None = None,
    reranker_model: str | None = None,
) -> PolicySearch:
    """The search as configured; the model arguments override the settings (evaluation)."""
    embedding = embedding_model or settings.tramita_embedding_model
    reranker = settings.tramita_reranker_model if reranker_model is None else reranker_model
    cache = settings.tramita_models_dir
    return PolicySearch(
        clauses=load_clauses(),
        lexical=LexicalIndex.connect(settings.opensearch_url),
        vectors=VectorIndex(settings.postgres_conninfo),
        embedder=FastEmbedEmbedder(embedding, cache),
        reranker=FastEmbedReranker(reranker, cache) if reranker.strip() else None,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Index the policy conditions for search.")
    parser.add_argument(
        "--embedding-model",
        action="append",
        help="index with this model instead of the configured one (repeatable)",
    )
    args = parser.parse_args(argv)
    settings = Settings()
    clauses = load_clauses()
    lexical = LexicalIndex.connect(settings.opensearch_url)
    vectors = VectorIndex(settings.postgres_conninfo)
    for model in args.embedding_model or [settings.tramita_embedding_model]:
        started = time.perf_counter()
        embedder = FastEmbedEmbedder(model, settings.tramita_models_dir)
        build_indexes(clauses, lexical, vectors, embedder)
        print(
            f"Indexed {len(clauses)} clauses (corpus {corpus_version(clauses)}) in OpenSearch and "
            f"pgvector with {model} in {time.perf_counter() - started:.1f} s"
        )


if __name__ == "__main__":
    main()
