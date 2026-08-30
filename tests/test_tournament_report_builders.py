from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from app.tournament_reports.builders import (
    ReportEligibilityError,
    build_archetype_report,
    build_event_overview,
)
from app.tournament_reports.contracts import (
    Record,
    ReportGrain,
    ReportSelection,
    ReportState,
    SnapshotManifest,
)
from app.tournament_reports.facts import (
    DecklistFact,
    FamilyOverrideSet,
    normalize_snapshot,
)
from app.tournament_reports.reconciliation import (
    ReconciliationResult,
    ValidationIssue,
    reconcile_tournament,
)
from app.tournament_reports.snapshots import SnapshotStore


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


@pytest.fixture
def facts():
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    snapshot = SnapshotStore().load_candidate(FIXTURE, manifest)
    return normalize_snapshot(snapshot, FamilyOverrideSet(version=1, mappings={}))


@pytest.fixture
def reconciliation(facts):
    return reconcile_tournament(facts)


def _eligible_dragapult_facts(facts):
    base_player = facts.players["11"]
    base_list = facts.decklists["11"]
    players = {
        "12": replace(
            facts.players["12"],
            decklist_available=False,
        )
    }
    decklists = {}
    for index in range(10):
        player_id = str(101 + index)
        players[player_id] = replace(
            base_player,
            tp_id=player_id,
            placement=index + 1,
            points=30 - index,
            decklist_available=True,
        )
        decklists[player_id] = DecklistFact(
            player_tp_id=player_id,
            cards=base_list.cards,
            valid=True,
        )
    return replace(
        facts,
        players=MappingProxyType(players),
        decklists=MappingProxyType(decklists),
    )


def _eleven_family_facts(facts):
    base_variant = facts.variants["charizard-ex"]
    base_player = facts.players["21"]
    variants = {}
    players = {}
    source_records = {}
    for index in range(11):
        selection_id = f"family-{index:02d}"
        variants[selection_id] = replace(
            base_variant,
            variant_id=selection_id,
            variant_name=f"Variant {index}",
            family_id=selection_id,
            family_name=f"Family {index}",
        )
        player_id = str(200 + index)
        players[player_id] = replace(
            base_player,
            tp_id=player_id,
            variant_id=selection_id,
            family_id=selection_id,
            source_record=Record(wins=0, losses=0, ties=0),
        )
        source_records[selection_id] = {
            1: Record(wins=0, losses=0, ties=0),
            2: Record(wins=0, losses=0, ties=0),
        }
    return replace(
        facts,
        variants=MappingProxyType(variants),
        players=MappingProxyType(players),
        pairings=(),
        decklists=MappingProxyType({}),
        matchup_references=MappingProxyType({}),
        source_phase_records=MappingProxyType(source_records),
    )


def test_overview_has_layered_distribution_then_conversion_then_ranking(facts, reconciliation) -> None:
    report = build_event_overview(facts, reconciliation, "2026-new-orleans-ma")

    assert [module.module_id for module in report.modules] == [
        "event_identity",
        "phase_topcut_distribution",
        "day2_conversion",
        "family_ranking",
    ]
    comparison = report.modules[1].data
    assert {row["family_id"] for row in comparison["first_phase"]} == {
        "dragapult-ex",
        "charizard-ex",
    }
    assert comparison["top_cut"][0]["family_id"] == "dragapult-ex"
    assert report.modules[2].data["first_phase_players"] == 4
    assert report.modules[2].data["day2_players"] == 3
    assert all(option.eligible for option in report.families)


def test_overview_retains_long_tail_but_only_top_ten_are_report_eligible(facts) -> None:
    expanded = _eleven_family_facts(facts)
    report = build_event_overview(
        expanded,
        ReconciliationResult(phase_boundary=None, issues=(), variant_records={}),
        "eleven-families",
    )

    assert len(report.families) == 11
    assert sum(option.eligible for option in report.families) == 10
    assert report.families[-1].reason_code == "outside_top_10_families"


def test_archetype_report_keeps_one_grain_across_every_module(facts, reconciliation) -> None:
    eligible = _eligible_dragapult_facts(facts)
    selection = ReportSelection(
        grain=ReportGrain.VARIANT,
        selection_id="dragapult-dusknoir",
    )

    report = build_archetype_report(
        eligible,
        reconciliation,
        "2026-new-orleans-ma",
        selection,
    )

    assert [module.module_id for module in report.modules] == [
        "headline_performance",
        "phase_performance",
        "top_finishers",
        "matchups_overall",
        "matchups_day2",
        "deck_composition_first_phase",
        "deck_composition_day2",
        "deck_composition_top_cut",
        "representative_lists",
    ]
    assert {module.grain for module in report.modules} == {ReportGrain.VARIANT}
    assert {module.selection_id for module in report.modules} == {"dragapult-dusknoir"}


def test_family_report_lists_all_variants_with_ten_player_gate(facts, reconciliation) -> None:
    report = build_archetype_report(
        _eligible_dragapult_facts(facts),
        reconciliation,
        "2026-new-orleans-ma",
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
    )
    variants = {option.selection_id: option for option in report.variants}

    assert variants["dragapult-dusknoir"].eligible is True
    assert variants["dragapult-dusknoir"].first_phase_players == 10
    assert variants["dragapult-ex"].eligible is False
    assert variants["dragapult-ex"].reason_code == "variant_players_below_10"


def test_direct_variant_report_below_ten_returns_structured_eligibility_error(
    facts,
    reconciliation,
) -> None:
    with pytest.raises(ReportEligibilityError) as error:
        build_archetype_report(
            facts,
            reconciliation,
            "2026-new-orleans-ma",
            ReportSelection(grain=ReportGrain.VARIANT, selection_id="dragapult-ex"),
        )

    assert error.value.reason_code == "variant_players_below_10"
    assert error.value.sample_size == 1


def test_every_archetype_module_is_self_describing(facts, reconciliation) -> None:
    report = build_archetype_report(
        _eligible_dragapult_facts(facts),
        reconciliation,
        "2026-new-orleans-ma",
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
    )

    for module in report.modules:
        assert module.provenance.snapshot_version == "fixture-v1"
        assert module.phase
        assert module.sample_size >= 0
        assert module.metric_notes
        assert module.status.exportable is (module.status.state is ReportState.READY)
        if module.status.state is not ReportState.READY:
            assert module.status.reason_code and module.status.message


def test_global_blocking_issue_degrades_no_module_silently(facts) -> None:
    blocked = ReconciliationResult(
        phase_boundary=1,
        issues=(
            ValidationIssue(
                code="source_schema_incompatible",
                message="Source schema changed.",
                affected_modules=frozenset({"*"}),
                blocks_publication=True,
            ),
        ),
        variant_records={},
    )

    report = build_event_overview(facts, blocked, "2026-new-orleans-ma")

    assert {module.status.state for module in report.modules} == {ReportState.BLOCKED}
    assert all(module.status.exportable is False for module in report.modules)
