"""Rule-based reading of claim documents: the fake model's answer to ``document.read``.

It parses the masked text quoted in the request (the PDF text layer or the scan's OCR) with
regular expressions written for Spanish invoices, estimates, police reports and accident
reports. It never looks at the image, so on scans it is only as good as the OCR. It is a
deterministic baseline that lets the whole pipeline run without an API key; every report
labels its numbers as coming from this responder, never as model quality (ADR 0007).
"""

from __future__ import annotations

import re
from datetime import date

from tramita_agents.documents.extraction import valid_cif
from tramita_agents.documents.injection import find_instructions
from tramita_agents.documents.schemas import (
    AccidentReportRead,
    DocumentRead,
    LineRead,
    PoliceReportRead,
    ReadDocumentType,
    RepairRead,
)
from tramita_agents.llm.types import ModelRequest, TextBlock

_DOCUMENT = re.compile(r"<document source=\"[^\"]*\">\n(.*)\n</document>", re.DOTALL)
_MONEY = r"\d{1,3}(?:[.,]?\d{3})*[,.]\d{2}"
_DATE = r"\d{1,2}/\d{1,2}/\d{4}"
_PSEUDONYM = r"<[A-Z_]+_\d+>"


def respond(request: ModelRequest) -> str:
    text = document_text(request)
    return read_text(text).model_dump_json()


def document_text(request: ModelRequest) -> str:
    for block in request.content:
        if isinstance(block, TextBlock):
            match = _DOCUMENT.search(block.text)
            if match:
                return match.group(1)
    return ""


# --------------------------------------------------------------------------- helpers


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _amount(raw: str | None) -> str | None:
    """'1.287,59' -> '1287.59'. OCR sometimes prints a dot as the decimal mark: '271.40'."""
    if raw is None:
        return None
    digits = re.sub(r"[^\d,.]", "", raw)
    if not re.fullmatch(r"[\d.,]*[.,]\d{2}", digits):
        return None
    whole, cents = digits[:-3], digits[-2:]
    return f"{re.sub(r'[.,]', '', whole) or '0'}.{cents}"


def _iso(raw: str | None) -> str | None:
    """'25/01/2026' -> '2026-01-25'. An impossible date (an OCR misread) is passed on as read,
    so the scoring marks it unparseable instead of the responder inventing a valid one."""
    if raw is None:
        return None
    day, month, year = (int(p) for p in raw.split("/"))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return raw


def _classify(text: str) -> ReadDocumentType:
    upper = text.upper()
    if "DECLARACIÓN AMISTOSA" in upper or "DECLARACION AMISTOSA" in upper:
        return ReadDocumentType.ACCIDENT_REPORT
    if re.search(r"\b(?:DENUNCIA|ATESTADO)\b", upper):
        return ReadDocumentType.POLICE_REPORT
    if re.search(r"\bPRESUPUESTO\s*N", upper):
        return ReadDocumentType.ESTIMATE
    if re.search(r"\bFACTURA\b", upper):
        return ReadDocumentType.INVOICE
    return ReadDocumentType.OTHER


# --------------------------------------------------------------------------- repairs


def _tax_id(text: str) -> str | None:
    raw = _search(r"\bC\.?I\.?F\.?:?\s*([A-Z0-9]\d{7}[0-9A-J])\b", text)
    if raw and raw[0] == "8" and valid_cif("B" + raw[1:]):
        return "B" + raw[1:]  # OCR reads the B of a limited company as an 8
    return raw


# One table row: description, quantity (OCR sometimes misses a lone "1"), unit price, amount.
_LINE = re.compile(
    rf"^(?P<description>[A-ZÁÉÍÓÚÑ¡][^\n€]*?)(?:\s+(?P<quantity>\d+(?:[.,]\d+)?))?\s+"
    rf"(?P<unit>{_MONEY})\s*€?\s+(?P<amount>{_MONEY})\s*€?\s*$",
    re.MULTILINE,
)


def _lines(text: str) -> list[LineRead]:
    return [
        LineRead(
            description=m["description"].lstrip("¡").strip(),
            quantity=m["quantity"].replace(",", ".") if m["quantity"] else None,
            unit_price=_amount(m["unit"]),
            amount=_amount(m["amount"]),
        )
        for m in _LINE.finditer(_table_body(text))
    ]


