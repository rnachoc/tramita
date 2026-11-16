import json
from pathlib import Path
from typing import Any

import pytest

from tramita_agents.evals.baseline import BASELINE, compare, lookup, main, scorecard, update

BASE: dict[str, Any] = {
    "sections": {
        "agents": {
            "report": "agents.json",
            "provider": "fake:responder",
            "metrics": {
                "summary.decision_accuracy": {"value": 0.96, "better": "higher", "tolerance": 0.01},
                "summary.unsafe_automatic": {"value": 0, "better": "lower", "tolerance": 0},
            },
        }
    }
}


def _report(tmp_path: Path, accuracy: float, unsafe: int, providers: list[str]) -> Path:
    body = {
        "summary": {
            "providers": providers,
            "decision_accuracy": accuracy,
            "unsafe_automatic": unsafe,
        }
    }
    (tmp_path / "agents.json").write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def test_a_run_within_tolerance_passes(tmp_path: Path) -> None:
    rows, notes = compare(BASE, ["agents"], _report(tmp_path, 0.951, 0, ["fake:responder"]))

    assert notes == []
    assert [r.regressed for r in rows] == [False, False]


def test_a_drop_beyond_tolerance_or_any_harm_regresses(tmp_path: Path) -> None:
    rows, _ = compare(BASE, ["agents"], _report(tmp_path, 0.94, 1, ["fake:responder"]))

    assert [r.regressed for r in rows] == [True, True]
    assert "**REGRESSED**" in scorecard(rows, [])


def test_another_provider_is_shown_but_never_compared(tmp_path: Path) -> None:
    rows, notes = compare(BASE, ["agents"], _report(tmp_path, 0.5, 3, ["anthropic"]))

    assert not any(r.regressed for r in rows)
    assert "not compared" in notes[0]


def test_update_writes_the_values_and_provider_of_the_run(tmp_path: Path) -> None:
    updated = update(json.loads(json.dumps(BASE)), ["agents"], _report(tmp_path, 0.97, 0, ["x"]))

    agents = updated["sections"]["agents"]
    assert agents["provider"] == "x"
    assert agents["metrics"]["summary.decision_accuracy"]["value"] == 0.97


def test_a_missing_report_fails_the_run(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(BASE), encoding="utf-8")

    with pytest.raises(SystemExit):
        main(["--baseline", str(baseline), "--reports", str(tmp_path / "none")])


def test_lookup_reads_dotted_paths_and_ignores_non_numbers() -> None:
    report = {"summary": {"a": {"b": 2}, "flag": True, "text": "x"}}

    assert lookup(report, "summary.a.b") == 2.0
    assert lookup(report, "summary.flag") is None
    assert lookup(report, "summary.missing") is None


def test_the_committed_baseline_covers_every_section_with_values() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert set(baseline["sections"]) == {
        "extraction",
        "retrieval-fast",
        "retrieval-reranked",
        "agents",
    }
    for name, section in baseline["sections"].items():
        assert section["provider"], name
        for metric, rule in section["metrics"].items():
            assert rule["value"] is not None, f"{name} {metric}"
            assert rule["better"] in {"higher", "lower"}
