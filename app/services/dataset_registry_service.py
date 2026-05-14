from __future__ import annotations

import json
from pathlib import Path

from ..models import DatasetRecord


class DatasetRegistryService:
    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root)

    def list_datasets(self) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        for analysis_path in sorted(self.data_root.glob("*/*/*/analysis.json")):
            record = self._build_record(analysis_path)
            if record is not None:
                records.append(record)
        return records

    def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        for record in self.list_datasets():
            if record.dataset_id == dataset_id:
                return record
        return None

    def _build_record(self, analysis_path: Path) -> DatasetRecord | None:
        try:
            payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        division = analysis_path.parent.name
        event_dir = analysis_path.parent.parent.name
        year = int(analysis_path.parent.parent.parent.name)
        event_slug = event_dir.lower().replace("_", "-")
        event_name = event_dir.replace("_", " ")
        dataset_id = f"{year}-{event_slug}-{division.lower()}"
        cache_path = analysis_path.parent / "cache"

        return DatasetRecord(
            dataset_id=dataset_id,
            year=year,
            event_slug=event_slug,
            event_name=event_name,
            division=division,
            display_name=f"{year} {event_name} / {division}",
            dataset_dir=str(analysis_path.parent),
            analysis_path=str(analysis_path),
            cache_path=str(cache_path) if cache_path.exists() else None,
            tournament_id=payload.get("source", {}).get("tournament_id"),
            city=payload.get("tournament", {}).get("city"),
            source_provider=payload.get("source", {}).get("provider"),
        )
