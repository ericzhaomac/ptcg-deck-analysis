from __future__ import annotations

from typing import Any

import httpx

from .base import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):
    provider_name = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport

    @property
    def chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    @property
    def models_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base.removesuffix("/chat/completions")
        return f"{base}/models"

    def list_models(self) -> list[str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            response = client.get(self.models_url, headers=headers)
            response.raise_for_status()
            data = response.json()
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError("Provider model response must contain a data list")
        model_ids = [row["id"].strip() for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"].strip()]
        if rows and not model_ids:
            raise ValueError("Provider model response did not contain model IDs")
        return sorted(set(model_ids))

    def build_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

    def generate(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = self.build_payload(system_prompt=system_prompt, user_prompt=user_prompt)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            response = client.post(self.chat_completions_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return {"provider": self.provider_name, "model": self.model, "answer": content, "raw": data}
