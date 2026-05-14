from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


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
