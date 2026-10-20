"""HTTP entry point of the agent service."""

from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from tramita_agents.settings import ModelProvider, Settings, get_settings

app = FastAPI(title="Tramita agents", version="0.1.0")


class Health(BaseModel):
    status: Literal["ok"]
    model_provider: ModelProvider


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    return Health(status="ok", model_provider=settings.model_provider)
