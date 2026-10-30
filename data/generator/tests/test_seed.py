import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tramita_datagen.cli import write_dataset
from tramita_datagen.models import Dataset
from tramita_datagen.seed import admin_key, import_policies


class _CoreStub(BaseHTTPRequestHandler):
    """Records the import request and answers like the core does."""

    received: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.received.append({"path": self.path, "key": self.headers["X-Api-Key"], "body": body})
        if self.headers["X-Api-Key"] != "admin-change-me-local-only":
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"detail": "forbidden"}')
            return
        reply = json.dumps(
            {"policyholders": len(body["policyholders"]), "policies": len(body["policies"])}
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(reply.encode())

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def core() -> Iterator[str]:
    _CoreStub.received.clear()
    server = HTTPServer(("127.0.0.1", 0), _CoreStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_admin_key_is_taken_from_the_admin_entry() -> None:
    keys = "agents:AGENT:agents-change-me-local-only;admin:ADMIN:admin-change-me-local-only"
    assert admin_key(keys) == "admin-change-me-local-only"


def test_missing_admin_key_fails_with_a_hint() -> None:
    with pytest.raises(SystemExit, match="ADMIN"):
        admin_key("agents:AGENT:agents-change-me-local-only")


def test_import_sends_the_generated_policies_in_the_core_format(
    core: str, dataset: Dataset, tmp_path: Path
) -> None:
    write_dataset(dataset, tmp_path, documents=False)

    result = import_policies(core, "admin-change-me-local-only", tmp_path)

    sent = _CoreStub.received[0]
    assert sent["path"] == "/api/import/policies"
    assert len(sent["body"]["policyholders"]) == len(dataset.policyholders)
    assert len(sent["body"]["policies"]) == len(dataset.policies)
    assert set(sent["body"]["policies"][0]) >= {
        "policy_number",
        "holder_id",
        "product_code",
        "line",
        "start_date",
    }
    assert result == {
        "policyholders": len(dataset.policyholders),
        "policies": len(dataset.policies),
    }


def test_rejected_import_reports_the_status_and_detail(
    core: str, dataset: Dataset, tmp_path: Path
) -> None:
    write_dataset(dataset, tmp_path, documents=False)

    with pytest.raises(SystemExit, match="HTTP 403"):
        import_policies(core, "wrong-change-me-local-only", tmp_path)
