"""What the core system receives about a read document.

``fields`` carries the whole reading, masked, with every confidence, check and note, for the
reviewer and the audit trail. The typed facts are what the rules act on, so a fact is only sent
when its field reached the review threshold: a doubtful reading is shown to a person instead of
silently driving a rule (a misread date would otherwise raise a false date inconsistency).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from tramita_agents.documents.extraction import REVIEW_THRESHOLD, ExtractedDocument, Value
from tramita_agents.documents.reader import ReadResult
from tramita_agents.documents.schemas import ReadDocumentType

# The date the rules compare with the incident date, per type of document.
_ISSUE_DATE = {
    ReadDocumentType.INVOICE: "issue_date",
    ReadDocumentType.ESTIMATE: "issue_date",
    ReadDocumentType.POLICE_REPORT: "filed_date",
    ReadDocumentType.ACCIDENT_REPORT: "report_date",
}


def _json(value: Value) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _trusted(extracted: ExtractedDocument, name: str) -> Value:
    field = extracted.fields.get(name)
    if field is None or field.confidence < REVIEW_THRESHOLD:
        return None
    return field.value


def _decimal(value: Value) -> str | None:
    return str(value) if isinstance(value, Decimal) else None


def extraction_payload(result: ReadResult) -> dict[str, Any]:
    extracted = result.extracted
    kind = extracted.document_type
    fields = {
        "document_type": kind.value,
        "source": extracted.source.value,
        "provider": result.provider,
        "model": result.model,
        "values": {
            name: {"value": _json(f.value), "confidence": f.confidence, "notes": list(f.notes)}
            for name, f in extracted.fields.items()
        },
        "checks": [asdict(c) for c in extracted.checks],
        "needs_review": extracted.low_confidence(),
        "notes": extracted.notes,
        "embedded_instructions": result.instructions(),
        "personal_data_masked": result.pii_counts,
        "ocr_confidence": result.ocr_confidence,
    }
    issue = _trusted(extracted, _ISSUE_DATE[kind]) if kind in _ISSUE_DATE else None
    payload: dict[str, Any] = {
        "fields": fields,
        "issue_date": issue.isoformat() if isinstance(issue, date) else None,
        "issuer_tax_id": None,
        "document_number": None,
        "stated_total": None,
        "tax_rate": None,
        "line_amounts": None,
    }
    if kind in {ReadDocumentType.INVOICE, ReadDocumentType.ESTIMATE}:
        tax_id = _trusted(extracted, "issuer_tax_id")
        number = _trusted(extracted, "document_number")
        payload["issuer_tax_id"] = tax_id if isinstance(tax_id, str) else None
        payload["document_number"] = number if isinstance(number, str) else None
        total = _decimal(_trusted(extracted, "total"))
        rate = _decimal(_trusted(extracted, "tax_rate_percent"))
        lines = extracted.line_amounts()
        lines_trusted = lines is not None and all(
            extracted.fields[f"lines[{i}].amount"].confidence >= REVIEW_THRESHOLD
            for i in range(len(lines))
        )
        # The rules need the three together; a partial set is no better than none.
        if total is not None and rate is not None and lines is not None and lines_trusted:
            payload["stated_total"] = total
            payload["tax_rate"] = rate
            payload["line_amounts"] = [str(a) for a in lines]
    return payload
