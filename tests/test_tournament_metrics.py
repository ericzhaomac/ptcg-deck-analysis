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


def test_phase1_distribution_uses_known_archetype_players(facts) -> None:
    unknown = replace(
        facts.players["21"],
        tp_id="99",
        variant_id=None,
        family_id=None,
    )
    changed = replace(facts, players=MappingProxyType({**facts.players, "99": unknown}))

    family_metric = distribution(changed, ReportGrain.FAMILY, ReportPhase.PHASE1)
    variant_metric = distribution(changed, ReportGrain.VARIANT, ReportPhase.PHASE1)

    family_rows = _rows_by_id(family_metric)
    assert family_metric.known_players == 4
    assert family_metric.unknown_players == 1
    assert family_rows["dragapult-ex"].players == 2
    assert family_rows["dragapult-ex"].share == pytest.approx(0.5)
    assert family_rows["dragapult-ex"].record == Record(wins=1, losses=1, ties=0)
    assert _rows_by_id(variant_metric)["dragapult-dusknoir"].players == 1


def test_phase2_top_cut_and_conversion_use_source_player_flags(facts) -> None:
    phase2 = distribution(facts, ReportGrain.FAMILY, ReportPhase.PHASE2)
    top_cut = distribution(facts, ReportGrain.FAMILY, ReportPhase.TOP_CUT)
    metric = conversion(facts, ReportGrain.FAMILY)

    assert phase2.known_players == 3
    assert _rows_by_id(top_cut)["dragapult-ex"].players == 2
    assert top_cut.known_players == 2
    conversion_rows = {row.selection_id: row for row in metric.rows}
    assert metric.phase1_known_players == 4
    assert metric.phase2_known_players == 3
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


def test_phase_matchups_use_the_reconciled_boundary(facts) -> None:
    phase1 = matchups(
        facts,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.PHASE1,
    )
    phase2 = matchups(
        facts,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.PHASE2,
    )

    assert phase1.phase_available is True
    assert phase1.phase_boundary == 1
    assert phase1.rows_by_id["charizard-ex"].matches == 1
    assert phase2.phase_available is True
    assert phase2.phase_boundary == 1
    assert phase2.rows_by_id["charizard-ex"].matches == 2
    assert phase2.rows_by_id["dragapult-ex"].matches == 1


def test_phase2_matchups_exclude_only_explicit_top_cut_pairings(facts) -> None:
    target = next(
        pairing
        for pairing in facts.pairings
        if pairing.round_number > 1 and "dragapult-ex" in {
            facts.variants.get(pairing.player1_variant_id or "").family_id
            if pairing.player1_variant_id in facts.variants else None,
            facts.variants.get(pairing.player2_variant_id or "").family_id
            if pairing.player2_variant_id in facts.variants else None,
        }
        and "charizard-ex" in {pairing.player1_variant_id, pairing.player2_variant_id}
    )
    explicit_top_cut = replace(target, competition_stage="top_cut")
    changed = replace(
        facts,
        pairings=tuple(explicit_top_cut if pairing is target else pairing for pairing in facts.pairings),
    )

    metric = matchups(
        changed,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.PHASE2,
    )

    assert metric.top_cut_exclusion == "explicit"
    assert metric.rows_by_id["charizard-ex"].matches == 1


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
        ReportPhase.PHASE1,
    )
    ready = deck_composition(
        _expanded_dragapult_facts(facts, players=10, valid_lists=10),
        selection,
        ReportPhase.PHASE1,
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


def test_top_cut_composition_classifies_small_available_sample(facts) -> None:
    selection = ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex")

    metric = deck_composition(facts, selection, ReportPhase.TOP_CUT)

    assert metric.eligible_player_count == 2
    assert metric.valid_list_count == 1
    assert metric.coverage == pytest.approx(0.5)
    assert metric.eligible_for_classification is True
    assert metric.small_sample_descriptive is True
    assert metric.rows


@pytest.mark.parametrize(
    ("valid_lists", "small_sample"),
    [(1, True), (9, True), (10, False)],
)
def test_top_cut_small_sample_rule_is_fewer_than_ten_valid_lists(
    facts,
    valid_lists: int,
    small_sample: bool,
) -> None:
    metric = deck_composition(
        _expanded_dragapult_facts(facts, players=10, valid_lists=valid_lists),
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.TOP_CUT,
    )

    assert metric.eligible_for_classification is True
    assert metric.small_sample_descriptive is small_sample


def test_top_cut_population_uses_source_flag_not_final_top_eight_placement(facts) -> None:
    play_in = replace(facts.players["21"], placement=9, top_cut=True)
    excluded_finalist = replace(facts.players["11"], placement=1, top_cut=False)
    changed = replace(
        facts,
        players=MappingProxyType({
            **facts.players,
            "21": play_in,
            "11": excluded_finalist,
        }),
    )

    metric = distribution(changed, ReportGrain.FAMILY, ReportPhase.TOP_CUT)

    assert _rows_by_id(metric)["charizard-ex"].players == 1
    assert _rows_by_id(metric)["dragapult-ex"].players == 1


def test_composition_comparison_exposes_union_deltas_and_fifteen_point_tags(facts) -> None:
    selection = ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex")
    current = deck_composition(facts, selection, ReportPhase.TOP_CUT)
    previous = replace(
        current,
        phase=ReportPhase.PHASE2,
        rows=tuple(
            replace(row, appearance_rate=0.70, average_when_present=3.0)
            for row in current.rows
        ),
    )

    compared = current.compared_to(previous)

    dreepy = next(row for row in compared.rows if row.card_name == "dreepy")
    assert dreepy.appearance_rate_delta_pp == pytest.approx(30.0)
    assert dreepy.average_when_present_delta == pytest.approx(1.0)
    assert dreepy.commonality_tag == "more_common"
    assert compared.comparison_phase is ReportPhase.PHASE2


def test_representative_lists_are_deterministic(facts) -> None:
    expanded = _expanded_dragapult_facts(facts, players=5, valid_lists=5)
    rows = representative_lists(
        expanded,
        ReportSelection(grain=ReportGrain.FAMILY, selection_id="dragapult-ex"),
        ReportPhase.PHASE1,
    )

    assert [row.player_tp_id for row in rows] == ["11", "15", "14"]
    assert rows[0].cards[0].set_code == "TWM"
