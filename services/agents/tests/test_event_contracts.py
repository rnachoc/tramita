import json

import pytest
from pydantic import ValidationError

from tramita_agents.events.contracts import (
    SCHEMA_FILE,
    ClaimEvent,
    EventType,
    ProposalEvaluated,
    render_schema,
)


def _event(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "event_id": "42",
        "event_type": "PROPOSAL_EVALUATED",
        "schema_version": 1,
        "claim_id": "CL-000001",
        "occurred_at": "2026-11-16T10:00:00Z",
        "actor_role": "AGENT",
        "data": {
            "proposal_id": "p-1",
            "proposed_decision": "APPROVE",
            "decision": "APPROVE",
            "payable_amount": 1110.0,
            "routing": "HUMAN_REVIEW",
            "fraud_score": 0.0,
            "violations": [],
        },
    }
    return {**base, **kw}


def test_the_committed_schema_matches_the_models() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == render_schema(), (
        "Event contracts changed: run `make event-schemas` and commit the schema."
    )


def test_an_event_parses_into_its_typed_payload() -> None:
    event = ClaimEvent.model_validate_json(json.dumps(_event()))

    payload = event.payload()
    assert event.known_type() is EventType.PROPOSAL_EVALUATED
    assert isinstance(payload, ProposalEvaluated)
    assert payload.routing == "HUMAN_REVIEW"


def test_unknown_types_are_skipped_not_rejected() -> None:
    event = ClaimEvent.model_validate(_event(event_type="SOMETHING_NEW", data={"x": 1}))

    assert (event.known_type(), event.payload()) == (None, None)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"extra": "field"},
        {"data": {"proposal_id": "p-1", "reviewer": "Ana"}},
    ],
)
def test_contract_breaks_are_refused(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ClaimEvent.model_validate(_event(**change)).payload()
