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
import statistics
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
# Lines whose vertical extents overlap by this fraction of the smaller one share a row.
ROW_OVERLAP = 0.5
# A vertical gap larger than this many word heights starts a new section (blank line).
SECTION_GAP = 1.2
# Lines with fewer words do not say much about the page's rotation.
MIN_WORDS_FOR_SKEW = 3
MIN_RUN_FOR_SKEW = 150
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


@dataclass(frozen=True)
class _Box:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    line: tuple[int, int, int]  # Tesseract's block, paragraph and line numbers


def _tesseract_words(image: Image.Image) -> list[_Box]:
    scale = max(1, round(OCR_TARGET_WIDTH / image.width))
    upscaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
    data = pytesseract.image_to_data(
        upscaled, lang=OCR_LANGUAGE, config=OCR_CONFIG, output_type=pytesseract.Output.DICT
    )
    boxes = []
    for i, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if text:
            boxes.append(
                _Box(
                    text=text,
                    left=int(data["left"][i]) // scale,
                    top=int(data["top"][i]) // scale,
                    width=-(-int(data["width"][i]) // scale),
                    height=-(-int(data["height"][i]) // scale),
                    confidence=max(float(data["conf"][i]), 0.0),
                    line=(
                        int(data["block_num"][i]),
                        int(data["par_num"][i]),
                        int(data["line_num"][i]),
                    ),
                )
            )
    return boxes


def _skew(lines: dict[tuple[int, int, int], list[_Box]], height: float) -> float:
    """Median slope along Tesseract's lines: the page's slight rotation.

    Only words of ordinary height are used (accents and descenders make boxes taller), and only
    lines long enough for the slope to show.
    """
    slopes = []
    for boxes in lines.values():
        plain = [b for b in boxes if 0.8 * height <= b.height <= 1.25 * height]
        if len(plain) >= MIN_WORDS_FOR_SKEW:
            first, last = plain[0], plain[-1]
            run = (last.left + last.width / 2) - (first.left + first.width / 2)
            if run >= MIN_RUN_FOR_SKEW:
                rise = (last.top + last.height / 2) - (first.top + first.height / 2)
                slopes.append(rise / run)
    return statistics.median(slopes) if slopes else 0.0


def _rows(boxes: list[_Box]) -> list[list[_Box]]:
    """Groups words into visual rows, also across Tesseract's blocks.

    Tesseract reads a table column by column, which separates each line description from its
    amounts. Rows are rebuilt from positions instead, after undoing the page's slight rotation:
    a line joins a row when their vertical extents overlap by at least half the smaller one.
    """
    lines: dict[tuple[int, int, int], list[_Box]] = {}
    for box in boxes:
        lines.setdefault(box.line, []).append(box)
    height = statistics.median(b.height for b in boxes)
    slope = _skew(lines, height)

    def extent(line: list[_Box]) -> tuple[float, float]:
        tops = [b.top - slope * (b.left + b.width / 2) for b in line]
        bottoms = [t + b.height for t, b in zip(tops, line, strict=True)]
        return min(tops), max(bottoms)

    rows: list[tuple[tuple[float, float], list[_Box]]] = []
    for line in sorted(lines.values(), key=lambda line: extent(line)[0]):
        top, bottom = extent(line)
        joined = False
        for (row_top, row_bottom), row in reversed(rows[-3:]):
            overlap = min(bottom, row_bottom) - max(top, row_top)
            if overlap >= ROW_OVERLAP * min(bottom - top, row_bottom - row_top):
                row.extend(line)
                joined = True
                break
        if not joined:
            rows.append(((top, bottom), list(line)))
    return [sorted(row, key=lambda b: b.left) for _, row in rows]


def read_page(image: Image.Image) -> OcrPage:
    """Runs Tesseract and lays the words out in visual rows, keeping their offsets.

    Rows are separated by a line break, and by a blank line where the vertical gap is large
    (a new section). Word boxes are in the coordinates of ``image``, whatever scale OCR ran at.
    """
    boxes = _tesseract_words(image)
    if not boxes:
        return OcrPage(text="", words=())
    rows = _rows(boxes)
    height = statistics.median(b.height for b in boxes)
    parts: list[str] = []
    words: list[OcrWord] = []
    offset = 0
    previous_bottom: float | None = None
    for row in rows:
        top = min(b.top for b in row)
        if previous_bottom is not None:
            separator = "\n\n" if top - previous_bottom > height * SECTION_GAP else "\n"
            parts.append(separator)
            offset += len(separator)
        previous_bottom = max(b.top + b.height for b in row)
        for index, box in enumerate(row):
            if index:
                parts.append(" ")
                offset += 1
            words.append(
                OcrWord(
                    text=box.text,
                    left=box.left,
                    top=box.top,
                    width=box.width,
                    height=box.height,
                    confidence=box.confidence,
                    start=offset,
                    end=offset + len(box.text),
                )
            )
            parts.append(box.text)
            offset += len(box.text)
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
