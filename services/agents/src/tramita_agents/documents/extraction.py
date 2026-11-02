"""Turns what the model read into checked facts with a confidence for every field.

The model's answer is a proposal. Code parses each value, checks its format, cross-checks
amounts against each other and looks for each value in an independent reading of the same
document (the PDF text layer, or Tesseract's OCR of a scan). The confidence of a field comes
from that evidence, not from the model's own opinion of itself:

* a value that is missing scores 0, and one that cannot be parsed scores 0.2;
* the starting point depends on the source: 0.85 for PDF text, 0.7 for a scan read by vision;
* found in the independent reading: +0.13; not found: x0.75;
* failing a format check (CIF control digit) or an arithmetic check it takes part in: x0.6.

A stated total that does not add up is reported as a failed check but does not lower the
total's confidence: an inflated total is what the document says, and the rules act on it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from tramita_agents.documents.schemas import DocumentRead, ReadDocumentType

CENT = Decimal("0.01")
REVIEW_THRESHOLD = 0.6
_UNPARSEABLE = 0.2
_FOUND_BONUS = 0.13
_NOT_FOUND = 0.75
_FAILED_CHECK = 0.6
_MAX = 0.99


class Source(StrEnum):
    TEXT_LAYER = "TEXT_LAYER"  # born-digital PDF: the model read the masked text layer
    SCAN = "SCAN"  # image: the model read the redacted scan; OCR text is the cross-check


_BASE = {Source.TEXT_LAYER: 0.85, Source.SCAN: 0.7}

type Value = str | Decimal | date | bool | list[str] | None


@dataclass(frozen=True)
class FieldValue:
    value: Value
    confidence: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class ExtractedDocument:
    document_type: ReadDocumentType
    source: Source
    fields: dict[str, FieldValue]
    checks: list[Check]
    embedded_instructions: list[str]
    key_fields: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    def value(self, name: str) -> Value:
        found = self.fields.get(name)
        return None if found is None else found.value

    def low_confidence(self) -> list[str]:
        """Key fields a person should check before the facts are relied on."""
        return [
            name
            for name in self.key_fields
            if name not in self.fields or self.fields[name].confidence < REVIEW_THRESHOLD
        ]

    def line_amounts(self) -> list[Decimal] | None:
        amounts = []
        index = 0
        while f"lines[{index}].amount" in self.fields:
            amount = self.fields[f"lines[{index}].amount"].value
            if not isinstance(amount, Decimal):
                return None
            amounts.append(amount)
            index += 1
        return amounts or None


# --------------------------------------------------------------------------- parsing


def parse_amount(raw: str | None) -> Decimal | None:
    """Accepts '1287.59' as asked, and also '1.287,59 €' in case the model kept the format."""
    if raw is None:
        return None
    text = raw.replace("€", "").replace("EUR", "").replace(" ", "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    text = raw.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def valid_cif(value: str) -> bool:
    """Spanish company tax id: letter, seven digits and a control digit or letter."""
    match = re.fullmatch(r"([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])", value)
    if not match:
        return False
    letter, digits, control = match.groups()
    numbers = [int(d) for d in digits]
    even = sum(numbers[1::2])
    odd = sum(sum(divmod(d * 2, 10)) for d in numbers[0::2])
    expected = (10 - (even + odd) % 10) % 10
    as_letter = "JABCDEFGHI"[expected]
    if letter in "ABEH":
        return control == str(expected)
    if letter in "NPQRSW":
        return control == as_letter
    return control in {str(expected), as_letter}


# --------------------------------------------------------------------------- evidence


def _fold(text: str) -> str:
    """Lower case, no accents, single spaces: OCR and models disagree on these all the time."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.lower().split())


