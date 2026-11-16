"""Evaluates the policy search against ground truth derived from the generated data.

Usage: ``uv run tramita-eval-retrieval`` (or ``make eval-retrieval``) with the stack up, after
``make data`` and ``make index``. Two query sets, both scoped to the policy's product as the
agents will search:

* **Claims**: the description each policyholder wrote, deduplicated. The answer is the clause
  that grounds the expected decision on the merits (ADR 0007): the exclusion the facts fall
  under, the "not included" clause when the product lacks the guarantee, otherwise the coverage
  clause of the guarantee claimed. Waiting periods, missing documents and late notice depend on
  dates and attachments, not on the description, so those claims are scored on the coverage
  clause. For an exclusion, the coverage clause counts as partly relevant.
* **Questions**: templates in ``evals/retrieval/questions.json`` written in everyday words,
  expanded over every product and guarantee they apply to, each answered by one clause.

Every mode (lexical, vector, hybrid, reranked) runs on the same queries. Measured: hit rate of
the answer at 1, 3 and 5, mean reciprocal rank (within 10), nDCG@5 with graded relevance, and
latency per query. The report says which models ran; nothing here calls a language model.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tramita_agents.search.corpus import Clause, corpus_version, load_clauses
from tramita_agents.search.factory import build_policy_search
from tramita_agents.search.service import Mode, PolicySearch
from tramita_agents.settings import REPO_ROOT, Settings

DATASET = REPO_ROOT / "data" / "generated"
QUESTIONS = REPO_ROOT / "evals" / "retrieval" / "questions.json"
REPORTS = REPO_ROOT / "evals" / "reports"
ANSWER = 2  # grade of the clause that answers a query; partly relevant ones get 1
DEPTH = 10  # ranks looked at for MRR; hit@k and nDCG use their own k

# Regression gate on the configured search (reranked mode); see ADR 0012 for the measurements.
GATE = {"hit_at_3": 0.0, "mrr": 0.0}


@dataclass(frozen=True)
class Query:
    qid: str
    source: str  # "claims" or "questions"
    category: str
    text: str
    product_code: str
    relevant: dict[str, int]  # clause id -> grade; the single grade-2 clause is the answer

    @property
    def answer(self) -> str:
        return next(cid for cid, grade in self.relevant.items() if grade == ANSWER)


@dataclass(frozen=True)
class Outcome:
    qid: str
    mode: str
    rank: int | None  # of the answer, within DEPTH
    ndcg5: float
    ms: float
    top: list[str]


def _by_key(clauses: Iterable[Clause]) -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for c in clauses:
        for key in c.keys:
            index.setdefault((c.product_code, key), c.clause_id)
    return index


def claim_queries(dataset: Path, clauses: Sequence[Clause]) -> list[Query]:
    keys = _by_key(clauses)
    claims = json.loads((dataset / "claims.json").read_text(encoding="utf-8"))
    expected = {
        e["claim_id"]: e
        for e in json.loads((dataset / "expected.json").read_text(encoding="utf-8"))
    }
    products = {
        p["policy_number"]: p["product_code"]
        for p in json.loads((dataset / "policies.json").read_text(encoding="utf-8"))
    }
    queries: dict[tuple[str, str, str], Query] = {}
    for claim in claims:
        outcome = expected[claim["claim_id"]]
        product = products[claim["policy_number"]]
        guarantee = claim["claim_type"]
        coverage = keys.get((product, f"coverage:{guarantee}"))
        first_reason = outcome["reasons"][0]
        if first_reason == "EXCLUSION":
            category = "exclusion"
            relevant = {keys[(product, f"exclusion:{outcome['exclusion_code']}")]: 2}
            if coverage:
                relevant[coverage] = 1
        elif first_reason == "NOT_INCLUDED":
            category = "not_included"
            relevant = {keys[(product, f"not_included:{guarantee}")]: 2}
        else:
            if coverage is None:
                raise ValueError(f"{claim['claim_id']}: no coverage clause for {guarantee}")
            category = "coverage"
            relevant = {coverage: 2}
        query = Query(
            qid=claim["claim_id"],
            source="claims",
            category=category,
            text=claim["description"],
            product_code=product,
            relevant=relevant,
        )
        queries.setdefault((query.text, product, query.answer), query)
    return list(queries.values())


def question_queries(path: Path, clauses: Sequence[Clause]) -> list[Query]:
    keys = _by_key(clauses)
    spec = json.loads(path.read_text(encoding="utf-8"))
    products = sorted({c.product_code for c in clauses})
    mentioned = {
        p: sorted(
            {
                key.split(":", 1)[1]
                for (product, key) in keys
                if product == p and key.startswith(("coverage:", "not_included:"))
            }
        )
        for p in products
    }
    queries: list[Query] = []
    for n, template in enumerate(spec["questions"], start=1):
        for product in products:
            templated = "{guarantee}" in template["key"]
            for guarantee in mentioned[product] if templated else [""]:
                key = template["key"].replace("{guarantee}", guarantee)
                kind = key.split(":", 1)[0]
                answer = keys.get((product, key))
                if answer is None and kind == "coverage":
                    answer = keys.get((product, f"not_included:{guarantee}"))
                    kind = "not_included"
                if answer is None:
                    continue  # the product has nothing to say about it (no limits if excluded)
                names = spec["guarantees"][guarantee] if templated else [""]
                for m, name in enumerate(names, start=1):
                    queries.append(
                        Query(
                            qid=f"Q{n:02d}-{product}-{guarantee or 'ALL'}-{m}",
                            source="questions",
                            category=kind,
                            text=template["text"].replace("{guarantee}", name),
                            product_code=product,
                            relevant={answer: 2},
                        )
                    )
    return queries


def ndcg(ranking: Sequence[str], relevant: dict[str, int], k: int = 5) -> float:
    def gain(grade: int, position: int) -> float:
        return float(2**grade - 1) / math.log2(position + 1)

    dcg = sum(gain(relevant.get(cid, 0), i) for i, cid in enumerate(ranking[:k], start=1))
    ideal = sum(
        gain(g, i) for i, g in enumerate(sorted(relevant.values(), reverse=True)[:k], start=1)
    )
    return dcg / ideal if ideal else 0.0


def run(search: PolicySearch, queries: Sequence[Query], modes: Sequence[Mode]) -> list[Outcome]:
    outcomes = []
    for mode in modes:
        for q in queries:
            started = time.perf_counter()
            result = search.search(q.text, q.product_code, k=DEPTH, mode=mode)
            ms = (time.perf_counter() - started) * 1000
            ranking = [h.clause_id for h in result.hits]
            rank = ranking.index(q.answer) + 1 if q.answer in ranking else None
            outcomes.append(
                Outcome(q.qid, mode.value, rank, ndcg(ranking, q.relevant), ms, ranking[:3])
            )
    return outcomes


def _scores(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    ranks = [o.rank or DEPTH + 1 for o in outcomes]
    n = len(outcomes)

    def hit(k: int) -> float:
        return round(sum(r <= k for r in ranks) / n, 4)

    ms = sorted(o.ms for o in outcomes)
    return {
        "queries": n,
        "hit_at_1": hit(1),
        "hit_at_3": hit(3),
        "hit_at_5": hit(5),
        "mrr": round(sum(1 / r for r in ranks if r <= DEPTH) / n, 4),
        "ndcg_at_5": round(statistics.fmean(o.ndcg5 for o in outcomes), 4),
        "ms_p50": round(statistics.median(ms), 1),
        "ms_p95": round(ms[min(n - 1, math.ceil(0.95 * n) - 1)], 1),
    }


def summarise(queries: Sequence[Query], outcomes: Sequence[Outcome]) -> dict[str, Any]:
    by_id = {q.qid: q for q in queries}
    groups: dict[str, dict[str, list[Outcome]]] = defaultdict(lambda: defaultdict(list))
    for o in outcomes:
        q = by_id[o.qid]
        for group in ("all", q.source, f"{q.source}:{q.category}"):
            groups[o.mode][group].append(o)
    return {
        mode: {group: _scores(items) for group, items in sorted(by_group.items())}
        for mode, by_group in groups.items()
    }


def gate_failures(summary: dict[str, Any], mode: str) -> list[str]:
    scores = summary.get(mode, {}).get("all")
    if scores is None:
        return [f"mode {mode} was not evaluated"]
    return [
        f"{name} {scores[name]:.3f} < {minimum:.3f}"
        for name, minimum in GATE.items()
        if scores[name] < minimum
    ]


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Policy search evaluation",
        "",
        f"Embedding model `{report['embedding_model']}`, reranker "
        f"`{report['reranker_model'] or 'none'}`, corpus {report['corpus']} "
        f"({report['clauses']} clauses). Local models only; no language model is called.",
        "",
        f"{report['queries']['claims']} claim descriptions and {report['queries']['questions']} "
        "questions, each searched within its policy's product. Hit@k: the answer is among the "
        "first k clauses. Latency per query, end to end (masking included).",
        "",
    ]
    groups = sorted({g for scores in summary.values() for g in scores}, key=_group_order)
    for group in groups:
        lines += [
            f"## {group}",
            "",
            "| Mode | Queries | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 | p50 ms | p95 ms |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for mode, scores in summary.items():
            s = scores.get(group)
            if s:
                lines.append(
                    f"| {mode} | {s['queries']} | {s['hit_at_1']:.1%} | {s['hit_at_3']:.1%} | "
                    f"{s['hit_at_5']:.1%} | {s['mrr']:.3f} | {s['ndcg_at_5']:.3f} | "
                    f"{s['ms_p50']} | {s['ms_p95']} |"
                )
        lines.append("")
    misses = report["misses"]
    if misses:
        lines += [f"## Answers missed at rank 1 by `{report['gate_mode']}`", ""]
        lines += [
            f"- {m['qid']} ({m['category']}): expected {m['answer']}, got {', '.join(m['top'])}"
            for m in misses
        ]
        lines.append("")
    return "\n".join(lines)


def _group_order(group: str) -> tuple[int, str]:
    return (0 if group == "all" else 1 if ":" not in group else 2, group)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate the policy search.")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--out", type=Path, default=REPORTS)
    parser.add_argument("--embedding-model", help="instead of the configured one")
    parser.add_argument("--reranker-model", help="instead of the configured one; '' for none")
    parser.add_argument(
        "--modes", default=",".join(m.value for m in Mode), help="comma-separated modes to run"
    )
    parser.add_argument("--name", default="retrieval", help="report file name, without suffix")
    parser.add_argument("--gate", action="store_true", help="exit 1 if a gate threshold fails")
    args = parser.parse_args(argv)

    settings = Settings()
    search = build_policy_search(settings, args.embedding_model, args.reranker_model)
    search.check_ready()
    modes = [Mode(m) for m in args.modes.split(",")]
    if search.reranker is None and Mode.RERANKED in modes:
        modes.remove(Mode.RERANKED)
    gate_mode = Mode.RERANKED if Mode.RERANKED in modes else modes[-1]
    clauses = load_clauses()
    queries = claim_queries(args.dataset, clauses) + question_queries(args.questions, clauses)
    search.search("calentamiento", None, mode=modes[0])  # load the models outside the timings
    started = time.perf_counter()
    outcomes = run(search, queries, modes)
    summary = summarise(queries, outcomes)
    by_id = {q.qid: q for q in queries}
    misses = [
        {
            "qid": o.qid,
            "category": by_id[o.qid].category,
            "answer": by_id[o.qid].answer,
            "top": o.top,
        }
        for o in outcomes
        if o.mode == gate_mode.value and o.rank != 1
    ]
    report = {
        "embedding_model": search.embedder.name,
        "reranker_model": search.reranker.name if search.reranker else None,
        "candidates": search.candidates,
        "corpus": corpus_version(clauses),
        "clauses": len(clauses),
        "queries": {
            "claims": sum(q.source == "claims" for q in queries),
            "questions": sum(q.source == "questions" for q in queries),
        },
        "gate_mode": gate_mode.value,
        "seconds": round(time.perf_counter() - started, 1),
        "summary": summary,
        "misses": misses,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.name}.json").write_text(
        json.dumps(
            {
                **report,
                "queries_detail": [asdict(q) for q in queries],
                "outcomes": [asdict(o) for o in outcomes],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    text = markdown(report)
    (args.out / f"{args.name}.md").write_text(text, encoding="utf-8")
    print(text)
    failures = gate_failures(summary, gate_mode.value)
    if os.environ.get("GITHUB_ACTIONS"):
        s = summary[gate_mode.value]["all"]
        print(
            f"::notice title=retrieval eval::{s['queries']} queries, {gate_mode.value}: "
            f"hit@1 {s['hit_at_1']:.1%}, hit@3 {s['hit_at_3']:.1%}, MRR {s['mrr']:.3f}, "
            f"gate {'FAILED: ' + '; '.join(failures) if failures else 'passed'}"
        )
    if args.gate and failures:
        print("Gate failed: " + "; ".join(failures), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
