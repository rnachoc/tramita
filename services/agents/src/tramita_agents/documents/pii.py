"""Detects and pseudonymises personal data in Spanish text before any model, trace or log sees it.

Presidio runs with the Spanish spaCy model and recognisers configured for Spain: NIF, NIE, IBAN,
e-mail, Spanish phone numbers, person names (spaCy NER), and two recognisers of our own for
vehicle plates and street addresses. Company tax ids (CIF), amounts and dates are not personal
data and are kept, because the rules need them.

Each value is replaced by a stable token such as ``<PERSON_1>``: the same value always gets the
same token within one :class:`Pseudonymizer`, so a model can still tell that two mentions refer
to the same person without ever seeing who it is. The mapping lives in memory only.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

import tldextract
from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    EmailRecognizer,
    EsNieRecognizer,
    EsNifRecognizer,
    IbanRecognizer,
    PhoneRecognizer,
    SpacyRecognizer,
)

LANGUAGE = "es"
SPACY_MODEL = "es_core_news_md"
MIN_SCORE = 0.35
MIN_NAME_WORDS = 2

PERSONAL_ENTITIES = (
    "PERSON",
    "ES_NIF",
    "ES_NIE",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "PHONE_NUMBER",
    "ES_PLATE",
    "ADDRESS",
)

_CAPITALISED = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+")


class _LabelBefore:
    """Matches a label that ends right before a position (a fixed-width lookbehind would not
    allow the optional colon and spaces)."""

    def __init__(self, label: str) -> None:
        self.pattern = re.compile(rf"\b{label}[ \t]*:?[ \t]*$")

    def search(self, text: str, start: int, end: int) -> bool:
        return self.pattern.search(text[max(start, end - 12) : end]) is not None


_CIF_LABEL = _LabelBefore("CIF")

# Company names keep their legal form; a person-name match inside one is not personal data.
_COMPANY = re.compile(
    r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ.\- ]{1,80}?\bS\.(?:L|A)\.(?:U\.)?"
    r"|\b(?:Aseguradora|Mutua|Seguros)(?:[ \t]+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+){1,3}"
)

_STREET_TYPES = (
    "Calle|C\\.|Avenida|Avda\\.|Plaza|Paseo|Camino|Ronda|Callejón|Callejon|Urbanización|"
    "Urbanizacion|Pasaje|Pasadizo|Carretera|Vía|Via|Vial|Travesía|Travesia|Cañada|Canada|"
    "Rambla|Alameda|Glorieta|Acceso|Cuesta|Partida|Plazuela|Polígono|Poligono|Bulevar|Senda|"
    "Carrer|Barrio|Colonia|Muelle|Paraje|Sector|Lugar"
)

# Horizontal space only: an address never continues on the next line, and letting it do so
# swallowed the invoice number and date printed under the issuer's address.
_SP = r"[ \t]"
_CITY = rf"[A-ZÁÉÍÓÚÑ][\wáéíóúñ'-]+(?:{_SP}+(?:de|del|la|las|los|el|[A-ZÁÉÍÓÚÑ][\wáéíóúñ'-]+))*"
# Street, number, then optionally floor and door ("3º B", also as OCR misreads it: "3? B")
# and postal code with city.
_ADDRESS = (
    rf"\b(?:{_STREET_TYPES}){_SP}+[^,\n]{{2,60}},{_SP}*\d{{1,4}}"
    rf"(?:,{_SP}*\d{{1,2}}{_SP}?\S?{_SP}*[A-Z]\b)?"
    rf"(?:,{_SP}*\d{{5}}\b(?:{_SP}+{_CITY})?)?"
)

_NAME_WORD = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+"
_NAME = rf"{_NAME_WORD}(?:{_SP}+(?:de{_SP}+(?:la{_SP}+)?)?{_NAME_WORD}){{1,5}}"
# Names in the places our documents print them, which spaCy misses when OCR breaks the
# sentence: after a label ("Cliente", "Conductor"...) or right before the person's NIF.
_LABELLED_NAMES = (
    re.compile(rf"\b(?:Cliente|Conductor|Compareciente|Nombre|Asegurado|Tomador):?\s*({_NAME})"),
    re.compile(rf"({_NAME}){_SP}*(?:[·\-\u2013,]{_SP}*)?(?:con{_SP}+)?NIF\b"),
)

# Whatever follows a "NIF" label, even when OCR misread or dropped the letter.
_NIF_AFTER_LABEL = re.compile(r"\b(?:NIF|NIE|DNI):?[ \t]*([A-Z]?\d{7,8}[^\s,.;]?)")
# The plates row of an accident report: OCR often garbles plates beyond any plate pattern.
_PLATES_ROW = re.compile(r"^Matr[ií]cula:?[ \t]+(\S[^\n]*)$", re.MULTILINE)


class LabelledFieldRecognizer(EntityRecognizer):
    """Personal data identified by where the document prints it rather than by its shape."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON", "ES_PLATE", "ES_NIF"], supported_language=LANGUAGE
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: object = None
    ) -> list[RecognizerResult]:
        names = [
            RecognizerResult("PERSON", m.start(1), m.end(1), 0.7)
            for pattern in _LABELLED_NAMES
            for m in pattern.finditer(text)
        ]
        plates = [
            RecognizerResult("ES_PLATE", m.start(1), m.end(1), 0.6)
            for m in _PLATES_ROW.finditer(text)
        ]
        nifs = [
            RecognizerResult("ES_NIF", m.start(1), m.end(1), 0.6)
            for m in _NIF_AFTER_LABEL.finditer(text)
        ]
        return names + plates + nifs


