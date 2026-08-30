from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from app.tournament_reports.contracts import RawTournamentSnapshot, Record, SourceProvenance


@dataclass(frozen=True)
class FamilyIdentity:
    family_id: str
    family_name: str


@dataclass(frozen=True)
class FamilyOverrideSet:
    version: int
    mappings: Mapping[tuple[str, str], FamilyIdentity]


@dataclass(frozen=True)
class TournamentFact:
    tournament_id: str
    division: str
    name: str
    date: str
    completed: bool
    declared_rounds: int


@dataclass(frozen=True)
class VariantFact:
    variant_id: str
    variant_name: str
    family_id: str
    family_name: str


@dataclass(frozen=True)
class PlayerFact:
    tp_id: str
    name: str
    variant_id: str | None
    family_id: str | None
    placement: int | None
    points: int
    day2: bool
    top_cut: bool
    decklist_available: bool
    source_record: Record


@dataclass(frozen=True)
class PairingFact:
    pairing_id: str
    round_number: int
    table_number: int
    player1_tp_id: str | None
    player2_tp_id: str | None
    player1_variant_id: str | None
    player2_variant_id: str | None
    outcome: Literal["player1", "player2", "tie", "procedural"]


@dataclass(frozen=True)
class CardFact:
    card_name: str
    display_name: str
    set_code: str
    collector_number: str
    count: int
    category: Literal["pokemon", "trainer", "energy"]


@dataclass(frozen=True)
class DecklistFact:
    player_tp_id: str
    cards: tuple[CardFact, ...]
    valid: bool


@dataclass(frozen=True)
class MatchupReference:
    variant_id: str
    payload: Mapping[str, Any] | tuple[Any, ...]


@dataclass(frozen=True)
class TournamentFacts:
    tournament: TournamentFact
    variants: Mapping[str, VariantFact]
    players: Mapping[str, PlayerFact]
    pairings: tuple[PairingFact, ...]
    decklists: Mapping[str, DecklistFact]
    matchup_references: Mapping[str, MatchupReference]
    source_phase_records: Mapping[str, Mapping[int, Record]]
    provenance: SourceProvenance


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_family_overrides(path: Path) -> FamilyOverrideSet:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid family override file: {path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("version"), int) or raw["version"] < 1:
        raise ValueError("family override version must be a positive integer")
    raw_mappings = raw.get("mappings")
    if not isinstance(raw_mappings, dict):
        raise ValueError("family override mappings must be an object")
    mappings: dict[tuple[str, str], FamilyIdentity] = {}
    for exact_key, value in raw_mappings.items():
        if not isinstance(exact_key, str) or exact_key.count(":") != 1:
            raise ValueError("family override key must be tournament_id:variant_id")
        tournament_id, variant_id = (part.strip() for part in exact_key.split(":", 1))
        if not tournament_id or not variant_id or not isinstance(value, dict):
            raise ValueError("family override key and value must be non-empty")
        family_id = str(value.get("family_id", "")).strip()
        family_name = str(value.get("family_name", "")).strip()
        if not family_id or not family_name:
            raise ValueError("family override identity must be non-empty")
        identity_key = (tournament_id, variant_id)
        if identity_key in mappings:
            raise ValueError(f"duplicate family mapping: {exact_key}")
        mappings[identity_key] = FamilyIdentity(family_id=family_id, family_name=family_name)
    return FamilyOverrideSet(version=raw["version"], mappings=MappingProxyType(mappings))


def family_for(
    tournament_id: str,
    raw_variant: dict[str, Any],
    overrides: FamilyOverrideSet,
) -> FamilyIdentity:
    variant_id = _required_text(raw_variant.get("identifier"), "variant identifier")
    source = FamilyIdentity(
        family_id=_required_text(raw_variant.get("sup_identifier"), "source family identifier"),
        family_name=_required_text(raw_variant.get("sup_name"), "source family name"),
    )
    return overrides.mappings.get((tournament_id, variant_id), source)


