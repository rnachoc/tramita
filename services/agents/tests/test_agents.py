from decimal import Decimal
from typing import Any

import pytest
from search_fixtures import CLAUSES, FakeEmbedder, FakeLexical, FakeVectors

from tramita_agents.agents import coverage, damage, fraud
from tramita_agents.agents.catalog import catalog
from tramita_agents.agents.context import build_context
from tramita_agents.agents.coordinator import Coordinator
from tramita_agents.agents.loop import SUBMIT
from tramita_agents.llm.fake import FakeModelClient
from tramita_agents.llm.steps import StepRequest
from tramita_agents.responders import STEP_RESPONDERS
from tramita_agents.search.service import PolicySearch

Script = dict[str, list[tuple[str, dict[str, Any]]]]


def _value(value: str) -> dict[str, Any]:
    return {"value": value, "confidence": 0.9, "notes": []}


def _view(
    *,
    product: str = "HP",
    claim_type: str = "HOME_WATER",
    start: str = "2025-01-01",
    incident: str = "2025-06-10",
    reported: str = "2025-06-11",
    description: str = "Soy Lucía Martínez Gómez. Se rompió la tubería del baño y mojó el suelo.",
    lines: list[tuple[str, str]] | None = None,
    instructions: int = 0,
    documents: list[str] | None = None,
) -> dict[str, Any]:
    lines = (
        lines if lines is not None else [("Reparación de tubería", "200.00"), ("Pintura", "100.00")]
    )
    values = {"tax_rate_percent": _value("21"), "issue_date": _value("2025-06-12")}
    for i, (text, amount) in enumerate(lines):
        values[f"lines[{i}].description"] = _value(text)
        values[f"lines[{i}].amount"] = _value(amount)
    return {
        "claim_id": "CL-T1",
        "status": "RECEIVED",
        "claim_type": claim_type,
        "incident_date": incident,
        "reported_date": reported,
        "description": description,
        "policy": {
            "policy_number": "BR-HP-1",
            "product_code": product,
            "product_name": "Hogar Plus",
            "start_date": start,
        },
        "documents": [
            {
                "document_id": f"DOC-{i}",
                "document_type": kind,
                "extraction": {
                    "values": values if kind == "INVOICE" else {},
                    "embedded_instructions": ["x"] * instructions if kind == "INVOICE" else [],
                },
            }
            for i, kind in enumerate(documents if documents is not None else ["INVOICE"])
        ],
    }


def _search(ranking: list[str]) -> PolicySearch:
    return PolicySearch(CLAUSES, FakeLexical(ranking), FakeVectors(ranking), FakeEmbedder())


def _scripted(script: Script) -> FakeModelClient:
    def responder(task: str) -> Any:
        def answer(request: StepRequest) -> list[tuple[str, dict[str, Any]]]:
            return [script[task][len(request.history)]]

        return answer

    return FakeModelClient(step_responders={task: responder(task) for task in script})


def _plan(view: dict[str, Any], client: FakeModelClient, ranking: list[str]) -> dict[str, Any]:
    coordinator = Coordinator(client, _search(ranking), catalog())
    return coordinator.plan(build_context(view, catalog()), list).body


def test_context_masks_the_description_and_reads_lines() -> None:
    context = build_context(_view(), catalog())

    assert "Martínez" not in context.description
    assert context.masked == {"PERSON": 1}
    assert context.coverage_title == "Daños por agua"
    document = context.amounts_document()
    assert document is not None
    assert [(line.index, line.amount) for line in document.lines] == [
        (0, Decimal("200.00")),
        (1, Decimal("100.00")),
    ]
    assert "Martínez" not in context.render()


def test_eligible_amount_is_related_lines_plus_tax() -> None:
    document = build_context(_view(), catalog()).amounts_document()
    assert document is not None
    verdicts = [
        damage.LineVerdict(index=0, related=True, reason="ok"),
        damage.LineVerdict(index=1, related=False, reason="ajena"),
    ]

    assert damage.eligible_amount(document, verdicts) == Decimal("242.00")


def test_fraud_signals_without_literal_evidence_are_dropped() -> None:
    context = build_context(_view(), catalog())
    signals = [
        fraud.Signal(type="DESCRIPTION_MISMATCH", evidence="Pintura", confidence=0.6),
        fraud.Signal(type="DESCRIPTION_MISMATCH", evidence="tejado roto", confidence=0.9),
    ]

    assert [s.evidence for s in fraud.grounded(signals, context)] == ["Pintura"]


def test_a_guarantee_the_product_lacks_is_rejected_without_any_agent() -> None:
    body = _plan(_view(product="HB", claim_type="HOME_GLASS"), FakeModelClient(), [])

    assert (body["decision"], body["citations"]) == ("REJECT", ["HB-2.3"])
    assert body["model_metadata"]["agents"] == {}


def test_a_waiting_period_is_rejected_on_its_clause() -> None:
    view = _view(claim_type="HOME_THEFT", start="2025-06-01", incident="2025-06-05")

    body = _plan(view, FakeModelClient(), [])

    assert (body["decision"], body["citations"]) == ("REJECT", ["HP-4.2"])


