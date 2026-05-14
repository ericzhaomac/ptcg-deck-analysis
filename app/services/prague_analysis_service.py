from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.tools.prague_phase15_tools import build_summary_markdown, compare_user_deck


class PragueAnalysisService:
    def __init__(self, report_path: str | Path) -> None:
        self.report_path = Path(report_path)

    def load_analysis(self) -> dict[str, Any]:
        if not self.report_path.exists():
            raise FileNotFoundError(f"Prague analysis report not found: {self.report_path}")
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def get_summary(self) -> dict[str, Any]:
        analysis = self.load_analysis()
        return {
            "tournament": analysis.get("tournament", {}),
            "field": analysis.get("field", {}),
            "archetypes": analysis.get("archetypes", []),
            "markdown": build_summary_markdown(analysis),
        }

    def compare_deck(self, archetype: str, deck_payload: dict[str, Any]) -> dict[str, Any]:
        analysis = self.load_analysis()
        return compare_user_deck(analysis=analysis, archetype_query=archetype, deck_payload=deck_payload)

    def build_explain_context(self, archetype: str | None = None, deck_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        analysis = self.load_analysis()
        context: dict[str, Any] = {
            "tournament": analysis.get("tournament", {}),
            "field": analysis.get("field", {}),
        }
        if archetype:
            matching = [row for row in analysis.get("archetypes", []) if archetype.lower() in {str(row.get("archetype_name", "")).lower(), str(row.get("archetype_id", "")).lower()}]
            if matching:
                context["archetype"] = matching[0]
        if archetype and deck_payload:
            context["comparison"] = compare_user_deck(analysis=analysis, archetype_query=archetype, deck_payload=deck_payload)
        return context
