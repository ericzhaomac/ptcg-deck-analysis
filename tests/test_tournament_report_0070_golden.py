from __future__ import annotations

import json
from pathlib import Path

from app.services.dataset_registry_service import DatasetRegistryService
from app.services.dataset_state_store import DatasetStateStore
from app.services.tournament_report_service import TournamentReportService
from app.tournament_reports.contracts import ReportGrain, ReportPhase, ReportSelection
from app.tournament_reports.facts import load_family_overrides, normalize_snapshot
from app.tournament_reports.metrics import conversion, matchups, selection_record, win_rate
from app.tournament_reports.reconciliation import _local_matchup_reference, reconcile_tournament
from app.tournament_reports.snapshots import SnapshotStore


DATA_ROOT = Path("data")
DATASET_DIR = DATA_ROOT / "2026/New_Orleans/MA"
EXPECTED = json.loads(
    Path("tests/fixtures/tournament_reports/0070-golden/expected.json").read_text()
)


def _record_dict(record) -> dict[str, int]:
    return {"wins": record.wins, "losses": record.losses, "ties": record.ties}


def _source_record(raw: dict[str, int]) -> dict[str, int]:
    return {key: int(raw[key]) for key in ("wins", "losses", "ties")}


def test_0070_dragapult_golden_metrics_and_family_sum() -> None:
    service = TournamentReportService(
        dataset_registry=DatasetRegistryService(DATA_ROOT),
        dataset_state_store=DatasetStateStore(DATA_ROOT / "config/dataset_state.json"),
        snapshot_store=SnapshotStore(),
        family_overrides_path=DATA_ROOT / "config/archetype_family_overrides.json",
    )
    service.get_overview(EXPECTED["dataset_id"])

    snapshot = SnapshotStore().load(DATASET_DIR)
    facts = normalize_snapshot(
        snapshot,
        load_family_overrides(DATA_ROOT / "config/archetype_family_overrides.json"),
    )
    reconciliation = reconcile_tournament(facts)
    selection = ReportSelection(**EXPECTED["selection"])

    assert facts.tournament.tournament_id == EXPECTED["tournament_id"]
    assert facts.tournament.division == EXPECTED["division"]
    assert reconciliation.phase_boundary == EXPECTED["phase_boundary"]
    for phase_name, phase in (
        ("overall", ReportPhase.OVERALL),
        ("phase1", ReportPhase.PHASE1),
        ("phase2", ReportPhase.PHASE2),
    ):
        record = selection_record(facts, selection, phase)
        assert _record_dict(record) == {
            key: EXPECTED[phase_name][key] for key in ("wins", "losses", "ties")
        }
        assert round(win_rate(record), 4) == EXPECTED[phase_name]["win_rate"]

    selected_conversion = next(
        row
        for row in conversion(facts, ReportGrain.VARIANT).rows
        if row.selection_id == selection.selection_id
    )
    assert selected_conversion.phase1_players == EXPECTED["conversion"]["phase1_players"]
    assert selected_conversion.phase2_players == EXPECTED["conversion"]["phase2_players"]
    assert round(selected_conversion.rate, 4) == EXPECTED["conversion"]["rate"]

    phase2_matchups = matchups(facts, selection, ReportPhase.PHASE2)
    assert phase2_matchups.phase_boundary == 8
    assert phase2_matchups.top_cut_exclusion == "not_available"

    family_variants = [
        variant.variant_id
        for variant in facts.variants.values()
        if variant.family_id == "dragapult-ex"
    ]
    family_record = selection_record(
        facts,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.OVERALL,
    )
    assert _record_dict(family_record) == {
        key: sum(getattr(reconciliation.variant_records[variant_id], key) for variant_id in family_variants)
        for key in ("wins", "losses", "ties")
    }
    for variant_id in family_variants:
        source = facts.matchup_references[variant_id].payload
        local_rows, local_unknown, local_procedural = _local_matchup_reference(
            facts,
            variant_id,
            ReportPhase.OVERALL,
        )
        assert {opponent_id: _record_dict(record) for opponent_id, record in local_rows.items()} == {
            row["id"]: _source_record(row) for row in source["decks"]
        }
        assert _record_dict(local_unknown) == _source_record(source["unknown"])
        assert _record_dict(local_procedural) == _source_record(source["procedural"])
    assert not [issue for issue in reconciliation.issues if issue.blocks_publication]
