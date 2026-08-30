from __future__ import annotations

from pathlib import Path

import pytest

from app.models import DatasetRecord, DatasetState
from app.services.dataset_state_store import DatasetStateStore
from app.services.tournament_report_service import (
    TournamentReportNotEligible,
    TournamentReportNotFound,
    TournamentReportService,
    TournamentSnapshotUnavailable,
)
from app.tournament_reports.contracts import SnapshotManifest
from app.tournament_reports.snapshots import SnapshotStore, SnapshotValidationError


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


class RegistryStub:
    def __init__(self, records: list[DatasetRecord]) -> None:
        self.records = {record.dataset_id: record for record in records}

    def list_datasets(self) -> list[DatasetRecord]:
        return list(self.records.values())

    def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        return self.records.get(dataset_id)


class SnapshotStoreStub:
    def __init__(self, snapshots: dict[str, object]) -> None:
        self.snapshots = snapshots

    def load(self, dataset_dir: Path):
        value = self.snapshots[str(dataset_dir)]
        if isinstance(value, Exception):
            raise value
        return value


def _record(dataset_id: str, dataset_dir: Path) -> DatasetRecord:
    return DatasetRecord(
        dataset_id=dataset_id,
        year=2026,
        event_slug=dataset_id,
        event_name=dataset_id,
        division="MA",
        display_name=dataset_id,
        dataset_dir=str(dataset_dir),
        analysis_path=str(dataset_dir / "analysis.json"),
        tournament_id="0070",
    )


def _snapshot(*, completed: bool = True, version: str = "fixture-v1"):
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    manifest = manifest.model_copy(update={"snapshot_version": version})
    snapshot = SnapshotStore().load_candidate(
        FIXTURE,
        SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text()),
    )
    tournament = {**snapshot.tournament, "completed": int(completed)}
    return snapshot.model_copy(update={"manifest": manifest, "tournament": tournament})


@pytest.fixture
def report_service(tmp_path: Path) -> TournamentReportService:
    records = [
        _record("completed", tmp_path / "completed"),
        _record("unfinished", tmp_path / "unfinished"),
        _record("missing", tmp_path / "missing"),
    ]
    state_path = tmp_path / "dataset-state.json"
    DatasetStateStore(state_path).save(
        DatasetState(mounted_dataset_ids=["completed", "unfinished", "missing"])
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"version": 1, "mappings": {}}', encoding="utf-8")
    return TournamentReportService(
        dataset_registry=RegistryStub(records),
        dataset_state_store=DatasetStateStore(state_path),
        snapshot_store=SnapshotStoreStub(
            {
                str(tmp_path / "completed"): _snapshot(),
                str(tmp_path / "unfinished"): _snapshot(completed=False),
                str(tmp_path / "missing"): SnapshotValidationError(
                    "missing_verified_pointer", "verified snapshot pointer is missing"
                ),
            }
        ),
        family_overrides_path=overrides,
    )


def test_index_contains_only_mounted_completed_events(report_service) -> None:
    response = report_service.list_reports(["completed", "unfinished", "unmounted"])

    assert [item.dataset_id for item in response.events] == ["completed"]


def test_fact_cache_is_keyed_by_dataset_and_snapshot_version(
    report_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.tournament_report_service as service_module

    calls = 0
    real_normalize = service_module.normalize_snapshot

    def counting_normalize(snapshot, overrides):
        nonlocal calls
        calls += 1
        return real_normalize(snapshot, overrides)

    monkeypatch.setattr(service_module, "normalize_snapshot", counting_normalize)

    report_service.get_overview("completed")
    report_service.get_overview("completed")

    assert calls == 1


def test_cache_invalidates_when_snapshot_version_changes(
    report_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.tournament_report_service as service_module

    calls = 0
    real_normalize = service_module.normalize_snapshot

    def counting_normalize(snapshot, overrides):
        nonlocal calls
        calls += 1
        return real_normalize(snapshot, overrides)

    monkeypatch.setattr(service_module, "normalize_snapshot", counting_normalize)
    report_service.get_overview("completed")
    report_service.snapshot_store.snapshots[
        str(Path(report_service.dataset_registry.get_dataset("completed").dataset_dir))
    ] = _snapshot(version="fixture-v2")

    response = report_service.get_overview("completed")

    assert calls == 2
    assert response.snapshot_version == "fixture-v2"


def test_service_distinguishes_unknown_unmounted_and_unavailable(report_service) -> None:
    with pytest.raises(TournamentReportNotFound):
        report_service.get_overview("unknown")
    state = report_service.dataset_state_store.load()
    report_service.dataset_state_store.save(
        DatasetState(mounted_dataset_ids=[item for item in state.mounted_dataset_ids if item != "completed"])
    )
    with pytest.raises(TournamentReportNotEligible, match="mounted"):
        report_service.get_overview("completed")
    with pytest.raises(TournamentSnapshotUnavailable):
        report_service.get_overview("missing")
