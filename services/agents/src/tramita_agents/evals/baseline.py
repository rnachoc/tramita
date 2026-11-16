"""Compares evaluation reports with the committed baseline and writes the scorecard (ADR 0017).

Usage: ``uv run tramita-eval-baseline [--sections extraction,agents] [--update]`` (or ``make
scorecard``) after the evaluations it covers have written their reports to ``evals/reports``.

``evals/baseline.json`` lists, per section, the report it reads, the provider or models the
numbers belong to, and for each metric its value, whether higher or lower is better, and the
tolerance a run may drift by (scores from ONNX models differ slightly across CPUs). A run is
compared only with the baseline of the same provider: numbers from a real model are reported
next to the keyless baseline's, never failed against them. ``--update`` writes the current values
into the baseline, to be reviewed in the commit like any other change.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tramita_agents.settings import REPO_ROOT

BASELINE = REPO_ROOT / "evals" / "baseline.json"
REPORTS = REPO_ROOT / "evals" / "reports"


@dataclass(frozen=True)
class Row:
    section: str
    metric: str
    baseline: float | None
    actual: float | None
    better: str
    tolerance: float
    compared: bool

    @property
    def regressed(self) -> bool:
        if not self.compared or self.baseline is None:
            return False
        if self.actual is None:
            return True
        if self.better == "higher":
            return self.actual < self.baseline - self.tolerance
        return self.actual > self.baseline + self.tolerance


def lookup(report: dict[str, Any], path: str) -> float | None:
    node: Any = report
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return float(node) if isinstance(node, int | float) and not isinstance(node, bool) else None


def provider(section: str, report: dict[str, Any]) -> str:
    """Who produced the numbers: the model provider, or the local search models."""
    if section.startswith("retrieval"):
        return f"{report.get('embedding_model')} + {report.get('reranker_model') or 'none'}"
    summary = report.get("summary", {})
    found = summary.get("providers")
    if isinstance(found, dict):
        return ", ".join(sorted(found))
    if isinstance(found, list):
        return ", ".join(sorted(found))
    return "unknown"


def compare(
    baseline: dict[str, Any], sections: Sequence[str], reports: Path
) -> tuple[list[Row], list[str]]:
    rows: list[Row] = []
    notes: list[str] = []
    for name in sections:
        spec = baseline["sections"][name]
        path = reports / spec["report"]
        if not path.exists():
            notes.append(f"{name}: no report at {path.name}; run its evaluation first")
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        produced_by = provider(name, report)
        same = produced_by == spec["provider"]
        if not same:
            notes.append(
                f"{name}: produced by {produced_by}, baseline by {spec['provider']}; "
                "shown for information, not compared"
            )
        for metric, rule in spec["metrics"].items():
            rows.append(
                Row(
                    section=name,
                    metric=metric,
                    baseline=rule["value"],
                    actual=lookup(report, metric),
                    better=rule["better"],
                    tolerance=rule.get("tolerance", 0.0),
                    compared=same,
                )
            )
    return rows, notes


def update(baseline: dict[str, Any], sections: Sequence[str], reports: Path) -> dict[str, Any]:
    for name in sections:
        spec = baseline["sections"][name]
        report = json.loads((reports / spec["report"]).read_text(encoding="utf-8"))
        spec["provider"] = provider(name, report)
        for metric, rule in spec["metrics"].items():
            rule["value"] = lookup(report, metric)
    return baseline


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:g}"


def scorecard(rows: Sequence[Row], notes: Sequence[str]) -> str:
    lines = [
        "# Evaluation scorecard",
        "",
        "Each metric against `evals/baseline.json`. Higher or lower is better as marked; a run may",
        "drift by the tolerance. Only runs of the baseline's provider are compared.",
        "",
        "| Section | Metric | Better | Baseline | This run | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        status = "not compared" if not r.compared else "**REGRESSED**" if r.regressed else "ok"
        lines.append(
            f"| {r.section} | `{r.metric}` | {r.better} (±{_fmt(r.tolerance)}) | "
            f"{_fmt(r.baseline)} | {_fmt(r.actual)} | {status} |"
        )
    if notes:
        lines += ["", *[f"- {n}" for n in notes]]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare evaluation reports with the baseline.")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    parser.add_argument("--sections", help="comma-separated sections (default: all)")
    parser.add_argument("--update", action="store_true", help="write current values to baseline")
    parser.add_argument("--name", default="scorecard", help="scorecard file name, no suffix")
    args = parser.parse_args(argv)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    sections = args.sections.split(",") if args.sections else list(baseline["sections"])
    if args.update:
        updated = update(baseline, sections, args.reports)
        args.baseline.write_text(
            json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"baseline updated for {', '.join(sections)}: review the diff before committing")
        return
    rows, notes = compare(baseline, sections, args.reports)
    text = scorecard(rows, notes)
    args.reports.mkdir(parents=True, exist_ok=True)
    (args.reports / f"{args.name}.md").write_text(text, encoding="utf-8")
    print(text)
    regressed = [
        f"{r.section} {r.metric}: {_fmt(r.actual)} vs {_fmt(r.baseline)}"
        for r in rows
        if r.regressed
    ]
    missing = [n for n in notes if "no report" in n]
    if os.environ.get("GITHUB_ACTIONS"):
        compared = sum(r.compared for r in rows)
        print(
            f"::notice title=scorecard ({' + '.join(sections)})::{compared} metrics compared, "
            f"{len(regressed)} regressed" + (f": {'; '.join(regressed)}" if regressed else "")
        )
    if regressed or missing:
        print("Regressed or missing: " + "; ".join(regressed + missing), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