def _table_body(text: str) -> str:
    start = re.search(r"^.*\bConcepto\b.*$", text, re.MULTILINE)
    end = re.search(r"^.*\bBase imponible\b", text, re.MULTILINE | re.IGNORECASE)
    begin = start.end() if start else 0
    return text[begin : end.start() if end and end.start() > begin else len(text)]


def _repair(text: str) -> RepairRead:
    tax = re.search(rf"IVA\s*\((\d+(?:[.,]\d+)?)\s*%\)\s*:?\s*({_MONEY})", text, re.IGNORECASE)
    company = re.search(r"^.*\bS\.(?:L|A)\.(?:U\.)?$", text, re.MULTILINE)
    return RepairRead(
        document_number=_search(
            r"(?:FACTURA|PRESUPUESTO)\s*N\S{0,2}\s*([A-Z]{1,3}\d{4}-\d+)", text
        ),
        issue_date=_iso(_search(rf"Fecha:\s*({_DATE})", text)),
        issuer_name=company.group(0).strip() if company else None,
        issuer_tax_id=_tax_id(text),
        customer=_search(rf"Cliente\s*:?\s*({_PSEUDONYM})", text),
        lines=_lines(text),
        subtotal=_amount(_search(rf"Base imponible:?\s*({_MONEY})", text)),
        tax_rate_percent=tax.group(1).replace(",", ".") if tax else None,
        tax_amount=_amount(tax.group(2)) if tax else None,
        total=_amount(_search(rf"\bTOTAL:?\s*({_MONEY})", text, 0)),
    )


# --------------------------------------------------------------------------- reports


def _police(text: str) -> PoliceReportRead:
    items = _search(r"Efectos sustra[íi]dos\s*\n(.*?)(?:\n\s*\n|\n(?:Se|No se) aprecian|$)", text)
    if re.search(r"No se aprecian señales de forzamiento", text, re.IGNORECASE):
        forced: bool | None = False
    elif re.search(r"Se aprecian señales de forzamiento", text, re.IGNORECASE):
        forced = True
    else:
        forced = None
    return PoliceReportRead(
        report_number=_search(r"N[úu]mero:?\s*([A-Z]{2,4}-\d{4}-\d+)", text),
        station=_search(
            r"^(.*(?:Comisar[íi]a|Guardia Civil|Polic[íi]a|Puesto).*)$", text, re.MULTILINE
        ),
        filed_date=_iso(_search(rf"presentaci[óo]n:?\s*({_DATE})", text)),
        incident_date=_iso(_search(rf"Fecha de los hechos:?\s*({_DATE})", text)),
        complainant=_search(rf"({_PSEUDONYM}),?\s*con\s+NIF", text),
        stolen_items=[
            i.strip(" .")
            for i in re.split(r",\s*", " ".join((items or "").split()))
            if i.strip(" .")
        ],
        forced_entry=forced,
        alcohol_test_mg_l=_search(r"aire espirado:?\s*(\d+[.,]\d+)\s*mg", text),
    )


def _accident(text: str) -> AccidentReportRead:
    insurers = _search(r"^Aseguradora\s+(.*)$", text, re.MULTILINE)
    circumstances = _search(r"Circunstancias\s*\n(.*?)(?:\n\s*Firma|$)", text, re.DOTALL)
    return AccidentReportRead(
        report_date=_iso(_search(rf"Fecha de la declaraci[óo]n:?\s*({_DATE})", text)),
        incident_date=_iso(_search(rf"Fecha del accidente:?\s*({_DATE})", text)),
        location=_search(r"Lugar:?\s*(.+)$", text, re.MULTILINE),
        other_party_involved=insurers is not None and not insurers.rstrip().endswith(" -"),
        circumstances=" ".join(circumstances.split()) if circumstances else None,
    )


# --------------------------------------------------------------------------- entry point


def read_text(text: str) -> DocumentRead:
    kind = _classify(text)
    repair = police = accident = None
    if kind in {ReadDocumentType.INVOICE, ReadDocumentType.ESTIMATE}:
        repair = _repair(text)
    elif kind is ReadDocumentType.POLICE_REPORT:
        police = _police(text)
    elif kind is ReadDocumentType.ACCIDENT_REPORT:
        accident = _accident(text)
    return DocumentRead(
        document_type=kind,
        repair=repair,
        police_report=police,
        accident_report=accident,
        embedded_instructions=[found.text for found in find_instructions(text)],
        unreadable_fields=[],
    )
