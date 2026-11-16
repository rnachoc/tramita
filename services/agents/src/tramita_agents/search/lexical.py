"""Lexical side of the policy search: BM25 over the clauses in OpenSearch.

The index uses a Spanish analyzer (stop words, light stemmer) followed by ASCII folding, so a
query typed without accents ("danos por agua") matches the conditions ("daños por agua"). Exact
terms of the conditions, such as "carencia", "franquicia" or "hurto", are where BM25 beats the
vectors. Titles weigh twice the body: they name what the clause is about.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx

from tramita_agents.search.corpus import Clause, corpus_version

INDEX = "policy-clauses"

_TEXT = {"type": "text", "analyzer": "spanish_folded"}
INDEX_BODY: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "filter": {
                "spanish_stop": {"type": "stop", "stopwords": "_spanish_"},
                "spanish_stemmer": {"type": "stemmer", "language": "light_spanish"},
            },
            "analyzer": {
                "spanish_folded": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "spanish_stop", "spanish_stemmer", "asciifolding"],
                }
            },
        },
    },
    "mappings": {
        "dynamic": "strict",
        "_meta": {},
        "properties": {
            "clause_id": {"type": "keyword"},
            "product_code": {"type": "keyword"},
            "keys": {"type": "keyword"},
            "product_name": _TEXT,
            "article": _TEXT,
            "title": _TEXT,
            "text": _TEXT,
        },
    },
}
FIELDS = ["title^2", "text", "article", "product_name"]


class SearchBackendError(RuntimeError):
    """A search backend that is unreachable or refuses a request. The message says which."""


class LexicalIndex:
    def __init__(self, client: httpx.Client, index: str = INDEX) -> None:
        self.client = client
        self.index = index

    @classmethod
    def connect(cls, url: str, timeout: float = 10.0) -> LexicalIndex:
        return cls(httpx.Client(base_url=url, timeout=timeout))

    def _check(self, response: httpx.Response, action: str) -> dict[str, Any]:
        if response.is_error:
            raise SearchBackendError(
                f"OpenSearch refused to {action} ({response.status_code}): {response.text[:300]}"
            )
        body: dict[str, Any] = response.json()
        return body

    def rebuild(self, clauses: Sequence[Clause]) -> None:
        """Drops and recreates the index with every clause. Safe to run again."""
        self.client.delete(f"/{self.index}", params={"ignore_unavailable": "true"})
        body = {
            **INDEX_BODY,
            "mappings": {**INDEX_BODY["mappings"], "_meta": {"corpus": corpus_version(clauses)}},
        }
        self._check(self.client.put(f"/{self.index}", json=body), "create the index")
        lines: list[str] = []
        for c in clauses:
            document = {
                "clause_id": c.clause_id,
                "product_code": c.product_code,
                "keys": list(c.keys),
                "product_name": c.product_name,
                "article": c.article,
                "title": c.title,
                "text": c.text,
            }
            lines.append(json.dumps({"index": {"_id": c.clause_id}}))
            lines.append(json.dumps(document, ensure_ascii=False))
        result = self._check(
            self.client.post(
                f"/{self.index}/_bulk",
                params={"refresh": "true"},
                content="\n".join(lines) + "\n",
                headers={"Content-Type": "application/x-ndjson"},
            ),
            "index the clauses",
        )
        if result.get("errors"):
            raise SearchBackendError("OpenSearch rejected some clauses in the bulk request")

    def version(self) -> str | None:
        """The corpus version the index was built from, or None if there is no index."""
        response = self.client.get(f"/{self.index}/_mapping")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        body = self._check(response, "read the mapping")
        meta: dict[str, str] = body[self.index]["mappings"].get("_meta", {})
        return meta.get("corpus")

    def search(self, query: str, product_code: str | None, size: int) -> list[tuple[str, float]]:
        """Clause ids with their BM25 scores, best first."""
        match = {"multi_match": {"query": query, "fields": FIELDS, "type": "best_fields"}}
        filters = [{"term": {"product_code": product_code}}] if product_code else []
        body = {
            "size": size,
            "_source": False,
            # Equal scores are ordered by id, so the same query always ranks the same way.
            "sort": ["_score", {"clause_id": "asc"}],
            "track_scores": True,
            "query": {"bool": {"must": [match], "filter": filters}},
        }
        result = self._check(
            self.client.post(f"/{self.index}/_search", json=body), "search the clauses"
        )
        return [(hit["_id"], float(hit["_score"])) for hit in result["hits"]["hits"]]
