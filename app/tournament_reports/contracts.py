from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReportState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class ReportGrain(str, Enum):
    FAMILY = "family"
    VARIANT = "variant"


class ReportPhase(str, Enum):
    PHASE1 = "phase1"
    PHASE2 = "phase2"
    TOP_CUT = "top_cut"
    OVERALL = "overall"


class Record(BaseModel):
    model_config = ConfigDict(frozen=True)

    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    ties: int = Field(ge=0)


class ReportSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    grain: ReportGrain
    selection_id: str = Field(min_length=1)


class SourceProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_provider: str
    tournament_id: str
    division: str
    source_updated_at: datetime | None = None
    fetched_at: datetime
    snapshot_version: str
    schema_version: int


class ModuleStatus(BaseModel):
    state: ReportState
    reason_code: str | None = None
    message: str | None = None
    exportable: bool


class ReportModule(BaseModel):
    module_id: str
    title: str
    status: ModuleStatus
    grain: ReportGrain | None = None
    phase: ReportPhase
    selection_id: str | None = None
    sample_size: int = Field(ge=0)
    metric_notes: list[str]
    provenance: SourceProvenance
    data: dict[str, Any]


class EventIdentity(BaseModel):
    tournament_id: str
    name: str
    date: str
    division: str
    location: str | None = None


class ReportSelectionOption(BaseModel):
    selection_id: str
    label: str
    phase1_players: int = Field(ge=0)
    eligible: bool
    reason_code: str | None = None


class TournamentReportIndexItem(BaseModel):
    dataset_id: str
    event: EventIdentity
    snapshot_version: str


class TournamentReportIndexResponse(BaseModel):
    events: list[TournamentReportIndexItem]


class EventOverviewResponse(BaseModel):
    dataset_id: str
    event: EventIdentity
    snapshot_version: str
    families: list[ReportSelectionOption]
    modules: list[ReportModule]


class ArchetypeReportResponse(BaseModel):
    dataset_id: str
    event: EventIdentity
    selection: ReportSelection
    variants: list[ReportSelectionOption]
    snapshot_version: str
    modules: list[ReportModule]


class SnapshotResource(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def path_must_be_relative_and_contained(cls, value: str) -> str:
        parts = value.replace("\\", "/").split("/")
        if not value or value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("resource path must be a contained relative path")
        return value


class SnapshotManifest(BaseModel):
    schema_version: int
    snapshot_version: str = Field(min_length=1)
    tournament_id: str = Field(min_length=1)
    division: str = Field(min_length=1)
    source_provider: str = Field(min_length=1)
    source_updated_at: datetime | None = None
    fetched_at: datetime
    declared_rounds: int = Field(ge=1)
    resources: dict[str, SnapshotResource]

    @field_validator("snapshot_version")
    @classmethod
    def snapshot_version_must_be_a_directory_name(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("snapshot version must be a directory name")
        return value


class SnapshotVerification(BaseModel):
    blocking_issue_codes: tuple[str, ...] = ()


class RawTournamentSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: SnapshotManifest
    tournament: dict[str, Any]
    decks: tuple[dict[str, Any], ...]
    standings: tuple[dict[str, Any], ...]
    pairings: dict[int, tuple[dict[str, Any], ...]]
    decklists: dict[str, dict[str, Any]]
    matchup_references: dict[str, dict[str, Any] | list[Any]]
