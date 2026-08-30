from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from app.tournament_reports.contracts import (
    Record,
    ReportGrain,
    ReportPhase,
    ReportSelection,
)
from app.tournament_reports.facts import (
    CardFact,
    PairingFact,
    PlayerFact,
    TournamentFacts,
    resolve_phase_boundary,
)


@dataclass(frozen=True)
class DistributionRow:
    selection_id: str
    label: str
    players: int
    share: float
    record: Record
    observed_win_rate: float | None


@dataclass(frozen=True)
class DistributionMetric:
    grain: ReportGrain
    phase: ReportPhase
    known_players: int
    unknown_players: int
    rows: tuple[DistributionRow, ...]


@dataclass(frozen=True)
class ConversionRow:
    selection_id: str
    label: str
    first_phase_players: int
    day2_players: int
    rate: float | None


@dataclass(frozen=True)
class ConversionMetric:
    grain: ReportGrain
    first_phase_known_players: int
    day2_known_players: int
    field_rate: float | None
    rows: tuple[ConversionRow, ...]


@dataclass(frozen=True)
class MatchupRow:
    selection_id: str
    label: str
    matches: int
    player_side_record: Record
    observed_win_rate: float | None
    sample_state: Literal["ready", "insufficient", "none"]


@dataclass(frozen=True)
class MatchupMetric:
    selection: ReportSelection
    phase: ReportPhase
    phase_available: bool
    phase_boundary: int | None
    rows: tuple[MatchupRow, ...]
    rows_by_id: Mapping[str, MatchupRow]
    unknown_count: int
    procedural_count: int


@dataclass(frozen=True)
class DeckCompositionRow:
    card_name: str
    display_name: str
    appearance_rate: float
    average_when_present: float
    bucket: Literal["core", "common", "tech", "rare"]


@dataclass(frozen=True)
class DeckCompositionMetric:
    selection: ReportSelection
    phase: ReportPhase
    eligible_player_count: int
    valid_list_count: int
    coverage: float
    eligible_for_classification: bool
    rows: tuple[DeckCompositionRow, ...]


@dataclass(frozen=True)
class RepresentativeList:
    player_tp_id: str
    player_name: str
    placement: int | None
    points: int
    cards: tuple[CardFact, ...]


def win_rate(record: Record) -> float | None:
    matches = record.wins + record.losses + record.ties
    return None if matches == 0 else (record.wins + record.ties / 3) / matches


def distribution(
    facts: TournamentFacts,
    grain: ReportGrain,
    phase: ReportPhase,
) -> DistributionMetric:
    population = tuple(player for player in facts.players.values() if _player_in_phase(player, phase))
    known = [player for player in population if _player_identity(facts, player, grain) is not None]
    unknown_players = len(population) - len(known)
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for player in known:
        identity = _player_identity(facts, player, grain)
        assert identity is not None
        selection_id, label = identity
        counts[selection_id] = counts.get(selection_id, 0) + 1
        labels[selection_id] = label
    denominator = len(known)
    rows = tuple(
        DistributionRow(
            selection_id=selection_id,
            label=labels[selection_id],
            players=players,
            share=players / denominator if denominator else 0.0,
            record=_record_for_group(facts, grain, selection_id, phase),
            observed_win_rate=win_rate(_record_for_group(facts, grain, selection_id, phase)),
        )
        for selection_id, players in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )
    return DistributionMetric(
        grain=grain,
        phase=phase,
        known_players=denominator,
        unknown_players=unknown_players,
        rows=rows,
    )


def conversion(facts: TournamentFacts, grain: ReportGrain) -> ConversionMetric:
    first_phase = distribution(facts, grain, ReportPhase.FIRST_PHASE)
    day2 = distribution(facts, grain, ReportPhase.DAY2)
    first_rows = {row.selection_id: row for row in first_phase.rows}
    day2_rows = {row.selection_id: row for row in day2.rows}
    rows = tuple(
        ConversionRow(
            selection_id=selection_id,
            label=row.label,
            first_phase_players=row.players,
            day2_players=day2_rows.get(selection_id).players if selection_id in day2_rows else 0,
            rate=(day2_rows.get(selection_id).players if selection_id in day2_rows else 0) / row.players
            if row.players
            else None,
        )
        for selection_id, row in first_rows.items()
    )
    return ConversionMetric(
        grain=grain,
        first_phase_known_players=first_phase.known_players,
        day2_known_players=day2.known_players,
        field_rate=(day2.known_players / first_phase.known_players) if first_phase.known_players else None,
        rows=rows,
    )


def matchup_sample_state(matches: int) -> Literal["ready", "insufficient", "none"]:
    if matches < 0:
        raise ValueError("match count must be non-negative")
    if matches == 0:
        return "none"
    return "ready" if matches >= 30 else "insufficient"


