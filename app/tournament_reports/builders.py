from __future__ import annotations

from dataclasses import asdict

from app.tournament_reports.contracts import (
    ArchetypeReportResponse,
    EventIdentity,
    EventOverviewResponse,
    Record,
    ReportGrain,
    ReportModule,
    ReportPhase,
    ReportSelection,
    ReportSelectionOption,
    ReportState,
)
from app.tournament_reports.facts import PlayerFact, TournamentFacts
from app.tournament_reports.metrics import (
    DeckCompositionMetric,
    DistributionMetric,
    MatchupMetric,
    conversion,
    deck_composition,
    distribution,
    matchups,
    representative_lists,
    selection_record,
    win_rate,
)
from app.tournament_reports.reconciliation import (
    ReconciliationResult,
    module_status,
    status_for,
)


class ReportEligibilityError(ValueError):
    def __init__(self, reason_code: str, sample_size: int, message: str) -> None:
        self.reason_code = reason_code
        self.sample_size = sample_size
        super().__init__(message)


def build_event_overview(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    dataset_id: str,
) -> EventOverviewResponse:
    first_phase = distribution(facts, ReportGrain.FAMILY, ReportPhase.FIRST_PHASE)
    second_phase = distribution(facts, ReportGrain.FAMILY, ReportPhase.DAY2)
    modules = [
        _event_identity_module(facts, reconciliation),
        _meta_share_module(
            facts,
            reconciliation,
            first_phase,
            module_id="phase1_meta_share",
            title="Phase 1 Meta Share Top 10",
        ),
        _meta_share_module(
            facts,
            reconciliation,
            second_phase,
            module_id="phase2_meta_share",
            title="Phase 2 Meta Share Top 10",
        ),
        _family_ranking_module(facts, reconciliation, first_phase),
    ]
    return EventOverviewResponse(
        dataset_id=dataset_id,
        event=_event_identity(facts),
        snapshot_version=facts.provenance.snapshot_version,
        families=_family_options(first_phase, limit=10),
        modules=modules,
    )


def build_archetype_report(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    dataset_id: str,
    selection: ReportSelection,
) -> ArchetypeReportResponse:
    family_id = _require_eligible_selection(facts, selection)
    variants = _variant_options(facts, family_id)
    overall_matchups = matchups(facts, selection, ReportPhase.OVERALL)
    day2_matchups = matchups(facts, selection, ReportPhase.DAY2)
    first_composition = deck_composition(facts, selection, ReportPhase.FIRST_PHASE)
    day2_composition = deck_composition(facts, selection, ReportPhase.DAY2)
    top_cut_composition = deck_composition(facts, selection, ReportPhase.TOP_CUT)
    modules = [
        _headline_module(facts, reconciliation, selection),
        _phase_performance_module(facts, reconciliation, selection),
        _top_finishers_module(facts, reconciliation, selection),
        _matchup_module(facts, reconciliation, overall_matchups),
        _matchup_module(facts, reconciliation, day2_matchups),
        _composition_module(facts, reconciliation, first_composition),
        _composition_module(facts, reconciliation, day2_composition),
        _composition_module(facts, reconciliation, top_cut_composition),
        _representative_lists_module(facts, reconciliation, selection),
    ]
    return ArchetypeReportResponse(
        dataset_id=dataset_id,
        event=_event_identity(facts),
        selection=selection,
        variants=variants,
        snapshot_version=facts.provenance.snapshot_version,
        modules=modules,
    )


def _event_identity(facts: TournamentFacts) -> EventIdentity:
    return EventIdentity(
        tournament_id=facts.tournament.tournament_id,
        name=facts.tournament.name,
        date=facts.tournament.date,
        division=facts.tournament.division,
    )


def _event_identity_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
) -> ReportModule:
    sample_size = len(facts.players)
    return ReportModule(
        module_id="event_identity",
        title="Event overview",
        status=module_status("event_identity", reconciliation, sample_size=sample_size),
        phase=ReportPhase.OVERALL,
        sample_size=sample_size,
        metric_notes=["Completed-event identity and verified local snapshot."],
        provenance=facts.provenance,
        data=_event_identity(facts).model_dump(mode="json"),
    )