def _amount_spellings(value: Decimal) -> list[str]:
    fixed = f"{value:.2f}"
    whole, cents = fixed.split(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return [f"{grouped},{cents}", f"{whole},{cents}", fixed]


def _date_spellings(value: date) -> list[str]:
    return [
        value.strftime("%d/%m/%Y"),
        f"{value.day}/{value.month}/{value.year}",
        value.strftime("%d-%m-%Y"),
        value.isoformat(),
    ]


class Evidence:
    """An independent reading of the document to look values up in."""

    def __init__(self, text: str) -> None:
        self.folded = _fold(text)
        self.compact = self.folded.replace(" ", "")

    def contains(self, value: Value, spellings: list[str] | None = None) -> bool:
        if spellings is not None:
            return any(self._has(s) for s in spellings)
        if value is None or isinstance(value, bool):
            return False
        if isinstance(value, Decimal):
            spellings = _amount_spellings(value)
        elif isinstance(value, date):
            spellings = _date_spellings(value)
        elif isinstance(value, list):
            return bool(value) and all(self.contains(item) for item in value)
        else:
            spellings = [value]
        return any(self._has(s) for s in spellings)

    def _has(self, spelling: str) -> bool:
        folded = _fold(spelling).replace(" ", "")
        return bool(folded) and folded in self.compact


# --------------------------------------------------------------------------- scoring


class _Scorer:
    def __init__(self, source: Source, evidence: Evidence) -> None:
        self.source = source
        self.evidence = evidence
        self.fields: dict[str, FieldValue] = {}

    def add(
        self,
        name: str,
        raw: object,
        value: Value,
        *,
        valid: bool = True,
        look_up: bool = True,
        spellings: list[str] | None = None,
    ) -> None:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            self.fields[name] = FieldValue(None, 0.0, ("not found in the document",))
            return
        if value is None:
            self.fields[name] = FieldValue(None, _UNPARSEABLE, (f"could not parse {raw!r}",))
            return
        confidence = _BASE[self.source]
        notes: list[str] = []
        if look_up:
            if self.evidence.contains(value, spellings):
                confidence += _FOUND_BONUS
            else:
                confidence *= _NOT_FOUND
                notes.append("not confirmed by the independent reading")
        if not valid:
            confidence *= _FAILED_CHECK
            notes.append("fails its format check")
        self.fields[name] = FieldValue(value, round(min(confidence, _MAX), 2), tuple(notes))

    def penalise(self, names: list[str], reason: str) -> None:
        for name in names:
            current = self.fields.get(name)
            if current is not None and current.value is not None:
                self.fields[name] = FieldValue(
                    current.value,
                    round(current.confidence * _FAILED_CHECK, 2),
                    (*current.notes, reason),
                )


def _text(raw: str | None) -> str | None:
    return raw.strip() if raw and raw.strip() else None


def _plain(value: Decimal) -> str:
    """21 -> '21', 10.5 -> '10,5': how a rate is printed."""
    text = format(value.normalize(), "f")
    return text.replace(".", ",")


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= CENT


# What the rules need from each type of document; below the review threshold, a person checks.
KEY_FIELDS: dict[ReadDocumentType, tuple[str, ...]] = {
    ReadDocumentType.INVOICE: (
        "document_number",
        "issue_date",
        "issuer_tax_id",
        "tax_rate_percent",
        "total",
    ),
    ReadDocumentType.POLICE_REPORT: ("report_number", "filed_date", "incident_date"),
    ReadDocumentType.ACCIDENT_REPORT: ("report_date", "incident_date"),
    ReadDocumentType.OTHER: (),
}
KEY_FIELDS[ReadDocumentType.ESTIMATE] = KEY_FIELDS[ReadDocumentType.INVOICE]


def _repair(read: DocumentRead, s: _Scorer, checks: list[Check]) -> int:
    """Returns the number of lines read."""
    r = read.repair
    if r is None:
        return 0
    number = _text(r.document_number)
    s.add("document_number", r.document_number, number)
    s.add("issue_date", r.issue_date, parse_date(r.issue_date))
    s.add("issuer_name", r.issuer_name, _text(r.issuer_name))
    tax_id = _text(r.issuer_tax_id)
    tax_id = tax_id.replace(" ", "").replace("-", "").upper() if tax_id else None
    s.add("issuer_tax_id", r.issuer_tax_id, tax_id, valid=tax_id is None or valid_cif(tax_id))
    s.add("customer", r.customer, _text(r.customer), look_up=False)
    for i, line in enumerate(r.lines):
        s.add(f"lines[{i}].description", line.description, _text(line.description))
        s.add(f"lines[{i}].quantity", line.quantity, parse_amount(line.quantity), look_up=False)
        s.add(f"lines[{i}].unit_price", line.unit_price, parse_amount(line.unit_price))
        s.add(f"lines[{i}].amount", line.amount, parse_amount(line.amount))
    s.add("subtotal", r.subtotal, parse_amount(r.subtotal))
    rate = parse_amount(r.tax_rate_percent)
    rate_spellings = None if rate is None else [f"{_plain(rate)}%", f"{_plain(rate)} %"]
    s.add("tax_rate_percent", r.tax_rate_percent, rate, spellings=rate_spellings)
    s.add("tax_amount", r.tax_amount, parse_amount(r.tax_amount))
    s.add("total", r.total, parse_amount(r.total))
    _repair_checks(s, checks, len(r.lines))
    return len(r.lines)


def _repair_checks(s: _Scorer, checks: list[Check], line_count: int) -> None:
    def amount(name: str) -> Decimal | None:
        value = s.fields[name].value if name in s.fields else None
        return value if isinstance(value, Decimal) else None

    for i in range(line_count):
        quantity, unit, total = (
            amount(f"lines[{i}].quantity"),
            amount(f"lines[{i}].unit_price"),
            amount(f"lines[{i}].amount"),
        )
        if quantity is not None and unit is not None and total is not None:
            ok = _close(quantity * unit, total)
            checks.append(Check(f"line {i + 1} amount", ok, f"{quantity} x {unit} vs {total}"))
            if not ok:
                names = [f"lines[{i}].quantity", f"lines[{i}].unit_price", f"lines[{i}].amount"]
                s.penalise(names, "quantity x unit price differs from the line amount")

    amounts = [amount(f"lines[{i}].amount") for i in range(line_count)]
    subtotal = amount("subtotal")
    if subtotal is not None and amounts and all(a is not None for a in amounts):
        lines_sum = sum((a for a in amounts if a is not None), Decimal(0))
        ok = _close(lines_sum, subtotal)
        checks.append(Check("lines add up to the subtotal", ok, f"{lines_sum} vs {subtotal}"))
        if not ok:
            names = [f"lines[{i}].amount" for i in range(line_count)] + ["subtotal"]
            s.penalise(names, "the lines do not add up to the subtotal")

    rate, tax = amount("tax_rate_percent"), amount("tax_amount")
    if subtotal is not None and rate is not None and tax is not None:
        expected = (subtotal * rate / 100).quantize(CENT)
        ok = _close(expected, tax)
        checks.append(Check("tax matches the rate", ok, f"{expected} expected vs {tax}"))
        if not ok:
            s.penalise(["tax_rate_percent", "tax_amount"], "the tax does not match the rate")

    total = amount("total")
    if subtotal is not None and tax is not None and total is not None:
        ok = _close(subtotal + tax, total)
        checks.append(Check("total is subtotal plus tax", ok, f"{subtotal + tax} vs {total}"))


def _police(read: DocumentRead, s: _Scorer) -> bool:
    p = read.police_report
    if p is None:
        return False
    s.add("report_number", p.report_number, _text(p.report_number))
    s.add("station", p.station, _text(p.station))
    s.add("filed_date", p.filed_date, parse_date(p.filed_date))
    s.add("incident_date", p.incident_date, parse_date(p.incident_date))
    s.add("complainant", p.complainant, _text(p.complainant), look_up=False)
    items = [i.strip() for i in p.stolen_items if i.strip()]
    s.add("stolen_items", items or None, items or None)
    s.add("forced_entry", p.forced_entry, p.forced_entry, look_up=False)
    s.add("alcohol_test_mg_l", p.alcohol_test_mg_l, parse_amount(p.alcohol_test_mg_l))
    return True


def _accident(read: DocumentRead, s: _Scorer) -> bool:
    a = read.accident_report
    if a is None:
        return False
    s.add("report_date", a.report_date, parse_date(a.report_date))
    s.add("incident_date", a.incident_date, parse_date(a.incident_date))
    s.add("location", a.location, _text(a.location))
    s.add("other_party_involved", a.other_party_involved, a.other_party_involved, look_up=False)
    s.add("circumstances", a.circumstances, _text(a.circumstances), look_up=False)
    return True


def score(read: DocumentRead, source: Source, independent_text: str) -> ExtractedDocument:
    """Checks the model's reading of a document against an independent reading of it."""
    scorer = _Scorer(source, Evidence(independent_text))
    checks: list[Check] = []
    notes: list[str] = []
    kind = read.document_type
    keys = KEY_FIELDS[kind]
    if kind in {ReadDocumentType.INVOICE, ReadDocumentType.ESTIMATE}:
        lines = _repair(read, scorer, checks)
        keys = keys + tuple(f"lines[{i}].amount" for i in range(lines))
        filled = read.repair is not None
        if filled and lines == 0:
            notes.append("no lines were read")
    elif kind is ReadDocumentType.POLICE_REPORT:
        filled = _police(read, scorer)
    elif kind is ReadDocumentType.ACCIDENT_REPORT:
        filled = _accident(read, scorer)
    else:
        filled = True
        notes.append("not a document type Tramita reads")
    if not filled:
        notes.append(f"classified as {kind} but its fields were not returned")
    for name in read.unreadable_fields:
        notes.append(f"the model could not read {name}")
    return ExtractedDocument(
        document_type=kind,
        source=source,
        fields=scorer.fields,
        checks=checks,
        embedded_instructions=[i for i in read.embedded_instructions if i.strip()],
        key_fields=keys,
        notes=notes,
    )
