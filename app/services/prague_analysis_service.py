from __future__ import annotations

from pathlib import Path
from typing import Any

from .dataset_analysis_service import DatasetAnalysisService


class PragueAnalysisService(DatasetAnalysisService):
    def __init__(self, report_path: str | Path) -> None:
        self.report_path = Path(report_path)

    def load_analysis(self, analysis_path: str | Path | None = None) -> dict[str, Any]:
        return super().load_analysis(analysis_path or self.report_path)

    def get_summary(self, analysis_path: str | Path | None = None) -> dict[str, Any]:
        return super().get_summary(analysis_path or self.report_path)

    def compare_deck(
        self,
        archetype: str,
        deck_payload: dict[str, Any],
        analysis_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return super().compare_deck(analysis_path or self.report_path, archetype, deck_payload)

    def build_explain_context(
        self,
        archetype: str | None = None,
        deck_payload: dict[str, Any] | None = None,
        analysis_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return super().build_explain_context(analysis_path or self.report_path, archetype, deck_payload)
