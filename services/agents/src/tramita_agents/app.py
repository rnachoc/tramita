"""HTTP entry point of the agent service."""

from dataclasses import asdict
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from tramita_agents import telemetry
from tramita_agents.search.factory import build_policy_search
from tramita_agents.search.lexical import SearchBackendError
from tramita_agents.search.service import MAX_QUERY_CHARS, Mode, PolicySearch
from tramita_agents.settings import ModelProvider, Settings, get_settings

telemetry.configure("tramita-agents-api")
app = FastAPI(title="Tramita agents", version="0.1.0")


class Health(BaseModel):
    status: Literal["ok"]
    model_provider: ModelProvider


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    return Health(status="ok", model_provider=settings.model_provider)


@lru_cache
def get_policy_search() -> PolicySearch:
    """Built on first use (loads the local models); not cached if the index is not ready."""
    search = build_policy_search(get_settings())
    search.check_ready()
    return search


class PolicySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    product_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    k: int = Field(default=5, ge=1, le=10)
    mode: Mode = Mode.RERANKED


class ClauseHit(BaseModel):
    clause_id: str
    product_code: str
    article: str
    title: str
    text: str
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    fused_rank: int | None
    rerank_score: float | None


class PolicySearchResponse(BaseModel):
    query: str = Field(description="The query as searched, with personal data masked")
    masked: dict[str, int] = Field(description="Kinds and counts of personal data removed")
    mode: Mode
    hits: list[ClauseHit]


@app.post("/policy-search")
def policy_search(request: PolicySearchRequest) -> PolicySearchResponse:
    """Clauses of the policy conditions that bear on the query, best first."""
    try:
        search = get_policy_search()
        result = search.search(request.query, request.product_code, request.k, request.mode)
    except SearchBackendError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return PolicySearchResponse(
        query=result.query,
        masked=result.masked,
        mode=result.mode,
        hits=[ClauseHit(**asdict(hit)) for hit in result.hits],
    )
