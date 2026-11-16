"""What analyst tools may return: the core's records reduced to what an analysis needs, with
personal data removed or masked, because every tool result is read by a model (ADR 0016).

Rules, applied to every view:

* the policyholder's description is masked like a document (ADR 0011); the incident address,
  contact details, reviewer names and account numbers are left out;
* document facts are the masked extraction; text the reader flagged as embedded instructions is
  never returned, only how many there were;
* evidence quoted in fraud signals comes from masked inputs or from the rules.
"""

from __future__ import annotations

from typing import Any

from tramita_agents.documents.pii import Pseudonymizer, mask


def claim_view(claim: dict[str, Any]) -> dict[str, Any]:
    policy = claim.get("policy") or {}
    masked = mask(claim.get("description") or "", Pseudonymizer())
    proposals = claim.get("proposals") or []
    latest = proposals[-1] if proposals else None
    payment = claim.get("payment")
    return {
        "claim_id": claim["claim_id"],
        "status": claim["status"],
        "claim_type": claim["claim_type"],
        "incident_date": claim["incident_date"],
        "reported_date": claim["reported_date"],
        "claimed_amount": claim.get("claimed_amount"),
        "policy": {
            k: policy.get(k)
            for k in ("policy_number", "product_code", "product_name", "start_date", "end_date")
        },
        "description_masked": masked.text,
        "personal_data_masked": masked.counts(),
        "documents": [_document(d) for d in claim.get("documents") or []],
        "evaluation": _evaluation(latest) if latest else None,
        "proposals": len(proposals),
        "reviews": [
            {k: r.get(k) for k in ("action", "decision", "amount", "created_at")}
            for r in claim.get("reviews") or []
        ],
        "payment": (
            {k: payment.get(k) for k in ("amount", "triggered_by", "executed_at")}
            if payment
            else None
        ),
    }


def _document(doc: dict[str, Any]) -> dict[str, Any]:
    extraction = doc.get("extraction") or {}
    values = {
        name: field.get("value")
        for name, field in (extraction.get("values") or {}).items()
        if field.get("value") is not None
    }
    return {
        "document_id": doc["document_id"],
        "document_type": doc["document_type"],
        "read_from": extraction.get("source"),
        "facts_masked": values,
        "doubtful_fields": extraction.get("needs_review") or [],
        "embedded_instructions_flagged": len(extraction.get("embedded_instructions") or []),
    }


def _evaluation(proposal: dict[str, Any]) -> dict[str, Any]:
    metadata = proposal.get("model_metadata") or {}
    return {
        "proposed_decision": proposal.get("proposed_decision"),
        "decision": proposal.get("decision"),
        "payable_amount": proposal.get("payable_amount"),
        "eligible_amount": proposal.get("eligible_amount"),
        "routing": proposal.get("routing"),
        "reasons": proposal.get("reasons"),
        "violations": [v.get("code") for v in proposal.get("violations") or []],
        "exclusion_code": proposal.get("exclusion_code"),
        "citations": proposal.get("citations"),
        "required_citations": proposal.get("required_citations"),
        "fraud_score": proposal.get("fraud_score"),
        "fraud_signals": [
            {k: s.get(k) for k in ("type", "evidence", "confidence", "source")}
            for s in proposal.get("fraud_signals") or []
        ],
        "missing_documents": proposal.get("missing_documents"),
        "review_requests": metadata.get("review_requests") or [],
    }


def audit_view(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The trail as types, times and roles: the details hold names and are left out."""
    return [
        {k: e.get(k) for k in ("event_id", "event_type", "occurred_at", "actor_role")}
        for e in events
    ]
