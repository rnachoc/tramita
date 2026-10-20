"""Renders claim documents as PDFs, and some of them as scanned-looking JPEGs.

PDFs are produced with reportlab's invariant mode, so the same seed produces the
same bytes. Scans are rasterised from the PDF and degraded (grey scale, slight
rotation, noise, blur, JPEG compression) with a seeded random generator.

Planted prompt-injection text is drawn in white in PDFs (invisible to a reader,
present in the text layer) and as small grey print in scans (visible to OCR and
vision models, easy for a human to overlook).
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from tramita_datagen.models import Document, DocumentFormat, DocumentType, RepairDocument
from tramita_datagen.util import require

rl_config.invariant = 1

FOOTER = "Documento sintético generado para el proyecto Tramita. Sin validez legal ni comercial."

_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontSize=15, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_styles["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9, textColor=colors.grey)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)


def eur(value: Decimal) -> str:
    whole, _, cents = f"{value:,.2f}".partition(".")
    return whole.replace(",", ".") + "," + cents + " €"


def _date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _table(rows: list[list[str | Flowable]], widths: list[float], header: bool = True) -> Table:
    table = Table(rows, colWidths=widths)
    style: list[Any] = [  # reportlab's command tuples are heterogeneous
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ]
    table.setStyle(TableStyle(style))
    return table


def _repair_story(doc: Document, repair: RepairDocument) -> list[Flowable]:
    title = "FACTURA" if doc.document_type is DocumentType.INVOICE else "PRESUPUESTO"
    story: list[Flowable] = [
        Paragraph(repair.issuer.name, H1),
        Paragraph(f"CIF {repair.issuer.tax_id} · {repair.issuer.address}", BODY),
        Spacer(1, 6 * mm),
        Paragraph(f"{title} Nº {repair.number}", H2),
        Paragraph(f"Fecha: {_date(repair.issue_date)}", BODY),
        Spacer(1, 3 * mm),
        Paragraph("Cliente", H2),
        Paragraph(f"{repair.customer.name} · NIF {repair.customer.tax_id}", BODY),
        Paragraph(repair.customer.address or "", BODY),
        Spacer(1, 4 * mm),
    ]
    rows: list[list[str | Flowable]] = [["Concepto", "Cantidad", "Precio unitario", "Importe"]]
    for item in repair.items:
        rows.append(
            [
                Paragraph(item.description, BODY),
                f"{item.quantity}",
                eur(item.unit_price),
                eur(item.amount),
            ]
        )
    story.append(_table(rows, [88 * mm, 20 * mm, 32 * mm, 30 * mm]))
    story += [
        Spacer(1, 3 * mm),
        Paragraph(f"Base imponible: {eur(repair.subtotal)}", RIGHT),
        Paragraph(f"IVA ({repair.tax_rate}%): {eur(repair.tax_amount)}", RIGHT),
        Paragraph(f"<b>TOTAL: {eur(repair.total)}</b>", RIGHT),
    ]
    if doc.document_type is DocumentType.ESTIMATE:
        story += [
            Spacer(1, 4 * mm),
            Paragraph("Presupuesto válido durante 30 días. Pendiente de aceptación.", BODY),
        ]
    else:
        story += [
            Spacer(1, 4 * mm),
            Paragraph("Forma de pago: transferencia bancaria a 30 días.", BODY),
        ]
    return story


def _police_story(doc: Document) -> list[Flowable]:
    report = require(doc.police_report, "police report")
    is_record = report.alcohol_test_mg_l is not None
    story: list[Flowable] = [
        Paragraph(report.station, BODY),
        Paragraph("ATESTADO" if is_record else "COPIA DE DENUNCIA", H1),
        Paragraph(
            f"Número: {report.report_number} · Fecha de presentación: {_date(report.filed_date)}",
            BODY,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Datos del compareciente", H2),
        Paragraph(
            f"{report.complainant.name}, con NIF {report.complainant.tax_id}, domicilio en "
            f"{report.complainant.address} y teléfono {report.complainant_phone}.",
            BODY,
        ),
        Paragraph("Hechos", H2),
        Paragraph(f"Fecha de los hechos: {_date(report.incident_date)}.", BODY),
        Paragraph(report.narrative, BODY),
    ]
    if report.stolen_items:
        story += [
            Paragraph("Efectos sustraídos", H2),
            Paragraph(", ".join(report.stolen_items) + ".", BODY),
        ]
    if not is_record:
        forced = (
            "Se aprecian señales de forzamiento."
            if report.forced_entry
            else "No se aprecian señales de forzamiento."
        )
        story.append(Paragraph(forced, BODY))
    else:
        story.append(
            Paragraph(
                f"Resultado de la prueba de detección alcohólica en aire espirado: {report.alcohol_test_mg_l} mg/l.",
                BODY,
            )
        )
    return story


def _accident_story(doc: Document) -> list[Flowable]:
    report = require(doc.accident_report, "accident report")
    rows: list[list[str | Flowable]] = [
        ["", "Vehículo A", "Vehículo B"],
        ["Conductor", report.driver_a.name, report.driver_b.name if report.driver_b else "-"],
        ["NIF", report.driver_a.tax_id, report.driver_b.tax_id if report.driver_b else "-"],
        ["Matrícula", report.plate_a, report.plate_b or "-"],
        ["Aseguradora", report.insurer_a, report.insurer_b or "-"],
    ]
    return [
        Paragraph("DECLARACIÓN AMISTOSA DE ACCIDENTE", H1),
        Paragraph("Modelo simplificado", SMALL),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Fecha del accidente: {_date(report.incident_date)} · Fecha de la declaración: {_date(report.report_date)}",
            BODY,
        ),
        Paragraph(f"Lugar: {report.location}", BODY),
        Spacer(1, 3 * mm),
        _table(rows, [35 * mm, 67 * mm, 67 * mm]),
        Paragraph("Circunstancias", H2),
        Paragraph(report.circumstances, BODY),
        Spacer(1, 6 * mm),
        Paragraph(
            "Firma conductor A ______________________     Firma conductor B ______________________",
            BODY,
        ),
    ]


def render_pdf(doc: Document) -> bytes:
    buffer = io.BytesIO()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=doc.filename,
        author="Tramita synthetic data",
        invariant=1,
    )
    if doc.repair is not None:
        story = _repair_story(doc, doc.repair)
    elif doc.police_report is not None:
        story = _police_story(doc)
    else:
        story = _accident_story(doc)

    injected = doc.injected_instruction
    visible_injection = doc.format is DocumentFormat.SCAN

    def decorate(canvas: Canvas, _template: object) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(18 * mm, 10 * mm, FOOTER)
        if injected:
            if visible_injection:
                canvas.setFont("Helvetica", 6)
                canvas.setFillColor(colors.Color(0.55, 0.55, 0.55))
                canvas.drawString(18 * mm, 14 * mm, injected[:150])
            else:
                canvas.setFont("Helvetica", 4)
                canvas.setFillColor(colors.white)
                canvas.drawString(18 * mm, 15 * mm, injected)
        canvas.restoreState()

    template.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


def to_scan(pdf_bytes: bytes, seed: int) -> bytes:
    """Rasterises the first page and makes it look photocopied."""
    rng = np.random.default_rng(seed)
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page = pdf[0]
        image = page.render(scale=1.4).to_pil().convert("L")
        page.close()
    finally:
        pdf.close()
    angle = float(rng.uniform(-1.6, 1.6))
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=245)
    pixels = np.asarray(image, dtype=np.float32)
    pixels = pixels * float(rng.uniform(0.88, 0.97)) + float(rng.uniform(4, 14))
    pixels += rng.normal(0, 7.0, pixels.shape)
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), mode="L")
    image = image.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.3, 0.7))))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=int(rng.integers(62, 78)), optimize=False)
    return out.getvalue()


def write_document(doc: Document, directory: Path, seed: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    pdf_bytes = render_pdf(doc)
    data = to_scan(pdf_bytes, seed) if doc.format is DocumentFormat.SCAN else pdf_bytes
    path = directory / doc.filename
    path.write_bytes(data)
    return path