def pairing_in_phase(
    pairing: PairingFact,
    phase: ReportPhase,
    boundary: int | None,
) -> bool:
    if phase is ReportPhase.OVERALL:
        return True
    if phase is ReportPhase.DAY2 and boundary is not None:
        return pairing.round_number > boundary
    return False


def matchups(
    facts: TournamentFacts,
    selection: ReportSelection,
    phase: ReportPhase,
) -> MatchupMetric:
    if phase not in {ReportPhase.OVERALL, ReportPhase.DAY2}:
        raise ValueError("matchups support only overall and day2 phases")
    boundary = resolve_phase_boundary(facts) if phase is ReportPhase.DAY2 else None
    phase_available = phase is ReportPhase.OVERALL or boundary is not None
    accumulators: dict[str, list[int]] = {}
    labels: dict[str, str] = {}
    unknown_count = 0
    procedural_count = 0
    if phase_available:
        for pairing in facts.pairings:
            if not pairing_in_phase(pairing, phase, boundary):
                continue
            player1_identity = _variant_identity(facts, pairing.player1_variant_id, selection.grain)
            player2_identity = _variant_identity(facts, pairing.player2_variant_id, selection.grain)
            player1_selected = player1_identity is not None and player1_identity[0] == selection.selection_id
            player2_selected = player2_identity is not None and player2_identity[0] == selection.selection_id
            if not player1_selected and not player2_selected:
                continue
            selected_sides = int(player1_selected) + int(player2_selected)
            missing_selected_opponent = (
                player1_selected and pairing.player2_tp_id is None
            ) or (
                player2_selected and pairing.player1_tp_id is None
            )
            if pairing.outcome == "procedural" or missing_selected_opponent:
                procedural_count += selected_sides
                continue
            if player1_selected and player2_selected:
                opponent_id = selection.selection_id
                labels[opponent_id] = player1_identity[1]
                row = accumulators.setdefault(opponent_id, [0, 0, 0, 0])
                row[0] += 1
                _add_player_side_result(row, pairing.outcome, side=1)
                _add_player_side_result(row, pairing.outcome, side=2)
                continue
            selected_side = 1 if player1_selected else 2
            opponent = player2_identity if selected_side == 1 else player1_identity
            if opponent is None:
                unknown_count += 1
                continue
            opponent_id, opponent_label = opponent
            labels[opponent_id] = opponent_label
            row = accumulators.setdefault(opponent_id, [0, 0, 0, 0])
            row[0] += 1
            _add_player_side_result(row, pairing.outcome, side=selected_side)
    rows = tuple(
        MatchupRow(
            selection_id=selection_id,
            label=labels[selection_id],
            matches=values[0],
            player_side_record=Record(wins=values[1], losses=values[2], ties=values[3]),
            observed_win_rate=win_rate(Record(wins=values[1], losses=values[2], ties=values[3])),
            sample_state=matchup_sample_state(values[0]),
        )
        for selection_id, values in sorted(accumulators.items(), key=lambda item: (-item[1][0], item[0]))
    )
    return MatchupMetric(
        selection=selection,
        phase=phase,
        phase_available=phase_available,
        phase_boundary=boundary,
        rows=rows,
        rows_by_id=MappingProxyType({row.selection_id: row for row in rows}),
        unknown_count=unknown_count,
        procedural_count=procedural_count,
    )


def composition_bucket(
    appearance_rate: float,
) -> Literal["core", "common", "tech", "rare"]:
    if not 0 <= appearance_rate <= 1:
        raise ValueError("appearance rate must be between zero and one")
    if appearance_rate >= 0.80:
        return "core"
    if appearance_rate >= 0.30:
        return "common"
    if appearance_rate >= 0.05:
        return "tech"
    return "rare"


