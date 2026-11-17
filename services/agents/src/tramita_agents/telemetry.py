"""Traces and metrics with OpenTelemetry, following the GenAI semantic conventions (ADR 0018).

Off unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set: then spans and metrics go over OTLP/HTTP to
the collector. Spans carry identifiers, counts, models, outcomes and timings, never text: no
prompt, no document, no description, no tool input or output (the conventions make content
capture opt-in, and it stays off). Outgoing HTTP calls carry ``traceparent``, so the core's spans
join the same trace.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, Status, StatusCode

TRACER = "tramita.agents"

# Attribute names from the OpenTelemetry GenAI semantic conventions.
OPERATION = "gen_ai.operation.name"
PROVIDER = "gen_ai.provider.name"
REQUEST_MODEL = "gen_ai.request.model"
RESPONSE_MODEL = "gen_ai.response.model"
INPUT_TOKENS = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
AGENT_NAME = "gen_ai.agent.name"
TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"

_configured = False


def configure(service: str) -> bool:
    """Sets up exporters once per process if an OTLP endpoint is configured."""
    global _configured  # noqa: PLW0603 - one provider per process
    if _configured or not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return _configured
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415
    from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # noqa: PLC0415
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    resource = Resource.create({"service.name": service, "service.namespace": "tramita"})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=5000)
            ],
        )
    )
    HTTPXClientInstrumentor().instrument()
    _configured = True
    return True


def shutdown() -> None:
    """Flushes what is buffered; short commands call it before they exit."""
    provider = trace.get_tracer_provider()
    for target in (provider, metrics.get_meter_provider()):
        flush = getattr(target, "shutdown", None)
        if callable(flush):
            flush()


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """A span whose failure is recorded by exception type only (messages may quote data)."""
    tracer = trace.get_tracer(TRACER)
    with tracer.start_as_current_span(
        name, attributes=_clean(attributes), record_exception=False
    ) as current:
        try:
            yield current
        except Exception as error:
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            current.set_attribute("error.type", type(error).__name__)
            raise


def _clean(attributes: dict[str, Any]) -> dict[str, Any]:
    return {k.replace("__", "."): v for k, v in attributes.items() if v is not None}


# Bucket boundaries from the GenAI conventions. The SDK's defaults (0, 5, 10, 25, ...) suit
# milliseconds: in seconds every call would fall into the first bucket and p95 would read ~4.75 s.
SECONDS = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]
TOKENS = [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304]


class Instruments:
    """Metric instruments, created against whichever meter provider is active."""

    def __init__(self, meter: metrics.Meter | None = None) -> None:
        meter = meter or metrics.get_meter(TRACER)
        self.operation_duration = meter.create_histogram(
            "gen_ai.client.operation.duration",
            unit="s",
            description="Model call duration",
            explicit_bucket_boundaries_advisory=SECONDS,
        )
        self.token_usage = meter.create_histogram(
            "gen_ai.client.token.usage",
            unit="{token}",
            description="Tokens per model call",
            explicit_bucket_boundaries_advisory=TOKENS,
        )
        self.claims = meter.create_counter(
            "tramita.claims.analysed", unit="{claim}", description="Claims analysed by outcome"
        )
        self.stage_duration = meter.create_histogram(
            "tramita.stage.duration",
            unit="s",
            description="Duration of a pipeline stage",
            explicit_bucket_boundaries_advisory=SECONDS,
        )


@lru_cache
def instruments() -> Instruments:
    return Instruments()
