"""Original claim documents in an S3-compatible object store."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from tramita_agents.settings import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


def _safe(part: str, what: str) -> str:
    """Rejects path tricks such as '..' or '/' in identifiers that become object keys."""
    if not _SAFE.fullmatch(part) or ".." in part:
        raise ValueError(f"Unsafe {what} for an object key: {part!r}")
    return part


class DocumentStore:
    def __init__(self, client: S3Client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> DocumentStore:
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name="us-east-1",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return cls(client, settings.s3_bucket)

    @staticmethod
    def key(claim_id: str, document_id: str, filename: str) -> str:
        return f"claims/{_safe(claim_id, 'claim id')}/{_safe(document_id, 'document id')}/{_safe(filename, 'filename')}"

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(
        self, claim_id: str, document_id: str, filename: str, data: bytes, content_type: str
    ) -> str:
        """Stores a document and returns its key. Re-uploading the same bytes is harmless."""
        key = self.key(claim_id, document_id, filename)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": hashlib.sha256(data).hexdigest()},
        )
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def sha256(self, key: str) -> str:
        return self.client.head_object(Bucket=self.bucket, Key=key)["Metadata"]["sha256"]
