from __future__ import annotations

from pathlib import Path

from app.tournament_reports.builders import build_archetype_report, build_event_overview
from app.tournament_reports.contracts import (
    ReportGrain,
    ReportSelection,
    ReportState,
    SnapshotManifest,
)
from app.tournament_reports.facts import FamilyOverrideSet, normalize_snapshot
from app.tournament_reports.reconciliation import reconcile_tournament
from app.tournament_reports.snapshots import SnapshotStore


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


def _reports():
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    snapshot = SnapshotStore().load_candidate(FIXTURE, manifest)
    facts = normalize_snapshot(snapshot, FamilyOverrideSet(version=1, mappings={}))
    reconciliation = reconcile_tournament(facts)
    return [
        build_event_overview(facts, reconciliation, "2026-new-orleans-ma"),
        build_archetype_report(
            facts,
            reconciliation,
            "2026-new-orleans-ma",
            ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ),
    ]


def test_ready_modules_have_complete_export_context() -> None:
    ready_count = 0
    non_ready_count = 0
    for report in _reports():
        for module in report.modules:
            if module.status.state is ReportState.READY:
                ready_count += 1
                assert module.status.exportable is True
                assert module.title and module.metric_notes
                assert module.sample_size >= 0
                assert module.provenance.source_provider == "Limitless Labs"
                assert module.provenance.fetched_at
                assert module.provenance.snapshot_version == report.snapshot_version
            else:
                non_ready_count += 1
                assert module.status.exportable is False
                assert module.status.reason_code and module.status.message

    assert ready_count > 0
    assert non_ready_count > 0
