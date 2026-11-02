"""Deterministic answers the fake model gives, per task, when no recording exists (ADR 0007)."""

from collections.abc import Mapping

from tramita_agents.documents import heuristic
from tramita_agents.documents.reader import READ_TASK
from tramita_agents.llm.fake import Responder

RESPONDERS: Mapping[str, Responder] = {READ_TASK: heuristic.respond}
