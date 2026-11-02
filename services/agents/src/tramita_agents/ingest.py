"""Takes claims with their documents into the system: store, read, register, record.

Usage: ``uv run tramita-ingest`` (or ``make ingest``) with the stack and the core running and the
policies seeded. For every claim form in the dataset it

1. registers the claim in the core system,
2. stores each original document in the S3-compatible store,
3. reads it (masked, see :mod:`tramita_agents.documents.reader`),
4. registers the document with the type it was read as, and records the extraction.

Only the claim forms (what a policyholder submits) and the document files are read from the
dataset; the ground truth next to them is never used. Every step is idempotent, so running it
twice is harmless while the claims are still open. Output names types, counts and confidences,
never personal data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tramita_agents.core_client import CoreClient, role_key
from tramita_agents.documents.payload import extraction_payload
from tramita_agents.documents.pii import Pseudonymizer
from tramita_agents.documents.reader import DocumentReader, UnsupportedDocumentError, media_type
from tramita_agents.documents.storage import DocumentStore
from tramita_agents.llm.factory import build_model_client
from tramita_agents.llm.types import ModelError
from tramita_agents.responders import RESPONDERS
from tramita_agents.settings import REPO_ROOT, Settings

UNKNOWN_CONTENT = "application/octet-stream"
CLAIM_FORM_FIELDS = (
    "claim_id",
    "policy_number",
    "reported_date",
    "incident_date",
    "claim_type",
    "location",
    "description",
    "claimed_amount",
    "contact_phone",
    "contact_email",
)


@dataclass(frozen=True)
class Outcome:
    claim_id: str
    document_id: str
    document_type: str
    source: str
    needs_review: int
    instructions: int
    masked: int
    error: str | None = None

    def line(self) -> str:
        if self.error:
            return f"{self.claim_id} {self.document_id} FAILED {self.error}"
        return (
            f"{self.claim_id} {self.document_id} {self.document_type:<15} {self.source:<10} "
            f"masked={self.masked:<3} review={self.needs_review:<2} instructions={self.instructions}"
        )


def document_file(dataset: Path, claim_id: str, document_id: str) -> Path:
    matches = sorted((dataset / "documents" / claim_id).glob(f"{document_id}-*"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one file for {document_id}, found {len(matches)}")
    return matches[0]


class Ingestor:
    def __init__(self, core: CoreClient, store: DocumentStore, reader: DocumentReader) -> None:
        self.core = core
        self.store = store
        self.reader = reader

    def claim(self, form: dict[str, Any], dataset: Path) -> list[Outcome]:
        claim_id = form["claim_id"]
        self.core.register_claim({k: form.get(k) for k in CLAIM_FORM_FIELDS})
        # One pseudonymiser per claim: the same person keeps the same token across documents.
        pseudonyms = Pseudonymizer()
        return [
            self.document(claim_id, document_id, dataset, pseudonyms)
            for document_id in form["document_ids"]
        ]

    def document(
        self, claim_id: str, document_id: str, dataset: Path, pseudonyms: Pseudonymizer
    ) -> Outcome:
        path = document_file(dataset, claim_id, document_id)
        data = path.read_bytes()
        try:
            content_type = media_type(data)
        except UnsupportedDocumentError as error:
            key = self.store.put(claim_id, document_id, path.name, data, UNKNOWN_CONTENT)
            self.core.add_document(claim_id, document_id, "OTHER", path.name, key)
            return Outcome(claim_id, document_id, "OTHER", "-", 0, 0, 0, str(error))
        key = self.store.put(claim_id, document_id, path.name, data, content_type)
        try:
            result = self.reader.read(data, pseudonyms)
        except ModelError as error:
            # Received but unread: registered so a person sees it, with no extraction.
            self.core.add_document(claim_id, document_id, "OTHER", path.name, key)
            return Outcome(claim_id, document_id, "OTHER", "-", 0, 0, 0, str(error))
        kind = result.extracted.document_type.value
        self.core.add_document(claim_id, document_id, kind, path.name, key)
        self.core.record_extraction(claim_id, document_id, extraction_payload(result))
        return Outcome(
            claim_id=claim_id,
            document_id=document_id,
            document_type=kind,
            source=result.source.value,
            needs_review=len(result.extracted.low_confidence()),
            instructions=len(result.instructions()),
            masked=sum(result.pii_counts.values()),
        )


def select(forms: list[dict[str, Any]], claims: str | None, limit: int | None) -> list[Any]:
    if claims:
        wanted = {c.strip() for c in claims.split(",") if c.strip()}
        forms = [f for f in forms if f["claim_id"] in wanted]
        missing = wanted - {f["claim_id"] for f in forms}
        if missing:
            raise SystemExit(f"Unknown claims: {', '.join(sorted(missing))}")
    return forms[:limit] if limit is not None else forms


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest claims and their documents.")
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "generated")
    parser.add_argument("--claims", help="comma-separated claim ids (default: all)")
    parser.add_argument("--limit", type=int, help="ingest only the first N claims")
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.tramita_api_keys is None:
        raise SystemExit("TRAMITA_API_KEYS is not set (see .env.example).")
    forms = select(
        json.loads((args.dataset / "claims.json").read_text(encoding="utf-8")),
        args.claims,
        args.limit,
    )
    store = DocumentStore.from_settings(settings)
    store.ensure_bucket()
    reader = DocumentReader(build_model_client(settings, RESPONDERS))
    print(f"Ingesting {len(forms)} claims with the {settings.model_provider} model provider")
    failures = 0
    key = role_key(settings.tramita_api_keys.get_secret_value(), "AGENT")
    with CoreClient(settings.tramita_core_url, key) as core:
        ingestor = Ingestor(core, store, reader)
        for form in forms:
            for outcome in ingestor.claim(form, args.dataset):
                print(outcome.line())
                failures += outcome.error is not None
    if failures:
        print(f"{failures} documents could not be read", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
