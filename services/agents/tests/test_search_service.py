import json

import httpx
import pytest
from search_fixtures import CLAUSES, VERSION, FakeEmbedder, FakeLexical, FakeReranker, FakeVectors

from tramita_agents.search.lexical import LexicalIndex, SearchBackendError
from tramita_agents.search.service import Mode, PolicySearch
from tramita_agents.search.vectors import _literal


def _search(
    lexical: list[str], vector: list[str], reranker: FakeReranker | None = None
) -> PolicySearch:
    return PolicySearch(
        CLAUSES, FakeLexical(lexical), FakeVectors(vector), FakeEmbedder(), reranker=reranker
    )


def test_each_mode_uses_only_its_stages() -> None:
    search = _search(["HP-2.1", "HP-3.2"], ["HP-3.2", "HP-6.2"], FakeReranker("HP-6.2"))

    lexical = search.search("agua", "HP", mode="lexical")
    vector = search.search("agua", "HP", mode=Mode.VECTOR)
    hybrid = search.search("agua", "HP", mode=Mode.HYBRID)

    assert [h.clause_id for h in lexical.hits] == ["HP-2.1", "HP-3.2"]
    assert set(lexical.timings_ms) == {"mask", "lexical"}
    assert [h.clause_id for h in vector.hits] == ["HP-3.2", "HP-6.2"]
    assert set(vector.timings_ms) == {"mask", "embed", "vector"}
    assert [h.clause_id for h in hybrid.hits] == ["HP-3.2", "HP-2.1", "HP-6.2"]
    assert "rerank" not in hybrid.timings_ms


def test_reranker_reorders_the_fused_candidates_and_hits_keep_every_rank() -> None:
    passage_of_62 = next(c for c in CLAUSES if c.clause_id == "HP-6.2").text[:40]
    search = _search(["HP-2.1", "HP-3.2"], ["HP-3.2", "HP-6.2"], FakeReranker(passage_of_62))

    result = search.search("agua", "HP", k=2)

    top = result.hits[0]
    assert [h.clause_id for h in result.hits] == ["HP-6.2", "HP-3.2"]
    assert (top.lexical_rank, top.vector_rank, top.fused_rank, top.rerank_score) == (
        None,
        2,
        3,
        1.0,
    )
    assert result.hits[1].fused_rank == 1  # equal rerank scores keep the fused order


def test_personal_data_is_masked_before_any_backend_or_model() -> None:
    lexical, embedder, reranker = FakeLexical(["HP-2.1"]), FakeEmbedder(), FakeReranker("x")
    search = PolicySearch(CLAUSES, lexical, FakeVectors(["HP-2.1"]), embedder, reranker=reranker)

    result = search.search(
        "Soy Lucía Martínez Gómez, NIF 12345678Z, teléfono 612 345 678: robo en casa", "HP"
    )

    seen = [lexical.queries[0][0], embedder.queries[0], reranker.queries[0], result.query]
    for text in seen:
        assert "Martínez" not in text
        assert "12345678Z" not in text
        assert "612 345 678" not in text
        assert "robo en casa" in text
    assert result.masked == {"PERSON": 1, "ES_NIF": 1, "PHONE_NUMBER": 1}


def test_the_product_filter_reaches_the_backends() -> None:
    lexical = FakeLexical(["AF-3.2"])
    search = PolicySearch(CLAUSES, lexical, FakeVectors(["AF-3.2"]), FakeEmbedder())

    search.search("alcoholemia", "AF", mode=Mode.HYBRID)

    assert lexical.queries == [("alcoholemia", "AF")]


@pytest.mark.parametrize(
    ("query", "product", "mode", "message"),
    [
        ("  ", "HP", Mode.HYBRID, "empty"),
        ("x" * 2001, "HP", Mode.HYBRID, "longer"),
        ("agua", "ZZ", Mode.HYBRID, "unknown product"),
        ("agua", "HP", Mode.RERANKED, "no reranker"),
    ],
)
def test_invalid_requests_are_refused(query: str, product: str, mode: Mode, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _search(["HP-2.1"], ["HP-2.1"]).search(query, product, mode=mode)


def test_a_missing_or_stale_index_says_how_to_fix_it() -> None:
    search = PolicySearch(
        CLAUSES, FakeLexical([], version=None), FakeVectors([], version="old"), FakeEmbedder()
    )

    with pytest.raises(
        SearchBackendError, match=r"OpenSearch, pgvector \(fake-embedder\).*make index"
    ):
        search.check_ready()
    _search([], []).check_ready()


def test_lexical_index_sends_a_filtered_bm25_query_and_reads_the_ranking() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        hits = [{"_id": "HP-5.1", "_score": 7.5}, {"_id": "HP-1.5", "_score": 2.0}]
        return httpx.Response(200, json={"hits": {"hits": hits}})

    index = LexicalIndex(httpx.Client(transport=httpx.MockTransport(handler), base_url="http://os"))

    assert index.search("plazo", "HP", 5) == [("HP-5.1", 7.5), ("HP-1.5", 2.0)]
    query = seen[0]["query"]
    assert query == {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": "plazo",
                        "fields": ["title^2", "text", "article", "product_name"],
                        "type": "best_fields",
                    }
                }
            ],
            "filter": [{"term": {"product_code": "HP"}}],
        }
    }
    assert seen[0]["size"] == 5


def test_lexical_index_bulk_loads_every_clause_with_the_corpus_version() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"errors": False, "acknowledged": True})

    index = LexicalIndex(httpx.Client(transport=httpx.MockTransport(handler), base_url="http://os"))
    index.rebuild(CLAUSES)

    created = json.loads(requests[1].content)
    bulk = requests[2].content.decode("utf-8").splitlines()
    assert [r.method for r in requests] == ["DELETE", "PUT", "POST"]
    assert created["mappings"]["_meta"] == {"corpus": VERSION}
    assert len(bulk) == 2 * len(CLAUSES)
    assert json.loads(bulk[1])["title"] == CLAUSES[0].title


def test_lexical_index_reports_a_refusal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad"})

    index = LexicalIndex(httpx.Client(transport=httpx.MockTransport(handler), base_url="http://os"))

    with pytest.raises(SearchBackendError, match="refused to search"):
        index.search("x", None, 3)


def test_vectors_are_sent_as_pgvector_literals() -> None:
    assert _literal([1, 0.5, -2e-3]) == "[1.0,0.5,-0.002]"
