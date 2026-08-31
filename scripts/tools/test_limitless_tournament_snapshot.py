from __future__ import annotations

import re
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.tools.limitless_tournament_snapshot import (
    LimitlessClient,
    LimitlessSnapshotAdapter,
    StagedSnapshot,
    TournamentRef,
    VerifiedSnapshotRefresher,
    main,
    parse_args,
)
from app.tournament_reports.contracts import SnapshotManifest
from app.tournament_reports.facts import FamilyOverrideSet
from app.tournament_reports.reconciliation import verify_candidate_snapshot
from app.tournament_reports.snapshots import SnapshotStore, SnapshotValidationError


FIXED_TIME = datetime(2026, 6, 14, 20, 0, tzinfo=UTC)
FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


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


def test_collect_reuses_valid_flat_cache_without_opening_network(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    payloads = _payloads(rounds=1)
    payloads["pairings"] = {
        "ok": True,
        "message": [{"table": 1, "winner": 0, "player1": {}, "player2": {}}],
    }
    cached = {
        "tournament.json": payloads["tournament"],
        "decks.json": payloads["decks"],
        "standings.json": payloads["standings"],
        "pairings/round-01.json": payloads["pairings"],
        "decklists/11.json": payloads["decklist"],
        "decklists/12.json": payloads["decklist"],
        "matchups/dragapult-ex.json": payloads["matchups"],
        "matchups/dragapult-dusknoir.json": payloads["matchups"],
    }
    for relative_path, payload in cached.items():
        path = dataset_dir / "cache" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def fail_open(*args, **kwargs):
        raise AssertionError("valid flat cache attempted a network request")

    staged = LimitlessSnapshotAdapter(
        client=LimitlessClient(opener=fail_open),
        clock=lambda: FIXED_TIME,
    ).collect(TournamentRef("0070"), dataset_dir)

    assert staged.raw.tournament["completed"] == 1
    assert set(staged.raw.pairings) == {1}
    assert set(staged.raw.decklists) == {"11", "12"}


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


class FixtureAdapter:
    def __init__(self, *, completed: bool = True) -> None:
        self.completed = completed

    def collect(self, ref: TournamentRef, dataset_dir: Path) -> StagedSnapshot:
        path = dataset_dir / "cache/snapshot-candidate-fixture"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(FIXTURE, path)
        manifest = SnapshotManifest.model_validate_json((path / "manifest.json").read_text())
        raw = SnapshotStore().load_candidate(path, manifest)
        if not self.completed:
            raw = raw.model_copy(update={"tournament": {**raw.tournament, "completed": 0}})
        return StagedSnapshot(path=path, manifest=manifest, raw=raw)


def test_verified_refresher_promotes_only_reconciled_candidate(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    refresher = VerifiedSnapshotRefresher(
        adapter=FixtureAdapter(),
        store=SnapshotStore(),
        family_overrides=FamilyOverrideSet(version=1, mappings={}),
    )

    manifest = refresher.refresh(TournamentRef("0070"), dataset_dir)

    assert manifest.snapshot_version == "fixture-v1"
    assert json.loads((dataset_dir / "cache/verified-snapshot.json").read_text())["snapshot_version"] == "fixture-v1"


def test_blocked_refresh_cleans_candidate_and_preserves_last_good_pointer(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    pointer = dataset_dir / "cache/verified-snapshot.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text('{"snapshot_version":"good"}', encoding="utf-8")
    refresher = VerifiedSnapshotRefresher(
        adapter=FixtureAdapter(completed=False),
        store=SnapshotStore(),
        family_overrides=FamilyOverrideSet(version=1, mappings={}),
    )

    with pytest.raises(SnapshotValidationError) as error:
        refresher.refresh(TournamentRef("0070"), dataset_dir)

    assert error.value.code == "verification_blocked"
    assert pointer.read_text(encoding="utf-8") == '{"snapshot_version":"good"}'
    assert not (dataset_dir / "cache/snapshot-candidate-fixture").exists()


def test_cli_requires_explicit_dataset_directory() -> None:
    args = parse_args(
        [
            "--tournament-id",
            "0070",
            "--division",
            "MA",
            "--dataset-dir",
            "data/2026/New_Orleans/MA",
        ]
    )
    assert args.dataset_dir == "data/2026/New_Orleans/MA"


def test_verify_only_uses_the_current_snapshot_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_dir = tmp_path / "dataset"
    candidate = dataset_dir / "cache/snapshot-candidate-fixture"
    candidate.parent.mkdir(parents=True)
    shutil.copytree(FIXTURE, candidate)
    manifest = SnapshotManifest.model_validate_json((candidate / "manifest.json").read_text())
    SnapshotStore().promote(dataset_dir, candidate, manifest, verification=verify_candidate_snapshot(
        SnapshotStore().load_candidate(FIXTURE, manifest),
        FamilyOverrideSet(version=1, mappings={}),
    ))
    overrides = tmp_path / "overrides.json"
    overrides.write_text('{"version": 1, "mappings": {}}', encoding="utf-8")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("verify-only attempted a network request")

    monkeypatch.setattr("scripts.tools.limitless_tournament_snapshot.LimitlessClient.fetch", fail_fetch)

    exit_code = main(
        [
            "--tournament-id", "0070",
            "--division", "MA",
            "--dataset-dir", str(dataset_dir),
            "--family-overrides", str(overrides),
            "--verify-only",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["snapshot_version"] == "fixture-v1"
    assert payload["phase_boundary"] == 1
    assert payload["blocking_issue_codes"] == []
    assert payload["eligible_family_count"] == 2


def test_parse_args_accepts_verify_only() -> None:
    args = parse_args(
        [
            "--tournament-id", "0070",
            "--dataset-dir", "data/2026/New_Orleans/MA",
            "--verify-only",
        ]
    )

    assert args.verify_only is True


def test_script_entrypoint_exposes_verified_refresh_arguments() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/tools/limitless_tournament_snapshot.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--dataset-dir" in result.stdout
    assert "--family-overrides" in result.stdout
