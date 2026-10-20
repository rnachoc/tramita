from collections import Counter
from decimal import Decimal

from tramita_datagen.catalog import Catalog
from tramita_datagen.cli import generate
from tramita_datagen.models import Dataset, Decision, DocumentFormat, Routing, Scenario
from tramita_datagen.policies import Conditions


def test_same_seed_produces_identical_data(dataset: Dataset) -> None:
    assert generate().model_dump_json() == dataset.model_dump_json()


def test_different_seed_produces_different_data(dataset: Dataset) -> None:
    assert generate(seed=7).model_dump_json() != dataset.model_dump_json()


def test_dataset_size_and_scenario_mix(dataset: Dataset) -> None:
    assert len(dataset.policyholders) == 200
    assert len(dataset.claims) == 150
    scenarios = Counter(e.scenario for e in dataset.expected)
    assert scenarios[Scenario.FRAUD] == 18
    assert scenarios[Scenario.EXCLUSION] == 14
    assert scenarios[Scenario.MISSING_DOCUMENTS] == 14
    assert sum(e.has_injection for e in dataset.expected) == 10
    assert sum(d.format is DocumentFormat.SCAN for d in dataset.documents) > 30


def test_every_citation_exists_in_the_policy_conditions(
    dataset: Dataset, conditions: dict[str, Conditions]
) -> None:
    policies = {p.policy_number: p for p in dataset.policies}
    claims = {c.claim_id: c for c in dataset.claims}
    for expected in dataset.expected:
        product = policies[claims[expected.claim_id].policy_number].product_code
        ids = {c.clause_id for c in conditions[product].clauses}
        assert expected.citations, expected.claim_id
        assert set(expected.citations) <= ids, expected.claim_id


def test_planted_fraud_is_investigated_and_nothing_else_is(
    dataset: Dataset, catalog: Catalog
) -> None:
    review = catalog.operations.fraud.review_threshold
    for expected in dataset.expected:
        if expected.is_fraud:
            assert expected.routing is Routing.FRAUD_INVESTIGATION, expected.claim_id
            assert not expected.decision_scored
        else:
            assert expected.fraud_score < review, (expected.claim_id, expected.fraud_signals)


def test_decoys_carry_one_weak_signal_and_stay_automatic(dataset: Dataset) -> None:
    decoys = [e for e in dataset.expected if e.scenario is Scenario.DECOY]
    assert len(decoys) == 6
    for decoy in decoys:
        assert len(decoy.fraud_signals) == 1
        assert decoy.routing is Routing.AUTO


def test_payments_respect_limits_and_deductibles(dataset: Dataset, catalog: Catalog) -> None:
    policies = {p.policy_number: p for p in dataset.policies}
    claims = {c.claim_id: c for c in dataset.claims}
    for expected in dataset.expected:
        if expected.decision is not Decision.APPROVE:
            assert expected.payable_amount == 0
            continue
        claim = claims[expected.claim_id]
        policy = policies[claim.policy_number]
        guarantee = catalog.product(policy.product_code).guarantees[claim.claim_type]
        limit = (
            policy.insured_value if guarantee.limit == "insured_value" else Decimal(guarantee.limit)
        )
        assert limit is not None
        assert expected.payable_amount <= limit
        assert expected.payable_amount <= max(
            Decimal(0), expected.eligible_amount - guarantee.deductible
        )


def test_large_payments_and_rejections_always_reach_a_human(
    dataset: Dataset, catalog: Catalog
) -> None:
    for expected in dataset.expected:
        large = expected.payable_amount > catalog.operations.review_threshold_eur
        if large or expected.decision is Decision.REJECT:
            assert expected.routing is not Routing.AUTO, expected.claim_id


def test_documents_never_contradict_the_claim_unless_planted(dataset: Dataset) -> None:
    claims = {c.claim_id: c for c in dataset.claims}
    expected = {e.claim_id: e for e in dataset.expected}
    for doc in dataset.documents:
        if expected[doc.claim_id].is_fraud:
            continue
        incident = claims[doc.claim_id].incident_date
        dates = [
            doc.repair.issue_date if doc.repair else None,
            doc.police_report.filed_date if doc.police_report else None,
            doc.accident_report.report_date if doc.accident_report else None,
        ]
        assert all(d is None or d >= incident for d in dates), doc.document_id
