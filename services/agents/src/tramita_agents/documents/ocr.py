"""OCR for scanned documents, used to find and black out personal data before a model sees it.

Tesseract (Spanish data) returns every word with its bounding box. The words are joined into
text with known character offsets, personal data is detected in that text with the same
recognisers used for PDFs, and every word that overlaps a finding is painted over in the image.
The model then reads the redacted image; the original never leaves the document store.

OCR misses some words, so redaction is not perfect: the extraction evaluation measures how much
personal data survives it (re-running OCR on the redacted image) instead of assuming it is zero.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pytesseract
from PIL import Image, ImageDraw

from tramita_agents.documents.pii import MaskedText, Pseudonymizer, mask

OCR_LANGUAGE = "spa"
# Fully automatic page segmentation, LSTM engine.
OCR_CONFIG = "--psm 3 --oem 1"
# Scans arrive at about 100 dpi, too coarse for Tesseract: it misreads the "B" of company tax
# ids and digits in amounts. Upscaling to about this width (300 dpi for A4) fixed every value
# in a sample of generated invoices, at roughly twice the OCR time.
OCR_TARGET_WIDTH = 2500
# Extra pixels around each redacted word, so anti-aliased edges do not survive.
BOX_PADDING = 3


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    start: int  # character offsets of the word in OcrPage.text
    end: int


@dataclass(frozen=True)
class OcrPage:
    text: str
    words: tuple[OcrWord, ...]

    def mean_confidence(self) -> float:
        if not self.words:
            return 0.0
        return sum(w.confidence for w in self.words) / len(self.words) / 100


def load_image(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return image.convert("L")


def read_page(image: Image.Image) -> OcrPage:
    """Runs Tesseract and joins the words into lines and blocks, keeping offsets.

    Word boxes are in the coordinates of ``image``, whatever scale OCR ran at.
    """
    scale = max(1, round(OCR_TARGET_WIDTH / image.width))
    upscaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
    data = pytesseract.image_to_data(
        upscaled, lang=OCR_LANGUAGE, config=OCR_CONFIG, output_type=pytesseract.Output.DICT
    )
    parts: list[str] = []
    words: list[OcrWord] = []
    offset = 0
    previous_line: tuple[int, int, int] | None = None
    for i, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        line = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        if previous_line is not None:
            separator = " " if line == previous_line else "\n"
            if line[0] != previous_line[0]:
                separator = "\n\n"
            parts.append(separator)
            offset += len(separator)
        previous_line = line
        words.append(
            OcrWord(
                text=text,
                left=int(data["left"][i]) // scale,
                top=int(data["top"][i]) // scale,
                width=-(-int(data["width"][i]) // scale),
                height=-(-int(data["height"][i]) // scale),
                confidence=max(float(data["conf"][i]), 0.0),
                start=offset,
                end=offset + len(text),
            )
        )
        parts.append(text)
        offset += len(text)
    return OcrPage(text="".join(parts), words=tuple(words))


@dataclass(frozen=True)
class RedactedScan:
    image: bytes  # PNG, grey scale
    ocr: OcrPage
    masked: MaskedText  # the OCR text with personal data replaced by tokens
    redacted_words: int


def redact(image: Image.Image, page: OcrPage, pseudonyms: Pseudonymizer) -> RedactedScan:
    masked = mask(page.text, pseudonyms)
    redacted = image.copy()
    draw = ImageDraw.Draw(redacted)
    covered = 0
    for finding in masked.findings:
        for word in page.words:
            if word.start < finding.end and finding.start < word.end:
                draw.rectangle(
                    (
                        word.left - BOX_PADDING,
                        word.top - BOX_PADDING,
                        word.left + word.width + BOX_PADDING,
                        word.top + word.height + BOX_PADDING,
                    ),
                    fill=0,
                )
                covered += 1
    out = io.BytesIO()
    redacted.save(out, format="PNG", optimize=True)
    return RedactedScan(image=out.getvalue(), ocr=page, masked=masked, redacted_words=covered)


def redact_scan(data: bytes, pseudonyms: Pseudonymizer) -> RedactedScan:
    image = load_image(data)
    return redact(image, read_page(image), pseudonyms)
