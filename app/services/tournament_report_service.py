from __future__ import annotations

from pathlib import Path

from app.services.dataset_registry_service import DatasetRegistryService
from app.services.dataset_state_store import DatasetStateStore
from app.tournament_reports.builders import (
    ReportEligibilityError,
    build_archetype_report,
    build_event_overview,
)
from app.tournament_reports.contracts import (
    ArchetypeReportResponse,
    EventOverviewResponse,
    ReportSelection,
    TournamentReportIndexItem,
    TournamentReportIndexResponse,
)
from app.tournament_reports.facts import (
    TournamentFacts,
    load_family_overrides,
    normalize_snapshot,
)
from app.tournament_reports.reconciliation import ReconciliationResult, reconcile_tournament
from app.tournament_reports.snapshots import SnapshotStore, SnapshotValidationError


class TournamentReportNotFound(LookupError):
    pass


class TournamentReportNotEligible(ValueError):
    def __init__(
        self,
        detail: str,
        reason_code: str,
        sample_size: int | None = None,
    ) -> None:
        self.detail = detail
        self.reason_code = reason_code
        self.sample_size = sample_size
        super().__init__(detail)


class TournamentSnapshotUnavailable(RuntimeError):
    def __init__(self, detail: str, reason_code: str) -> None:
        self.detail = detail
        self.reason_code = reason_code
        super().__init__(detail)


class TournamentReportService:
    def __init__(
        self,
        dataset_registry: DatasetRegistryService,
        dataset_state_store: DatasetStateStore,
        snapshot_store: SnapshotStore,
        family_overrides_path: Path,
    ) -> None:
        self.dataset_registry = dataset_registry
        self.dataset_state_store = dataset_state_store
        self.snapshot_store = snapshot_store
        self.family_overrides_path = Path(family_overrides_path)
        self._cache: dict[
            tuple[str, str, int], tuple[TournamentFacts, ReconciliationResult]
        ] = {}

    def list_reports(self, mounted_dataset_ids: list[str]) -> TournamentReportIndexResponse:
        events: list[TournamentReportIndexItem] = []
        mounted = set(self._mounted_dataset_ids())
        for dataset_id in mounted_dataset_ids:
            if dataset_id not in mounted:
                continue
            try:
                facts, reconciliation = self._load(dataset_id)
            except (TournamentReportNotFound, TournamentSnapshotUnavailable):
                continue
            if not facts.tournament.completed:
                continue
            overview = build_event_overview(facts, reconciliation, dataset_id)
            events.append(
                TournamentReportIndexItem(
                    dataset_id=dataset_id,
                    event=overview.event,
                    snapshot_version=facts.provenance.snapshot_version,
                )
            )
        return TournamentReportIndexResponse(events=events)

    def get_overview(self, dataset_id: str) -> EventOverviewResponse:
        facts, reconciliation = self._load_eligible(dataset_id)
        return build_event_overview(facts, reconciliation, dataset_id)

    def get_archetype_report(
        self,
        dataset_id: str,
        selection: ReportSelection,
    ) -> ArchetypeReportResponse:
        facts, reconciliation = self._load_eligible(dataset_id)
        try:
            return build_archetype_report(facts, reconciliation, dataset_id, selection)
        except KeyError as error:
            raise TournamentReportNotFound("Archetype selection was not found") from error
        except ReportEligibilityError as error:
            raise TournamentReportNotEligible(
                str(error), error.reason_code, error.sample_size
            ) from error

    def _load_eligible(
        self, dataset_id: str
    ) -> tuple[TournamentFacts, ReconciliationResult]:
        facts, reconciliation = self._load(dataset_id)
        if not facts.tournament.completed:
            raise TournamentReportNotEligible(
                "Tournament report is available only for completed events",
                "event_incomplete",
            )
        return facts, reconciliation

    def _load(self, dataset_id: str) -> tuple[TournamentFacts, ReconciliationResult]:
        record = self.dataset_registry.get_dataset(dataset_id)
        if record is None:
            raise TournamentReportNotFound("Tournament dataset was not found")
        if dataset_id not in self._mounted_dataset_ids():
            raise TournamentReportNotEligible(
                "Tournament dataset must be mounted",
                "dataset_not_mounted",
            )
        try:
            snapshot = self.snapshot_store.load(Path(record.dataset_dir))
        except SnapshotValidationError as error:
            raise TournamentSnapshotUnavailable(str(error), error.code) from error
        try:
            overrides = load_family_overrides(self.family_overrides_path)
        except ValueError as error:
            raise TournamentSnapshotUnavailable(
                str(error), "family_overrides_unavailable"
            ) from error
        key = (
            dataset_id,
            snapshot.manifest.snapshot_version,
            overrides.version,
        )
        if key not in self._cache:
            facts = normalize_snapshot(snapshot, overrides)
            self._cache[key] = (facts, reconcile_tournament(facts))
        return self._cache[key]

    def _mounted_dataset_ids(self) -> list[str]:
        available = [record.dataset_id for record in self.dataset_registry.list_datasets()]
        state = self.dataset_state_store.reconcile(
            self.dataset_state_store.load(), available_dataset_ids=available
        )
        return state.mounted_dataset_ids