def _meta_share_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    metric: DistributionMetric,
    *,
    module_id: str,
    title: str,
) -> ReportModule:
    return ReportModule(
        module_id=module_id,
        title=title,
        status=module_status(
            module_id,
            reconciliation,
            sample_size=metric.known_players,
        ),
        grain=ReportGrain.FAMILY,
        phase=metric.phase,
        sample_size=metric.known_players,
        metric_notes=[
            "Families are ranked independently for this phase before the Top 10 is selected.",
            "Family and variant shares use all players with a known archetype in this phase as the denominator.",
        ],
        provenance=facts.provenance,
        data={
            "rows": _family_distribution_rows(facts, metric, limit=10),
            "known_players": metric.known_players,
            "unknown_players": metric.unknown_players,
        },
    )


def _family_ranking_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    metric: DistributionMetric,
) -> ReportModule:
    return ReportModule(
        module_id="family_ranking",
        title="Archetype family ranking",
        status=module_status(
            "family_ranking",
            reconciliation,
            sample_size=metric.known_players,
        ),
        grain=ReportGrain.FAMILY,
        phase=ReportPhase.OVERALL,
        sample_size=metric.known_players,
        metric_notes=["Observed win rate weights each tie as one-third of a win."],
        provenance=facts.provenance,
        data={"rows": _family_distribution_rows(facts, metric, include_performance=True)},
    )


def _family_distribution_rows(
    facts: TournamentFacts,
    metric: DistributionMetric,
    *,
    limit: int | None = None,
    include_performance: bool = False,
) -> list[dict]:
    variant_metric = distribution(facts, ReportGrain.VARIANT, metric.phase)
    first_phase_variants = distribution(facts, ReportGrain.VARIANT, ReportPhase.FIRST_PHASE)
    first_phase_families = distribution(facts, ReportGrain.FAMILY, ReportPhase.FIRST_PHASE)
    first_phase_counts = {row.selection_id: row.players for row in first_phase_variants.rows}
    eligible_family_ids = {row.selection_id for row in first_phase_families.rows[:10]}
    variants_by_family: dict[str, list[dict]] = {}
    for row in variant_metric.rows:
        variant = facts.variants[row.selection_id]
        variants_by_family.setdefault(variant.family_id, []).append(
            {
                "variant_id": row.selection_id,
                "variant_name": row.label,
                "players": row.players,
                "share": row.share,
                "report_eligible": first_phase_counts.get(row.selection_id, 0) >= 10,
            }
        )

    rows = []
    selected_rows = metric.rows if limit is None else metric.rows[:limit]
    for row in selected_rows:
        variants = variants_by_family.get(row.selection_id, [])
        family_row = {
            "family_id": row.selection_id,
            "family_name": row.label,
            "players": sum(variant["players"] for variant in variants),
            "share": sum(variant["share"] for variant in variants),
            "report_eligible": row.selection_id in eligible_family_ids,
            "variants": variants,
        }
        if include_performance:
            family_row.update(
                {
                    "record": _record_data(row.record),
                    "observed_win_rate": row.observed_win_rate,
                }
            )
        rows.append(family_row)
    return rows


def _family_options(metric: DistributionMetric, *, limit: int) -> list[ReportSelectionOption]:
    return [
        ReportSelectionOption(
            selection_id=row.selection_id,
            label=row.label,
            first_phase_players=row.players,
            eligible=index < limit,
            reason_code=None if index < limit else "outside_top_10_families",
        )
        for index, row in enumerate(metric.rows)
    ]


def _variant_options(
    facts: TournamentFacts,
    family_id: str,
) -> list[ReportSelectionOption]:
    metric = distribution(facts, ReportGrain.VARIANT, ReportPhase.FIRST_PHASE)
    rows = [row for row in metric.rows if facts.variants[row.selection_id].family_id == family_id]
    return [
        ReportSelectionOption(
            selection_id=row.selection_id,
            label=row.label,
            first_phase_players=row.players,
            eligible=row.players >= 10,
            reason_code=None if row.players >= 10 else "variant_players_below_10",
        )
        for row in rows
    ]


