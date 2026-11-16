"""Vector side of the policy search: clause embeddings in PostgreSQL with pgvector.

The agent service owns the ``policy_search`` schema; the core service owns ``core`` and never
reads this one. Rows are keyed by embedding model, so several models can be indexed side by side
and compared by the retrieval evaluation. The corpus is a few hundred clauses, so the search is an
exact scan ordered by cosine distance: an approximate index (HNSW) would only add recall loss.
"""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

from tramita_agents.search.corpus import Clause, corpus_version

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS policy_search;
CREATE TABLE IF NOT EXISTS policy_search.clause_embeddings (
    model        text   NOT NULL,
    clause_id    text   NOT NULL,
    product_code text   NOT NULL,
    corpus       text   NOT NULL,
    embedding    vector NOT NULL,
    PRIMARY KEY (model, clause_id)
);
"""


def _literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class VectorIndex:
    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo

    def _connect(self) -> psycopg.Connection[tuple[object, ...]]:
        return psycopg.connect(self.conninfo, connect_timeout=10)

    def rebuild(
        self, model: str, clauses: Sequence[Clause], vectors: Sequence[Sequence[float]]
    ) -> None:
        """Replaces every row of ``model`` in one transaction. Safe to run again."""
        if len(clauses) != len(vectors):
            raise ValueError("one vector per clause is needed")
        version = corpus_version(clauses)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute("DELETE FROM policy_search.clause_embeddings WHERE model = %s", (model,))
            cur.executemany(
                "INSERT INTO policy_search.clause_embeddings "
                "(model, clause_id, product_code, corpus, embedding) "
                "VALUES (%s, %s, %s, %s, %s::vector)",
                [
                    (model, c.clause_id, c.product_code, version, _literal(v))
                    for c, v in zip(clauses, vectors, strict=True)
                ],
            )

    def version(self, model: str) -> str | None:
        """The corpus version indexed for ``model``, or None if it has no rows."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('policy_search.clause_embeddings') IS NOT NULL")
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            cur.execute(
                "SELECT min(corpus), count(DISTINCT corpus) "
                "FROM policy_search.clause_embeddings WHERE model = %s",
                (model,),
            )
            found = cur.fetchone()
        if not found or found[0] is None or found[1] != 1:
            return None
        return str(found[0])

    def search(
        self, model: str, vector: Sequence[float], product_code: str | None, size: int
    ) -> list[tuple[str, float]]:
        """Clause ids with their cosine similarity, best first; equal distances by id."""
        literal = _literal(vector)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT clause_id, 1 - (embedding <=> %s::vector) AS similarity "
                "FROM policy_search.clause_embeddings "
                "WHERE model = %s AND (%s::text IS NULL OR product_code = %s) "
                "ORDER BY embedding <=> %s::vector, clause_id LIMIT %s",
                (literal, model, product_code, product_code, literal, size),
            )
            return [(str(row[0]), float(str(row[1]))) for row in cur.fetchall()]
