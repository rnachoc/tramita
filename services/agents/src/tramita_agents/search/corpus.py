"""The searchable corpus: one entry per clause of the policy conditions.

The clause index (``data/policies/clauses.json``) is rendered from the product catalog together
with the Spanish conditions, so the ids found here are the ids the rules engine accepts as
citations. Clauses are short (one numbered paragraph each), so a clause is the unit of retrieval
and is never split.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tramita_agents.settings import REPO_ROOT

CLAUSES = REPO_ROOT / "data" / "policies" / "clauses.json"


@dataclass(frozen=True)
class Clause:
    clause_id: str
    product_code: str
    product_name: str
    article: str
    title: str
    text: str
    keys: tuple[str, ...]

    def passage(self) -> str:
        """The text that is embedded and reranked: where the clause sits, then what it says."""
        return f"{self.product_name}. {self.article}. {self.title}. {self.text}"


def load_clauses(path: Path = CLAUSES) -> list[Clause]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    clauses = [
        Clause(
            clause_id=item["clause_id"],
            product_code=item["product_code"],
            product_name=item["product_name"],
            article=item["article"],
            title=item["title"],
            text=item["text"],
            keys=tuple(item["keys"]),
        )
        for item in raw
    ]
    ids = [c.clause_id for c in clauses]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path} repeats clause ids")
    return clauses


def corpus_version(clauses: Sequence[Clause]) -> str:
    """Short hash of everything indexed, so a stale index can be told apart from a fresh one."""
    canonical = json.dumps(
        [[c.clause_id, c.product_code, c.passage(), list(c.keys)] for c in clauses],
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
