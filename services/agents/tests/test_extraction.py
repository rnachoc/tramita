from datetime import date
from decimal import Decimal

import pytest

from tramita_agents.documents.extraction import (
    REVIEW_THRESHOLD,
    Source,
    parse_amount,
    parse_date,
    score,
    valid_cif,
)
from tramita_agents.documents.schemas import (
    DocumentRead,
    LineRead,
    PoliceReportRead,
    ReadDocumentType,
    RepairRead,
)

INVOICE_TEXT = """Fontanería Hermanos Robledo S.L.
CIF B09318460 · <ADDRESS_1>
FACTURA Nº F2026-4661
Fecha: 25/01/2026
Cliente <PERSON_1> · NIF <ES_NIF_1>
Sustitución de tubería de cobre 2 120,50 € 241,00 €
Mano de obra de fontanería 3 45,00 € 135,00 €
Base imponible: 376,00 €
IVA (21%): 78,96 €
TOTAL: 454,96 €
"""


def _invoice(**changes: object) -> DocumentRead:
    repair = RepairRead(
        document_number="F2026-4661",
        issue_date="2026-01-25",
        issuer_name="Fontanería Hermanos Robledo S.L.",
        issuer_tax_id="B09318460",
        customer="<PERSON_1>",
        lines=[
            LineRead(
                description="Sustitución de tubería de cobre",
                quantity="2",
                unit_price="120.50",
                amount="241.00",
            ),
            LineRead(
                description="Mano de obra de fontanería",
                quantity="3",
                unit_price="45.00",
                amount="135.00",
            ),
        ],
        subtotal="376.00",
        tax_rate_percent="21",
        tax_amount="78.96",
        total="454.96",
    ).model_copy(update=changes)
    return DocumentRead(
        document_type=ReadDocumentType.INVOICE,
        repair=repair,
        police_report=None,
        accident_report=None,
        embedded_instructions=[],
        unreadable_fields=[],
    )


def test_values_confirmed_by_the_text_layer_score_high() -> None:
    result = score(_invoice(), Source.TEXT_LAYER, INVOICE_TEXT)

    assert result.value("total") == Decimal("454.96")
    assert result.value("issue_date") == date(2026, 1, 25)
    assert result.fields["total"].confidence == pytest.approx(0.98)
    assert result.fields["issuer_tax_id"].confidence == pytest.approx(0.98)
    assert result.low_confidence() == []
    assert all(check.passed for check in result.checks)
    assert result.line_amounts() == [Decimal("241.00"), Decimal("135.00")]


def test_a_scan_value_ocr_could_not_confirm_goes_to_review() -> None:
    ocr_text = INVOICE_TEXT.replace("454,96", "45496")

    result = score(_invoice(), Source.SCAN, ocr_text)

    assert result.fields["subtotal"].confidence == pytest.approx(0.83)
    assert result.fields["total"].confidence < REVIEW_THRESHOLD
    assert result.low_confidence() == ["total"]


def test_missing_and_unparseable_values() -> None:
    result = score(_invoice(document_number=None, total="cuatrocientos"), Source.TEXT_LAYER, "")

    assert result.fields["document_number"].confidence == 0.0
    assert result.fields["total"].value is None
    assert result.fields["total"].confidence == pytest.approx(0.2)
    assert {"document_number", "total"} <= set(result.low_confidence())


def test_a_cif_with_a_wrong_control_digit_is_doubted() -> None:
    result = score(
        _invoice(issuer_tax_id="B09318461"),
        Source.TEXT_LAYER,
        INVOICE_TEXT.replace("B09318460", "B09318461"),
    )

    assert result.fields["issuer_tax_id"].confidence == pytest.approx(0.59)
    assert "issuer_tax_id" in result.low_confidence()


def test_misread_line_amounts_lower_the_confidence_of_the_lines_and_subtotal() -> None:
    result = score(_invoice(subtotal="386.00"), Source.TEXT_LAYER, INVOICE_TEXT)

    failed = {c.name for c in result.checks if not c.passed}
    assert "lines add up to the subtotal" in failed
    assert result.fields["lines[0].amount"].confidence < 0.6
    assert result.fields["subtotal"].confidence < 0.6


def test_an_inflated_total_is_reported_but_trusted_as_printed() -> None:
    text = INVOICE_TEXT.replace("454,96", "563,15")

    result = score(_invoice(total="563.15"), Source.TEXT_LAYER, text)

    failed = [c for c in result.checks if not c.passed]
    assert [c.name for c in failed] == ["total is subtotal plus tax"]
    assert result.fields["total"].confidence == pytest.approx(0.98)


def test_a_type_without_its_fields_asks_for_review() -> None:
    read = _invoice().model_copy(update={"repair": None})

    result = score(read, Source.TEXT_LAYER, INVOICE_TEXT)

    assert "total" in result.low_confidence()
    assert any("fields were not returned" in note for note in result.notes)


def test_police_report_dates_and_items() -> None:
    read = DocumentRead(
        document_type=ReadDocumentType.POLICE_REPORT,
        repair=None,
        police_report=PoliceReportRead(
            report_number="DEN-2026-41691",
            station="Comisaría de Distrito de Sevilla (ficticia)",
            filed_date="2026-03-01",
            incident_date="2026-02-27",
            complainant="<PERSON_1>",
            stolen_items=["ordenador portátil", "televisor"],
            forced_entry=True,
            alcohol_test_mg_l=None,
        ),
        accident_report=None,
        embedded_instructions=["  "],
        unreadable_fields=[],
    )
    text = (
        "Número: DEN-2026-41691 · Fecha de presentación: 01/03/2026 Comisaria de Distrito de "
        "Sevilla (ficticia) Fecha de los hechos: 27/02/2026. Efectos sustraídos: ordenador "
        "portatil, televisor."
    )

    result = score(read, Source.TEXT_LAYER, text)

    assert result.low_confidence() == []
    assert result.fields["stolen_items"].confidence == pytest.approx(0.98)
    assert result.fields["alcohol_test_mg_l"].confidence == 0.0
    assert result.embedded_instructions == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1287.59", Decimal("1287.59")),
        ("1.287,59 €", Decimal("1287.59")),
        ("135,00", Decimal("135.00")),
        ("21", Decimal(21)),
        ("NaN", None),
        ("doce", None),
        (None, None),
    ],
)
def test_parse_amount(raw: str | None, expected: Decimal | None) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-25", date(2026, 1, 25)),
        ("25/01/2026", date(2026, 1, 25)),
        ("31/09/2026", None),
        ("ayer", None),
    ],
)
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_valid_cif() -> None:
    assert valid_cif("B09318460")
    assert valid_cif("B16618928")
    assert not valid_cif("B09318461")
    assert not valid_cif("809318460")
    assert valid_cif("Q2826000H")
    assert not valid_cif("Q28260008")


def test_an_invoice_without_lines_goes_to_review() -> None:
    read = _invoice()
    assert read.repair is not None
    read.repair.lines.clear()

    result = score(read, Source.TEXT_LAYER, INVOICE_TEXT)

    assert result.low_confidence() == ["lines"]
    assert result.line_amounts() is None