# The Public Suffix List snapshot bundled with tldextract: no network call at runtime.
_OFFLINE_SUFFIXES = tldextract.TLDExtract(suffix_list_urls=())
# Top-level domains reserved for tests and examples (RFC 2606, RFC 6761).
_RESERVED_TLDS = {"example", "test", "invalid", "localhost"}


class OfflineEmailRecognizer(EmailRecognizer):
    """Presidio's e-mail recogniser validates the domain by downloading the Public Suffix List.

    This one uses the bundled snapshot instead, and also accepts reserved test domains, which
    would otherwise slip through unmasked.
    """

    def validate_result(self, pattern_text: str) -> bool:
        domain = pattern_text.rsplit("@", 1)[-1].lower()
        return _OFFLINE_SUFFIXES(domain).fqdn != "" or domain.rsplit(".", 1)[-1] in _RESERVED_TLDS


def _recognizers() -> list[object]:
    plate = PatternRecognizer(
        supported_entity="ES_PLATE",
        supported_language=LANGUAGE,
        patterns=[Pattern("current Spanish plate", r"\b\d{4}\s?[BCDFGHJKLMNPRSTVWXYZ]{3}\b", 0.6)],
        context=["matrícula", "matricula", "vehículo", "vehiculo"],
    )
    address = PatternRecognizer(
        supported_entity="ADDRESS",
        supported_language=LANGUAGE,
        patterns=[Pattern("street and number", _ADDRESS, 0.6)],
    )
    # Checksum-free fallbacks: a NIF or IBAN misread by OCR fails validation in the standard
    # recognisers and would reach the model unmasked. Here privacy wins over precision.
    unverified_nif = PatternRecognizer(
        supported_entity="ES_NIF",
        supported_language=LANGUAGE,
        patterns=[Pattern("NIF without check", r"\b\d{8}\s?-?[A-Z]{1,2}\b", 0.45)],
    )
    unverified_iban = PatternRecognizer(
        supported_entity="IBAN_CODE",
        supported_language=LANGUAGE,
        patterns=[Pattern("Spanish IBAN without check", r"\bES\d{2}(?:\s?\d{4}){5}\b", 0.6)],
    )
    # Phone numbers that OCR split over two lines, which the phonenumbers library rejects.
    split_phone = PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        supported_language=LANGUAGE,
        patterns=[
            Pattern(
                "Spanish phone", r"(?<![\d\w])(?:\+34\s*)?[6789]\d{2}(?:\s*\d{3}){2}(?!\d)", 0.4
            )
        ],
    )
    return [
        EsNifRecognizer(supported_language=LANGUAGE),
        split_phone,
        LabelledFieldRecognizer(),
        unverified_nif,
        unverified_iban,
        EsNieRecognizer(supported_language=LANGUAGE),
        OfflineEmailRecognizer(supported_language=LANGUAGE),
        IbanRecognizer(supported_language=LANGUAGE),
        PhoneRecognizer(supported_regions=("ES",), supported_language=LANGUAGE),
        SpacyRecognizer(supported_language=LANGUAGE, supported_entities=["PERSON"]),
        plate,
        address,
    ]


