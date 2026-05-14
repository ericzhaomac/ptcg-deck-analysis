from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DatasetRecord(BaseModel):
    dataset_id: str
    year: int
    event_slug: str
    event_name: str
    division: str
    display_name: str
    dataset_dir: str
    analysis_path: str
    cache_path: str | None = None
    tournament_id: str | None = None
    city: str | None = None
    source_provider: str | None = None


class DatasetState(BaseModel):
    mounted_dataset_ids: list[str] = Field(default_factory=list)
    current_dataset_id: str | None = None


class DatasetIdRequest(BaseModel):
    dataset_id: str


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
