from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.tournament_reports.contracts import (
    SnapshotManifest,
    SnapshotResource,
    SnapshotVerification,
)
from app.tournament_reports.snapshots import SnapshotStore, SnapshotValidationError


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _resource_payloads(rounds: int = 2) -> dict[str, object]:
    resources: dict[str, object] = {
        "tournament": {
            "ok": True,
            "message": {
                "name": "Test Regional",
                "date": "2026-06-14",
                "round": rounds,
                "updated_at": "2026-06-14T19:37:59Z",
            },
        },
        "decks": {
            "ok": True,
            "message": [
                {
                    "identifier": "dragapult-ex",
                    "name": "Dragapult",
                    "sup_identifier": "dragapult-ex",
                    "sup_name": "Dragapult",
                }
            ],
        },
        "standings": {
            "ok": True,
            "message": [{"tp_id": "11", "deck_id": "dragapult-ex", "decklist": 1}],
        },
        "decklists/11": {
            "ok": True,
            "message": {"pokemon": [], "trainer": [], "energy": []},
        },
        "matchups/dragapult-ex": {"ok": True, "message": {"records": {}, "matchups": []}},
    }
    for round_number in range(1, rounds + 1):
        resources[f"pairings/round-{round_number:02d}"] = {
            "ok": True,
            "message": [{"table": 1, "winner": 0, "player1": {}, "player2": {}}],
        }
    return resources


