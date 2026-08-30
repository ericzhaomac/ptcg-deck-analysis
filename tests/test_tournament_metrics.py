from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from app.tournament_reports.contracts import (
    Record,
    ReportGrain,
    ReportPhase,
    ReportSelection,
    SnapshotManifest,
)
from app.tournament_reports.facts import (
    DecklistFact,
    FamilyOverrideSet,
    PairingFact,
    normalize_snapshot,
)
from app.tournament_reports.metrics import (
    composition_bucket,
    conversion,
    deck_composition,
    distribution,
    matchup_sample_state,
    matchups,
    representative_lists,
    win_rate,
)
from app.tournament_reports.snapshots import SnapshotStore


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


@pytest.fixture
def facts():
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    snapshot = SnapshotStore().load_candidate(FIXTURE, manifest)
    return normalize_snapshot(snapshot, FamilyOverrideSet(version=1, mappings={}))


def _rows_by_id(metric):
    return {row.selection_id: row for row in metric.rows}


def _expanded_dragapult_facts(facts, *, players: int, valid_lists: int):
    base_player = facts.players["11"]
    base_list = facts.decklists["11"]
    expanded_players = {}
    expanded_lists = {}
    for index in range(players):
        player_id = str(11 + index)
        placement = 1 if player_id == "11" else 2 if player_id in {"14", "15"} else 3 + index
        points = 8 if player_id == "15" else 7 if player_id in {"11", "14"} else 3
        expanded_players[player_id] = replace(
            base_player,
            tp_id=player_id,
            placement=placement,
            points=points,
            decklist_available=index < valid_lists,
        )
        if index < valid_lists:
            expanded_lists[player_id] = DecklistFact(
                player_tp_id=player_id,
                cards=base_list.cards,
                valid=True,
            )
    return replace(
        facts,
        players=MappingProxyType(expanded_players),
        pairings=(),
        decklists=MappingProxyType(expanded_lists),
    )


def test_win_rate_weights_ties_as_one_third() -> None:
    assert win_rate(Record(wins=3278, losses=2466, ties=1021)) == pytest.approx(0.5349, abs=0.00005)
    assert win_rate(Record(wins=0, losses=0, ties=0)) is None


def test_first_phase_distribution_uses_known_archetype_players(facts) -> None:
    unknown = replace(
        facts.players["21"],
        tp_id="99",
        variant_id=None,
        family_id=None,
    )
    changed = replace(facts, players=MappingProxyType({**facts.players, "99": unknown}))

    family_metric = distribution(changed, ReportGrain.FAMILY, ReportPhase.FIRST_PHASE)
    variant_metric = distribution(changed, ReportGrain.VARIANT, ReportPhase.FIRST_PHASE)

    family_rows = _rows_by_id(family_metric)
    assert family_metric.known_players == 4
    assert family_metric.unknown_players == 1
    assert family_rows["dragapult-ex"].players == 2
    assert family_rows["dragapult-ex"].share == pytest.approx(0.5)
    assert family_rows["dragapult-ex"].record == Record(wins=2, losses=3, ties=1)
    assert _rows_by_id(variant_metric)["dragapult-dusknoir"].players == 1


def test_day2_top_cut_and_conversion_use_source_player_flags(facts) -> None:
    day2 = distribution(facts, ReportGrain.FAMILY, ReportPhase.DAY2)
    top_cut = distribution(facts, ReportGrain.FAMILY, ReportPhase.TOP_CUT)
    metric = conversion(facts, ReportGrain.FAMILY)

    assert day2.known_players == 3
    assert _rows_by_id(top_cut)["dragapult-ex"].players == 2
    assert top_cut.known_players == 2
    conversion_rows = {row.selection_id: row for row in metric.rows}
    assert metric.first_phase_known_players == 4
    assert metric.day2_known_players == 3
    assert metric.field_rate == pytest.approx(0.75)
    assert conversion_rows["dragapult-ex"].rate == 1.0
    assert conversion_rows["charizard-ex"].rate == 0.5


