from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.tournament_reports.contracts import Record, SnapshotManifest
from app.tournament_reports.facts import (
    FamilyIdentity,
    FamilyOverrideSet,
    load_family_overrides,
    normalize_snapshot,
    resolve_phase_boundary,
)
from app.tournament_reports.snapshots import SnapshotStore


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


@pytest.fixture
def raw_snapshot():
    manifest = SnapshotManifest.model_validate_json((FIXTURE / "manifest.json").read_text())
    return SnapshotStore().load_candidate(FIXTURE, manifest)


@pytest.fixture
def empty_overrides() -> FamilyOverrideSet:
    return FamilyOverrideSet(version=1, mappings={})


def test_normalize_uses_source_family_and_unique_pairings(raw_snapshot, empty_overrides) -> None:
    facts = normalize_snapshot(raw_snapshot, empty_overrides)

    assert facts.variants["dragapult-dusknoir"].family_id == "dragapult-ex"
    assert facts.variants["dragapult-dusknoir"].family_name == "Dragapult"
    assert facts.players["11"].top_cut is True
    assert facts.pairings[0].pairing_id == "round-01-table-1"
    assert facts.pairings[0].player1_tp_id == "11"
    assert facts.pairings[0].outcome == "player1"
    assert next(row for row in facts.pairings if row.pairing_id == "round-02-table-1").outcome == "tie"
    assert next(row for row in facts.pairings if row.pairing_id == "round-03-table-2").outcome == "procedural"


def test_exact_tournament_variant_override_replaces_source_family(raw_snapshot, tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "mappings": {
                    "0070:dragapult-dusknoir": {
                        "family_id": "dragapult-dusknoir-family",
                        "family_name": "Dragapult Dusknoir",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    facts = normalize_snapshot(raw_snapshot, load_family_overrides(path))

    assert facts.variants["dragapult-dusknoir"].family_id == "dragapult-dusknoir-family"
    assert facts.variants["dragapult-ex"].family_id == "dragapult-ex"


def test_override_loader_rejects_duplicate_mapping_keys(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    path.write_text(
        '{"version":1,"mappings":{"0070:dragapult-ex":{"family_id":"a","family_name":"A"},'
        '"0070:dragapult-ex":{"family_id":"b","family_name":"B"}}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_family_overrides(path)


def test_cards_use_canonical_name_but_keep_printing_identity(raw_snapshot, empty_overrides) -> None:
    facts = normalize_snapshot(raw_snapshot, empty_overrides)
    card = facts.decklists["11"].cards[0]

    assert card.card_name == "dragapult ex"
    assert card.display_name == "Dragapult   ex"
    assert card.set_code == "TWM"
    assert card.collector_number == "130"
    assert card.count == 3


def test_pairing_winner_must_match_a_participant(raw_snapshot, empty_overrides) -> None:
    invalid = dict(raw_snapshot.pairings[1][0])
    invalid["winner"] = 999
    changed = raw_snapshot.model_copy(
        update={"pairings": {**raw_snapshot.pairings, 1: (invalid, *raw_snapshot.pairings[1][1:])}}
    )

    with pytest.raises(ValueError, match="winner does not match"):
        normalize_snapshot(changed, empty_overrides)


def test_duplicate_round_table_pairing_is_rejected(raw_snapshot, empty_overrides) -> None:
    changed = raw_snapshot.model_copy(
        update={"pairings": {**raw_snapshot.pairings, 1: (*raw_snapshot.pairings[1], raw_snapshot.pairings[1][0])}}
    )

    with pytest.raises(ValueError, match="duplicate pairing"):
        normalize_snapshot(changed, empty_overrides)


def test_procedural_pairing_without_table_uses_stable_round_sequence(raw_snapshot, empty_overrides) -> None:
    procedural = {
        **raw_snapshot.pairings[1][0],
        "table": None,
        "player2": None,
        "winner": -1,
    }
    changed = raw_snapshot.model_copy(
        update={"pairings": {**raw_snapshot.pairings, 1: (*raw_snapshot.pairings[1], procedural)}}
    )

    facts = normalize_snapshot(changed, empty_overrides)

    pairing = next(row for row in facts.pairings if row.pairing_id == "round-01-procedural-1")
    assert pairing.pairing_id == "round-01-procedural-1"
    assert pairing.table_number is None
    assert pairing.outcome == "procedural"


def test_phase_boundary_requires_one_split_matching_every_variant(raw_snapshot, empty_overrides) -> None:
    facts = normalize_snapshot(raw_snapshot, empty_overrides)

    assert resolve_phase_boundary(facts) == 1

    impossible = {
        **facts.source_phase_records,
        "dragapult-ex": {1: Record(wins=99, losses=0, ties=0), 2: Record(wins=0, losses=0, ties=0)},
    }
    assert resolve_phase_boundary(replace(facts, source_phase_records=impossible)) is None

    zeros = {
        variant_id: {
            1: Record(wins=0, losses=0, ties=0),
            2: Record(wins=0, losses=0, ties=0),
        }
        for variant_id in facts.variants
    }
    assert resolve_phase_boundary(replace(facts, pairings=(), source_phase_records=zeros)) is None


def test_family_override_set_is_immutable_by_contract() -> None:
    overrides = FamilyOverrideSet(
        version=1,
        mappings={("0070", "dragapult-ex"): FamilyIdentity("dragapult-ex", "Dragapult")},
    )
    assert overrides.mappings[("0070", "dragapult-ex")].family_name == "Dragapult"