def _require_eligible_selection(
    facts: TournamentFacts,
    selection: ReportSelection,
) -> str:
    if selection.grain is ReportGrain.FAMILY:
        family_metric = distribution(facts, ReportGrain.FAMILY, ReportPhase.FIRST_PHASE)
        options = _family_options(family_metric, limit=10)
        option = next((row for row in options if row.selection_id == selection.selection_id), None)
        if option is None:
            raise KeyError(selection.selection_id)
        if not option.eligible:
            raise ReportEligibilityError(
                option.reason_code or "outside_top_10_families",
                option.first_phase_players,
                "Family is outside the event Top 10.",
            )
        return selection.selection_id
    variant = facts.variants.get(selection.selection_id)
    if variant is None:
        raise KeyError(selection.selection_id)
    count = sum(1 for player in facts.players.values() if player.variant_id == selection.selection_id)
    if count < 10:
        raise ReportEligibilityError(
            "variant_players_below_10",
            count,
            "Variant has fewer than 10 First Phase players.",
        )
    return variant.family_id


def _headline_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    selection: ReportSelection,
) -> ReportModule:
    population = _selection_population(facts, selection, ReportPhase.FIRST_PHASE)
    record = selection_record(facts, selection, ReportPhase.OVERALL)
    return _selection_module(
        facts,
        reconciliation,
        selection,
        module_id="headline_performance",
        title="Headline performance",
        phase=ReportPhase.OVERALL,
        sample_size=len(population),
        metric_notes=["Observed win rate weights each tie as one-third of a win."],
        data={
            "players": len(population),
            "record": _record_data(record),
            "observed_win_rate": win_rate(record),
        },
    )


def _phase_performance_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    selection: ReportSelection,
) -> ReportModule:
    day1_record = selection_record(facts, selection, ReportPhase.DAY1)
    day2_record = selection_record(facts, selection, ReportPhase.DAY2)
    conversion_metric = conversion(facts, selection.grain)
    selected_conversion = next(
        (row for row in conversion_metric.rows if row.selection_id == selection.selection_id),
        None,
    )
    return _selection_module(
        facts,
        reconciliation,
        selection,
        module_id="phase_performance",
        title="Phase performance",
        phase=ReportPhase.DAY2,
        sample_size=selected_conversion.first_phase_players if selected_conversion else 0,
        metric_notes=["Day 1 and Day 2 records use the reconciled unique phase boundary."],
        data={
            "day1": {
                "record": _record_data(day1_record),
                "observed_win_rate": win_rate(day1_record),
            },
            "day2": {
                "record": _record_data(day2_record),
                "observed_win_rate": win_rate(day2_record),
            },
            "conversion": asdict(selected_conversion) if selected_conversion else None,
        },
    )


def _top_finishers_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    selection: ReportSelection,
) -> ReportModule:
    players = sorted(
        _selection_population(facts, selection, ReportPhase.FIRST_PHASE),
        key=lambda player: (
            player.placement if player.placement is not None else 10**9,
            -player.points,
            player.tp_id,
        ),
    )[:8]
    return _selection_module(
        facts,
        reconciliation,
        selection,
        module_id="top_finishers",
        title="Top finishers",
        phase=ReportPhase.OVERALL,
        sample_size=len(players),
        metric_notes=["Finishers are ordered by placement, points, then player ID."],
        data={
            "rows": [
                {
                    "player_tp_id": player.tp_id,
                    "player_name": player.name,
                    "placement": player.placement,
                    "points": player.points,
                    "record": _record_data(player.source_record),
                }
                for player in players
            ]
        },
    )


def _matchup_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    metric: MatchupMetric,
) -> ReportModule:
    module_id = f"matchups_{metric.phase.value}"
    sample_size = sum(row.matches for row in metric.rows)
    status = module_status(module_id, reconciliation, sample_size=sample_size)
    if not metric.phase_available:
        status = status_for(
            ReportState.BLOCKED,
            "phase_boundary_unresolved",
            "Day 2 matchup boundary could not be resolved.",
        )
    return ReportModule(
        module_id=module_id,
        title="Observed matchups" if metric.phase is ReportPhase.OVERALL else "Observed Day 2 matchups",
        status=status,
        grain=metric.selection.grain,
        phase=metric.phase,
        selection_id=metric.selection.selection_id,
        sample_size=sample_size,
        metric_notes=[
            "Bars require at least 30 unique known-opponent matches.",
            "Unknown opponents and procedural results are excluded and disclosed separately.",
        ],
        provenance=facts.provenance,
        data={
            "rows": [
                {
                    "opponent_id": row.selection_id,
                    "opponent_name": row.label,
                    "matches": row.matches,
                    "record": _record_data(row.player_side_record),
                    "observed_win_rate": row.observed_win_rate,
                    "sample_state": row.sample_state,
                }
                for row in metric.rows
            ],
            "unknown_count": metric.unknown_count,
            "procedural_count": metric.procedural_count,
            "phase_boundary": metric.phase_boundary,
        },
    )


