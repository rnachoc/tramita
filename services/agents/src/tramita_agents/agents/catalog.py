"""The product catalog and the clause index, as the agents and the coordinator read them.

``data/policies/catalog.yaml`` is the single source of truth the core rules also load, and
``clauses.json`` maps rule keys (``coverage:HOME_WATER``, ``exclusion:WATER_EXTERIOR``) to the
clause ids the rules accept as citations. The coordinator uses them for the deterministic parts of
a proposal; the agents only judge what needs reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from tramita_agents.search.corpus import load_clauses
from tramita_agents.settings import REPO_ROOT

CATALOG = REPO_ROOT / "data" / "policies" / "catalog.yaml"

# Which received document types satisfy each required document (as the core's RequiredDocument).
SATISFIED_BY: dict[str, frozenset[str]] = {
    "REPAIR_INVOICE_OR_ESTIMATE": frozenset({"INVOICE", "ESTIMATE"}),
    "POLICE_REPORT": frozenset({"POLICE_REPORT"}),
    "ACCIDENT_REPORT": frozenset({"ACCIDENT_REPORT", "POLICE_REPORT"}),
}


@dataclass(frozen=True)
class Exclusion:
    code: str
    text: str


@dataclass(frozen=True)
class Coverage:
    code: str
    title: str
    exclusions: tuple[Exclusion, ...]
    required_documents: tuple[str, ...]


@dataclass(frozen=True)
class Guarantee:
    limit: str  # euros, or "insured_value"
    deductible: int
    waiting_days: int


@dataclass(frozen=True)
class Catalog:
    notice_days: int
    coverages: dict[str, Coverage]
    products: dict[str, dict[str, Guarantee]]
    clause_keys: dict[tuple[str, str], str]  # (product, rule key) -> clause id

    def clause(self, product: str, key: str) -> str | None:
        return self.clause_keys.get((product, key))

    def guarantee(self, product: str, coverage: str) -> Guarantee | None:
        return self.products[product].get(coverage)

    def in_waiting_period(self, product: str, coverage: str, start: date, incident: date) -> bool:
        guarantee = self.guarantee(product, coverage)
        return guarantee is not None and (incident - start).days < guarantee.waiting_days

    def missing_documents(self, coverage: str, received: set[str]) -> list[str]:
        return [
            r for r in self.coverages[coverage].required_documents if not SATISFIED_BY[r] & received
        ]


def _load(path: Path) -> Catalog:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    coverages = {
        code: Coverage(
            code=code,
            title=spec["title"],
            exclusions=tuple(
                Exclusion(e["code"], " ".join(e["text"].split())) for e in spec["exclusions"]
            ),
            required_documents=tuple(spec["required_documents"]),
        )
        for code, spec in raw["coverages"].items()
    }
    products = {
        code: {
            g: Guarantee(str(v["limit"]), int(v["deductible"]), int(v["waiting_days"]))
            for g, v in (spec["guarantees"] or {}).items()
        }
        for code, spec in raw["products"].items()
    }
    keys: dict[tuple[str, str], str] = {}
    for clause in load_clauses():
        for key in clause.keys:
            keys.setdefault((clause.product_code, key), clause.clause_id)
    return Catalog(raw["operations"]["notice_days"], coverages, products, keys)


@lru_cache
def catalog() -> Catalog:
    return _load(CATALOG)