def deck_composition(
    facts: TournamentFacts,
    selection: ReportSelection,
    phase: ReportPhase,
) -> DeckCompositionMetric:
    if phase not in {ReportPhase.FIRST_PHASE, ReportPhase.DAY2, ReportPhase.TOP_CUT}:
        raise ValueError("deck composition supports first_phase, day2, and top_cut")
    eligible_players = [
        player
        for player in facts.players.values()
        if _player_in_phase(player, phase) and _player_matches_selection(facts, player, selection)
    ]
    valid_lists = [
        facts.decklists[player.tp_id]
        for player in eligible_players
        if player.tp_id in facts.decklists and facts.decklists[player.tp_id].valid
    ]
    eligible_player_count = len(eligible_players)
    valid_list_count = len(valid_lists)
    coverage = valid_list_count / eligible_player_count if eligible_player_count else 0.0
    eligible_for_classification = valid_list_count >= 10 and coverage >= 0.60
    rows: tuple[DeckCompositionRow, ...] = ()
    if eligible_for_classification:
        appearances: dict[str, int] = {}
        totals: dict[str, int] = {}
        display_names: dict[str, str] = {}
        for decklist in valid_lists:
            deck_counts: dict[str, int] = {}
            for card in decklist.cards:
                deck_counts[card.card_name] = deck_counts.get(card.card_name, 0) + card.count
                display_names.setdefault(card.card_name, card.display_name)
            for card_name, count in deck_counts.items():
                appearances[card_name] = appearances.get(card_name, 0) + 1
                totals[card_name] = totals.get(card_name, 0) + count
        unsorted_rows = [
            DeckCompositionRow(
                card_name=card_name,
                display_name=display_names[card_name],
                appearance_rate=appearances[card_name] / valid_list_count,
                average_when_present=totals[card_name] / appearances[card_name],
                bucket=composition_bucket(appearances[card_name] / valid_list_count),
            )
            for card_name in appearances
        ]
        bucket_order = {"core": 0, "common": 1, "tech": 2, "rare": 3}
        rows = tuple(
            sorted(
                unsorted_rows,
                key=lambda row: (
                    bucket_order[row.bucket],
                    -row.appearance_rate,
                    -row.average_when_present,
                    row.card_name,
                ),
            )
        )
    return DeckCompositionMetric(
        selection=selection,
        phase=phase,
        eligible_player_count=eligible_player_count,
        valid_list_count=valid_list_count,
        coverage=coverage,
        eligible_for_classification=eligible_for_classification,
        rows=rows,
    )


def representative_lists(
    facts: TournamentFacts,
    selection: ReportSelection,
    phase: ReportPhase,
    limit: int = 3,
) -> tuple[RepresentativeList, ...]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    players = [
        player
        for player in facts.players.values()
        if _player_in_phase(player, phase)
        and _player_matches_selection(facts, player, selection)
        and player.tp_id in facts.decklists
        and facts.decklists[player.tp_id].valid
    ]
    players.sort(
        key=lambda player: (
            player.placement if player.placement is not None else 10**9,
            -player.points,
            player.tp_id,
        )
    )
    return tuple(
        RepresentativeList(
            player_tp_id=player.tp_id,
            player_name=player.name,
            placement=player.placement,
            points=player.points,
            cards=facts.decklists[player.tp_id].cards,
        )
        for player in players[:limit]
    )


def selection_record(
    facts: TournamentFacts,
    selection: ReportSelection,
    phase: ReportPhase,
) -> Record:
    return _record_for_group(facts, selection.grain, selection.selection_id, phase)


def _record_for_group(
    facts: TournamentFacts,
    grain: ReportGrain,
    selection_id: str,
    phase: ReportPhase,
) -> Record:
    if phase is ReportPhase.TOP_CUT:
        return _sum_records(
            player.source_record
            for player in facts.players.values()
            if player.top_cut and _player_identity_id(facts, player, grain) == selection_id
        )
    phase_numbers = (1,) if phase is ReportPhase.DAY1 else (2,) if phase is ReportPhase.DAY2 else (1, 2)
    records = []
    for variant_id, phase_records in facts.source_phase_records.items():
        identity = _variant_identity(facts, variant_id, grain)
        if identity is not None and identity[0] == selection_id:
            records.extend(phase_records[phase_number] for phase_number in phase_numbers)
    return _sum_records(records)


def _sum_records(records) -> Record:
    wins = losses = ties = 0
    for record in records:
        wins += record.wins
        losses += record.losses
        ties += record.ties
    return Record(wins=wins, losses=losses, ties=ties)


def _player_in_phase(player: PlayerFact, phase: ReportPhase) -> bool:
    if phase is ReportPhase.DAY2:
        return player.day2
    if phase is ReportPhase.TOP_CUT:
        return player.top_cut
    return True


def _player_identity(
    facts: TournamentFacts,
    player: PlayerFact,
    grain: ReportGrain,
) -> tuple[str, str] | None:
    return _variant_identity(facts, player.variant_id, grain)


def _player_identity_id(
    facts: TournamentFacts,
    player: PlayerFact,
    grain: ReportGrain,
) -> str | None:
    identity = _player_identity(facts, player, grain)
    return identity[0] if identity is not None else None


def _variant_identity(
    facts: TournamentFacts,
    variant_id: str | None,
    grain: ReportGrain,
) -> tuple[str, str] | None:
    variant = facts.variants.get(variant_id or "")
    if variant is None:
        return None
    if grain is ReportGrain.VARIANT:
        return variant.variant_id, variant.variant_name
    return variant.family_id, variant.family_name


def _player_matches_selection(
    facts: TournamentFacts,
    player: PlayerFact,
    selection: ReportSelection,
) -> bool:
    identity = _player_identity(facts, player, selection.grain)
    return identity is not None and identity[0] == selection.selection_id


def _add_player_side_result(row: list[int], outcome: str, *, side: int) -> None:
    if outcome == "tie":
        row[3] += 1
    elif (outcome == "player1" and side == 1) or (outcome == "player2" and side == 2):
        row[1] += 1
    else:
        row[2] += 1
