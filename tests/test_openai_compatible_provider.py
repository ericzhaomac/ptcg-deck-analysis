from __future__ import annotations

import httpx
import pytest

from app.providers.openai_compatible import OpenAICompatibleProvider


def test_list_models_uses_normalized_models_url_and_bearer_auth():
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"data": [{"id": "model-b"}, {"id": "model-a"}, {"id": "model-a"}]},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1/chat/completions/",
        api_key="secret",
        model="model-a",
        transport=httpx.MockTransport(handler),
    )

    assert provider.models_url == "https://provider.test/v1/models"
    assert provider.list_models() == ["model-a", "model-b"]
    assert observed == {
        "url": "https://provider.test/v1/models",
        "authorization": "Bearer secret",
    }


def test_list_models_raises_for_provider_http_errors():
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="bad-key",
        model="model-a",
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "unauthorized"})),
    )

    with pytest.raises(httpx.HTTPStatusError):
        provider.list_models()


@pytest.mark.parametrize("payload", [{}, {"data": "wrong"}, {"data": [{"name": "missing-id"}]}])
def test_list_models_rejects_malformed_provider_payloads(payload):
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="secret",
        model="model-a",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ValueError, match="model"):
        provider.list_models()


def test_list_models_strips_and_deduplicates_model_ids():
    provider = OpenAICompatibleProvider(
        base_url="https://provider.test/v1",
        api_key="secret",
        model="model-a",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"data": [{"id": " model-b "}, {"id": "model-a"}, {"id": "model-b"}]},
            )
        ),
    )

    assert provider.list_models() == ["model-a", "model-b"]
