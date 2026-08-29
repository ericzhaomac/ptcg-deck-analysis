from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path) -> TestClient:
    return TestClient(
        create_app(
            data_root=tmp_path / "data",
            dataset_state_path=tmp_path / "dataset-state.json",
            provider_config_path=tmp_path / "provider.json",
            user_decks_path=tmp_path / "decks.json",
        )
    )


def valid_payload(name: str = "Dragapult") -> dict:
    return {
        "name": name,
        "pokemon": [{"name": "Dreepy TWM 128", "count": 4}],
        "trainer": [{"name": "Buddy-Buddy Poffin TEF 144", "count": 4}],
        "energy": [{"name": "Psychic Energy MEE 5", "count": 3}],
    }


def test_saved_deck_crud_and_duplicate_lifecycle(tmp_path):
    client = make_client(tmp_path)

    assert client.get("/api/v1/decks").json() == []

    create_response = client.post("/api/v1/decks", json=valid_payload())
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Dragapult"
    assert created["created_at"] == created["updated_at"]

    assert client.get("/api/v1/decks").json()[0]["id"] == created["id"]
    assert client.get(f"/api/v1/decks/{created['id']}").json() == created

    update_response = client.put(
        f"/api/v1/decks/{created['id']}",
        json={**valid_payload("Dragapult v2"), "pokemon": [{"name": "Dreepy", "count": 3}]},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Dragapult v2"
    assert updated["created_at"] == created["created_at"]
    assert updated["pokemon"] == [{"name": "Dreepy", "count": 3}]

    duplicate_response = client.post(f"/api/v1/decks/{created['id']}/duplicate")
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["id"] != created["id"]
    assert duplicate["name"] == "Dragapult v2 (Copy)"

    delete_response = client.delete(f"/api/v1/decks/{created['id']}")
    assert delete_response.status_code == 204
    assert [deck["id"] for deck in client.get("/api/v1/decks").json()] == [duplicate["id"]]


def test_saved_deck_routes_return_404_for_unknown_ids(tmp_path):
    client = make_client(tmp_path)

    assert client.get("/api/v1/decks/missing").status_code == 404
    assert client.put("/api/v1/decks/missing", json=valid_payload()).status_code == 404
    assert client.post("/api/v1/decks/missing/duplicate").status_code == 404
    assert client.delete("/api/v1/decks/missing").status_code == 404


def test_saved_deck_routes_return_structured_validation_errors(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/v1/decks",
        json={"name": "Invalid", "pokemon": [{"name": "Dreepy", "count": 61}], "trainer": [], "energy": []},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "count"
