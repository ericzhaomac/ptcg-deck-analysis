from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.openai_compatible import OpenAICompatibleProvider


def make_client(tmp_path) -> TestClient:
    return TestClient(
        create_app(
            data_root=tmp_path / "data",
            dataset_state_path=tmp_path / "dataset-state.json",
            provider_config_path=tmp_path / "provider.json",
            user_decks_path=tmp_path / "decks.json",
        )
    )


def test_provider_settings_require_first_key_then_preserve_blank_key(tmp_path):
    client = make_client(tmp_path)

    first_without_key = client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://provider.test/v1", "model": "model-a", "api_key": ""},
    )
    assert first_without_key.status_code == 400

    saved_response = client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://provider.test/v1", "model": "model-a", "api_key": "1234567890abcdef"},
    )
    assert saved_response.status_code == 200
    assert saved_response.json()["api_key"] == "1234********cdef"
    assert "1234567890abcdef" not in saved_response.text

    preserved_response = client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://provider.test/v1", "model": "model-b", "api_key": ""},
    )
    assert preserved_response.status_code == 200
    assert preserved_response.json()["model"] == "model-b"
    assert client.get("/api/v1/provider/settings").json()["file"]["api_key"] == "1234********cdef"

    changed_url_response = client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://different.test/v1", "model": "model-c", "api_key": ""},
    )
    assert changed_url_response.status_code == 400
    assert changed_url_response.json() == {"detail": "API key is required when changing the Base URL"}
    assert client.get("/api/v1/provider/settings").json()["file"]["base_url"] == "https://provider.test/v1"


def test_model_discovery_uses_requested_fields_and_returns_models(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    observed = {}

    def fake_list_models(self):
        observed.update(base_url=self.base_url, api_key=self.api_key)
        return ["model-a", "model-b"]

    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", fake_list_models)

    response = client.post(
        "/api/v1/provider/models",
        json={"base_url": "https://provider.test/v1", "api_key": "entered-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"base_url": "https://provider.test/v1", "models": ["model-a", "model-b"]}
    assert observed == {"base_url": "https://provider.test/v1", "api_key": "entered-secret"}


def test_model_discovery_uses_saved_key_when_field_is_blank(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://saved.test/v1", "model": "model-a", "api_key": "saved-secret"},
    )
    observed = {}

    def fake_list_models(self):
        observed.update(base_url=self.base_url, api_key=self.api_key)
        return ["saved-model"]

    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", fake_list_models)

    response = client.post("/api/v1/provider/models", json={"base_url": "", "api_key": ""})

    assert response.status_code == 200
    assert response.json()["models"] == ["saved-model"]
    assert observed == {"base_url": "https://saved.test/v1", "api_key": "saved-secret"}


def test_model_discovery_does_not_send_saved_key_to_changed_base_url(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://saved.test/v1", "model": "model-a", "api_key": "saved-secret"},
    )
    called = False

    def fake_list_models(self):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", fake_list_models)

    response = client.post(
        "/api/v1/provider/models",
        json={"base_url": "https://different.test/v1", "api_key": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "API key is required when fetching models from a different Base URL"}
    assert called is False


def test_model_discovery_maps_upstream_errors_to_clear_502(tmp_path, monkeypatch):
    client = make_client(tmp_path)

    def fail(self):
        request = httpx.Request("GET", "https://provider.test/v1/models")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(OpenAICompatibleProvider, "list_models", fail)

    response = client.post(
        "/api/v1/provider/models",
        json={"base_url": "https://provider.test/v1", "api_key": "bad-key"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to fetch models from the configured provider (HTTP 401)"}


def test_legacy_provider_form_does_not_reuse_saved_key_for_changed_base_url(tmp_path):
    client = make_client(tmp_path)
    client.put(
        "/api/v1/provider/settings",
        json={"base_url": "https://saved.test/v1", "model": "model-a", "api_key": "saved-secret"},
    )

    response = client.post(
        "/api/v1/provider/config",
        data={"base_url": "https://different.test/v1", "model": "model-b", "api_key": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "API key is required when changing the Base URL"}
    assert client.get("/api/v1/provider/settings").json()["file"]["base_url"] == "https://saved.test/v1"
