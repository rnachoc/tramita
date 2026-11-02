import json
from datetime import date
from decimal import Decimal

from tramita_agents.documents.extraction import FieldValue, Source, score
from tramita_agents.documents.payload import extraction_payload
from tramita_agents.documents.reader import ReadResult
from tramita_agents.documents.schemas import (
    DocumentRead,
    LineRead,
    PoliceReportRead,
    ReadDocumentType,
    RepairRead,
)
from tramita_agents.llm.types import Usage

TEXT = (
    "FACTURA Nº F2026-4661 Fecha: 25/01/2026 CIF B09318460 "
    "Tubería 2 120,50 € 241,00 € Base imponible: 241,00 € IVA (21%): 50,61 € TOTAL: 291,61 €"
)


def _read(**changes: object) -> DocumentRead:
    repair = RepairRead(
        document_number="F2026-4661",
        issue_date="2026-01-25",
        issuer_name=None,
        issuer_tax_id="B09318460",
        customer="<PERSON_1>",
        lines=[LineRead(description="Tubería", quantity="2", unit_price="120.50", amount="241.00")],
        subtotal="241.00",
        tax_rate_percent="21",
        tax_amount="50.61",
        total="291.61",
    ).model_copy(update=changes)
    return DocumentRead(
        document_type=ReadDocumentType.INVOICE,
        repair=repair,
        police_report=None,
        accident_report=None,
        embedded_instructions=[],
        unreadable_fields=[],
    )


def _result(read: DocumentRead, text: str = TEXT) -> ReadResult:
    return ReadResult(
        extracted=score(read, Source.TEXT_LAYER, text),
        masked_text=text,
        pii_counts={"PERSON": 1},
        redacted_image=None,
        suspected_instructions=(),
        ocr_confidence=None,
        provider="fake:responder",
        model="fake",
        usage=Usage(),
        latency_ms=1.0,
    )


def test_payload_carries_typed_facts_and_the_full_masked_reading() -> None:
    payload = extraction_payload(_result(_read()))

    assert payload["issue_date"] == "2026-01-25"
    assert payload["issuer_tax_id"] == "B09318460"
    assert payload["document_number"] == "F2026-4661"
    assert (payload["stated_total"], payload["tax_rate"]) == ("291.61", "21")
    assert payload["line_amounts"] == ["241.00"]
    fields = payload["fields"]
    assert fields["values"]["customer"]["value"] == "<PERSON_1>"
    assert fields["values"]["total"] == {"value": "291.61", "confidence": 0.98, "notes": []}
    assert fields["needs_review"] == []
    assert fields["personal_data_masked"] == {"PERSON": 1}
    json.dumps(payload)  # everything is JSON-serialisable


def test_doubtful_facts_are_withheld_from_the_rules() -> None:
    result = _result(_read())
    result.extracted.fields["issue_date"] = FieldValue(date(2026, 1, 25), 0.4)
    result.extracted.fields["lines[0].amount"] = FieldValue(Decimal("241.00"), 0.5)

    payload = extraction_payload(result)

    assert payload["issue_date"] is None
    assert payload["line_amounts"] is None
    assert payload["stated_total"] is None
    assert payload["tax_rate"] is None
    assert payload["document_number"] == "F2026-4661"
    assert set(payload["fields"]["needs_review"]) == {"issue_date", "lines[0].amount"}


def test_police_reports_send_their_filing_date_as_issue_date() -> None:
    read = DocumentRead(
        document_type=ReadDocumentType.POLICE_REPORT,
        repair=None,
        police_report=PoliceReportRead(
            report_number="DEN-2026-1",
            station=None,
            filed_date="2026-03-01",
            incident_date="2026-02-27",
            complainant=None,
            stolen_items=[],
            forced_entry=None,
            alcohol_test_mg_l=None,
        ),
        accident_report=None,
        embedded_instructions=[],
        unreadable_fields=[],
    )

    payload = extraction_payload(_result(read, "Número: DEN-2026-1 01/03/2026 27/02/2026"))

    assert payload["issue_date"] == "2026-03-01"
    assert payload["line_amounts"] is None