def _composition_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    metric: DeckCompositionMetric,
) -> ReportModule:
    module_id = f"deck_composition_{metric.phase.value}"
    return ReportModule(
        module_id=module_id,
        title=f"Deck composition — {metric.phase.value.replace('_', ' ').title()}",
        status=module_status(
            module_id,
            reconciliation,
            sample_size=metric.eligible_player_count,
            valid_lists=metric.valid_list_count,
            coverage=metric.coverage,
        ),
        grain=metric.selection.grain,
        phase=metric.phase,
        selection_id=metric.selection.selection_id,
        sample_size=metric.valid_list_count,
        metric_notes=[
            "Classification requires at least 10 valid lists and 60% coverage.",
            "Core ≥80%; Common 30–<80%; Tech 5–<30%; Rare/Other <5%.",
        ],
        provenance=facts.provenance,
        data={
            "eligible_players": metric.eligible_player_count,
            "valid_lists": metric.valid_list_count,
            "coverage": metric.coverage,
            "eligible_for_classification": metric.eligible_for_classification,
            "rows": [asdict(row) for row in metric.rows],
        },
    )


def _representative_lists_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    selection: ReportSelection,
) -> ReportModule:
    rows = representative_lists(facts, selection, ReportPhase.FIRST_PHASE)
    return _selection_module(
        facts,
        reconciliation,
        selection,
        module_id="representative_lists",
        title="Representative top lists",
        phase=ReportPhase.FIRST_PHASE,
        sample_size=len(rows),
        metric_notes=["At most three valid lists, ordered deterministically by finish."],
        data={
            "rows": [
                {
                    "player_tp_id": row.player_tp_id,
                    "player_name": row.player_name,
                    "placement": row.placement,
                    "points": row.points,
                    "cards": [asdict(card) for card in row.cards],
                }
                for row in rows
            ]
        },
    )


def _selection_module(
    facts: TournamentFacts,
    reconciliation: ReconciliationResult,
    selection: ReportSelection,
    *,
    module_id: str,
    title: str,
    phase: ReportPhase,
    sample_size: int,
    metric_notes: list[str],
    data: dict,
) -> ReportModule:
    return ReportModule(
        module_id=module_id,
        title=title,
        status=module_status(module_id, reconciliation, sample_size=sample_size),
        grain=selection.grain,
        phase=phase,
        selection_id=selection.selection_id,
        sample_size=sample_size,
        metric_notes=metric_notes,
        provenance=facts.provenance,
        data=data,
    )


def _selection_population(
    facts: TournamentFacts,
    selection: ReportSelection,
    phase: ReportPhase,
) -> list[PlayerFact]:
    players = []
    for player in facts.players.values():
        if phase is ReportPhase.DAY2 and not player.day2:
            continue
        if phase is ReportPhase.TOP_CUT and not player.top_cut:
            continue
        variant = facts.variants.get(player.variant_id or "")
        if variant is None:
            continue
        identity = variant.variant_id if selection.grain is ReportGrain.VARIANT else variant.family_id
        if identity == selection.selection_id:
            players.append(player)
    return players


def _distribution_rows(metric: DistributionMetric, identity_key: str) -> list[dict]:
    label_key = "family_name" if identity_key == "family_id" else "variant_name"
    return [
        {
            identity_key: row.selection_id,
            label_key: row.label,
            "players": row.players,
            "share": row.share,
            "record": _record_data(row.record),
            "observed_win_rate": row.observed_win_rate,
        }
        for row in metric.rows
    ]


def _record_data(record: Record) -> dict[str, int]:
    return record.model_dump(mode="json")
