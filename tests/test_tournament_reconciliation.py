from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from app.tournament_reports.contracts import (
    Record,
    ReportState,
    SnapshotManifest,
)
from app.tournament_reports.facts import (
    FamilyOverrideSet,
    MatchupReference,
    normalize_snapshot,
)
from app.tournament_reports.reconciliation import (
    ReconciliationResult,
    ValidationIssue,
    module_status,
    reconcile_tournament,
    verify_candidate_snapshot,
)
from app.tournament_reports.snapshots import SnapshotStore


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


@pytest.fixture
def raw_snapshot():
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    return SnapshotStore().load_candidate(FIXTURE, manifest)


@pytest.fixture
def facts(raw_snapshot):
    return normalize_snapshot(raw_snapshot, FamilyOverrideSet(version=1, mappings={}))


def test_reconciliation_happens_at_variant_grain_before_family_rollup(facts) -> None:
    result = reconcile_tournament(facts)

    assert result.issues == ()
    assert result.phase_boundary == 1
    assert result.variant_records["dragapult-ex"] == Record(wins=1, losses=1, ties=0)
    assert result.variant_records["dragapult-dusknoir"] == Record(wins=1, losses=1, ties=1)


def test_equal_and_opposite_variant_errors_do_not_cancel_at_family_grain(facts) -> None:
    source_records = {variant_id: dict(records) for variant_id, records in facts.source_phase_records.items()}
    source_records["dragapult-ex"] = {
        1: Record(wins=1, losses=0, ties=0),
        2: source_records["dragapult-ex"][2],
    }
    source_records["dragapult-dusknoir"] = {
        1: Record(wins=0, losses=0, ties=0),
        2: source_records["dragapult-dusknoir"][2],
    }
    corrupted = replace(facts, source_phase_records=MappingProxyType(source_records))

    result = reconcile_tournament(corrupted)

    mismatches = [issue for issue in result.issues if issue.code == "variant_record_mismatch"]
    assert len(mismatches) == 2
    assert {"dragapult-ex", "dragapult-dusknoir"} == {
        issue.message.split(":", 1)[0] for issue in mismatches
    }


def test_completed_round_and_standings_gates_are_independent(facts) -> None:
    incomplete = replace(facts, tournament=replace(facts.tournament, completed=False))
    missing_round = replace(facts, rounds_present=frozenset({1, 2}))
    changed_player = replace(facts.players["11"], source_record=Record(wins=9, losses=0, ties=0))
    bad_standings = replace(
        facts,
        players=MappingProxyType({**facts.players, "11": changed_player}),
    )

    assert "tournament_not_completed" in {issue.code for issue in reconcile_tournament(incomplete).issues}
    assert "missing_pairing_round" in {issue.code for issue in reconcile_tournament(missing_round).issues}
    assert "standing_record_mismatch" in {issue.code for issue in reconcile_tournament(bad_standings).issues}


def test_unresolved_phase_blocks_only_phase_dependent_modules(facts) -> None:
    ambiguous = replace(
        facts,
        pairings=(),
        source_phase_records=MappingProxyType(
            {
                variant_id: {
                    1: Record(wins=0, losses=0, ties=0),
                    2: Record(wins=0, losses=0, ties=0),
                }
                for variant_id in facts.variants
            }
        ),
    )

    result = reconcile_tournament(ambiguous)

    phase_issue = next(issue for issue in result.issues if issue.code == "phase_boundary_unresolved")
    assert "matchups_day2" in phase_issue.affected_modules
    assert "matchups_overall" not in phase_issue.affected_modules


def test_matchup_reference_mismatch_is_reported_at_variant_grain(facts) -> None:
    reference = MatchupReference(
        variant_id="dragapult-ex",
        payload={
            "overall": {
                "rows": [
                    {"opponent_id": "charizard-ex", "wins": 9, "losses": 0, "ties": 0},
                ],
                "unknown_count": 0,
                "procedural_count": 1,
            }
        },
    )
    changed = replace(
        facts,
        matchup_references=MappingProxyType({"dragapult-ex": reference}),
    )

    result = reconcile_tournament(changed)

    assert {issue.code for issue in result.issues} >= {"matchup_reference_mismatch"}


def test_unknown_and_procedural_counts_do_not_degrade_on_their_own(facts) -> None:
    result = reconcile_tournament(facts)

    assert "unknown_opponent" not in {issue.code for issue in result.issues}
    assert "procedural_result" not in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("issue_code", "module_id", "blocks_publication", "expected_state"),
    [
        ("phase_boundary_unresolved", "matchups_day2", False, ReportState.BLOCKED),
        ("matchup_sample_below_30", "matchups_overall", False, ReportState.DEGRADED),
        ("decklist_coverage_below_60", "deck_composition_first_phase", False, ReportState.DEGRADED),
        ("variant_record_mismatch", "headline_performance", True, ReportState.BLOCKED),
    ],
)
def test_module_state_policy(
    issue_code: str,
    module_id: str,
    blocks_publication: bool,
    expected_state: ReportState,
) -> None:
    result = ReconciliationResult(
        phase_boundary=1,
        issues=(
            ValidationIssue(
                code=issue_code,
                message="quality gate failed",
                affected_modules=frozenset({module_id}),
                blocks_publication=blocks_publication,
            ),
        ),
        variant_records={},
    )

    status = module_status(
        module_id,
        result,
        sample_size=12,
        valid_lists=10,
        coverage=0.80,
    )

    assert status.state is expected_state
    assert status.exportable is (expected_state is ReportState.READY)
    assert status.reason_code == issue_code
    assert status.message


@pytest.mark.parametrize(
    ("module_id", "sample_size", "valid_lists", "coverage", "reason_code"),
    [
        ("matchups_overall", 0, None, None, "no_matches"),
        ("matchups_overall", 29, None, None, "matchup_sample_below_30"),
        ("deck_composition_first_phase", 12, 9, 0.75, "decklist_count_below_10"),
        ("deck_composition_first_phase", 12, 10, 0.59, "decklist_coverage_below_60"),
    ],
)
def test_module_state_applies_sample_and_coverage_thresholds(
    module_id: str,
    sample_size: int,
    valid_lists: int | None,
    coverage: float | None,
    reason_code: str,
) -> None:
    status = module_status(
        module_id,
        ReconciliationResult(phase_boundary=1, issues=(), variant_records={}),
        sample_size=sample_size,
        valid_lists=valid_lists,
        coverage=coverage,
    )

    assert status.state is ReportState.DEGRADED
    assert status.reason_code == reason_code
    assert status.exportable is False


def test_clean_candidate_verification_has_no_blocking_codes(raw_snapshot) -> None:
    verification = verify_candidate_snapshot(
        raw_snapshot,
        FamilyOverrideSet(version=1, mappings={}),
    )
    assert verification.blocking_issue_codes == ()
