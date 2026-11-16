import json
from pathlib import Path
from typing import Any

import pytest

from tramita_agents.evals.retrieval import (
    QUESTIONS,
    Outcome,
    claim_queries,
    gate_failures,
    markdown,
    ndcg,
    question_queries,
    summarise,
)
from tramita_agents.search.corpus import load_clauses

CLAUSES = load_clauses()


def _claim(claim_id: str, policy: str, claim_type: str, description: str) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "policy_number": policy,
        "claim_type": claim_type,
        "description": description,
    }


def _expected(claim_id: str, reasons: list[str], exclusion: str | None = None) -> dict[str, Any]:
    return {"claim_id": claim_id, "reasons": reasons, "exclusion_code": exclusion}


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    claims = [
        _claim("CL-1", "BR-HT-1", "HOME_WATER", "Dejamos la ventana abierta y entró la lluvia."),
        _claim("CL-2", "BR-HB-1", "HOME_GLASS", "Se rompió el cristal del salón."),
        _claim("CL-3", "BR-HP-1", "HOME_THEFT", "Forzaron la puerta y se llevaron el portátil."),
        _claim("CL-4", "BR-HP-2", "HOME_THEFT", "Forzaron la puerta y se llevaron el portátil."),
    ]
    expected = [
        _expected("CL-1", ["EXCLUSION"], "WATER_EXTERIOR"),
        _expected("CL-2", ["NOT_INCLUDED"]),
        _expected("CL-3", ["WAITING_PERIOD"]),
        _expected("CL-4", ["COVERED"]),
    ]
    policies = [
        {"policy_number": n, "product_code": n.split("-")[1]}
        for n in ("BR-HT-1", "BR-HB-1", "BR-HP-1", "BR-HP-2")
    ]
    for name, content in [("claims", claims), ("expected", expected), ("policies", policies)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")
    return tmp_path


def test_claims_are_answered_by_the_clause_that_grounds_the_decision(dataset: Path) -> None:
    queries = {q.qid: q for q in claim_queries(dataset, CLAUSES)}

    assert queries["CL-1"].relevant == {"HT-3.2": 2, "HT-2.1": 1}
    assert queries["CL-1"].answer == "HT-3.2"
    assert queries["CL-2"].relevant == {"HB-2.3": 2}
    assert queries["CL-2"].category == "not_included"
    # A waiting period depends on dates, not on the description: scored on the coverage clause.
    assert queries["CL-3"].relevant == {"HP-2.2": 2}
    assert "CL-4" not in queries  # same text, product and answer as CL-3


def test_questions_expand_over_products_and_fall_back_to_not_included() -> None:
    queries = question_queries(QUESTIONS, CLAUSES)
    by_id = {q.qid: q for q in queries}

    covered = by_id["Q01-HP-HOME_GLASS-1"]
    missing = by_id["Q01-HB-HOME_GLASS-1"]
    assert covered.text == "¿Mi seguro cubre el cristal roto de una ventana?"
    assert covered.relevant == {"HP-2.3": 2}
    assert (missing.category, missing.relevant) == ("not_included", {"HB-2.3": 2})
    # No limits question for a guarantee the product does not include.
    assert not any(q.qid.startswith("Q04-HB-HOME_GLASS") for q in queries)
    assert len({q.qid for q in queries}) == len(queries)


def test_keyword_terms_are_a_set_of_their_own() -> None:
    terms = [q for q in question_queries(QUESTIONS, CLAUSES) if q.source == "terms"]

    hurto = next(q for q in terms if q.text == "hurto" and q.product_code == "HP")
    assert hurto.relevant == {"HP-3.3": 2}
    assert {q.product_code for q in terms if q.text == "circuitos cerrados"} == {"AF", "AR"}


def test_every_question_points_to_a_clause_of_its_product() -> None:
    ids = {c.clause_id for c in CLAUSES}

    for q in question_queries(QUESTIONS, CLAUSES):
        assert q.answer in ids
        assert q.answer.startswith(f"{q.product_code}-")


def test_ndcg_rewards_the_answer_first_and_counts_partial_relevance() -> None:
    relevant = {"A": 2, "B": 1}

    assert ndcg(["A", "B"], relevant) == pytest.approx(1.0)
    assert ndcg(["B", "A"], relevant) < 1.0
    assert ndcg(["X", "Y"], relevant) == 0.0


def test_summary_gate_and_report(dataset: Path) -> None:
    queries = claim_queries(dataset, CLAUSES)
    outcomes = [
        Outcome("CL-1", "reranked", 1, 1.0, 10.0, ["HT-3.2"]),
        Outcome("CL-2", "reranked", 4, 0.4, 20.0, ["HB-2.1", "HB-3.1", "HB-1.1"]),
        Outcome("CL-3", "reranked", None, 0.0, 30.0, ["HP-3.3"]),
    ]

    summary = summarise(queries, outcomes)

    scores = summary["reranked"]["all"]
    assert (scores["hit_at_1"], scores["hit_at_5"], scores["mrr"]) == (0.3333, 0.6667, 0.4167)
    assert summary["reranked"]["claims:exclusion"]["queries"] == 1
    assert gate_failures(summary, "reranked") == []
    assert gate_failures(summary, "hybrid") == ["mode hybrid was not evaluated"]
    report: dict[str, Any] = {
        "embedding_model": "e",
        "reranker_model": None,
        "corpus": "c",
        "clauses": 1,
        "queries": {"claims": 3, "questions": 0, "terms": 0},
        "gate_mode": "reranked",
        "summary": summary,
        "misses": [],
    }
    assert "| reranked | 3 | 33.3% |" in markdown(report)
