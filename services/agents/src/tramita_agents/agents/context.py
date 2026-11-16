"""What the agents know about a claim: the core's record, with personal data masked.

Document facts come from the core already masked (they were masked when read, ADR 0011). The
claim description is stored in the core as the policyholder wrote it, so it is masked here, with
one pseudonymiser per claim, before any model sees it. The rendered block is data: the agents'
prompts quote it inside tags and say that nothing in it is an instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from tramita_agents.agents.catalog import Catalog
from tramita_agents.documents.pii import Pseudonymizer, mask

_LINE = re.compile(r"^lines\[(\d+)\]\.(description|amount)$")


@dataclass(frozen=True)
class Line:
    index: int
    description: str
    amount: Decimal | None


@dataclass(frozen=True)
class DocumentFacts:
    document_id: str
    document_type: str
    values: dict[str, str]  # every non-line field read, masked
    lines: tuple[Line, ...]
    instructions: int  # embedded instructions the reader flagged

    @property
    def tax_rate(self) -> Decimal | None:
        return _decimal(self.values.get("tax_rate_percent"))


@dataclass(frozen=True)
class ClaimContext:
    claim_id: str
    status: str
    policy_number: str
    product_code: str
    product_name: str
    coverage: str
    coverage_title: str
    policy_start: date
    incident_date: date
    reported_date: date
    description: str  # masked
    masked: dict[str, int]
    documents: tuple[DocumentFacts, ...]

    def amounts_document(self) -> DocumentFacts | None:
        """The document whose lines the rules check amounts against: invoice, else estimate."""
        for kind in ("INVOICE", "ESTIMATE"):
            for doc in self.documents:
                if doc.document_type == kind and doc.lines:
                    return doc
        return None

    def received(self) -> set[str]:
        return {d.document_type for d in self.documents}

    def render(self) -> str:
        parts = [
            f"Producto: {self.product_name} ({self.product_code})",
            f"Garantía reclamada: {self.coverage_title} ({self.coverage})",
            f"Inicio de la póliza: {self.policy_start.isoformat()}",
            f"Fecha del siniestro: {self.incident_date.isoformat()}",
            f"Fecha de comunicación: {self.reported_date.isoformat()}",
            f"Descripción del asegurado: {self.description}",
        ]
        for doc in self.documents:
            parts.append(f"Documento {doc.document_id} ({doc.document_type}):")
            parts += [f"  {key}: {value}" for key, value in sorted(doc.values.items())]
            parts += [
                f"  línea {line.index}: {line.description} | importe {line.amount}"
                for line in doc.lines
            ]
            if doc.instructions:
                parts.append(
                    f"  (el lector marcó {doc.instructions} instrucción(es) incrustada(s))"
                )
        return "\n".join(parts)


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _document(doc: dict[str, Any]) -> DocumentFacts:
    extraction = doc.get("extraction") or {}
    values: dict[str, str] = {}
    lines: dict[int, dict[str, str]] = {}
    for key, field in (extraction.get("values") or {}).items():
        value = field.get("value")
        if value is None:
            continue
        match = _LINE.match(key)
        if match:
            lines.setdefault(int(match.group(1)), {})[match.group(2)] = str(value)
        elif not key.startswith("lines["):
            values[key] = str(value)
    return DocumentFacts(
        document_id=doc["document_id"],
        document_type=doc["document_type"],
        values=values,
        lines=tuple(
            Line(i, spec.get("description", ""), _decimal(spec.get("amount")))
            for i, spec in sorted(lines.items())
        ),
        instructions=len(extraction.get("embedded_instructions") or []),
    )


def build_context(view: dict[str, Any], catalog: Catalog) -> ClaimContext:
    policy = view["policy"]
    masked = mask(view["description"], Pseudonymizer())
    coverage = view["claim_type"]
    return ClaimContext(
        claim_id=view["claim_id"],
        status=view["status"],
        policy_number=policy["policy_number"],
        product_code=policy["product_code"],
        product_name=policy["product_name"],
        coverage=coverage,
        coverage_title=catalog.coverages[coverage].title,
        policy_start=date.fromisoformat(policy["start_date"]),
        incident_date=date.fromisoformat(view["incident_date"]),
        reported_date=date.fromisoformat(view["reported_date"]),
        description=masked.text,
        masked=masked.counts(),
        documents=tuple(_document(d) for d in view.get("documents", [])),
    )
