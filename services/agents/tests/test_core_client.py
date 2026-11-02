import json

import httpx
import pytest

from tramita_agents.core_client import CoreClient, CoreError, role_key


def _client(handler: httpx.MockTransport) -> CoreClient:
    return CoreClient("http://core.test", "agents-key-for-tests", transport=handler)


def test_client_sends_the_api_key_and_snake_case_bodies() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"document_id": "DOC-1"})

    with _client(httpx.MockTransport(handle)) as core:
        core.add_document("CL-1", "DOC-1", "INVOICE", "f.pdf", "CL-1/DOC-1/f.pdf")

    assert seen[0].url == "http://core.test/api/claims/CL-1/documents"
    assert seen[0].headers["X-Api-Key"] == "agents-key-for-tests"
    assert json.loads(seen[0].content)["storage_key"] == "CL-1/DOC-1/f.pdf"


def test_client_reports_api_errors_with_their_detail() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Claim CL-1 is frozen"})

    with _client(httpx.MockTransport(handle)) as core, pytest.raises(CoreError) as error:
        core.record_extraction("CL-1", "DOC-1", {"fields": {}})

    assert error.value.status == 409
    assert "frozen" in error.value.detail


@pytest.mark.parametrize("bad", ["../admin", "CL-1/../../x", "", "a" * 25, "CL 1"])
def test_client_refuses_identifiers_that_are_not_plain(bad: str) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200))
    with _client(transport) as core, pytest.raises(ValueError, match="identifier"):
        core.claim(bad)


def test_role_key() -> None:
    keys = "agents:AGENT:agent-key-0123456789;admin:ADMIN:admin-key-0123456789"

    assert role_key(keys, "AGENT") == "agent-key-0123456789"
    with pytest.raises(ValueError, match="REVIEWER"):
        role_key(keys, "REVIEWER")
