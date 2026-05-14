from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DatasetAnalysisService:
    def load_analysis(self, analysis_path: str | Path) -> dict[str, Any]:
        path = Path(analysis_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset analysis report not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def get_summary(self, analysis_path: str | Path) -> dict[str, Any]:
        analysis = self.load_analysis(analysis_path)
        return {
            "tournament": analysis.get("tournament", {}),
            "field": analysis.get("field", {}),
            "archetypes": analysis.get("archetypes", []),
            "markdown": self._build_summary_markdown(analysis),
        }

    def compare_deck(self, analysis_path: str | Path, archetype: str, deck_payload: dict[str, Any]) -> dict[str, Any]:
        analysis = self.load_analysis(analysis_path)
        match = self._find_archetype(analysis, archetype)
        return {
            "archetype": match,
            "deck": deck_payload,
            "summary": {},
        }

    def build_explain_context(
        self,
        analysis_path: str | Path,
        archetype: str | None = None,
        deck_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = self.load_analysis(analysis_path)
        context: dict[str, Any] = {
            "tournament": analysis.get("tournament", {}),
            "field": analysis.get("field", {}),
        }
        if archetype:
            matching = self._find_archetype(analysis, archetype)
            if matching:
                context["archetype"] = matching
        if archetype and deck_payload:
            context["comparison"] = self.compare_deck(analysis_path=analysis_path, archetype=archetype, deck_payload=deck_payload)
        return context

    def _find_archetype(self, analysis: dict[str, Any], archetype: str) -> dict[str, Any] | None:
        query = archetype.lower()
        for row in analysis.get("archetypes", []):
            names = {
                str(row.get("archetype_name", "")).lower(),
                str(row.get("archetype_id", "")).lower(),
            }
            if query in names:
                return row
        return None

    def _build_summary_markdown(self, analysis: dict[str, Any]) -> str:
        tournament = analysis.get("tournament", {})
        name = tournament.get("name", "Tournament")
        archetypes = analysis.get("archetypes", [])
        lines = [f"# {name}", "", f"Archetypes: {len(archetypes)}"]
        return "\n".join(lines)
