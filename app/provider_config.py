from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str
    model: str
    source: str = "file"

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def masked(self) -> dict[str, str | bool]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key": mask_secret(self.api_key),
            "source": self.source,
            "configured": self.is_configured,
        }


class ProviderConfigStore:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def load(self) -> ProviderConfig | None:
        if not self.config_path.exists():
            return None
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return ProviderConfig(
            base_url=(data.get("base_url") or "").strip(),
            api_key=(data.get("api_key") or "").strip(),
            model=(data.get("model") or "").strip(),
            source="file",
        )

    def save(self, *, base_url: str, api_key: str, model: str) -> ProviderConfig:
        config = ProviderConfig(
            base_url=base_url.strip(),
            api_key=api_key.strip(),
            model=model.strip(),
            source="file",
        )
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config


def mask_secret(secret: str | None) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"
