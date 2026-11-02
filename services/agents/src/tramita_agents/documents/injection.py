"""Finds text in a document that tries to instruct the system instead of describing the claim.

Documents are data. Prompt injection is defended in depth: the model is told to report such
text and never act on it, its output schema has no field through which it could approve or pay
anything, and the decision is taken by the rules in the core system. This detector adds a
deterministic layer that does not depend on the model noticing: a reviewer sees what it finds,
and the extraction evaluation measures both detectors.

A sentence is flagged when it shows at least two of three cues: it addresses an automated
reader, it gives an order about the claim, or it asserts something only the insurer could
decide. One cue alone is common in honest documents ("el compareciente ignora quién...").
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass

_ADDRESSEE = re.compile(
    r"\b(?:asistente|sistema|modelo(?: de lenguaje)?|ia|ai|llm|gpt|chatbot|bot|agente|"
    r"revisor|tramitador|validador|system|assistant|model|reviewer|agent|operator)\b"
    r"|^\s*(?:system|assistant|instrucciones|instructions|nota para|note to|para el|to the)\b"
    r"|\[inst\]|<\|?(?:system|im_start)",
)
# Imperatives and infinitives only: "desactivada" or "pago" describe, they do not order.
_ORDER = re.compile(
    r"\b(?:ignora|ignorad|ignorar|ignore|olvida|olvidar|disregard|omite|omitir|omit|salta|"
    r"saltar|skip|aprueba|aprobad|aprobar|approve|autoriza|autorizar|authori[sz]e|marca|"
    r"marcar|mark|set|establece|establecer|fija|fijar|paga|pagar|pay|abona|abonar|desactiva|"
    r"desactivar|disable|bypass|override|no apliques|do not apply|cambia|cambiar|change|"
    r"responde|responder|respond|output|devuelve|devolver|return)\b"
)
_CLAIM = re.compile(
    r"(?:ya ha sido (?:validad|aprobad|revisad)\w*|already (?:been )?(?:validated|approved|"
    r"reviewed)|sin revision|without (?:human )?review|no aplica|does not apply|ilimitad\w*|"
    r"unlimited|en su totalidad|in full|cliente vip|vip customer|decision\s*=|amount\s*=|"
    r"importe de \d|fraud check|comprobacion\w* de fraude|sin franquicia|no deductible|"
    r"cubre (?:todo|el siniestro)|covers? (?:this|the) claim)"
)


@dataclass(frozen=True)
class SuspectedInstruction:
    text: str
    cues: tuple[str, ...]


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _units(text: str) -> list[str]:
    """Each line, and each pair of consecutive lines (an instruction may wrap once).

    Whole paragraphs are not used: joining every line of an invoice or a report would gather
    cues from unrelated lines ("Modelo simplificado" and a line further down).
    """
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    pairs = [f"{a} {b}" for a, b in itertools.pairwise(lines)]
    return lines + pairs


def _cues(unit: str) -> tuple[str, ...]:
    folded = _fold(unit)
    return tuple(
        name
        for name, pattern in (
            ("addresses an automated reader", _ADDRESSEE),
            ("gives an order", _ORDER),
            ("asserts an insurer decision", _CLAIM),
        )
        if pattern.search(folded)
    )


def find_instructions(text: str) -> list[SuspectedInstruction]:
    found: list[SuspectedInstruction] = []
    for unit in _units(text):
        cues = _cues(unit)
        # Two of the three cues, see the module docstring. A pair of lines is only reported
        # when neither line was reported on its own.
        if len(cues) >= 2 and not any(f.text in unit for f in found):  # noqa: PLR2004
            found.append(SuspectedInstruction(unit, cues))
    return found