@lru_cache(maxsize=1)
def analyzer() -> AnalyzerEngine:
    """The configured analyzer. Loading the spaCy model takes a second, so it is shared."""
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": LANGUAGE, "model_name": SPACY_MODEL}],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": {"PER": "PERSON"},
                "labels_to_ignore": ["LOC", "ORG", "MISC"],
            },
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=[LANGUAGE])
    for recognizer in _recognizers():
        registry.add_recognizer(recognizer)  # type: ignore[arg-type]
    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry, supported_languages=[LANGUAGE])


@dataclass(frozen=True)
class Finding:
    entity_type: str
    start: int
    end: int
    score: float


@dataclass
class Pseudonymizer:
    """Maps each personal value to a stable token. One instance per claim."""

    _tokens: dict[tuple[str, str], str] = field(default_factory=dict)
    _counts: Counter[str] = field(default_factory=Counter)

    def token(self, entity_type: str, value: str) -> str:
        key = (entity_type, " ".join(value.lower().split()))
        if key not in self._tokens:
            self._counts[entity_type] += 1
            self._tokens[key] = f"<{entity_type}_{self._counts[entity_type]}>"
        return self._tokens[key]

    def values(self) -> set[str]:
        """The original values seen so far, for leak checks in tests and evals."""
        return {value for (_, value) in self._tokens}


@dataclass(frozen=True)
class MaskedText:
    text: str
    findings: tuple[Finding, ...]

    def counts(self) -> dict[str, int]:
        """How many values of each type were masked; safe to log (no values)."""
        return dict(Counter(f.entity_type for f in self.findings))


def find_personal_data(text: str) -> list[Finding]:
    results = analyzer().analyze(
        text=text, language=LANGUAGE, entities=list(PERSONAL_ENTITIES), score_threshold=MIN_SCORE
    )
    companies = [m.span() for m in _COMPANY.finditer(text)]
    findings = []
    for r in results:
        value = text[r.start : r.end]
        if r.entity_type == "PERSON":
            inside_company = any(start <= r.start and r.end <= end for start, end in companies)
            # A single capitalised word is far more often a product or a place than a person.
            if inside_company or len(_CAPITALISED.findall(value)) < MIN_NAME_WORDS:
                continue
        # A company tax id is not personal data; OCR reading its letter as a digit makes it
        # look like a phone number or a NIF.
        if r.entity_type in {"PHONE_NUMBER", "ES_NIF"} and _CIF_LABEL.search(text, 0, r.start):
            continue
        findings.append(Finding(r.entity_type, r.start, r.end, r.score))
    return _without_overlaps(findings)


def _without_overlaps(findings: list[Finding]) -> list[Finding]:
    """Keeps the longest, then highest-scoring, finding among overlapping ones."""
    chosen: list[Finding] = []
    for f in sorted(findings, key=lambda f: (-(f.end - f.start), -f.score, f.start)):
        if all(f.end <= c.start or f.start >= c.end for c in chosen):
            chosen.append(f)
    return sorted(chosen, key=lambda f: f.start)


def mask(text: str, pseudonyms: Pseudonymizer) -> MaskedText:
    findings = find_personal_data(text)
    parts: list[str] = []
    cursor = 0
    for f in findings:
        parts.append(text[cursor : f.start])
        parts.append(pseudonyms.token(f.entity_type, text[f.start : f.end]))
        cursor = f.end
    parts.append(text[cursor:])
    return MaskedText("".join(parts), tuple(findings))
