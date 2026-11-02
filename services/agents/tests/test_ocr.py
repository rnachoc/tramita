import io

from documents_fixtures import HOLDER, PHONE, invoice, police_report, render, requires_tesseract
from PIL import Image

from tramita_agents.documents.ocr import load_image, read_page, redact_scan
from tramita_agents.documents.pii import Pseudonymizer
from tramita_datagen.models import DocumentFormat

pytestmark = requires_tesseract


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


def test_redacted_scan_no_longer_shows_personal_data_to_ocr() -> None:
    redacted = redact_scan(render(police_report(DocumentFormat.SCAN)), Pseudonymizer())

    seen_again = read_page(load_image(redacted.image)).text

    for value in ("Lucía", "Fernández", HOLDER.tax_id, "Calle Mayor"):
        assert value not in seen_again, value
    assert _digits(PHONE)[2:] not in _digits(seen_again)
    assert redacted.redacted_words >= 8


def test_redaction_leaves_what_the_rules_need_untouched() -> None:
    data = render(invoice(DocumentFormat.SCAN))
    original = load_image(data)

    redacted = redact_scan(data, Pseudonymizer())

    after = load_image(redacted.image)
    kept = {"B09318460", "F2026-4661", "25/01/2026", "454,96"}
    words = [w for w in redacted.ocr.words if w.text in kept]
    assert {w.text for w in words} == kept
    for word in words:
        box = (word.left, word.top, word.left + word.width, word.top + word.height)
        assert after.crop(box).tobytes() == original.crop(box).tobytes(), word.text
        assert word.text in redacted.masked.text


def test_masked_ocr_text_carries_tokens_instead_of_values() -> None:
    redacted = redact_scan(render(police_report(DocumentFormat.SCAN)), Pseudonymizer())

    assert "<PERSON_1>" in redacted.masked.text
    assert "<ES_NIF_1>" in redacted.masked.text
    assert HOLDER.tax_id not in redacted.masked.text
    assert redacted.ocr.mean_confidence() > 0.7


def test_word_boxes_are_in_the_original_image_coordinates() -> None:
    data = render(invoice(DocumentFormat.SCAN))
    image = load_image(data)

    page = read_page(image)

    assert page.words
    for word in page.words:
        assert 0 <= word.left < image.width
        assert 0 <= word.top < image.height
        assert word.left + word.width <= image.width + 1
        assert page.text[word.start : word.end] == word.text


def test_redacted_image_is_a_grey_png_of_the_same_size() -> None:
    data = render(invoice(DocumentFormat.SCAN))

    redacted = redact_scan(data, Pseudonymizer())

    with Image.open(io.BytesIO(redacted.image)) as image:
        assert image.format == "PNG"
        assert image.mode == "L"
        assert image.size == load_image(data).size
