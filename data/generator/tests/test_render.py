import pypdfium2 as pdfium

from tramita_datagen.models import Dataset, DocumentFormat
from tramita_datagen.render import FOOTER, render_pdf, to_scan


def _text(pdf_bytes: bytes) -> str:
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        return str(document[0].get_textpage().get_text_range())
    finally:
        document.close()


def test_pdfs_render_byte_for_byte_reproducibly(dataset: Dataset) -> None:
    pdf = next(d for d in dataset.documents if d.format is DocumentFormat.PDF)
    assert render_pdf(pdf) == render_pdf(pdf)


def test_scans_are_reproducible_for_a_seed_and_vary_across_seeds(dataset: Dataset) -> None:
    page = render_pdf(dataset.documents[0])
    assert to_scan(page, seed=11) == to_scan(page, seed=11)
    assert to_scan(page, seed=11) != to_scan(page, seed=12)


def test_every_document_carries_the_synthetic_disclaimer(dataset: Dataset) -> None:
    for doc in dataset.documents[:20]:
        assert FOOTER in _text(render_pdf(doc))


def test_hidden_instructions_reach_the_pdf_text_layer(dataset: Dataset) -> None:
    injected = [
        d for d in dataset.documents if d.injected_instruction and d.format is DocumentFormat.PDF
    ]
    assert injected
    for doc in injected:
        assert doc.injected_instruction is not None
        assert doc.injected_instruction[:40] in " ".join(_text(render_pdf(doc)).split())


def test_invoice_text_contains_its_total(dataset: Dataset) -> None:
    doc = next(
        d for d in dataset.documents if d.repair is not None and d.format is DocumentFormat.PDF
    )
    assert doc.repair is not None
    whole, _, cents = f"{doc.repair.total:,.2f}".partition(".")
    assert whole.replace(",", ".") + "," + cents in _text(render_pdf(doc))
