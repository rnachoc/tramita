"""Decides which scenario each claim exercises and picks facts that make it true.

Each recipe returns one or more ``Plan`` objects: a policy, a coverage, dates, the
declared incident and the manipulations to apply (missing documents, unrelated
invoice lines, planted fraud, hidden instructions...). Documents are built from the
plans in ``documents.py`` and expected resolutions are derived from the resulting
facts in ``resolution.py``.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from tramita_datagen import content
from tramita_datagen.catalog import Catalog, CoverageCode, Guarantee, Line, RequiredDocument
from tramita_datagen.models import Document, Policy, RepairDocument, Scenario
from tramita_datagen.util import require

# How many claims of each kind the dataset contains (150 in total).
SCENARIO_COUNTS: dict[str, int] = {
    "approve": 42,
    "approve_above_threshold": 8,
    "approve_limit": 4,
    "not_included": 10,
    "exclusion": 14,
    "waiting_period": 6,
    "late_notice": 10,
    "missing_documents": 14,
    "amount_unrelated": 8,
    "amount_inflated": 4,
    "fraud_duplicate": 6,
    "fraud_date_description": 5,
    "fraud_early_round_date": 4,
    "fraud_frequent": 3,  # each also adds two earlier legitimate claims on the same policy
    "decoy_round": 3,
    "decoy_early": 3,
}
INJECTED_CLAIMS = 10
EARLY_WINDOW_END = 55  # days after policy start; within the catalog's early-claim window
NORMAL_START = 61  # first day after the early-claim window


@dataclass
class Plan:
    kind: str
    scenario: Scenario
    policy: Policy
    coverage: CoverageCode
    incident: date
    reported: date
    story: content.Incident
    exclusion: str | None = None
    missing: RequiredDocument | None = None
    target_total: float = 0.0
    adjust: str | None = None  # "unrelated" | "inflated"
    round_amounts: bool = False
    documents_before_incident: bool = False
    description_mismatch: bool = False
    duplicate_of: Plan | None = None
    injection: str | None = None
    injection_target: str | None = None  # "invoice" | "description" | "scan"
    is_fraud: bool = False
    # Filled in when documents are built.
    claim_id: str = ""
    documents: list[Document] = field(default_factory=list)
    repair_document: RepairDocument | None = None

    @property
    def description(self) -> str:
        return self.story.description


class Planner:
    def __init__(
        self, rng: random.Random, catalog: Catalog, policies: list[Policy], reference_date: date
    ) -> None:
        self.rng = rng
        self.catalog = catalog
        self.policies = policies
        self.reference_date = reference_date
        self._used: set[str] = set()
        self._missing_count = 0
        self._recipes: dict[str, Callable[[str], list[Plan]]] = {
            "approve": self._ordinary,
            "late_notice": self._ordinary,
            "amount_unrelated": self._ordinary,
            "amount_inflated": self._ordinary,
            "decoy_round": self._ordinary,
            "missing_documents": self._missing_documents,
            "approve_above_threshold": self._large,
            "approve_limit": self._large,
            "not_included": self._not_included,
            "exclusion": self._exclusion,
            "waiting_period": self._waiting_period,
            "decoy_early": self._early,
            "fraud_early_round_date": self._early,
            "fraud_date_description": self._date_description,
            "fraud_frequent": self._frequent,
        }

    # ---------------------------------------------------------------- helpers

    def guarantee(self, policy: Policy, coverage: CoverageCode) -> Guarantee | None:
        return self.catalog.product(policy.product_code).guarantees.get(coverage)

    def limit(self, policy: Policy, coverage: CoverageCode) -> Decimal:
        guarantee = require(self.guarantee(policy, coverage), "guarantee")
        if guarantee.limit == "insured_value":
            return require(policy.insured_value, "insured value")
        return Decimal(guarantee.limit)

    def take_policy(
        self,
        coverage: CoverageCode | None = None,
        *,
        included: bool = True,
        min_age_days: int = 75,
        min_waiting: int = 0,
        line: Line | None = None,
        products: set[str] | None = None,
    ) -> tuple[Policy, CoverageCode]:
        """Picks an unused policy that fits; each policy is used by one scenario only."""
        candidates = []
        for policy in self.policies:
            if policy.policy_number in self._used:
                continue
            if (self.reference_date - policy.start_date).days < min_age_days:
                continue
            if (line and policy.line is not line) or (
                products and policy.product_code not in products
            ):
                continue
            guarantees = self.catalog.product(policy.product_code).guarantees
            if coverage is None:
                if guarantees:
                    candidates.append((policy, self.rng.choice(list(guarantees))))
                continue
            if (coverage in guarantees) != included:
                continue
            if included and guarantees[coverage].waiting_days < min_waiting:
                continue
            candidates.append((policy, coverage))
        if not candidates:
            raise ValueError(
                f"no policy left for coverage={coverage} line={line} products={products}"
            )
        policy, chosen = self.rng.choice(candidates)
        self._used.add(policy.policy_number)
        return policy, chosen

    def dates(
        self,
        policy: Policy,
        *,
        late: bool = False,
        after_days: int = NORMAL_START,
        before_days: int | None = None,
    ) -> tuple[date, date]:
        """Incident at least ``after_days`` after the policy start; report a few days later."""
        lag = self.rng.randint(10, 35) if late else self.rng.randint(0, 5)
        earliest = policy.start_date + timedelta(days=after_days)
        latest = self.reference_date - timedelta(days=lag + 2)
        if before_days is not None:
            latest = min(latest, policy.start_date + timedelta(days=before_days))
        if earliest > latest:
            raise ValueError(f"no room for an incident on {policy.policy_number}")
        incident = earliest + timedelta(days=self.rng.randint(0, (latest - earliest).days))
        return incident, incident + timedelta(days=lag)

    def target(self, policy: Policy, coverage: CoverageCode, kind: str) -> float:
        """Total amount (tax included) the repair documents should add up to."""
        limit = float(self.limit(policy, coverage))
        if kind == "approve_limit":
            return self.rng.uniform(limit * 1.08, limit * 1.35)
        if kind == "approve_above_threshold":
            return self.rng.uniform(3300.0, min(limit * 0.95, 9500.0))
        upper = min(limit * 0.9, 2600.0)
        return self.rng.uniform(min(260.0, upper * 0.5), upper)

    def _new(
        self,
        kind: str,
        scenario: Scenario,
        policy: Policy,
        coverage: CoverageCode,
        *,
        late: bool = False,
        after_days: int = NORMAL_START,
        before_days: int | None = None,
    ) -> Plan:
        incident, reported = self.dates(
            policy, late=late, after_days=after_days, before_days=before_days
        )
        story = self.rng.choice(content.INCIDENTS[coverage])
        plan = Plan(kind, scenario, policy, coverage, incident, reported, story)
        if self.guarantee(policy, coverage):
            plan.target_total = self.target(policy, coverage, kind)
        else:
            plan.target_total = self.rng.uniform(300, 2400)
        return plan

    # ---------------------------------------------------------------- recipes

    def _ordinary(self, kind: str) -> list[Plan]:
        scenario = {
            "approve": Scenario.APPROVE,
            "late_notice": Scenario.LATE_NOTICE,
            "amount_unrelated": Scenario.AMOUNT_ADJUSTED,
            "amount_inflated": Scenario.AMOUNT_ADJUSTED,
            "decoy_round": Scenario.DECOY,
        }[kind]
        late = kind == "late_notice"
        # Late reports need older policies so the incident still falls after the early-claim window.
        policy, coverage = self.take_policy(min_age_days=110 if late else 75)
        plan = self._new(kind, scenario, policy, coverage, late=late)
        if kind.startswith("amount_"):
            plan.adjust = kind.removeprefix("amount_")
        plan.round_amounts = kind == "decoy_round"
        return [plan]

    def _missing_documents(self, kind: str) -> list[Plan]:
        self._missing_count += 1
        if self._missing_count % 2 == 0:
            # Every other case lacks the police or accident report rather than the invoice.
            coverage = self.rng.choice(
                [CoverageCode.HOME_THEFT, CoverageCode.AUTO_COLLISION, CoverageCode.AUTO_THEFT]
            )
            policy, coverage = self.take_policy(coverage)
        else:
            policy, coverage = self.take_policy()
        plan = self._new(kind, Scenario.MISSING_DOCUMENTS, policy, coverage)
        required = list(self.catalog.coverages[coverage].required_documents)
        reports = [r for r in required if r is not RequiredDocument.REPAIR_INVOICE_OR_ESTIMATE]
        plan.missing = reports[0] if self._missing_count % 2 == 0 else self.rng.choice(required)
        return [plan]

    def _large(self, kind: str) -> list[Plan]:
        if kind == "approve_above_threshold":
            options = [
                CoverageCode.HOME_WATER,
                CoverageCode.HOME_THEFT,
                CoverageCode.AUTO_COLLISION,
                CoverageCode.AUTO_THEFT,
            ]
            products = None
        else:
            options = [CoverageCode.HOME_WATER, CoverageCode.HOME_GLASS, CoverageCode.AUTO_GLASS]
            products = {"HB", "HP", "AA", "AF"}
        policy, coverage = self.take_policy(self.rng.choice(options), products=products)
        return [self._new(kind, Scenario.APPROVE, policy, coverage)]

    def _not_included(self, kind: str) -> list[Plan]:
        line = self.rng.choice([Line.HOME, Line.AUTO])
        options = (
            [CoverageCode.HOME_GLASS]
            if line is Line.HOME
            else [CoverageCode.AUTO_COLLISION, CoverageCode.AUTO_GLASS, CoverageCode.AUTO_THEFT]
        )
        policy, coverage = self.take_policy(self.rng.choice(options), included=False, line=line)
        return [self._new(kind, Scenario.NOT_INCLUDED, policy, coverage)]

    def _exclusion(self, kind: str) -> list[Plan]:
        exclusion = self.rng.choice(list(content.EXCLUSION_INCIDENTS))
        policy, coverage = self.take_policy(content.EXCLUSION_COVERAGE[exclusion])
        plan = self._new(kind, Scenario.EXCLUSION, policy, coverage)
        plan.story = self.rng.choice(content.EXCLUSION_INCIDENTS[exclusion])
        plan.exclusion = exclusion
        return [plan]

    def _waiting_period(self, kind: str) -> list[Plan]:
        policy, coverage = self.take_policy(
            CoverageCode.HOME_THEFT, min_age_days=60, min_waiting=15
        )
        waiting = require(self.guarantee(policy, coverage), "guarantee").waiting_days
        return [
            self._new(
                kind,
                Scenario.WAITING_PERIOD,
                policy,
                coverage,
                after_days=2,
                before_days=waiting - 1,
            )
        ]

    def _early(self, kind: str) -> list[Plan]:
        """Incident shortly after the policy start but after any waiting period."""
        policy, coverage = self.take_policy(min_age_days=75)
        waiting = require(self.guarantee(policy, coverage), "guarantee").waiting_days
        after = max(waiting + 1, 3)
        fraud = kind.startswith("fraud")
        plan = self._new(
            kind,
            Scenario.FRAUD if fraud else Scenario.DECOY,
            policy,
            coverage,
            after_days=after,
            before_days=EARLY_WINDOW_END,
        )
        plan.target_total = self.target(policy, coverage, "approve")
        if fraud:
            plan.round_amounts = True
            plan.documents_before_incident = True
            plan.is_fraud = True
        return [plan]

    def _date_description(self, kind: str) -> list[Plan]:
        policy, coverage = self.take_policy(min_age_days=90)
        plan = self._new(kind, Scenario.FRAUD, policy, coverage)
        plan.target_total = self.target(policy, coverage, "approve")
        plan.documents_before_incident = True
        plan.description_mismatch = True
        plan.is_fraud = True
        return [plan]

    def _frequent(self, kind: str) -> list[Plan]:
        """Two legitimate claims followed by a third, suspicious one on the same policy."""
        policy, coverage = self.take_policy(min_age_days=300)
        first = policy.start_date + timedelta(days=self.rng.randint(65, 90))
        second = first + timedelta(days=self.rng.randint(30, 60))
        third = second + timedelta(days=self.rng.randint(20, 50))
        plans = []
        for incident in (first, second, third):
            last = incident == third
            plan = Plan(
                kind if last else "approve",
                Scenario.FRAUD if last else Scenario.APPROVE,
                policy,
                coverage,
                incident,
                incident + timedelta(days=self.rng.randint(0, 4)),
                self.rng.choice(content.INCIDENTS[coverage]),
            )
            plan.target_total = self.target(policy, coverage, "approve")
            if last:
                plan.round_amounts = True
                plan.documents_before_incident = True
                plan.is_fraud = True
            plans.append(plan)
        return plans

    def _duplicates(self, plans: list[Plan]) -> list[Plan]:
        """Claims that reuse the invoice of an earlier legitimate claim of another policyholder."""
        sources = [p for p in plans if p.kind == "approve" and p.missing is None]
        self.rng.shuffle(sources)
        duplicates = []
        for source in sources[: SCENARIO_COUNTS["fraud_duplicate"]]:
            policy, coverage = self.take_policy(source.coverage)
            plan = self._new("fraud_duplicate", Scenario.FRAUD, policy, coverage)
            if plan.incident <= source.reported:
                plan.incident = source.reported + timedelta(days=self.rng.randint(5, 20))
                plan.reported = plan.incident + timedelta(days=self.rng.randint(0, 3))
            if plan.reported > self.reference_date:
                plan.incident = self.reference_date - timedelta(days=4)
                plan.reported = self.reference_date - timedelta(days=2)
            plan.duplicate_of = source
            plan.is_fraud = True
            duplicates.append(plan)
        return duplicates

    def _inject(self, plans: list[Plan]) -> None:
        """Layers prompt-injection attempts on top of ordinary claims."""
        hosts = [p for p in plans if p.kind in {"approve", "exclusion", "missing_documents"}]
        self.rng.shuffle(hosts)
        for host in hosts[:INJECTED_CLAIMS]:
            host.injection = self.rng.choice(content.INJECTIONS)
            if host.missing is RequiredDocument.REPAIR_INVOICE_OR_ESTIMATE:
                host.injection_target = "description"
            else:
                host.injection_target = self.rng.choice(
                    ["invoice", "invoice", "description", "scan"]
                )

    def plan(self) -> list[Plan]:
        plans: list[Plan] = []
        for kind, count in SCENARIO_COUNTS.items():
            if kind == "fraud_duplicate":
                continue
            for _ in range(count):
                plans.extend(self._recipes[kind](kind))
        plans.extend(self._duplicates(plans))
        self._inject(plans)
        plans.sort(key=lambda p: (p.reported, p.incident, p.policy.policy_number))
        for number, plan in enumerate(plans, start=1):
            plan.claim_id = f"CL-{number:06d}"
        return plans
