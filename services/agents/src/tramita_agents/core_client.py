"""Client for the core system's claim API, used with the AGENT role.

Every call is idempotent on the core side: registering a claim or a document that already
exists with the same content returns it, and recording an extraction replaces the previous one
while the claim is still open for evidence.
"""

from __future__ import annotations

import re
from typing import Any, Self

import httpx

TIMEOUT_SECONDS = 30.0
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,23}")


def _id(value: str) -> str:
    """Identifiers go into URL paths: anything but a plain id is refused."""
    if not _ID.fullmatch(value):
        raise ValueError(f"Not a valid identifier: {value!r}")
    return value


class CoreError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Core API returned HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def role_key(configuration: str, role: str) -> str:
    """The key of the first client with ``role`` in a ``name:ROLE:key;...`` configuration."""
    for entry in configuration.split(";"):
        parts = entry.strip().split(":", 2)
        if len(parts) == 3 and parts[1] == role:  # noqa: PLR2004 - name, role and key
            return parts[2]
    raise ValueError(f"No {role} key in TRAMITA_API_KEYS")


class CoreClient:
    def __init__(self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"Refusing to call a non-HTTP URL: {base_url}")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Api-Key": api_key},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        response = self._http.request(method, path, json=body)
        if response.is_error:
            raise CoreError(response.status_code, response.text[:500])
        return response.json()

    def register_claim(self, claim: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = self._call("POST", "/api/claims", claim)
        return result

    def add_document(
        self, claim_id: str, document_id: str, document_type: str, filename: str, storage_key: str
    ) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "POST",
            f"/api/claims/{_id(claim_id)}/documents",
            {
                "document_id": document_id,
                "document_type": document_type,
                "filename": filename,
                "storage_key": storage_key,
            },
        )
        return result

    def record_extraction(
        self, claim_id: str, document_id: str, extraction: dict[str, Any]
    ) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "PUT",
            f"/api/claims/{_id(claim_id)}/documents/{_id(document_id)}/extraction",
            extraction,
        )
        return result

    def claim(self, claim_id: str) -> dict[str, Any]:
        result: dict[str, Any] = self._call("GET", f"/api/claims/{_id(claim_id)}")
        return result
