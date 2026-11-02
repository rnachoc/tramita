import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import httpx
import pytest
from documents_fixtures import HOLDER, invoice, police_report, render
from moto import mock_aws

from tramita_agents.core_client import CoreClient
from tramita_agents.documents.reader import READ_TASK, DocumentReader
from tramita_agents.documents.storage import DocumentStore
from tramita_agents.ingest import Ingestor, document_file, select
from tramita_agents.llm.fake import FakeModelClient
from tramita_agents.llm.types import ModelError, ModelRequest
from tramita_agents.responders import RESPONDERS

FORM: dict[str, Any] = {
    "claim_id": "CL-TEST",
    "policy_number": "BR-HP-000211",
    "reported_date": "2026-03-01",
    "incident_date": "2026-02-27",
    "claim_type": "HOME_THEFT",
    "location": "Sevilla",
    "description": "Forzaron la puerta.",
    "claimed_amount": "454.96",
    "contact_phone": "+34 612 345 678",
    "contact_email": "lucia@correo.example",
    "document_ids": ["DOC-TEST-01", "DOC-TEST-02"],
}


class FakeCore:
    """Records the calls the core API receives and answers like the real one."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        return httpx.Response(201 if request.method == "POST" else 200, json=body or {})

    def bodies(self, method: str, suffix: str) -> list[Any]:
        return [b for m, p, b in self.calls if m == method and p.endswith(suffix)]


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    folder = tmp_path / "documents" / "CL-TEST"
    folder.mkdir(parents=True)
    (folder / "DOC-TEST-01-invoice.pdf").write_bytes(render(invoice()))
    (folder / "DOC-TEST-02-police-report.pdf").write_bytes(render(police_report()))
    return tmp_path


@pytest.fixture
def store() -> Iterator[DocumentStore]:
    with mock_aws():
        document_store = DocumentStore(boto3.client("s3", region_name="us-east-1"), "docs")
        document_store.ensure_bucket()
        yield document_store


def _ingestor(core: FakeCore, store: DocumentStore, model: FakeModelClient) -> Ingestor:
    client = CoreClient("http://core.test", "agent-key-0123456789", httpx.MockTransport(core))
    return Ingestor(client, store, DocumentReader(model))


def test_a_claim_goes_through_store_read_register_and_record(
    dataset: Path, store: DocumentStore
) -> None:
    core = FakeCore()

    outcomes = _ingestor(core, store, FakeModelClient(responders=dict(RESPONDERS))).claim(
        FORM, dataset
    )

    assert [o.document_type for o in outcomes] == ["INVOICE", "POLICE_REPORT"]
    assert all(o.error is None and o.needs_review == 0 for o in outcomes)
    registered = core.bodies("POST", "/api/claims")[0]
    assert "document_ids" not in registered
    documents = core.bodies("POST", "/documents")
    assert [d["document_type"] for d in documents] == ["INVOICE", "POLICE_REPORT"]
    assert store.get(documents[0]["storage_key"]) == render(invoice())
    extractions = core.bodies("PUT", "/extraction")
    assert extractions[0]["stated_total"] == "454.96"
    assert extractions[1]["issue_date"] == "2026-03-01"


def test_nothing_personal_reaches_the_extractions_or_the_output(
    dataset: Path, store: DocumentStore
) -> None:
    core = FakeCore()

    outcomes = _ingestor(core, store, FakeModelClient(responders=dict(RESPONDERS))).claim(
        FORM, dataset
    )

    sent = json.dumps(core.bodies("PUT", "/extraction"), ensure_ascii=False)
    printed = "\n".join(o.line() for o in outcomes)
    for value in (HOLDER.name, HOLDER.tax_id, "Calle Mayor", "612 345 678"):
        assert value not in sent, value
        assert value not in printed, value
    assert "<PERSON_1>" in sent


def test_the_same_person_keeps_one_token_across_a_claims_documents(
    dataset: Path, store: DocumentStore
) -> None:
    core = FakeCore()

    _ingestor(core, store, FakeModelClient(responders=dict(RESPONDERS))).claim(FORM, dataset)

    invoice_values, report_values = (
        e["fields"]["values"] for e in core.bodies("PUT", "/extraction")
    )
    assert invoice_values["customer"]["value"] == report_values["complainant"]["value"]


def test_an_unreadable_document_is_registered_without_an_extraction(
    dataset: Path, store: DocumentStore
) -> None:
    def fail(_: ModelRequest) -> str:
        raise ModelError("model unavailable")

    core = FakeCore()

    outcomes = _ingestor(core, store, FakeModelClient(responders={READ_TASK: fail})).claim(
        FORM, dataset
    )

    assert [o.error for o in outcomes] == ["model unavailable", "model unavailable"]
    assert [d["document_type"] for d in core.bodies("POST", "/documents")] == ["OTHER", "OTHER"]
    assert core.bodies("PUT", "/extraction") == []


def test_unsupported_files_are_kept_and_registered_as_other(
    dataset: Path, store: DocumentStore
) -> None:
    (dataset / "documents" / "CL-TEST" / "DOC-TEST-01-invoice.pdf").write_bytes(b"GIF89a")
    core = FakeCore()

    outcome = _ingestor(core, store, FakeModelClient(responders=dict(RESPONDERS))).claim(
        FORM, dataset
    )[0]

    assert outcome.error is not None
    assert core.bodies("POST", "/documents")[0]["document_type"] == "OTHER"


def test_document_files_and_claim_selection(dataset: Path) -> None:
    assert document_file(dataset, "CL-TEST", "DOC-TEST-02").name == "DOC-TEST-02-police-report.pdf"
    with pytest.raises(FileNotFoundError):
        document_file(dataset, "CL-TEST", "DOC-TEST-99")
    forms = [{"claim_id": "A"}, {"claim_id": "B"}, {"claim_id": "C"}]
    assert select(forms, None, 2) == forms[:2]
    assert select(forms, "C, A", None) == [forms[0], forms[2]]
    with pytest.raises(SystemExit, match="Z"):
        select(forms, "A,Z", None)
