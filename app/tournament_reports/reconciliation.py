from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from app.tournament_reports.contracts import (
    ModuleStatus,
    RawTournamentSnapshot,
    Record,
    ReportGrain,
    ReportPhase,
    ReportSelection,
    ReportState,
    SnapshotVerification,
)
from app.tournament_reports.facts import (
    FamilyOverrideSet,
    TournamentFacts,
    normalize_snapshot,
    resolve_phase_boundary,
)
from app.tournament_reports.metrics import matchups


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    affected_modules: frozenset[str]
    blocks_publication: bool


@dataclass(frozen=True)
class ReconciliationResult:
    phase_boundary: int | None
    issues: tuple[ValidationIssue, ...]
    variant_records: Mapping[str, Record]


PHASE_MODULES = frozenset(
    {
        "day2_conversion",
        "phase_performance",
        "matchups_day2",
        "deck_composition_day2",
    }
)
PERFORMANCE_MODULES = frozenset(
    {
        "performance",
        "headline_performance",
        "phase_performance",
        "top_finishers",
        "family_ranking",
    }
)
ALL_MODULES = frozenset({"*"})


def reconcile_tournament(facts: TournamentFacts) -> ReconciliationResult:
    issues: list[ValidationIssue] = []
    phase_boundary = resolve_phase_boundary(facts)
    variant_records = pairing_records_by_variant(facts)
    issues.extend(_check_completed_and_rounds(facts))
    issues.extend(_check_standings_records(facts))
    issues.extend(_check_variant_records(facts, variant_records))
    if phase_boundary is None:
        issues.append(
            ValidationIssue(
                code="phase_boundary_unresolved",
                message="No unique round split reproduces every source phase record.",
                affected_modules=PHASE_MODULES,
                blocks_publication=False,
            )
        )
    issues.extend(_check_matchup_references(facts))
    issues.extend(_check_family_membership(facts))
    issues.extend(_check_decklists(facts))
    return ReconciliationResult(
        phase_boundary=phase_boundary,
        issues=tuple(issues),
        variant_records=MappingProxyType(variant_records),
    )


def verify_candidate_snapshot(
    snapshot: RawTournamentSnapshot,
    overrides: FamilyOverrideSet,
) -> SnapshotVerification:
    try:
        result = reconcile_tournament(normalize_snapshot(snapshot, overrides))
    except (TypeError, ValueError):
        return SnapshotVerification(blocking_issue_codes=("source_schema_incompatible",))
    return SnapshotVerification(
        blocking_issue_codes=tuple(
            dict.fromkeys(issue.code for issue in result.issues if issue.blocks_publication)
        )
    )


def module_status(
    module_id: str,
    reconciliation: ReconciliationResult,
    *,
    sample_size: int,
    valid_lists: int | None = None,
    coverage: float | None = None,
) -> ModuleStatus:
    affecting = [
        issue
        for issue in reconciliation.issues
        if "*" in issue.affected_modules or module_id in issue.affected_modules
    ]
    if affecting:
        issue = affecting[0]
        blocked = issue.blocks_publication or issue.code in {
            "phase_boundary_unresolved",
            "missing_pairing_round",
            "source_schema_incompatible",
        }
        return status_for(
            ReportState.BLOCKED if blocked else ReportState.DEGRADED,
            issue.code,
            issue.message,
        )
    if module_id.startswith("matchups_"):
        if sample_size == 0:
            return status_for(ReportState.DEGRADED, "no_matches", "No observed matches are available.")
        if sample_size < 30:
            return status_for(
                ReportState.DEGRADED,
                "matchup_sample_below_30",
                f"Observed matchup sample is below 30 (n={sample_size}).",
            )
    if module_id.startswith("deck_composition"):
        if valid_lists is None or valid_lists < 10:
            return status_for(
                ReportState.DEGRADED,
                "decklist_count_below_10",
                f"Fewer than 10 valid decklists are available (n={valid_lists or 0}).",
            )
        if coverage is None or coverage < 0.60:
            return status_for(
                ReportState.DEGRADED,
                "decklist_coverage_below_60",
                f"Decklist coverage is below 60% ({(coverage or 0):.1%}).",
            )
    return status_for(ReportState.READY)


def status_for(
    state: ReportState,
    reason_code: str | None = None,
    message: str | None = None,
) -> ModuleStatus:
    return ModuleStatus(
        state=state,
        reason_code=reason_code,
        message=message,
        exportable=state is ReportState.READY,
    )


