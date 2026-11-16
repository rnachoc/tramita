"""Coordinator: runs the agents a claim needs and composes the proposal for the core.

It is code, not a model (ADR 0013). The order of the questions is fixed by the rules, the facts
that need no reading are checked here, and only the judgements go to agents:

1. Guarantee not included in the product, or incident inside the waiting period: a rejection,
   grounded on the clause the rules require. No agent is needed.
2. Coverage agent: does an exclusion apply? If so, a rejection on that exclusion.
3. Required documents missing: a request for them.
4. Damage agent: which repair lines belong to the incident; code computes the eligible amount.
5. Fraud agent, on every claim that reaches an amount: signals with quoted evidence.

Any agent can ask for a person to look, and so does any document with embedded instructions. The
request travels with the proposal and the core then never settles the claim automatically: agents
can only escalate, never skip a review.

The grounding citation of each outcome comes from the clause index, the same one the core
checks; the agents' own citations are added when they exist in the product. The proposal is
only a proposal: the core's rules decide, compute every amount and route (ADR 0008).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from tramita_agents.agents import coverage, damage, fraud
from tramita_agents.agents.catalog import Catalog
from tramita_agents.agents.context import ClaimContext
from tramita_agents.agents.loop import AgentRun
from tramita_agents.llm.types import ModelClient
from tramita_agents.search.service import PolicySearch


@dataclass
class Plan:
    """A proposal for the core, plus what produced it (no personal data)."""

    claim_id: str
    body: dict[str, Any]
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_citations: list[str] = field(default_factory=list)

    def idempotency_key(self) -> str:
        # Timings and token counts vary between runs; the key covers what is proposed.
        stable = {k: v for k, v in self.body.items() if k != "model_metadata"}
        canonical = json.dumps(stable, sort_keys=True, default=str)
        return f"{self.claim_id}-{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def _trace(run: AgentRun[Any]) -> dict[str, Any]:
    return {
        "steps": run.steps,
        "calls": run.calls,
        "tool_errors": run.errors,
        "providers": sorted(run.providers),
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "seconds": run.seconds,
    }


@dataclass
class _Draft:
    """The proposal being composed: its citations, notes and agent traces."""

    context: ClaimContext
    catalog: Catalog
    plan: Plan
    citations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reviews: list[str] = field(default_factory=list)

    def ask_review(self, reason: str | None) -> None:
        if reason and reason not in self.reviews:
            self.reviews.append(reason[:500])

    def cite(self, key: str) -> None:
        clause = self.catalog.clause(self.context.product_code, key)
        if clause and clause not in self.citations:
            self.citations.append(clause)

    def finish(self, decision: str, rationale: str, **extra: Any) -> Plan:
        context = self.context
        if (context.reported_date - context.incident_date).days > self.catalog.notice_days:
            self.cite("notice")
        self.plan.body = {
            "decision": decision,
            "eligible_amount": None,
            "proposed_amount": None,
            "exclusion_code": None,
            "citations": list(self.citations),
            "fraud_signals": [],
            "review_requests": list(self.reviews),
            "rationale": "\n".join([rationale, *self.notes])[:20_000],
            "model_metadata": {
                "agents": self.plan.agents,
                "agent_citations": self.plan.agent_citations,
                "review_requests": list(self.reviews),
                "masked": context.masked,
            },
            **extra,
        }
        return self.plan


class Coordinator:
    def __init__(self, client: ModelClient, search: PolicySearch, catalog: Catalog) -> None:
        self.client = client
        self.search = search
        self.catalog = catalog

    def plan(self, context: ClaimContext, history: Callable[[], list[dict[str, Any]]]) -> Plan:
        draft = _Draft(context, self.catalog, Plan(context.claim_id, {}))
        cov = context.coverage
        if self.catalog.guarantee(context.product_code, cov) is None:
            draft.cite(f"not_included:{cov}")
            return draft.finish(
                "REJECT",
                f"El producto {context.product_name} no incluye la garantía {context.coverage_title}.",
            )
        if self.catalog.in_waiting_period(
            context.product_code, cov, context.policy_start, context.incident_date
        ):
            draft.cite(f"waiting:{cov}")
            return draft.finish(
                "REJECT", "El siniestro ocurre dentro del periodo de carencia de la garantía."
            )
        flagged = sum(d.instructions for d in context.documents)
        if flagged:
            draft.ask_review(f"{flagged} instrucción(es) incrustada(s) en los documentos.")
        found = self._coverage(draft)
        draft.ask_review(found.review_request)
        if found.exclusion_code:
            draft.cite(f"exclusion:{found.exclusion_code}")
            draft.citations.extend(
                c for c in draft.plan.agent_citations if c not in draft.citations
            )
            return draft.finish("REJECT", found.rationale, exclusion_code=found.exclusion_code)
        missing = self.catalog.missing_documents(cov, context.received())
        if missing:
            draft.cite(f"documents:{cov}")
            return draft.finish(
                "REQUEST_INFO", "Falta documentación imprescindible: " + ", ".join(missing) + "."
            )
        return self._approve(draft, found.rationale, history)

    def _coverage(self, draft: _Draft) -> coverage.CoverageFinding:
        context, product = draft.context, draft.context.product_code
        run = coverage.analyse(self.client, self.search, context, self.catalog)
        draft.plan.agents["coverage"] = _trace(run)
        draft.plan.agent_citations = [
            c
            for c in run.output.citations
            if c in self.search.clauses and c.startswith(f"{product}-")
        ]
        valid = {e.code for e in self.catalog.coverages[context.coverage].exclusions}
        code = run.output.exclusion_code
        if code and code not in valid:
            draft.notes.append(
                f"El agente de cobertura propuso una exclusión desconocida ({code}); se ignora."
            )
            return run.output.model_copy(update={"exclusion_code": None})
        return run.output

    def _approve(
        self, draft: _Draft, coverage_rationale: str, history: Callable[[], list[dict[str, Any]]]
    ) -> Plan:
        context, cov = draft.context, draft.context.coverage
        draft.cite(f"coverage:{cov}")
        draft.cite(f"limits:{cov}")
        rationale = [coverage_rationale]
        eligible: Decimal | None = None
        document = context.amounts_document()
        if document is None:
            draft.notes.append("No hay líneas de importe legibles; el importe lo fija la revisión.")
        else:
            assessed = damage.assess(self.client, context, document)
            draft.ask_review(assessed.output.review_request)
            draft.plan.agents["damage"] = _trace(assessed)
            eligible = damage.eligible_amount(document, assessed.output.lines)
            if any(not v.related for v in assessed.output.lines):
                draft.cite("indemnity")
            rationale.append(assessed.output.rationale)
        reviewed = fraud.review(self.client, context, history)
        draft.ask_review(reviewed.output.review_request)
        draft.plan.agents["fraud"] = _trace(reviewed)
        signals = fraud.grounded(reviewed.output.signals, context)
        if dropped := len(reviewed.output.signals) - len(signals):
            draft.notes.append(f"Se descartan {dropped} señal(es) de fraude sin evidencia literal.")
        rationale.append(reviewed.output.rationale)
        draft.citations.extend(c for c in draft.plan.agent_citations if c not in draft.citations)
        amount = str(eligible) if eligible is not None else None
        return draft.finish(
            "APPROVE",
            "\n".join(rationale),
            eligible_amount=amount,
            proposed_amount=amount,
            fraud_signals=[s.model_dump() for s in signals],
        )
