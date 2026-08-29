from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def write_analysis(tmp_path, year="2026", event="Prague", division="MA"):
    dataset_dir = tmp_path / "data" / year / event / division
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "analysis.json").write_text(json.dumps({
        "source": {"tournament_id": "0062", "division": division},
        "tournament": {"name": f"{event} Special Event"},
        "field": {},
        "archetypes": []
    }), encoding="utf-8")
    return dataset_dir


def test_datasets_endpoint_lists_available_and_state(tmp_path):
    write_analysis(tmp_path)
    state_path = tmp_path / "data" / "config" / "dataset_state.json"

    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))

    response = client.get("/api/v1/datasets")

    assert response.status_code == 200
    assert response.json()["datasets"][0]["dataset_id"] == "2026-prague-ma"
    assert response.json()["mounted_dataset_ids"] == []
    assert response.json()["current_dataset_id"] is None


def test_mount_then_set_current(tmp_path):
    write_analysis(tmp_path)
    state_path = tmp_path / "data" / "config" / "dataset_state.json"
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))

    mount_response = client.post("/api/v1/datasets/mount", json={"dataset_id": "2026-prague-ma"})
    current_response = client.post("/api/v1/datasets/current", json={"dataset_id": "2026-prague-ma"})

    assert mount_response.status_code == 200
    assert current_response.status_code == 200
    assert current_response.json()["current_dataset_id"] == "2026-prague-ma"


def test_unmount_endpoint_removes_dataset_and_reassigns_current(tmp_path):
    write_analysis(tmp_path, event="Prague")
    write_analysis(tmp_path, event="Utrecht")
    state_path = tmp_path / "data" / "config" / "dataset_state.json"
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))
    client.post("/api/v1/datasets/mount", json={"dataset_id": "2026-prague-ma"})
    client.post("/api/v1/datasets/mount", json={"dataset_id": "2026-utrecht-ma"})
    client.post("/api/v1/datasets/current", json={"dataset_id": "2026-prague-ma"})

    response = client.post("/api/v1/datasets/unmount", json={"dataset_id": "2026-prague-ma"})

    assert response.status_code == 200
    assert response.json() == {
        "mounted_dataset_ids": ["2026-utrecht-ma"],
        "current_dataset_id": "2026-utrecht-ma",
    }
    assert client.get("/api/v1/datasets/mounted").json() == response.json()


def test_summary_uses_current_dataset_from_state(tmp_path):
    prague_dir = tmp_path / "data" / "2026" / "Prague" / "MA"
    prague_dir.mkdir(parents=True)
    (prague_dir / "analysis.json").write_text(json.dumps({
        "source": {"tournament_id": "0062", "division": "MA"},
        "tournament": {"name": "Prague Special Event"},
        "field": {},
        "archetypes": []
    }), encoding="utf-8")
    state_path = tmp_path / "data" / "config" / "dataset_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "mounted_dataset_ids": ["2026-prague-ma"],
        "current_dataset_id": "2026-prague-ma"
    }), encoding="utf-8")

    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))
    response = client.get("/api/v1/analysis/summary")

    assert response.status_code == 200
    assert response.json()["tournament"]["name"] == "Prague Special Event"


def test_summary_accepts_explicit_dataset_id(tmp_path):
    write_analysis(tmp_path, event="Prague")
    la_dir = write_analysis(tmp_path, event="Los_Angeles")
    (la_dir / "analysis.json").write_text(json.dumps({
        "source": {"tournament_id": "0063", "division": "MA"},
        "tournament": {"name": "Los Angeles Regional"},
        "field": {},
        "archetypes": []
    }), encoding="utf-8")
    state_path = tmp_path / "data" / "config" / "dataset_state.json"

    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))

    response = client.get("/api/v1/analysis/summary", params={"dataset_id": "2026-los-angeles-ma"})

    assert response.status_code == 200
    assert response.json()["tournament"]["name"] == "Los Angeles Regional"


def test_summary_without_current_or_dataset_id_returns_400(tmp_path):
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=tmp_path / "data/config/dataset_state.json"))

    response = client.get("/api/v1/analysis/summary")

    assert response.status_code == 400


def test_provider_page_redirect_still_works(tmp_path):
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=tmp_path / "data/config/dataset_state.json"))
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {200, 307}


def test_provider_config_endpoint_exists(tmp_path):
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=tmp_path / "data/config/dataset_state.json"))
    response = client.get("/api/v1/provider/config")
    assert response.status_code == 200
