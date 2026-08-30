from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.tools.limitless_tournament_snapshot import (
    LimitlessSnapshotAdapter,
    TournamentRef,
)


FIXED_TIME = datetime(2026, 6, 14, 20, 0, tzinfo=UTC)


def _payloads(rounds: int = 3) -> dict[str, dict[str, Any]]:
    return {
        "tournament": {
            "ok": True,
            "message": {
                "name": "New Orleans",
                "date": "June 12–14, 2026",
                "updated_at": "2026-06-14 19:37:59",
                "round": rounds,
                "completed": 1,
            },
        },
        "decks": {
            "ok": True,
            "message": [
                {"identifier": "dragapult-ex", "name": "Dragapult"},
                {"identifier": "dragapult-dusknoir", "name": "Dragapult Dusknoir"},
            ],
        },
        "standings": {
            "ok": True,
            "message": [
                {"tp_id": 11, "deck_id": "dragapult-ex", "decklist": 1},
                {"tp_id": 12, "deck_id": "dragapult-dusknoir", "decklist": 1},
                {"tp_id": 13, "deck_id": "other", "decklist": 0},
            ],
        },
        "pairings": {"ok": True, "message": []},
        "decklist": {
            "ok": True,
            "message": {"pokemon": [], "trainer": [], "energy": []},
        },
        "matchups": {"ok": True, "message": {"records": {}, "matchups": []}},
    }


class RecordingClient:
    def __init__(self, payloads: dict[str, dict[str, Any]], fail_on: str | None = None) -> None:
        self.payloads = payloads
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def fetch(self, endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
        self.calls.append((endpoint, params))
        if endpoint == self.fail_on:
            raise OSError(f"failed {endpoint}")
        return self.payloads[endpoint]


def test_collect_fetches_every_declared_round_decklist_and_variant_matchup(tmp_path: Path) -> None:
    client = RecordingClient(_payloads(rounds=3))
    dataset_dir = tmp_path / "2026/New_Orleans/MA"

    staged = LimitlessSnapshotAdapter(client=client, clock=lambda: FIXED_TIME).collect(
        TournamentRef("0070", "MA"),
        dataset_dir,
    )

    assert ("tournament", {"id": "0070", "division": "MA"}) in client.calls
    assert ("decks", {"tournamentId": "0070", "division": "MA"}) in client.calls
    assert ("standings", {"tournamentId": "0070", "division": "MA"}) in client.calls
    for round_number in (1, 2, 3):
        assert (
            "pairings",
            {"tournamentId": "0070", "division": "MA", "round": round_number},
        ) in client.calls
    for player_id in ("11", "12"):
        assert ("decklist", {"tournamentId": "0070", "playerId": player_id}) in client.calls
    for variant_id in ("dragapult-ex", "dragapult-dusknoir"):
        assert (
            "matchups",
            {"tournamentId": "0070", "division": "MA", "deckId": variant_id},
        ) in client.calls
    assert staged.manifest.declared_rounds == 3
    assert staged.raw.manifest == staged.manifest
    assert staged.raw.decklists.keys() == {"11", "12"}
    assert set(staged.raw.matchup_references) == {"dragapult-ex", "dragapult-dusknoir"}
    assert re.fullmatch(r"0070-ma-[0-9a-f]{12}", staged.manifest.snapshot_version)
    assert not (dataset_dir / "cache/verified-snapshot.json").exists()


def test_content_version_is_deterministic_and_excludes_fetch_time(tmp_path: Path) -> None:
    first = LimitlessSnapshotAdapter(
        client=RecordingClient(_payloads()),
        clock=lambda: FIXED_TIME,
    ).collect(TournamentRef("0070"), tmp_path / "first")
    second = LimitlessSnapshotAdapter(
        client=RecordingClient(_payloads()),
        clock=lambda: datetime(2026, 6, 15, tzinfo=UTC),
    ).collect(TournamentRef("0070"), tmp_path / "second")

    assert first.manifest.snapshot_version == second.manifest.snapshot_version
    assert first.manifest.fetched_at != second.manifest.fetched_at


def test_failed_collection_removes_only_candidate_and_preserves_pointer(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    pointer = dataset_dir / "cache/verified-snapshot.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text('{"snapshot_version":"good"}', encoding="utf-8")
    client = RecordingClient(_payloads(), fail_on="pairings")

    with pytest.raises(OSError, match="failed pairings"):
        LimitlessSnapshotAdapter(client=client, clock=lambda: FIXED_TIME).collect(
            TournamentRef("0070"),
            dataset_dir,
        )

    assert pointer.read_text(encoding="utf-8") == '{"snapshot_version":"good"}'
    assert list((dataset_dir / "cache").glob("snapshot-candidate-*")) == []


def test_unsuccessful_source_envelope_fails_collection(tmp_path: Path) -> None:
    payloads = _payloads()
    payloads["decks"] = {"ok": False, "message": []}

    with pytest.raises(ValueError, match="unsuccessful payload"):
        LimitlessSnapshotAdapter(
            client=RecordingClient(payloads),
            clock=lambda: FIXED_TIME,
        ).collect(TournamentRef("0070"), tmp_path / "dataset")