def pairing_records_by_player(facts: TournamentFacts) -> dict[str, Record]:
    counts = {player_id: [0, 0, 0] for player_id in facts.players}
    for pairing in facts.pairings:
        if pairing.outcome == "procedural":
            _add_procedural_loss(counts, pairing.player1_tp_id)
            _add_procedural_loss(counts, pairing.player2_tp_id)
            continue
        _add_side_record(counts, pairing.player1_tp_id, pairing.outcome, side=1)
        _add_side_record(counts, pairing.player2_tp_id, pairing.outcome, side=2)
    return {
        player_id: Record(wins=row[0], losses=row[1], ties=row[2])
        for player_id, row in counts.items()
    }


def pairing_records_by_variant(facts: TournamentFacts) -> dict[str, Record]:
    counts = {variant_id: [0, 0, 0] for variant_id in facts.variants}
    for pairing in facts.pairings:
        player1_variant = _standing_variant(facts, pairing.player1_tp_id, pairing.player1_variant_id)
        player2_variant = _standing_variant(facts, pairing.player2_tp_id, pairing.player2_variant_id)
        if pairing.outcome == "procedural":
            _add_procedural_loss(counts, player1_variant)
            _add_procedural_loss(counts, player2_variant)
            continue
        _add_side_record(counts, player1_variant, pairing.outcome, side=1)
        _add_side_record(counts, player2_variant, pairing.outcome, side=2)
    return {
        variant_id: Record(wins=row[0], losses=row[1], ties=row[2])
        for variant_id, row in counts.items()
    }


def _check_completed_and_rounds(facts: TournamentFacts) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not facts.tournament.completed:
        issues.append(
            ValidationIssue(
                code="tournament_not_completed",
                message="Tournament metadata does not mark the event completed.",
                affected_modules=ALL_MODULES,
                blocks_publication=True,
            )
        )
    expected_rounds = frozenset(range(1, facts.tournament.declared_rounds + 1))
    if facts.rounds_present != expected_rounds:
        missing = sorted(expected_rounds - facts.rounds_present)
        extra = sorted(facts.rounds_present - expected_rounds)
        issues.append(
            ValidationIssue(
                code="missing_pairing_round",
                message=f"Pairing rounds differ from metadata; missing={missing}, extra={extra}.",
                affected_modules=ALL_MODULES,
                blocks_publication=True,
            )
        )
    return issues


def _check_standings_records(facts: TournamentFacts) -> list[ValidationIssue]:
    local = pairing_records_by_player(facts)
    return [
        ValidationIssue(
            code="standing_record_mismatch",
            message=f"{player_id}: pairing record differs from standings.",
            affected_modules=PERFORMANCE_MODULES,
            blocks_publication=True,
        )
        for player_id, player in facts.players.items()
        if local[player_id] != player.source_record
    ]