def test_an_exclusion_found_by_the_coverage_agent_grounds_a_rejection() -> None:
    client = _scripted(
        {
            coverage.TASK: [
                ("search_conditions", {"query": "humedad"}),
                (
                    SUBMIT,
                    {
                        "exclusion_code": "WATER_MAINTENANCE",
                        "citations": ["HP-3.2", "HP-2.1", "HB-3.2"],
                        "rationale": "Filtración lenta por falta de mantenimiento.",
                    },
                ),
            ]
        }
    )

    body = _plan(_view(), client, ["HP-3.2", "HP-2.1"])

    assert body["decision"] == "REJECT"
    assert body["exclusion_code"] == "WATER_MAINTENANCE"
    # The grounding clause from the index, then the agent's own citations of this product only.
    assert body["citations"] == ["HP-3.2", "HP-2.1"]
    assert body["model_metadata"]["agents"]["coverage"]["calls"] == ["search_conditions", SUBMIT]


def test_an_unknown_exclusion_code_is_ignored_and_noted() -> None:
    script: Script = {
        coverage.TASK: [
            (
                SUBMIT,
                {
                    "exclusion_code": "MADE_UP",
                    "citations": ["HP-2.1"],
                    "rationale": "Inventada por error.",
                },
            )
        ],
        damage.TASK: [(SUBMIT, {"lines": [], "rationale": "Todo relacionado."})],
        fraud.TASK: [(SUBMIT, {"signals": [], "rationale": "Nada que señalar."})],
    }

    body = _plan(_view(), _scripted(script), [])

    assert body["decision"] == "APPROVE"
    assert "exclusión desconocida (MADE_UP)" in body["rationale"]


def test_missing_documents_are_requested_on_the_documents_clause() -> None:
    script: Script = {
        coverage.TASK: [
            (
                SUBMIT,
                {"exclusion_code": None, "citations": ["HP-2.2"], "rationale": "Robo con fuerza."},
            )
        ]
    }
    view = _view(claim_type="HOME_THEFT", start="2024-01-01", documents=["INVOICE"])

    body = _plan(view, _scripted(script), [])

    assert (body["decision"], body["citations"]) == ("REQUEST_INFO", ["HP-6.3"])
    assert "POLICE_REPORT" in body["rationale"]


def test_an_approval_has_code_computed_amount_signals_and_review_requests() -> None:
    script: Script = {
        coverage.TASK: [
            (
                SUBMIT,
                {
                    "exclusion_code": None,
                    "citations": ["HP-2.1"],
                    "rationale": "Escape accidental.",
                },
            )
        ],
        damage.TASK: [
            (
                SUBMIT,
                {
                    "lines": [
                        {"index": 0, "related": True, "reason": "tubería"},
                        {"index": 1, "related": False, "reason": "pintura ajena"},
                    ],
                    "rationale": "La pintura no es del siniestro.",
                    "review_request": "Dudo de la línea 1.",
                },
            )
        ],
        fraud.TASK: [
            (
                SUBMIT,
                {
                    "signals": [
                        {"type": "DESCRIPTION_MISMATCH", "evidence": "Pintura", "confidence": 0.4}
                    ],
                    "rationale": "Una línea no encaja.",
                },
            )
        ],
    }

    body = _plan(_view(instructions=1), _scripted(script), [])

    assert body["decision"] == "APPROVE"
    assert body["eligible_amount"] == "242.00"
    assert body["citations"] == ["HP-2.1", "HP-4.1", "HP-4.4"]
    assert body["fraud_signals"] == [
        {"type": "DESCRIPTION_MISMATCH", "evidence": "Pintura", "confidence": 0.4}
    ]
    assert body["review_requests"] == [
        "1 instrucción(es) incrustada(s) en los documentos.",
        "Dudo de la línea 1.",
    ]


def test_late_notice_adds_the_notice_clause() -> None:
    body = _plan(
        _view(product="HB", claim_type="HOME_GLASS", reported="2025-07-30"), FakeModelClient(), []
    )

    assert body["citations"] == ["HB-2.3", "HB-5.1"]


def test_the_keyless_baselines_always_ask_for_a_person() -> None:
    client = FakeModelClient(step_responders=dict(STEP_RESPONDERS))

    body = _plan(_view(), client, ["HP-2.1", "HP-3.2"])

    assert body["decision"] == "APPROVE"
    assert len(body["review_requests"]) == 3
    assert all(r.startswith("Sin modelo") for r in body["review_requests"])
    assert {p for a in body["model_metadata"]["agents"].values() for p in a["providers"]} == {
        "fake:responder"
    }


def test_the_coverage_baseline_proposes_the_exclusion_closest_to_the_description() -> None:
    client = FakeModelClient(step_responders=dict(STEP_RESPONDERS))
    view = _view(
        description="Dejamos la ventana abierta durante la tormenta y entró la lluvia por ella."
    )

    body = _plan(view, client, ["HP-3.2", "HP-2.1"])

    assert (body["decision"], body["exclusion_code"]) == ("REJECT", "WATER_EXTERIOR")


@pytest.mark.parametrize("clause", ["HB-3.2", "HP-9.9"])
def test_read_clause_refuses_clauses_outside_the_product(clause: str) -> None:
    read = next(t for t in coverage.tools(_search([]), "HP") if t.name == "read_clause")

    with pytest.raises(Exception, match="does not exist in product HP"):
        read.run(coverage.ClauseInput(clause_id=clause))
