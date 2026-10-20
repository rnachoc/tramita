"""Command line entry point: ``uv run tramita-datagen --help``."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from datetime import date
from pathlib import Path

from faker import Faker

from tramita_datagen.catalog import CATALOG_PATH, REPO_ROOT, load_catalog
from tramita_datagen.documents import DocumentBuilder
from tramita_datagen.models import Dataset
from tramita_datagen.people import PeopleFactory
from tramita_datagen.planning import Planner
from tramita_datagen.policies import build_all_conditions, render_markdown
from tramita_datagen.render import write_document
from tramita_datagen.resolution import resolve

DEFAULT_SEED = 20261020
REFERENCE_DATE = date(2026, 9, 30)
POLICYHOLDERS = 200


def write_policies(directory: Path) -> list[Path]:
    """Renders the policy conditions and the clause index committed under data/policies."""
    catalog = load_catalog()
    conditions = build_all_conditions(catalog)
    written = []
    clauses = []
    for code, cond in conditions.items():
        path = directory / f"{code}.md"
        path.write_text(render_markdown(catalog, cond), encoding="utf-8")
        written.append(path)
        for clause in cond.clauses:
            keys = sorted(k for k, v in cond.index.items() if v == clause.clause_id)
            clauses.append(
                {
                    "clause_id": clause.clause_id,
                    "product_code": code,
                    "product_name": cond.product_name,
                    "article": clause.article,
                    "title": clause.title,
                    "text": " ".join(clause.text.split()),
                    "keys": keys,
                }
            )
    index_path = directory / "clauses.json"
    index_path.write_text(
        json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    written.append(index_path)
    return written


def generate(seed: int = DEFAULT_SEED, holders: int = POLICYHOLDERS) -> Dataset:
    rng = random.Random(seed)
    faker = Faker("es_ES")
    faker.seed_instance(seed)
    catalog = load_catalog()
    conditions = build_all_conditions(catalog)

    people, policies = PeopleFactory(rng, faker, catalog, REFERENCE_DATE).build(holders)
    plans = Planner(rng, catalog, policies, REFERENCE_DATE).plan()
    claims, documents = DocumentBuilder(rng, faker, catalog, people).build(plans)
    expected = resolve(plans, claims, catalog, conditions)
    return Dataset(
        seed=seed,
        reference_date=REFERENCE_DATE,
        policyholders=people,
        policies=policies,
        claims=claims,
        documents=documents,
        expected=expected,
    )


def _dump(path: Path, records: object) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_dataset(dataset: Dataset, out: Path, *, documents: bool = True) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    data = dataset.model_dump(mode="json")
    for name in ("policyholders", "policies", "claims", "documents", "expected"):
        _dump(out / f"{name}.json", data[name])
    if documents:
        for index, doc in enumerate(dataset.documents):
            write_document(doc, out / "documents" / doc.claim_id, seed=dataset.seed * 1000 + index)
    digests = {
        str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    summary = {
        "seed": dataset.seed,
        "reference_date": dataset.reference_date.isoformat(),
        "counts": {
            "policyholders": len(dataset.policyholders),
            "policies": len(dataset.policies),
            "claims": len(dataset.claims),
            "documents": len(dataset.documents),
        },
        "scenarios": dict(sorted(Counter(e.scenario.value for e in dataset.expected).items())),
        "decisions": dict(sorted(Counter(e.decision.value for e in dataset.expected).items())),
        "routing": dict(sorted(Counter(e.routing.value for e in dataset.expected).items())),
        "files": digests,
    }
    _dump(out / "manifest.json", summary)
    return digests


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate Tramita's synthetic dataset.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "generated")
    parser.add_argument("--policies-only", action="store_true", help="only render data/policies")
    parser.add_argument("--no-documents", action="store_true", help="skip rendering PDFs and scans")
    args = parser.parse_args(argv)

    for path in write_policies(CATALOG_PATH.parent):
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    if args.policies_only:
        return
    dataset = generate(args.seed)
    write_dataset(dataset, args.out, documents=not args.no_documents)
    manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {k: manifest[k] for k in ("counts", "scenarios", "decisions", "routing")}, indent=2
        )
    )


if __name__ == "__main__":
    main()
