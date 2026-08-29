from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROVIDER_CONFIG_PATH = Path("data/runtime/provider.json")
DEFAULT_USER_DECKS_PATH = Path("data/runtime/decks.json")
DEFAULT_DATA_ROOT = Path("data")
DEFAULT_DATASET_STATE_PATH = Path("data/config/dataset_state.json")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Ptcg Deck Analysis Service"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "kimi-code"
    provider_config_path: Path = DEFAULT_PROVIDER_CONFIG_PATH
    user_decks_path: Path = DEFAULT_USER_DECKS_PATH
    data_root: Path = DEFAULT_DATA_ROOT
    dataset_state_path: Path = DEFAULT_DATASET_STATE_PATH

    @classmethod
    def from_env(
        cls,
        data_root: Path | None = None,
        dataset_state_path: Path | None = None,
        provider_config_path: Path | None = None,
        user_decks_path: Path | None = None,
    ) -> "Settings":
        return cls(
            openai_base_url=os.getenv("OPENAI_COMPATIBLE_BASE_URL"),
            openai_api_key=os.getenv("OPENAI_COMPATIBLE_API_KEY"),
            openai_model=os.getenv("OPENAI_COMPATIBLE_MODEL", "kimi-code"),
            provider_config_path=provider_config_path or Path(os.getenv("PROVIDER_CONFIG_PATH", DEFAULT_PROVIDER_CONFIG_PATH)),
            user_decks_path=user_decks_path or Path(os.getenv("USER_DECKS_PATH", DEFAULT_USER_DECKS_PATH)),
            data_root=data_root or Path(os.getenv("DATA_ROOT", DEFAULT_DATA_ROOT)),
            dataset_state_path=dataset_state_path or Path(os.getenv("DATASET_STATE_PATH", DEFAULT_DATASET_STATE_PATH)),
        )
