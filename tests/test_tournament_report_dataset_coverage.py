from __future__ import annotations

from pathlib import Path

from app.services.dataset_registry_service import DatasetRegistryService
from app.services.dataset_state_store import DatasetStateStore
from app.services.tournament_report_service import TournamentReportService
from app.tournament_reports.contracts import ReportGrain, ReportSelection, ReportState
from app.tournament_reports.snapshots import SnapshotStore
from scripts.tools.limitless_tournament_snapshot import LimitlessClient


DATA_ROOT = Path("data")


def production_report_service(data_root: Path) -> TournamentReportService:
    return TournamentReportService(
        dataset_registry=DatasetRegistryService(data_root),
        dataset_state_store=DatasetStateStore(data_root / "config/dataset_state.json"),
        snapshot_store=SnapshotStore(),
        family_overrides_path=data_root / "config/archetype_family_overrides.json",
    )


def test_every_mounted_completed_event_has_mvp_report_coverage(monkeypatch) -> None:
    monkeypatch.setattr(
        LimitlessClient,
        "fetch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("report coverage opened the network")),
    )
    state = DatasetStateStore(DATA_ROOT / "config/dataset_state.json").load()
    service = production_report_service(DATA_ROOT)

    index = service.list_reports(state.mounted_dataset_ids)
    assert {event.dataset_id for event in index.events} == set(state.mounted_dataset_ids)

    for event in index.events:
        overview = service.get_overview(event.dataset_id)
        top_ten = [family for family in overview.families if family.eligible]
        assert len(top_ten) == min(10, len(overview.families))
        for family in top_ten:
            family_report = service.get_archetype_report(
                event.dataset_id,
                ReportSelection(grain=ReportGrain.FAMILY, selection_id=family.selection_id),
            )
            assert all(module.status.state in set(ReportState) for module in family_report.modules)
            ineligible_variants = [variant for variant in family_report.variants if not variant.eligible]
            assert all(variant.reason_code == "variant_players_below_10" for variant in ineligible_variants)
            for variant in [row for row in family_report.variants if row.eligible]:
                variant_report = service.get_archetype_report(
                    event.dataset_id,
                    ReportSelection(grain=ReportGrain.VARIANT, selection_id=variant.selection_id),
                )
                assert variant.first_phase_players >= 10
                assert all(module.status.state in set(ReportState) for module in variant_report.modules)
