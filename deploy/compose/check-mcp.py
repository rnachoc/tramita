"""End-to-end check of the MCP server against the running core (used by CI).

Starts ``tramita-mcp`` over stdio, as a desktop client would, and checks that:

* it offers only read-only tools;
* ``get_claim`` and ``claim_audit`` for every claim of the dataset return no personal value of
  the ground truth (names, NIF, phones, e-mails, account numbers, street addresses);
* the overview accounts for every claim, and a search returns citable clauses;
* the key it uses is refused when it tries to write (the core's roles guard the server too).

Prints one notice line for CI; exits 1 on the first broken expectation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from tramita_agents.core_client import role_key
from tramita_agents.settings import Settings

DATASET = Path("data/generated")


def fail(message: str) -> None:
    print(f"FAILED: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=mcp check::{message}")
    raise SystemExit(1)


def personal_values() -> list[str]:
    values: list[str] = []
    for holder in json.loads((DATASET / "policyholders.json").read_text("utf-8")):
        values += [holder["full_name"], holder["nif"], holder["email"], holder["phone"]]
        values += [holder["iban"], holder["address"]["street"]]
    for claim in json.loads((DATASET / "claims.json").read_text("utf-8")):
        values += [claim["contact_phone"], claim["contact_email"], claim["location"]]
    return [v for v in values if v]


async def call(client: Client, tool: str, **args: Any) -> Any:
    result = await client.call_tool(tool, args)
    if result.is_error:
        fail(f"{tool} {args} failed: {result.content}")
    return result.structured_content


async def run() -> str:
    params = StdioServerParameters(
        command="uv", args=["run", "--quiet", "tramita-mcp"], env=dict(os.environ)
    )
    leaks: list[str] = []
    values = personal_values()
    claims = [c["claim_id"] for c in json.loads((DATASET / "claims.json").read_text("utf-8"))]
    async with Client(params, read_timeout_seconds=120) as client:
        tools = (await client.list_tools()).tools
        writable = [t.name for t in tools if not (t.annotations and t.annotations.read_only_hint)]
        if writable:
            fail(f"tools not declared read-only: {writable}")
        for claim_id in claims:
            text = json.dumps(
                [
                    await call(client, "get_claim", claim_id=claim_id),
                    await call(client, "claim_audit", claim_id=claim_id),
                ],
                ensure_ascii=False,
            )
            leaks += [f"{claim_id}: {v[:4]}…" for v in values if v in text]
        overview = await call(client, "claims_overview")
        hits = await call(
            client,
            "search_policy_conditions",
            query="¿Cuántos días tengo para avisar?",
            product_code="HP",
        )
    if leaks:
        fail(f"{len(leaks)} personal value(s) in tool results, e.g. {leaks[:3]}")
    if sum(overview.values()) != len(claims):
        fail(f"overview counts {sum(overview.values())} claims, the dataset has {len(claims)}")
    if not hits["result"] or not hits["result"][0]["clause_id"].startswith("HP-"):
        fail(f"search returned {hits}")
    return (
        f"{len(tools)} read-only tools; {len(claims)} claims read with 0 of {len(values)} "
        f"personal values in the results; top clause {hits['result'][0]['clause_id']}"
    )


def main() -> None:
    settings = Settings()
    keys = settings.tramita_api_keys.get_secret_value() if settings.tramita_api_keys else ""
    refused = httpx.post(
        f"{settings.tramita_core_url}/api/claims/CL-000001/reviews",
        headers={"X-Api-Key": role_key(keys, "ANALYST"), "Idempotency-Key": "mcp-check"},
        json={"reviewer": "mcp", "action": "APPROVE"},
        timeout=30,
    )
    if refused.status_code != httpx.codes.FORBIDDEN:
        fail(f"the analyst key was answered {refused.status_code} when writing, expected 403")
    summary = asyncio.run(run()) + "; writes with its key refused (403)"
    print(f"  ok   {summary}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=mcp check::{summary}")


if __name__ == "__main__":
    main()