def canonical_card_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def normalize_snapshot(
    snapshot: RawTournamentSnapshot,
    overrides: FamilyOverrideSet,
) -> TournamentFacts:
    manifest = snapshot.manifest
    tournament = TournamentFact(
        tournament_id=manifest.tournament_id,
        division=manifest.division,
        name=str(snapshot.tournament.get("name") or snapshot.tournament.get("city") or manifest.tournament_id).strip(),
        date=str(snapshot.tournament.get("date", "")).strip(),
        completed=_as_bool(snapshot.tournament.get("completed", False)),
        declared_rounds=manifest.declared_rounds,
    )

    variants: dict[str, VariantFact] = {}
    source_phase_records: dict[str, Mapping[int, Record]] = {}
    for raw_variant in snapshot.decks:
        variant_id = _required_text(raw_variant.get("identifier"), "variant identifier")
        if variant_id in variants:
            raise ValueError(f"duplicate variant: {variant_id}")
        family = family_for(manifest.tournament_id, raw_variant, overrides)
        variants[variant_id] = VariantFact(
            variant_id=variant_id,
            variant_name=_required_text(raw_variant.get("name"), "variant name"),
            family_id=family.family_id,
            family_name=family.family_name,
        )
        source_phase_records[variant_id] = MappingProxyType(_parse_phase_records(raw_variant.get("records")))

    players: dict[str, PlayerFact] = {}
    for raw_player in snapshot.standings:
        tp_id = _required_text(raw_player.get("tp_id"), "player tp_id")
        if tp_id in players:
            raise ValueError(f"duplicate player: {tp_id}")
        variant_id = _optional_text(raw_player.get("deck_id"))
        variant = variants.get(variant_id) if variant_id else None
        players[tp_id] = PlayerFact(
            tp_id=tp_id,
            name=str(raw_player.get("name", "")).strip(),
            variant_id=variant_id,
            family_id=variant.family_id if variant else None,
            placement=_optional_int(raw_player.get("placement")),
            points=_int_or_zero(raw_player.get("points")),
            day2=_as_bool(raw_player.get("day2", False)),
            top_cut=_as_bool(raw_player.get("topcut", False)),
            decklist_available=_as_bool(raw_player.get("decklist", False)),
            source_record=Record(
                wins=_int_or_zero(raw_player.get("wins")),
                losses=_int_or_zero(raw_player.get("losses")),
                ties=_int_or_zero(raw_player.get("ties")),
            ),
        )

    pairings: list[PairingFact] = []
    identities: set[tuple[int, int]] = set()
    for round_number, raw_pairings in sorted(snapshot.pairings.items()):
        for raw_pairing in raw_pairings:
            table_number = _required_int(raw_pairing.get("table"), "pairing table")
            identity = (round_number, table_number)
            if identity in identities:
                raise ValueError(f"duplicate pairing: round {round_number} table {table_number}")
            identities.add(identity)
            player1_tp_id, player1_variant_id = _participant(raw_pairing, "player1", players)
            player2_tp_id, player2_variant_id = _participant(raw_pairing, "player2", players)
            outcome = _pairing_outcome(raw_pairing.get("winner"), player1_tp_id, player2_tp_id)
            pairings.append(
                PairingFact(
                    pairing_id=f"round-{round_number:02d}-table-{table_number}",
                    round_number=round_number,
                    table_number=table_number,
                    player1_tp_id=player1_tp_id,
                    player2_tp_id=player2_tp_id,
                    player1_variant_id=player1_variant_id,
                    player2_variant_id=player2_variant_id,
                    outcome=outcome,
                )
            )

    decklists = {
        player_id: _normalize_decklist(player_id, payload)
        for player_id, payload in snapshot.decklists.items()
    }
    matchup_references = {
        variant_id: MatchupReference(
            variant_id=variant_id,
            payload=MappingProxyType(payload) if isinstance(payload, dict) else tuple(payload),
        )
        for variant_id, payload in snapshot.matchup_references.items()
    }
    provenance = SourceProvenance(
        source_provider=manifest.source_provider,
        tournament_id=manifest.tournament_id,
        division=manifest.division,
        source_updated_at=manifest.source_updated_at,
        fetched_at=manifest.fetched_at,
        snapshot_version=manifest.snapshot_version,
        schema_version=manifest.schema_version,
    )
    return TournamentFacts(
        tournament=tournament,
        variants=MappingProxyType(variants),
        players=MappingProxyType(players),
        pairings=tuple(pairings),
        decklists=MappingProxyType(decklists),
        matchup_references=MappingProxyType(matchup_references),
        source_phase_records=MappingProxyType(source_phase_records),
        provenance=provenance,
    )


def resolve_phase_boundary(facts: TournamentFacts) -> int | None:
    matches = [
        split
        for split in range(1, facts.tournament.declared_rounds)
        if _phase_records_for_split(facts, split) == facts.source_phase_records
    ]
    return matches[0] if len(matches) == 1 else None