def test_matchups_count_unique_pairings_and_separate_exclusions(facts) -> None:
    unknown_pairing = PairingFact(
        pairing_id="round-02-table-99",
        round_number=2,
        table_number=99,
        player1_tp_id="11",
        player2_tp_id="unknown",
        player1_variant_id="dragapult-dusknoir",
        player2_variant_id=None,
        outcome="player1",
    )
    changed = replace(facts, pairings=(*facts.pairings, unknown_pairing))

    metric = matchups(
        changed,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.OVERALL,
    )

    assert metric.rows_by_id["dragapult-ex"].matches == 1
    assert metric.rows_by_id["dragapult-ex"].player_side_record == Record(wins=1, losses=1, ties=0)
    assert metric.rows_by_id["charizard-ex"].matches == 3
    assert metric.rows_by_id["charizard-ex"].player_side_record == Record(wins=1, losses=1, ties=1)
    assert metric.unknown_count == 1
    assert metric.procedural_count == 1


def test_matchups_classify_a_bye_as_procedural_not_unknown(facts) -> None:
    bye = PairingFact(
        pairing_id="round-02-procedural-1",
        round_number=2,
        table_number=None,
        player1_tp_id="11",
        player2_tp_id=None,
        player1_variant_id="dragapult-dusknoir",
        player2_variant_id=None,
        outcome="player1",
    )

    metric = matchups(
        replace(facts, pairings=(*facts.pairings, bye)),
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.OVERALL,
    )

    assert metric.unknown_count == 0
    assert metric.procedural_count == 2


def test_day2_matchups_use_rounds_after_the_unique_boundary(facts) -> None:
    metric = matchups(
        facts,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.DAY2,
    )

    assert metric.phase_available is True
    assert metric.phase_boundary == 1
    assert metric.rows_by_id["charizard-ex"].matches == 2
    assert metric.rows_by_id["dragapult-ex"].matches == 1


@pytest.mark.parametrize(
    ("matches", "expected"),
    [(0, "none"), (1, "insufficient"), (29, "insufficient"), (30, "ready")],
)
def test_matchup_sample_gate_uses_thirty_unique_matches(matches: int, expected: str) -> None:
    assert matchup_sample_state(matches) == expected


@pytest.mark.parametrize(
    ("appearance", "expected"),
    [(0.80, "core"), (0.30, "common"), (0.05, "tech"), (0.049, "rare")],
)
def test_composition_bucket_boundaries(appearance: float, expected: str) -> None:
    assert composition_bucket(appearance) == expected


def test_composition_requires_ten_valid_lists_and_sixty_percent_coverage(facts) -> None:
    selection = ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex")
    too_few = deck_composition(
        _expanded_dragapult_facts(facts, players=10, valid_lists=6),
        selection,
        ReportPhase.FIRST_PHASE,
    )
    ready = deck_composition(
        _expanded_dragapult_facts(facts, players=10, valid_lists=10),
        selection,
        ReportPhase.FIRST_PHASE,
    )

    assert too_few.valid_list_count == 6
    assert too_few.coverage == pytest.approx(0.60)
    assert too_few.eligible_for_classification is False
    assert too_few.rows == ()
    assert ready.eligible_for_classification is True
    dreepy = next(row for row in ready.rows if row.card_name == "dreepy")
    assert dreepy.appearance_rate == 1.0
    assert dreepy.average_when_present == 4.0
    assert dreepy.bucket == "core"


def test_representative_lists_are_deterministic(facts) -> None:
    expanded = _expanded_dragapult_facts(facts, players=5, valid_lists=5)
    rows = representative_lists(
        expanded,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.FIRST_PHASE,
    )

    assert [row.player_tp_id for row in rows] == ["11", "15", "14"]
    assert rows[0].cards[0].set_code == "TWM"