def _check_variant_records(
    facts: TournamentFacts,
    local: Mapping[str, Record],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for variant_id, phase_records in facts.source_phase_records.items():
        source = _sum_records(phase_records.values())
        if local.get(variant_id, Record(wins=0, losses=0, ties=0)) != source:
            issues.append(
                ValidationIssue(
                    code="variant_record_mismatch",
                    message=f"{variant_id}: pairing record differs from source deck totals.",
                    affected_modules=PERFORMANCE_MODULES,
                    blocks_publication=True,
                )
            )
    return issues


def _check_matchup_references(facts: TournamentFacts) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for variant_id, reference in facts.matchup_references.items():
        if not isinstance(reference.payload, Mapping):
            continue
        if isinstance(reference.payload.get("decks"), list):
            local_rows, local_unknown, local_procedural = _local_matchup_reference(
                facts,
                variant_id,
                ReportPhase.OVERALL,
            )
            if (
                _reference_rows(reference.payload.get("decks"), id_key="id") != local_rows
                or _reference_record(reference.payload.get("unknown")) != local_unknown
                or _reference_record(reference.payload.get("procedural")) != local_procedural
            ):
                issues.append(
                    ValidationIssue(
                        code="matchup_reference_mismatch",
                        message=f"{variant_id}:overall: local matchups differ from source reference.",
                        affected_modules=frozenset({"matchups_overall"}),
                        blocks_publication=True,
                    )
                )
            continue
        for source_phase, report_phase, module_id in (
            ("overall", ReportPhase.OVERALL, "matchups_overall"),
            ("day2", ReportPhase.DAY2, "matchups_day2"),
        ):
            expected = reference.payload.get(source_phase)
            if not isinstance(expected, Mapping):
                continue
            local = matchups(
                facts,
                ReportSelection(grain=ReportGrain.VARIANT, selection_id=variant_id),
                report_phase,
            )
            expected_rows = _reference_rows(expected.get("rows"))
            local_rows = {
                opponent_id: row.player_side_record
                for opponent_id, row in local.rows_by_id.items()
            }
            if (
                expected_rows != local_rows
                or _optional_count(expected.get("unknown_count")) != local.unknown_count
                or _optional_count(expected.get("procedural_count")) != local.procedural_count
            ):
                issues.append(
                    ValidationIssue(
                        code="matchup_reference_mismatch",
                        message=f"{variant_id}:{source_phase}: local matchups differ from source reference.",
                        affected_modules=frozenset({module_id}),
                        blocks_publication=True,
                    )
                )
    return issues


def _check_family_membership(facts: TournamentFacts) -> list[ValidationIssue]:
    invalid = [
        variant.variant_id
        for variant in facts.variants.values()
        if not variant.family_id or not variant.family_name
    ]
    if not invalid:
        return []
    return [
        ValidationIssue(
            code="family_membership_invalid",
            message=f"Variants lack one exact family: {sorted(invalid)}.",
            affected_modules=ALL_MODULES,
            blocks_publication=True,
        )
    ]


def _check_decklists(facts: TournamentFacts) -> list[ValidationIssue]:
    if all(decklist.valid for decklist in facts.decklists.values()):
        return []
    return [
        ValidationIssue(
            code="invalid_decklist",
            message="One or more fetched decklists are structurally invalid.",
            affected_modules=frozenset(
                {
                    "deck_composition_first_phase",
                    "deck_composition_day2",
                    "deck_composition_top_cut",
                    "representative_lists",
                }
            ),
            blocks_publication=False,
        )
    ]


def _reference_rows(value: Any, *, id_key: str = "opponent_id") -> dict[str, Record]:
    if not isinstance(value, list):
        return {}
    rows: dict[str, Record] = {}
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("matchup reference row is incompatible")
        opponent_id = str(raw.get(id_key, "")).strip()
        if not opponent_id or opponent_id in rows:
            raise ValueError("matchup reference opponent is missing or duplicated")
        rows[opponent_id] = Record(
            wins=int(raw.get("wins", 0)),
            losses=int(raw.get("losses", 0)),
            ties=int(raw.get("ties", 0)),
        )
    return rows


def _reference_record(value: Any) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError("matchup reference bucket is incompatible")
    return Record(
        wins=int(value.get("wins", 0)),
        losses=int(value.get("losses", 0)),
        ties=int(value.get("ties", 0)),
    )


def _local_matchup_reference(
    facts: TournamentFacts,
    variant_id: str,
    phase: ReportPhase,
) -> tuple[dict[str, Record], Record, Record]:
    boundary = resolve_phase_boundary(facts) if phase is ReportPhase.DAY2 else None
    rows: dict[str, list[int]] = {}
    unknown = [0, 0, 0]
    procedural = [0, 0, 0]
    for pairing in facts.pairings:
        if phase is ReportPhase.DAY2 and (boundary is None or pairing.round_number <= boundary):
            continue
        for side, selected_variant, selected_player, opponent_variant, opponent_player in (
            (1, pairing.player1_variant_id, pairing.player1_tp_id, pairing.player2_variant_id, pairing.player2_tp_id),
            (2, pairing.player2_variant_id, pairing.player2_tp_id, pairing.player1_variant_id, pairing.player1_tp_id),
        ):
            if selected_variant != variant_id:
                continue
            if pairing.outcome == "procedural":
                procedural[1] += 1
                continue
            bucket = procedural if opponent_player is None else unknown if opponent_variant is None else rows.setdefault(opponent_variant, [0, 0, 0])
            _add_side_record({variant_id: bucket}, variant_id, pairing.outcome, side=side)
    return (
        {opponent_id: Record(wins=row[0], losses=row[1], ties=row[2]) for opponent_id, row in rows.items()},
        Record(wins=unknown[0], losses=unknown[1], ties=unknown[2]),
        Record(wins=procedural[0], losses=procedural[1], ties=procedural[2]),
    )


def _optional_count(value: Any) -> int:
    return int(value) if value is not None else 0


def _sum_records(records: Iterable[Record]) -> Record:
    wins = losses = ties = 0
    for record in records:
        wins += record.wins
        losses += record.losses
        ties += record.ties
    return Record(wins=wins, losses=losses, ties=ties)


def _add_side_record(
    counts: dict[str, list[int]],
    identity: str | None,
    outcome: str,
    *,
    side: int,
) -> None:
    if identity is None or identity not in counts:
        return
    if outcome == "tie":
        counts[identity][2] += 1
    elif (outcome == "player1" and side == 1) or (outcome == "player2" and side == 2):
        counts[identity][0] += 1
    else:
        counts[identity][1] += 1


def _add_procedural_loss(counts: dict[str, list[int]], identity: str | None) -> None:
    if identity is not None and identity in counts:
        counts[identity][1] += 1


def _standing_variant(
    facts: TournamentFacts,
    player_id: str | None,
    pairing_variant_id: str | None,
) -> str | None:
    if player_id is not None and player_id in facts.players:
        return facts.players[player_id].variant_id
    return pairing_variant_id
