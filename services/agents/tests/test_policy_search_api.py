import pytest
from fastapi.testclient import TestClient
from search_fixtures import CLAUSES, FakeEmbedder, FakeLexical, FakeReranker, FakeVectors

from tramita_agents import app as app_module
from tramita_agents.search.lexical import SearchBackendError
from tramita_agents.search.service import PolicySearch


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    search = PolicySearch(
        CLAUSES,
        FakeLexical(["HP-5.1", "HP-7.2"]),
        FakeVectors(["HP-5.1", "HP-1.5"]),
        FakeEmbedder(),
        reranker=FakeReranker("siete días"),
    )
    monkeypatch.setattr(app_module, "get_policy_search", lambda: search)
    return TestClient(app_module.app)


def test_search_returns_masked_query_and_cited_clauses(client: TestClient) -> None:
    response = client.post(
        "/policy-search",
        json={"query": "Soy Lucía Martínez Gómez, ¿cuándo aviso?", "product_code": "HP", "k": 2},
    )

    body = response.json()
    assert response.status_code == 200
    assert "Martínez" not in body["query"]
    assert body["masked"] == {"PERSON": 1}
    assert body["mode"] == "reranked"
    assert [h["clause_id"] for h in body["hits"]] == ["HP-5.1", "HP-1.5"]  # tie at rank 2, by id
    assert body["hits"][0]["title"] == "Plazo de comunicación"
    assert body["hits"][0]["lexical_rank"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "agua", "product_code": "hogar"},
        {"query": "agua", "k": 50},
        {"query": "agua", "mode": "magic"},
        {"query": "agua", "product_code": "ZZ"},
    ],
)
def test_invalid_requests_get_422(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/policy-search", json=payload).status_code == 422


def test_an_index_that_is_not_ready_gets_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_ready() -> PolicySearch:
        raise SearchBackendError("Policy search index missing: run `make index`.")

    monkeypatch.setattr(app_module, "get_policy_search", not_ready)

    response = TestClient(app_module.app).post("/policy-search", json={"query": "agua"})

    assert response.status_code == 503
    assert "make index" in response.json()["detail"]
