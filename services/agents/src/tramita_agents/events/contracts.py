"""Claim events: the public record of what happened to each claim (ADRs 0004 and 0014).

The core publishes its audit trail to ``tramita.claim-events``, one envelope per state change,
keyed by claim so each claim's events stay in order. These models are the contract: the JSON
Schema in ``docs/events/claim-event.schema.json`` is generated from them (``make
event-schemas``), a test fails if it drifts, and a core test checks the relay against the same
file. Events carry no personal data.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from tramita_agents.settings import REPO_ROOT

TOPIC = "tramita.claim-events"
SCHEMA_FILE = REPO_ROOT / "docs" / "events" / "claim-event.schema.json"


class EventType(StrEnum):
    CLAIM_RECEIVED = "CLAIM_RECEIVED"
    DOCUMENT_RECEIVED = "DOCUMENT_RECEIVED"
    DOCUMENT_EXTRACTED = "DOCUMENT_EXTRACTED"
    PROPOSAL_EVALUATED = "PROPOSAL_EVALUATED"
    REVIEW_RECORDED = "REVIEW_RECORDED"
    PAYMENT_EXECUTED = "PAYMENT_EXECUTED"


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimReceived(_Data):
    policy_number: str
    claim_type: str


class DocumentReceived(_Data):
    document_id: str
    document_type: str


class DocumentExtracted(_Data):
    document_id: str
    has_amounts: bool


class ProposalEvaluated(_Data):
    proposal_id: str
    proposed_decision: str
    decision: str
    payable_amount: Decimal | None = None
    routing: str
    fraud_score: float
    violations: list[str]


class ReviewRecorded(_Data):
    review_id: str
    action: str
    decision: str
    amount: Decimal | None = None
    agrees_with_proposal: bool | None = None


class PaymentExecuted(_Data):
    payment_id: str
    amount: Decimal
    triggered_by: str


DATA: dict[EventType, type[_Data]] = {
    EventType.CLAIM_RECEIVED: ClaimReceived,
    EventType.DOCUMENT_RECEIVED: DocumentReceived,
    EventType.DOCUMENT_EXTRACTED: DocumentExtracted,
    EventType.PROPOSAL_EVALUATED: ProposalEvaluated,
    EventType.REVIEW_RECORDED: ReviewRecorded,
    EventType.PAYMENT_EXECUTED: PaymentExecuted,
}


class ClaimEvent(BaseModel):
    """The envelope. ``event_id`` is unique and increasing per core; consumers deduplicate by it."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    schema_version: Literal[1]
    claim_id: str
    occurred_at: datetime
    actor_role: str
    data: dict[str, Any]

    def known_type(self) -> EventType | None:
        """The type, or None for a type added after this consumer was written (skip it)."""
        try:
            return EventType(self.event_type)
        except ValueError:
            return None

    def payload(self) -> _Data | None:
        kind = self.known_type()
        return DATA[kind].model_validate(self.data) if kind else None


def schema_document() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Tramita claim event",
        "description": f"Messages on the Kafka topic {TOPIC}, keyed by claim id.",
        "envelope": ClaimEvent.model_json_schema(),
        "data": {kind.value: model.model_json_schema() for kind, model in DATA.items()},
    }


def render_schema() -> str:
    return json.dumps(schema_document(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    """Writes the schema file (``make event-schemas``)."""
    SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_FILE.write_text(render_schema(), encoding="utf-8")
    print(f"wrote {SCHEMA_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
