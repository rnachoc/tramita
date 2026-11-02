"""Synthetic claim documents rendered with the data generator, for document-reading tests."""

from __future__ import annotations

import os
import shutil
from datetime import date
from decimal import Decimal

import pytest

from tramita_datagen.models import (
    Document,
    DocumentFormat,
    DocumentType,
    LineItem,
    Party,
    PoliceReport,
    RepairDocument,
)
from tramita_datagen.render import render_pdf, to_scan

# OCR needs the tesseract binary with Spanish data. CI installs it, so there a missing binary
# fails the tests; on a developer machine without it they are skipped.
requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None and not os.environ.get("CI"),
    reason="tesseract is not installed (apt install tesseract-ocr tesseract-ocr-spa)",
)

HOLDER = Party(
    name="Lucía Fernández García",
    tax_id="12345678Z",
    address="Calle Mayor, 15, 3º B, 41001 Sevilla",
)
PHONE = "+34 612 345 678"
SUPPLIER = Party(
    name="Fontanería Hermanos Robledo S.L.",
    tax_id="B09318460",
    address="Avenida de la Constitución, 21, 41004 Sevilla",
)


def invoice(fmt: DocumentFormat = DocumentFormat.PDF, injected: str | None = None) -> Document:
    items = [
        LineItem(
            description="Sustitución de tubería de cobre",
            quantity=Decimal(2),
            unit_price=Decimal("120.50"),
            amount=Decimal("241.00"),
        ),
        LineItem(
            description="Mano de obra de fontanería",
            quantity=Decimal(3),
            unit_price=Decimal("45.00"),
            amount=Decimal("135.00"),
        ),
    ]
    return Document(
        document_id="DOC-TEST-01",
        claim_id="CL-TEST",
        document_type=DocumentType.INVOICE,
        format=fmt,
        filename="DOC-TEST-01-invoice." + ("jpg" if fmt is DocumentFormat.SCAN else "pdf"),
        repair=RepairDocument(
            number="F2026-4661",
            issue_date=date(2026, 1, 25),
            issuer=SUPPLIER,
            customer=HOLDER,
            items=items,
            subtotal=Decimal("376.00"),
            tax_rate=Decimal(21),
            tax_amount=Decimal("78.96"),
            total=Decimal("454.96"),
        ),
        injected_instruction=injected,
    )


def police_report(fmt: DocumentFormat = DocumentFormat.PDF) -> Document:
    return Document(
        document_id="DOC-TEST-02",
        claim_id="CL-TEST",
        document_type=DocumentType.POLICE_REPORT,
        format=fmt,
        filename="DOC-TEST-02-police-report." + ("jpg" if fmt is DocumentFormat.SCAN else "pdf"),
        police_report=PoliceReport(
            report_number="DEN-2026-41691",
            station="Comisaría de Distrito de Sevilla (ficticia)",
            filed_date=date(2026, 3, 1),
            incident_date=date(2026, 2, 27),
            complainant=Party(name=HOLDER.name, tax_id=HOLDER.tax_id, address=HOLDER.address),
            complainant_phone=PHONE,
            narrative="El compareciente manifiesta que al regresar a su domicilio encontró la puerta forzada.",
            stolen_items=["ordenador portátil", "televisor"],
            forced_entry=True,
        ),
    )


def render(doc: Document, seed: int = 7) -> bytes:
    pdf = render_pdf(doc)
    return to_scan(pdf, seed) if doc.format is DocumentFormat.SCAN else pdf