def _stage(
    tmp_path: Path,
    *,
    version: str,
    rounds: int = 2,
    payloads: dict[str, object] | None = None,
) -> tuple[Path, Path, SnapshotManifest]:
    dataset_dir = tmp_path / "dataset"
    staged_dir = dataset_dir / "cache" / f"snapshot-candidate-{version}"
    resources: dict[str, SnapshotResource] = {}
    for key, payload in (payloads or _resource_payloads(rounds)).items():
        relative_path = f"{key}.json"
        path = staged_dir / relative_path
        _write_json(path, payload)
        resources[key] = SnapshotResource(
            path=relative_path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    manifest = SnapshotManifest(
        schema_version=1,
        snapshot_version=version,
        tournament_id="0070",
        division="MA",
        source_provider="Limitless Labs",
        source_updated_at=datetime(2026, 6, 14, 19, 37, 59, tzinfo=UTC),
        fetched_at=datetime(2026, 6, 14, 20, 0, tzinfo=UTC),
        declared_rounds=rounds,
        resources=resources,
    )
    _write_json(staged_dir / "manifest.json", manifest.model_dump(mode="json"))
    return dataset_dir, staged_dir, manifest


def _promote(tmp_path: Path, version: str = "good") -> tuple[Path, SnapshotManifest]:
    dataset_dir, staged_dir, manifest = _stage(tmp_path, version=version)
    SnapshotStore().promote(dataset_dir, staged_dir, manifest, SnapshotVerification())
    return dataset_dir, manifest


def test_promote_writes_immutable_snapshot_and_atomic_pointer(tmp_path: Path) -> None:
    dataset_dir, staged_dir, manifest = _stage(tmp_path, version="0070-ma-abc123")

    promoted = SnapshotStore().promote(
        dataset_dir,
        staged_dir,
        manifest,
        SnapshotVerification(),
    )

    assert promoted == dataset_dir / "cache/snapshots/0070-ma-abc123"
    assert not staged_dir.exists()
    assert json.loads((dataset_dir / "cache/verified-snapshot.json").read_text())["snapshot_version"] == manifest.snapshot_version
    loaded = SnapshotStore().load(dataset_dir)
    assert loaded.manifest.snapshot_version == manifest.snapshot_version
    assert loaded.tournament["name"] == "Test Regional"
    assert loaded.decks[0]["identifier"] == "dragapult-ex"
    assert set(loaded.pairings) == {1, 2}


def test_invalid_refresh_cannot_replace_last_verified_snapshot(tmp_path: Path) -> None:
    dataset_dir, _ = _promote(tmp_path, version="good")
    _, staged_dir, manifest = _stage(tmp_path, version="bad")
    missing = staged_dir / manifest.resources["pairings/round-02"].path
    missing.unlink()

    with pytest.raises(SnapshotValidationError, match="missing resource") as error:
        SnapshotStore().promote(dataset_dir, staged_dir, manifest, SnapshotVerification())

    assert error.value.code == "missing_resource"
    assert json.loads((dataset_dir / "cache/verified-snapshot.json").read_text())["snapshot_version"] == "good"


def test_blocking_verification_cannot_replace_last_verified_snapshot(tmp_path: Path) -> None:
    dataset_dir, _ = _promote(tmp_path, version="good")
    _, staged_dir, manifest = _stage(tmp_path, version="blocked")

    with pytest.raises(SnapshotValidationError) as error:
        SnapshotStore().promote(
            dataset_dir,
            staged_dir,
            manifest,
            SnapshotVerification(blocking_issue_codes=("pairing_incomplete",)),
        )

    assert error.value.code == "verification_blocked"
    assert json.loads((dataset_dir / "cache/verified-snapshot.json").read_text())["snapshot_version"] == "good"


def test_load_rejects_missing_pointer(tmp_path: Path) -> None:
    with pytest.raises(SnapshotValidationError) as error:
        SnapshotStore().load(tmp_path / "dataset")
    assert error.value.code == "missing_verified_pointer"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("malformed_json", "malformed_json"),
        ("schema_mismatch", "source_schema_incompatible"),
        ("hash_mismatch", "hash_mismatch"),
        ("missing_round", "missing_round"),
    ],
)
def test_candidate_validation_rejects_invalid_resources(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    dataset_dir, staged_dir, manifest = _stage(tmp_path, version=mutation)
    if mutation == "malformed_json":
        (staged_dir / manifest.resources["decks"].path).write_text("{", encoding="utf-8")
        manifest.resources["decks"].sha256 = hashlib.sha256(
            (staged_dir / manifest.resources["decks"].path).read_bytes()
        ).hexdigest()
    elif mutation == "schema_mismatch":
        path = staged_dir / manifest.resources["standings"].path
        _write_json(path, {"ok": True, "message": {"not": "a list"}})
        manifest.resources["standings"].sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation == "hash_mismatch":
        (staged_dir / manifest.resources["tournament"].path).write_text("{}", encoding="utf-8")
    else:
        manifest.resources.pop("pairings/round-02")
    _write_json(staged_dir / "manifest.json", manifest.model_dump(mode="json"))

    with pytest.raises(SnapshotValidationError) as error:
        SnapshotStore().promote(dataset_dir, staged_dir, manifest, SnapshotVerification())

    assert error.value.code == expected_code
    assert not (dataset_dir / "cache/verified-snapshot.json").exists()


def test_same_snapshot_version_is_idempotent_but_cannot_be_mutated(tmp_path: Path) -> None:
    dataset_dir, manifest = _promote(tmp_path, version="stable")
    _, identical_staging, identical_manifest = _stage(tmp_path, version="stable")

    assert SnapshotStore().promote(
        dataset_dir,
        identical_staging,
        identical_manifest,
        SnapshotVerification(),
    ) == dataset_dir / "cache/snapshots/stable"

    _, changed_staging, changed_manifest = _stage(tmp_path, version="stable")
    changed_path = changed_staging / changed_manifest.resources["tournament"].path
    changed_payload = json.loads(changed_path.read_text())
    changed_payload["message"]["name"] = "Changed Regional"
    _write_json(changed_path, changed_payload)
    changed_manifest.resources["tournament"].sha256 = hashlib.sha256(changed_path.read_bytes()).hexdigest()
    _write_json(changed_staging / "manifest.json", changed_manifest.model_dump(mode="json"))

    with pytest.raises(SnapshotValidationError) as error:
        SnapshotStore().promote(dataset_dir, changed_staging, changed_manifest, SnapshotVerification())

    assert error.value.code == "immutable_version_collision"
    assert SnapshotStore().load(dataset_dir).tournament["name"] == "Test Regional"


def test_load_rejects_pointer_to_missing_snapshot(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    _write_json(dataset_dir / "cache/verified-snapshot.json", {"snapshot_version": "missing"})

    with pytest.raises(SnapshotValidationError) as error:
        SnapshotStore().load(dataset_dir)

    assert error.value.code == "missing_snapshot"
