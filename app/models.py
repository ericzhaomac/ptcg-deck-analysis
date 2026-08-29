from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeckCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    count: int = Field(..., ge=1, le=60)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Card name cannot be empty")
        return value


class DeckWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    pokemon: list[DeckCard] = Field(default_factory=list)
    trainer: list[DeckCard] = Field(default_factory=list)
    energy: list[DeckCard] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Deck name cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_cards(self) -> Self:
        total = 0
        for section in (self.pokemon, self.trainer, self.energy):
            normalized_names: set[str] = set()
            for card in section:
                key = card.name.casefold()
                if key in normalized_names:
                    raise ValueError(f"Duplicate card in category: {card.name}")
                normalized_names.add(key)
                total += card.count
        if total > 60:
            raise ValueError("Deck cannot contain more than 60 cards")
        return self


class SavedDeck(DeckWrite):
    id: str
    created_at: datetime
    updated_at: datetime


class ProviderSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(..., min_length=1, max_length=500)
    model: str = Field(..., min_length=1, max_length=200)
    api_key: str = Field(default="", max_length=1000)

    @field_validator("base_url", "model")
    @classmethod
    def strip_required_provider_field(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class ModelDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=1000)


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


class DatasetStateResponse(BaseModel):
    mounted_dataset_ids: list[str]
    current_dataset_id: str | None = None


class DatasetListResponse(DatasetStateResponse):
    datasets: list[DatasetRecord]


class DeckCompareRequest(BaseModel):
    archetype: str = Field(..., description="Archetype name or id")
    deck: dict[str, list[dict[str, Any]]] = Field(..., description="Normalized deck payload")
    dataset_id: str | None = None


class ExplainRequest(BaseModel):
    question: str
    archetype: str | None = None
    deck: dict[str, list[dict[str, Any]]] | None = None
    dataset_id: str | None = None


class ExplainResponse(BaseModel):
    provider: str
    model: str
    answer: str
    context: dict[str, Any]
