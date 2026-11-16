"""Deterministic answers the fake model gives, per task, when no recording exists (ADR 0010)."""

from collections.abc import Mapping

from tramita_agents.agents import coverage, damage, fraud
from tramita_agents.documents import heuristic
from tramita_agents.documents.reader import READ_TASK
from tramita_agents.llm.fake import Responder
from tramita_agents.llm.steps import StepResponder

RESPONDERS: Mapping[str, Responder] = {READ_TASK: heuristic.respond}
STEP_RESPONDERS: Mapping[str, StepResponder] = {
    coverage.TASK: coverage.respond,
    damage.TASK: damage.respond,
    fraud.TASK: fraud.respond,
}
