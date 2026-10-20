"""Expected resolution of every claim, derived from the generated facts.

This is the reference implementation of the insurer's rules for the eval set. The
core service implements the same rules independently (in Java) from *extracted*
data; any disagreement between the two points at an extraction, reasoning or rules
error. Fraud signals are computed from facts visible at reporting time, in
reporting order, so a legitimate claim never carries a signal it does not exhibit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from tramita_datagen.catalog import Catalog, FraudSignalType, Guarantee, RequiredDocument
from tramita_datagen.models import (
    ClaimForm,
    Decision,
    Document,
    DocumentType,
    ExpectedResolution,
    Reason,
    RepairDocument,
    Routing,
)
from tramita_datagen.planning import Plan
from tramita_datagen.policies import Conditions
from tramita_datagen.util import TAX_FACTOR, money, require

ROUND_UNIT = 50  # every line a multiple of this many euros counts as round amounts
MIN_ROUND_LINES = 2
TOTAL_TOLERANCE = Decimal("0.05")


@dataclass
class History:
    """What the insurer knew before each claim: earlier repair documents and incidents."""

    repair_documents: set[tuple[str, str]] = field(default_factory=set)
    incidents_by_policy: dict[str, list[date]] = field(default_factory=dict)


@dataclass
class Outcome:
    decision: Decision
    reasons: list[Reason] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    eligible: Decimal = Decimal(0)
    payable: Decimal = Decimal(0)
    exclusion_code: str | None = None
    missing: list[RequiredDocument] = field(default_factory=list)


def amounts_document(docs: list[Document]) -> RepairDocument | None:
    """The document amounts are taken from: the latest invoice, otherwise the latest estimate."""
    invoices = [d.repair for d in docs if d.document_type is DocumentType.INVOICE and d.repair]
    estimates = [d.repair for d in docs if d.document_type is DocumentType.ESTIMATE and d.repair]
    candidates = invoices or estimates
    return candidates[-1] if candidates else None


def satisfies(required: RequiredDocument, docs: list[Document]) -> bool:
    types = {d.document_type for d in docs}
    if required is RequiredDocument.REPAIR_INVOICE_OR_ESTIMATE:
        return bool(types & {DocumentType.INVOICE, DocumentType.ESTIMATE})
    if required is RequiredDocument.POLICE_REPORT:
        return DocumentType.POLICE_REPORT in types
    # An accident report requirement is met by a friendly report or a police record.
    return bool(types & {DocumentType.ACCIDENT_REPORT, DocumentType.POLICE_REPORT})


def _document_dates(docs: list[Document]) -> list[date]:
    dates: list[date] = []
    for d in docs:
        if d.repair:
            dates.append(d.repair.issue_date)
        if d.police_report:
            dates.append(d.police_report.filed_date)
        if d.accident_report:
            dates.append(d.accident_report.report_date)
    return dates


def fraud_signals(
    plan: Plan, claim: ClaimForm, catalog: Catalog, history: History
) -> list[FraudSignalType]:
    rules = catalog.operations.fraud
    docs = plan.documents
    signals: list[FraudSignalType] = []
    if (claim.incident_date - plan.policy.start_date).days <= rules.early_claim_days:
        signals.append(FraudSignalType.EARLY_CLAIM)
    repair = amounts_document(docs)
    if (
        repair
        and len(repair.items) >= MIN_ROUND_LINES
        and all(i.amount % ROUND_UNIT == 0 for i in repair.items)
    ):
        signals.append(FraudSignalType.ROUND_AMOUNTS)
    if any(d < claim.incident_date for d in _document_dates(docs)):
        signals.append(FraudSignalType.DATE_INCONSISTENCY)
    if plan.description_mismatch:
        signals.append(FraudSignalType.DESCRIPTION_MISMATCH)
    keys = {(d.repair.issuer.tax_id, d.repair.number) for d in docs if d.repair}
    if keys & history.repair_documents:
        signals.append(FraudSignalType.DUPLICATE_INVOICE)
    history.repair_documents |= keys
    window = timedelta(days=rules.frequent_claims_window_days)
    earlier = history.incidents_by_policy.setdefault(plan.policy.policy_number, [])
    if (
        len([d for d in earlier if claim.incident_date - d <= window]) + 1
        >= rules.frequent_claims_min
    ):
        signals.append(FraudSignalType.FREQUENT_CLAIMS)
    earlier.append(claim.incident_date)
    return signals


def fraud_score(signals: list[FraudSignalType], catalog: Catalog) -> float:
    """Noisy-OR combination: score = 1 - prod(1 - weight)."""
    remaining = 1.0
    for signal in signals:
        remaining *= 1 - catalog.operations.fraud.weights[signal]
    return round(1 - remaining, 4)


def _approve(
    plan: Plan, guarantee: Guarantee, catalog: Catalog, cond: Conditions, out: Outcome
) -> None:
    claim_type = plan.coverage
    out.reasons.append(Reason.COVERED)
    out.citations += [cond.cite(f"coverage:{claim_type}"), cond.cite(f"limits:{claim_type}")]
    repair = require(amounts_document(plan.documents), "repair document")
    computed = money(sum((i.amount for i in repair.items), Decimal(0)) * TAX_FACTOR)
    if plan.description_mismatch:
        # Under fraud investigation the merits are undefined; keep the documented amount.
        out.eligible = computed
    else:
        related = sum((i.amount for i in repair.items if i.related_to_claim), Decimal(0))
        out.eligible = money(related * TAX_FACTOR)
        if out.eligible < computed or repair.total > computed + TOTAL_TOLERANCE:
            out.reasons.append(Reason.AMOUNT_ADJUSTED)
            out.citations.append(cond.cite("indemnity"))
            out.explanation.append(
                "Se descuentan partidas no relacionadas con el siniestro o importes que no cuadran con el detalle."
            )
    limit = (
        require(plan.policy.insured_value, "insured value")
        if guarantee.limit == "insured_value"
        else Decimal(guarantee.limit)
    )
    if out.eligible > limit:
        out.reasons.append(Reason.LIMIT_APPLIED)
    if guarantee.deductible:
        out.reasons.append(Reason.DEDUCTIBLE_APPLIED)
    out.payable = max(Decimal(0), money(min(out.eligible, limit) - guarantee.deductible))
    if out.payable > catalog.operations.review_threshold_eur:
        out.reasons.append(Reason.ABOVE_REVIEW_THRESHOLD)
    out.explanation.append(f"Daños acreditados {out.eligible} €, indemnización {out.payable} €.")


def assess(plan: Plan, claim: ClaimForm, catalog: Catalog, cond: Conditions) -> Outcome:
    """Coverage, waiting period, exclusions, documents and amounts, in that order."""
    product = catalog.product(plan.policy.product_code)
    guarantee = product.guarantees.get(claim.claim_type)
    if guarantee is None:
        return Outcome(
            Decision.REJECT,
            [Reason.NOT_INCLUDED],
            [cond.cite(f"not_included:{claim.claim_type}")],
            [f"El producto {product.name} no incluye la garantía reclamada."],
        )
    if (claim.incident_date - plan.policy.start_date).days < guarantee.waiting_days:
        return Outcome(
            Decision.REJECT,
            [Reason.WAITING_PERIOD],
            [cond.cite(f"waiting:{claim.claim_type}")],
            [
                f"El siniestro ocurre dentro del periodo de carencia de {guarantee.waiting_days} días."
            ],
        )
    if plan.exclusion:
        return Outcome(
            Decision.REJECT,
            [Reason.EXCLUSION],
            [cond.cite(f"exclusion:{plan.exclusion}")],
            ["Los hechos declarados encajan en una exclusión de la garantía."],
            exclusion_code=plan.exclusion,
        )
    required = catalog.coverages[claim.claim_type].required_documents
    missing = [r for r in required if not satisfies(r, plan.documents)]
    if missing:
        return Outcome(
            Decision.REQUEST_INFO,
            [Reason.MISSING_DOCUMENTS],
            [cond.cite(f"documents:{claim.claim_type}")],
            ["Falta documentación imprescindible para valorar el siniestro."],
            missing=missing,
        )
    out = Outcome(Decision.APPROVE)
    _approve(plan, guarantee, catalog, cond, out)
    return out


def route(out: Outcome, *, late: bool, score: float, catalog: Catalog) -> Routing:
    """Who acts next. Rejections, large or adjusted payments and late notices need a human."""
    fraud = catalog.operations.fraud
    if score >= fraud.investigation_threshold:
        return Routing.FRAUD_INVESTIGATION
    if score >= fraud.review_threshold:
        return Routing.HUMAN_REVIEW
    if out.decision is Decision.REQUEST_INFO:
        # Asking for documents is low risk; the claim is reviewed when they arrive.
        return Routing.AUTO
    needs_human = {Reason.AMOUNT_ADJUSTED, Reason.ABOVE_REVIEW_THRESHOLD}
    if out.decision is Decision.REJECT or late or needs_human & set(out.reasons):
        return Routing.HUMAN_REVIEW
    return Routing.AUTO


def resolve(
    plans: list[Plan],
    claims: list[ClaimForm],
    catalog: Catalog,
    conditions: dict[str, Conditions],
) -> list[ExpectedResolution]:
    by_id = {c.claim_id: c for c in claims}
    history = History()
    results = []
    for plan in plans:  # plans are sorted by reporting date
        claim = by_id[plan.claim_id]
        cond = conditions[plan.policy.product_code]
        signals = fraud_signals(plan, claim, catalog, history)
        score = fraud_score(signals, catalog)
        out = assess(plan, claim, catalog, cond)

        late = (claim.reported_date - claim.incident_date).days > catalog.operations.notice_days
        if late:
            out.reasons.append(Reason.LATE_NOTICE)
            out.citations.append(cond.cite("notice"))
            out.explanation.append(
                "Comunicado fuera del plazo de siete días: requiere revisión, no anula la cobertura."
            )
        routing = route(out, late=late, score=score, catalog=catalog)
        if score >= catalog.operations.fraud.review_threshold:
            out.reasons.append(Reason.FRAUD_SUSPECTED)
            out.citations.append(cond.cite("fraud"))

        results.append(
            ExpectedResolution(
                claim_id=claim.claim_id,
                scenario=plan.scenario,
                decision=out.decision,
                payable_amount=out.payable,
                eligible_amount=out.eligible,
                routing=routing,
                reasons=out.reasons,
                exclusion_code=out.exclusion_code,
                citations=list(dict.fromkeys(out.citations)),
                missing_documents=out.missing,
                fraud_signals=signals,
                fraud_score=score,
                is_fraud=plan.is_fraud,
                decision_scored=not plan.is_fraud,
                has_injection=plan.injection is not None,
                explanation=" ".join(out.explanation),
            )
        )
    return results
