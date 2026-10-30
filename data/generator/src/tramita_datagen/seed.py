"""Loads the generated policyholders and policies into a running core service.

Usage: ``uv run tramita-seed`` (or ``make seed``) after ``make data`` and with the core running.
The admin key is read from ``TRAMITA_API_KEYS`` (the ``ADMIN`` entry) unless ``--api-key`` is
given. Importing is idempotent, so seeding twice is harmless.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tramita_datagen.catalog import REPO_ROOT

DEFAULT_URL = "http://localhost:8080"
TIMEOUT_SECONDS = 60


def admin_key(configuration: str) -> str:
    """The key of the first ADMIN client in a ``name:ROLE:key;...`` configuration."""
    for entry in configuration.split(";"):
        parts = entry.strip().split(":", 2)
        if len(parts) == 3 and parts[1] == "ADMIN":  # noqa: PLR2004 - name, role and key
            return parts[2]
    raise SystemExit("No ADMIN key found in TRAMITA_API_KEYS; pass --api-key.")


def import_policies(base_url: str, api_key: str, dataset: Path) -> dict[str, Any]:
    body = {
        "policyholders": json.loads((dataset / "policyholders.json").read_text(encoding="utf-8")),
        "policies": json.loads((dataset / "policies.json").read_text(encoding="utf-8")),
    }
    url = base_url.rstrip("/") + "/api/import/policies"
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"Refusing to call a non-HTTP URL: {url}")
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            result: dict[str, Any] = json.loads(response.read())
            return result
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Import failed with HTTP {error.code}: {detail}") from error


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Load the synthetic policies into the core service."
    )
    parser.add_argument("--url", default=os.environ.get("TRAMITA_CORE_URL", DEFAULT_URL))
    parser.add_argument(
        "--api-key", default=None, help="admin API key (default: from TRAMITA_API_KEYS)"
    )
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "generated")
    args = parser.parse_args(argv)

    if not (args.dataset / "policies.json").exists():
        raise SystemExit(f"No dataset in {args.dataset}; run `make data` first.")
    key = args.api_key or admin_key(os.environ.get("TRAMITA_API_KEYS", ""))
    result = import_policies(args.url, key, args.dataset)
    print(f"Imported {result['policyholders']} policyholders and {result['policies']} policies.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