def _phase_records_for_split(
    facts: TournamentFacts,
    split: int,
) -> dict[str, dict[int, Record]]:
    counts = {
        variant_id: {
            1: [0, 0, 0],
            2: [0, 0, 0],
        }
        for variant_id in facts.variants
    }
    for pairing in facts.pairings:
        if pairing.outcome == "procedural":
            continue
        phase = 1 if pairing.round_number <= split else 2
        player1 = counts.get(pairing.player1_variant_id or "")
        player2 = counts.get(pairing.player2_variant_id or "")
        if pairing.outcome == "tie":
            if player1 is not None:
                player1[phase][2] += 1
            if player2 is not None:
                player2[phase][2] += 1
        elif pairing.outcome == "player1":
            if player1 is not None:
                player1[phase][0] += 1
            if player2 is not None:
                player2[phase][1] += 1
        else:
            if player1 is not None:
                player1[phase][1] += 1
            if player2 is not None:
                player2[phase][0] += 1
    return {
        variant_id: {
            phase: Record(wins=row[0], losses=row[1], ties=row[2])
            for phase, row in phase_counts.items()
        }
        for variant_id, phase_counts in counts.items()
    }


def _parse_phase_records(value: Any) -> dict[int, Record]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("variant phase records are malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("variant phase records must be an object")
    result: dict[int, Record] = {}
    for phase in (1, 2):
        raw_record = value.get(str(phase), value.get(phase))
        if not isinstance(raw_record, dict):
            raise ValueError(f"variant phase record {phase} is missing")
        result[phase] = Record(
            wins=_nonnegative_int(raw_record.get("wins"), "record wins"),
            losses=_nonnegative_int(raw_record.get("losses"), "record losses"),
            ties=_nonnegative_int(raw_record.get("ties"), "record ties"),
        )
    return result


def _participant(
    raw_pairing: dict[str, Any],
    side: Literal["player1", "player2"],
    players: Mapping[str, PlayerFact],
) -> tuple[str | None, str | None]:
    raw = raw_pairing.get(side)
    if raw is None:
        tp_id = _optional_text(raw_pairing.get(f"{side}_tp_id"))
        return tp_id, players.get(tp_id).variant_id if tp_id in players else None
    if not isinstance(raw, dict):
        tp_id = _optional_text(raw)
        return tp_id, players.get(tp_id).variant_id if tp_id in players else None
    tp_id = _optional_text(raw.get("tp_id", raw.get("player_id", raw.get("id"))))
    variant_id = _optional_text(raw.get("deck_id"))
    if variant_id is None and tp_id in players:
        variant_id = players[tp_id].variant_id
    return tp_id, variant_id


def _pairing_outcome(
    winner: Any,
    player1_tp_id: str | None,
    player2_tp_id: str | None,
) -> Literal["player1", "player2", "tie", "procedural"]:
    normalized = _optional_text(winner)
    if normalized == "-1":
        return "procedural"
    if normalized == "0":
        return "tie"
    if normalized is not None and normalized == player1_tp_id:
        return "player1"
    if normalized is not None and normalized == player2_tp_id:
        return "player2"
    raise ValueError("pairing winner does not match either participant")


def _normalize_decklist(player_id: str, payload: dict[str, Any]) -> DecklistFact:
    cards: list[CardFact] = []
    valid = True
    for category in ("pokemon", "trainer", "energy"):
        entries = payload.get(category)
        if not isinstance(entries, list):
            valid = False
            continue
        for raw_card in entries:
            if not isinstance(raw_card, dict):
                valid = False
                continue
            display_name = str(raw_card.get("name", "")).strip()
            count = _optional_int(raw_card.get("count"))
            if not display_name or count is None or count < 1:
                valid = False
                continue
            cards.append(
                CardFact(
                    card_name=canonical_card_name(display_name),
                    display_name=display_name,
                    set_code=str(raw_card.get("set", raw_card.get("set_code", ""))).strip(),
                    collector_number=str(raw_card.get("number", raw_card.get("collector_number", ""))).strip(),
                    count=count,
                    category=category,
                )
            )
    return DecklistFact(player_tp_id=player_id, cards=tuple(cards), valid=valid and bool(cards))


def _required_text(value: Any, field: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _required_int(value: Any, field: str) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected integer, got {value!r}") from exc


def _nonnegative_int(value: Any, field: str) -> int:
    parsed = _required_int(value, field)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _int_or_zero(value: Any) -> int:
    return 0 if value in (None, "") else _required_int(value, "numeric field")


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes"}
    return bool(value)
