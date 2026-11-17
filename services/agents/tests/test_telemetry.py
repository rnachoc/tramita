from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from search_fixtures import CLAUSES, FakeEmbedder, FakeLexical, FakeReranker, FakeVectors
from test_agents import _view

from tramita_agents.agents.catalog import catalog
from tramita_agents.agents.context import build_context
from tramita_agents.agents.coordinator import Coordinator
from tramita_agents.llm.fake import FakeModelClient
from tramita_agents.llm.tracing import TracingModelClient
from tramita_agents.responders import STEP_RESPONDERS
from tramita_agents.search.service import PolicySearch

EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
trace.set_tracer_provider(_provider)

PERSONAL = ["Lucía", "Martínez", "Gómez", "612 345 678", "12345678Z", "tubería"]


@pytest.fixture
def spans() -> Iterator[list[ReadableSpan]]:
    EXPORTER.clear()
    found: list[ReadableSpan] = []
    yield found
    EXPORTER.clear()


def _analyse() -> list[ReadableSpan]:
    view = _view(
        description="Soy Lucía Martínez Gómez, NIF 12345678Z, teléfono 612 345 678: "
        "se rompió la tubería del baño."
    )
    search = PolicySearch(
        CLAUSES,
        FakeLexical(["HP-2.1", "HP-3.2"]),
        FakeVectors(["HP-2.1", "HP-3.2"]),
        FakeEmbedder(),
        reranker=FakeReranker("agua"),
    )
    client = TracingModelClient(FakeModelClient(step_responders=dict(STEP_RESPONDERS)))
    Coordinator(client, search, catalog()).plan(build_context(view, catalog()), list)
    return list(EXPORTER.get_finished_spans())


def _by_name(found: list[ReadableSpan]) -> dict[str, ReadableSpan]:
    return {s.name: s for s in found}


def test_a_claim_is_one_trace_of_agent_tool_model_and_search_spans(
    spans: list[ReadableSpan],
) -> None:
    found = _analyse()
    names = [s.name for s in found]

    assert {s.context.trace_id for s in found} == {found[0].context.trace_id}
    root = _by_name(found)["analyse_claim"]
    assert root.parent is None
    for name in (
        "invoke_agent agent.coverage",
        "invoke_agent agent.damage",
        "invoke_agent agent.fraud",
    ):
        assert name in names
        assert _by_name(found)[name].parent.span_id == root.context.span_id  # type: ignore[union-attr]
    tool = _by_name(found)["execute_tool search_conditions"]
    search = _by_name(found)["policy_search"]
    assert search.parent.span_id == tool.context.span_id  # type: ignore[union-attr]
    chat = next(s for s in found if s.name.startswith("chat "))
    attrs: dict[str, Any] = dict(chat.attributes or {})
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.provider.name"] == "tramita.fake"
    assert attrs["tramita.answered_by"] == "fake:responder"
    assert attrs["gen_ai.usage.input_tokens"] == 0
    assert dict(root.attributes or {})["tramita.proposed_decision"] == "APPROVE"


def test_no_span_carries_personal_data_or_claim_text(spans: list[ReadableSpan]) -> None:
    found = _analyse()

    for span in found:
        values = [str(v) for v in (span.attributes or {}).values()]
        values += [e.name for e in span.events]
        for value in values:
            for personal in PERSONAL:
                assert personal not in value, f"{span.name} carries {personal!r}"
