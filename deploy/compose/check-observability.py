"""End-to-end check of traces and metrics after the agents analysed the claims (used by CI).

Expects the observability profile up (``make obs-up``) and claims processed with
OTEL_EXPORTER_OTLP_ENDPOINT and MANAGEMENT_OTLP_TRACING_ENDPOINT set. Checks that:

* every claim the agents processed is one trace that joins the agents and the core, with the
  claim, agent, tool, model and search spans of the GenAI conventions;
* no span carries a personal value of the ground truth, nor any claim description;
* Prometheus has the agents' and the core's metrics, and model call durations are bucketed in
  seconds (a p95 in milliseconds for keyless calls, not the ~4.75 s of the default buckets).

Prints one notice line for CI; exits 1 on the first broken expectation.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

JAEGER = os.environ.get("JAEGER_URL", "http://localhost:16686")
PROMETHEUS = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
DATASET = Path("data/generated")
EXPECTED = {
    "process_claim",
    "analyse_claim",
    "invoke_agent",
    "chat",
    "execute_tool",
    "policy_search",
}


def fail(message: str) -> None:
    print(f"FAILED: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=observability check::{message}")
    raise SystemExit(1)


def traces() -> tuple[str, list[dict[str, Any]]]:
    now = datetime.now(UTC)
    response = httpx.get(
        f"{JAEGER}/api/v3/traces",
        params={
            "query.service_name": "tramita-agents",
            "query.operation_name": "process_claim",
            "query.start_time_min": (now - timedelta(hours=3)).isoformat(),
            "query.start_time_max": (now + timedelta(minutes=5)).isoformat(),
            "query.search_depth": 1000,
        },
        timeout=60,
    )
    if response.is_error:
        fail(f"Jaeger answered {response.status_code}: {response.text[:200]}")
    return response.text, response.json()["result"]["resourceSpans"]


def personal_values() -> list[str]:
    values: list[str] = []
    for holder in json.loads((DATASET / "policyholders.json").read_text("utf-8")):
        values += [holder["full_name"], holder["nif"], holder["email"], holder["phone"]]
        values += [holder["iban"], holder["address"]["street"]]
    for claim in json.loads((DATASET / "claims.json").read_text("utf-8")):
        values += [claim["contact_phone"], claim["contact_email"], claim["location"]]
        values.append(claim["description"][:40])
    return [v for v in values if v]


def prometheus(query: str) -> float | None:
    response = httpx.get(f"{PROMETHEUS}/api/v1/query", params={"query": query}, timeout=30)
    result = response.json()["data"]["result"]
    return float(result[0]["value"][1]) if result else None


def main() -> None:
    deadline = time.monotonic() + 60
    while True:  # spans are exported in batches; give the last ones time to land
        raw, resource_spans = traces()
        services: dict[str, set[str]] = defaultdict(set)
        names: Counter[str] = Counter()
        for resource in resource_spans:
            service = next(
                a["value"]["stringValue"]
                for a in resource["resource"]["attributes"]
                if a["key"] == "service.name"
            )
            for scope in resource["scopeSpans"]:
                for span in scope["spans"]:
                    services[span["traceId"]].add(service)
                    names[span["name"].split(" ")[0]] += 1
        if services or time.monotonic() > deadline:
            break
        time.sleep(5)
    if not services:
        fail("no claim traces in Jaeger")
    joined = sum(svc == {"tramita-agents", "tramita-core"} for svc in services.values())
    if joined != len(services):
        fail(f"{len(services) - joined} of {len(services)} claim traces lack the core's spans")
    if missing := EXPECTED - set(names):
        fail(f"span kinds missing from the traces: {sorted(missing)}")
    values = personal_values()
    if leaked := [v for v in values if v in raw]:
        fail(f"{len(leaked)} personal value(s) in the traces")

    checks = {
        # Over the last 10 minutes: batch commands stop reporting when they end.
        "claims analysed (agents)": "sum(max_over_time(tramita_claims_analysed_total[10m]))",
        "proposals evaluated (core)": "sum(max_over_time(tramita_proposals_total[10m]))",
        "model calls": "sum(max_over_time(gen_ai_client_operation_duration_seconds_count[10m]))",
        "damage call p95 (s)": (
            "histogram_quantile(0.95, sum by (le) (max_over_time("
            'gen_ai_client_operation_duration_seconds_bucket{tramita_task="agent.damage"}[10m])))'
        ),
    }
    found = {name: prometheus(query) for name, query in checks.items()}
    if any(v is None or math.isnan(v) for v in found.values()):
        fail(f"metrics missing in Prometheus: {found}")
    if found["damage call p95 (s)"] >= 1:  # type: ignore[operator]
        fail(f"keyless model calls read as slow: p95 {found['damage call p95 (s)']} s")
    summary = (
        f"{len(services)} claim traces joining agents and core, {sum(names.values())} spans, "
        f"0 of {len(values)} personal values; claims analysed "
        f"{found['claims analysed (agents)']:.0f}, proposals evaluated "
        f"{found['proposals evaluated (core)']:.0f}, model calls {found['model calls']:.0f}, "
        f"damage call p95 {found['damage call p95 (s)']:.3f} s"
    )
    print(f"  ok   {summary}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=observability check::{summary}")


if __name__ == "__main__":
    main()
