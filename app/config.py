from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPORT_PATH = Path("tmp/limitless_reports/limitless_0062_MA_analysis.json")
DEFAULT_PROVIDER_CONFIG_PATH = Path("/data/config/provider.json")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Ptcg Deck Analysis Service"
    report_path: Path = DEFAULT_REPORT_PATH
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "kimi-code"
    provider_config_path: Path = DEFAULT_PROVIDER_CONFIG_PATH

    @classmethod
    def from_env(cls, report_path: Path | None = None) -> "Settings":
        return cls(
            report_path=report_path or Path(os.getenv("PRAGUE_ANALYSIS_REPORT_PATH", DEFAULT_REPORT_PATH)),
            openai_base_url=os.getenv("OPENAI_COMPATIBLE_BASE_URL"),
            openai_api_key=os.getenv("OPENAI_COMPATIBLE_API_KEY"),
            openai_model=os.getenv("OPENAI_COMPATIBLE_MODEL", "kimi-code"),
            provider_config_path=Path(os.getenv("PROVIDER_CONFIG_PATH", DEFAULT_PROVIDER_CONFIG_PATH)),
        )
