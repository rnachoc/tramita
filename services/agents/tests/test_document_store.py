import hashlib
from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from tramita_agents.documents.storage import DocumentStore


@pytest.fixture
def store() -> Iterator[DocumentStore]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        document_store = DocumentStore(client, "claim-documents")
        document_store.ensure_bucket()
        yield document_store


def test_round_trip_keeps_bytes_type_and_checksum(store: DocumentStore) -> None:
    data = b"%PDF-1.4 factura"

    key = store.put("CL-000001", "DOC-000001", "DOC-000001-invoice.pdf", data, "application/pdf")

    assert key == "claims/CL-000001/DOC-000001/DOC-000001-invoice.pdf"
    assert store.get(key) == data
    assert store.sha256(key) == hashlib.sha256(data).hexdigest()


def test_creating_the_bucket_twice_is_harmless(store: DocumentStore) -> None:
    store.ensure_bucket()


@pytest.mark.parametrize(
    ("claim", "document", "filename"),
    [
        ("../etc", "DOC-1", "a.pdf"),
        ("CL-1", "DOC/1", "a.pdf"),
        ("CL-1", "DOC-1", "..pdf"),
        ("", "D", "a"),
    ],
)
def test_identifiers_cannot_escape_the_claim_prefix(
    claim: str, document: str, filename: str
) -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        DocumentStore.key(claim, document, filename)
