from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


FIXTURE = Path("tests/fixtures/tournament_reports/minimal_verified_snapshot")


def _install_dataset(tmp_path: Path, *, mounted: bool = True, snapshot: bool = True) -> TestClient:
    data_root = tmp_path / "data"
    dataset_dir = data_root / "2026" / "New_Orleans" / "MA"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "analysis.json").write_text(
        json.dumps({"source": {"tournament_id": "0070"}, "tournament": {}, "archetypes": []}),
        encoding="utf-8",
    )
    if snapshot:
        target = dataset_dir / "cache" / "snapshots" / "fixture-v1"
        shutil.copytree(FIXTURE, target)
        (dataset_dir / "cache" / "verified-snapshot.json").write_text(
            '{"snapshot_version": "fixture-v1"}', encoding="utf-8"
        )
    config_dir = data_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "archetype_family_overrides.json").write_text(
        '{"version": 1, "mappings": {}}', encoding="utf-8"
    )
    state_path = config_dir / "dataset_state.json"
    state_path.write_text(
        json.dumps(
            {
                "mounted_dataset_ids": ["2026-new-orleans-ma"] if mounted else [],
                "current_dataset_id": "2026-new-orleans-ma" if mounted else None,
            }
        ),
        encoding="utf-8",
    )
    return TestClient(create_app(data_root=data_root, dataset_state_path=state_path))


def test_index_overview_and_family_routes_expose_report_contract(tmp_path: Path) -> None:
    client = _install_dataset(tmp_path)

    index = client.get("/api/v1/tournament-reports")
    overview = client.get("/api/v1/tournament-reports/2026-new-orleans-ma")
    family = client.get(
        "/api/v1/tournament-reports/2026-new-orleans-ma/families/dragapult-ex"
    )

    assert index.status_code == 200
    assert [item["dataset_id"] for item in index.json()["events"]] == ["2026-new-orleans-ma"]
    assert overview.status_code == 200
    assert [module["module_id"] for module in overview.json()["modules"]] == [
        "event_identity",
        "phase1_meta_share",
        "phase2_meta_share",
        "family_ranking",
    ]
    assert family.status_code == 200
    assert family.json()["selection"] == {"grain": "family", "selection_id": "dragapult-ex"}


def test_report_routes_map_not_found_conflict_ineligible_and_unavailable(tmp_path: Path) -> None:
    client = _install_dataset(tmp_path)

    unknown = client.get("/api/v1/tournament-reports/not-a-dataset")
    ineligible = client.get(
        "/api/v1/tournament-reports/2026-new-orleans-ma/variants/dragapult-dusknoir"
    )

    assert unknown.status_code == 404
    assert ineligible.status_code == 422
    assert ineligible.json()["reason_code"] == "variant_players_below_10"
    assert ineligible.json()["sample_size"] == 1

    unmounted = _install_dataset(tmp_path / "unmounted", mounted=False)
    assert unmounted.get("/api/v1/tournament-reports/2026-new-orleans-ma").status_code == 409

    unavailable = _install_dataset(tmp_path / "unavailable", snapshot=False)
    assert unavailable.get("/api/v1/tournament-reports/2026-new-orleans-ma").status_code == 503
