from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from app.tournament_reports.builders import build_archetype_report
from app.tournament_reports.contracts import ReportGrain, ReportSelection, SnapshotManifest
from app.tournament_reports.facts import DecklistFact, FamilyOverrideSet, normalize_snapshot
from app.tournament_reports.reconciliation import reconcile_tournament
from app.tournament_reports.snapshots import SnapshotStore


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")
MODULE_IDS = [
    "headline_performance",
    "phase_performance",
    "top_finishers",
    "matchups_overall",
    "matchups_phase1",
    "matchups_phase2",
    "deck_composition_phase1",
    "deck_composition_phase2",
    "deck_composition_top_cut",
    "representative_lists",
]


def _eligible_facts():
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    snapshot = SnapshotStore().load_candidate(FIXTURE, manifest)
    facts = normalize_snapshot(snapshot, FamilyOverrideSet(version=1, mappings={}))
    base_player = facts.players["11"]
    base_list = facts.decklists["11"]
    players = {}
    decklists = {}
    for index in range(10):
        player_id = str(101 + index)
        players[player_id] = replace(
            base_player,
            tp_id=player_id,
            placement=index + 1,
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


def test_family_and_variant_payloads_match_the_ui_module_contract() -> None:
    facts = _eligible_facts()
    reconciliation = reconcile_tournament(facts)
    family = build_archetype_report(
        facts,
        reconciliation,
        "2026-new-orleans-ma",
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
    )
    variant = build_archetype_report(
        facts,
        reconciliation,
        "2026-new-orleans-ma",
        ReportSelection(grain=ReportGrain.VARIANT, selection_id="dragapult-dusknoir"),
    )

    assert [module.module_id for module in family.modules] == MODULE_IDS
    assert [module.module_id for module in variant.modules] == MODULE_IDS
    assert all(
        option.phase1_players >= 10
        for option in family.variants
        if option.eligible
    )
    assert {module.grain for module in family.modules} == {ReportGrain.FAMILY}
    assert {module.grain for module in variant.modules} == {ReportGrain.VARIANT}
