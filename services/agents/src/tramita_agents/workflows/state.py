"""Types shared by the claim workflow and its activities.

Kept apart from the activities so the workflow module imports nothing heavy: Temporal's sandbox
re-imports workflow modules, and the activities pull in the models and the search.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaimState:
    status: str
    decision: str | None = None
    routing: str | None = None
