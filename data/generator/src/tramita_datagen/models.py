"""Shapes of the generated dataset.

Three kinds of records are produced:

* What the insurer's systems know: policyholders and policies.
* What arrives with a claim: the claim form and its attached documents.
* Ground truth for evaluation: the true content of every document (for extraction
  accuracy) and the expected resolution of every claim.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from tramita_datagen.catalog import CoverageCode, FraudSignalType, Line, RequiredDocument


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(_Model):
    street: str
    postal_code: str
    city: str
    province: str


class Policyholder(_Model):
    holder_id: str
    full_name: str
    nif: str
    birth_date: date
    email: str
    phone: str
    address: Address
    iban: str


class Vehicle(_Model):
    plate: str
    make: str
    model: str
    year: int


class Policy(_Model):
    policy_number: str
    holder_id: str
    product_code: str
    line: Line
    start_date: date
    end_date: date
    annual_premium: Decimal
    insured_address: Address | None = None
    vehicle: Vehicle | None = None
    insured_value: Decimal | None = None


class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    ESTIMATE = "ESTIMATE"
    POLICE_REPORT = "POLICE_REPORT"
    ACCIDENT_REPORT = "ACCIDENT_REPORT"


class DocumentFormat(StrEnum):
    PDF = "PDF"
    SCAN = "SCAN"  # JPEG image of a printed page


class LineItem(_Model):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    # Ground truth only: whether the item is related to the declared incident.
    related_to_claim: bool = True


class Party(_Model):
    name: str
    tax_id: str
    address: str | None = None


class RepairDocument(_Model):
    """Invoice or estimate from a repairer, workshop or supplier."""

    number: str
    issue_date: date
    issuer: Party
    customer: Party
    items: list[LineItem]
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal


class PoliceReport(_Model):
    report_number: str
    station: str
    filed_date: date
    incident_date: date
    complainant: Party
    complainant_phone: str
    narrative: str
    stolen_items: list[str]
    forced_entry: bool
    alcohol_test_mg_l: Decimal | None = None


class AccidentReport(_Model):
    report_date: date
    incident_date: date
    location: str
    driver_a: Party
    plate_a: str
    insurer_a: str
    driver_b: Party | None
    plate_b: str | None
    insurer_b: str | None
    circumstances: str


class Document(_Model):
    document_id: str
    claim_id: str
    document_type: DocumentType
    format: DocumentFormat
    filename: str
    repair: RepairDocument | None = None
    police_report: PoliceReport | None = None
    accident_report: AccidentReport | None = None
    # Text planted in the document to test prompt-injection resistance, if any.
    injected_instruction: str | None = None


class ClaimForm(_Model):
    """What the policyholder submits through the claims portal."""

    claim_id: str
    policy_number: str
    reported_date: date
    incident_date: date
    claim_type: CoverageCode
    location: str
    description: str
    claimed_amount: Decimal | None
    contact_phone: str
    contact_email: str
    document_ids: list[str]


class Decision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_INFO = "REQUEST_INFO"


class Routing(StrEnum):
    AUTO = "AUTO"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FRAUD_INVESTIGATION = "FRAUD_INVESTIGATION"


class Reason(StrEnum):
    COVERED = "COVERED"
    NOT_INCLUDED = "NOT_INCLUDED"
    EXCLUSION = "EXCLUSION"
    WAITING_PERIOD = "WAITING_PERIOD"
    MISSING_DOCUMENTS = "MISSING_DOCUMENTS"
    LATE_NOTICE = "LATE_NOTICE"
    AMOUNT_ADJUSTED = "AMOUNT_ADJUSTED"
    LIMIT_APPLIED = "LIMIT_APPLIED"
    DEDUCTIBLE_APPLIED = "DEDUCTIBLE_APPLIED"
    ABOVE_REVIEW_THRESHOLD = "ABOVE_REVIEW_THRESHOLD"
    FRAUD_SUSPECTED = "FRAUD_SUSPECTED"


class Scenario(StrEnum):
    APPROVE = "approve"
    NOT_INCLUDED = "not_included"
    EXCLUSION = "exclusion"
    WAITING_PERIOD = "waiting_period"
    LATE_NOTICE = "late_notice"
    MISSING_DOCUMENTS = "missing_documents"
    AMOUNT_ADJUSTED = "amount_adjusted"
    FRAUD = "fraud"
    DECOY = "decoy"  # legitimate claim with one weak fraud signal


class ExpectedResolution(_Model):
    claim_id: str
    scenario: Scenario
    decision: Decision
    payable_amount: Decimal
    eligible_amount: Decimal
    routing: Routing
    reasons: list[Reason]
    exclusion_code: str | None
    citations: list[str]
    missing_documents: list[RequiredDocument]
    fraud_signals: list[FraudSignalType]
    fraud_score: float
    is_fraud: bool
    # False for planted fraud: the merits of a claim under investigation are not
    # defined until the investigation ends, so only routing and signals are scored.
    decision_scored: bool
    has_injection: bool
    explanation: str


class Dataset(_Model):
    seed: int
    reference_date: date
    policyholders: list[Policyholder]
    policies: list[Policy]
    claims: list[ClaimForm]
    documents: list[Document]
    expected: list[ExpectedResolution]
