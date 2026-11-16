import json
from pathlib import Path

import pytest

from tramita_agents.search.corpus import CLAUSES, corpus_version, load_clauses
from tramita_agents.search.fusion import reciprocal_rank_fusion


def test_corpus_has_every_clause_of_every_product() -> None:
    clauses = load_clauses()

    assert len(clauses) == len(json.loads(CLAUSES.read_text(encoding="utf-8")))
    assert {c.product_code for c in clauses} == {"HB", "HP", "HT", "AT", "AA", "AR", "AF"}
    assert all(c.clause_id.startswith(f"{c.product_code}-") for c in clauses)


def test_passage_says_where_the_clause_sits() -> None:
    clause = next(c for c in load_clauses() if c.clause_id == "HB-1.3")

    assert clause.passage().startswith("Hogar Básico. Artículo 1. Objeto del seguro")
    assert "Siniestro. Todo hecho súbito" in clause.passage()


def test_repeated_clause_ids_are_refused(tmp_path: Path) -> None:
    item = json.loads(CLAUSES.read_text(encoding="utf-8"))[0]
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps([item, item]), encoding="utf-8")

    with pytest.raises(ValueError, match="repeats"):
        load_clauses(path)


def test_corpus_version_changes_with_the_text() -> None:
    clauses = load_clauses()
    edited = [*clauses[:-1], clauses[-1].__class__(**{**vars(clauses[-1]), "text": "otro"})]

    assert corpus_version(clauses) == corpus_version(load_clauses())
    assert corpus_version(edited) != corpus_version(clauses)


def test_rrf_rewards_agreement_between_rankings() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["d", "b", "e"]])

    # b is second in both; a and d lead only one ranking each.
    assert [item for item, _ in fused] == ["b", "a", "d", "c", "e"]
    assert fused[0][1] == pytest.approx(2 / 62)


def test_rrf_breaks_ties_by_best_rank_then_id() -> None:
    fused = reciprocal_rank_fusion([["a", "x"], ["y", "a"], ["x", "y"]], k=1)

    # a: 1/2 + 1/3, x: 1/3 + 1/2, y: 1/2 + 1/3; all share the best rank 1.
    assert [item for item, _ in fused] == ["a", "x", "y"]


def test_rrf_refuses_a_ranking_with_duplicates() -> None:
    with pytest.raises(ValueError, match="repeats"):
        reciprocal_rank_fusion([["a", "a"]])
