from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeckCompareRequest(BaseModel):
    archetype: str = Field(..., description="Archetype name or id")
    deck: dict[str, list[dict[str, Any]]] = Field(..., description="Normalized deck payload")


class ExplainRequest(BaseModel):
    question: str
    archetype: str | None = None
    deck: dict[str, list[dict[str, Any]]] | None = None


class ExplainResponse(BaseModel):
    provider: str
    model: str
    answer: str
    context: dict[str, Any]
