from pathlib import Path

from tramita_datagen.catalog import CATALOG_PATH, Catalog
from tramita_datagen.policies import Conditions, render_markdown


def test_clause_ids_are_unique_within_each_product(conditions: dict[str, Conditions]) -> None:
    for cond in conditions.values():
        ids = [c.clause_id for c in cond.clauses]
        assert len(ids) == len(set(ids)), cond.product_code


def test_every_index_key_points_to_an_existing_clause(conditions: dict[str, Conditions]) -> None:
    for cond in conditions.values():
        ids = {c.clause_id for c in cond.clauses}
        assert set(cond.index.values()) <= ids


def test_each_included_guarantee_has_coverage_limit_exclusion_and_document_clauses(
    catalog: Catalog, conditions: dict[str, Conditions]
) -> None:
    for code, product in catalog.products.items():
        index = conditions[code].index
        for coverage in product.guarantees:
            assert f"coverage:{coverage}" in index
            assert f"limits:{coverage}" in index
            assert f"documents:{coverage}" in index
            for exclusion in catalog.coverages[coverage].exclusions:
                assert f"exclusion:{exclusion.code}" in index


def test_guarantees_not_in_a_product_are_explicitly_listed_as_not_included(
    catalog: Catalog, conditions: dict[str, Conditions]
) -> None:
    for code, product in catalog.products.items():
        line_coverages = [c for c, cov in catalog.coverages.items() if cov.line is product.line]
        for coverage in line_coverages:
            key = (
                f"coverage:{coverage}"
                if coverage in product.guarantees
                else f"not_included:{coverage}"
            )
            assert key in conditions[code].index, (code, coverage)


def test_limit_and_deductible_numbers_in_the_text_match_the_catalog(
    catalog: Catalog, conditions: dict[str, Conditions]
) -> None:
    for code, product in catalog.products.items():
        cond = conditions[code]
        texts = {c.clause_id: " ".join(c.text.split()) for c in cond.clauses}
        for coverage, guarantee in product.guarantees.items():
            text = texts[cond.cite(f"limits:{coverage}")]
            if guarantee.limit != "insured_value":
                assert f"{guarantee.limit:,}".replace(",", ".") + " €" in text
            if guarantee.deductible:
                assert f"franquicia de {guarantee.deductible}" in text
            if guarantee.waiting_days:
                assert f"carencia de {guarantee.waiting_days} días" in text


def test_committed_policy_documents_are_in_sync_with_the_catalog(
    catalog: Catalog, conditions: dict[str, Conditions]
) -> None:
    directory: Path = CATALOG_PATH.parent
    for code, cond in conditions.items():
        committed = (directory / f"{code}.md").read_text(encoding="utf-8")
        assert committed == render_markdown(catalog, cond), f"run `make data` to refresh {code}.md"
