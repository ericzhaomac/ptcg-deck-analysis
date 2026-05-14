from __future__ import annotations

import json
from pathlib import Path

from ..models import DatasetState


class DatasetStateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = Path(state_path)

    def load(self) -> DatasetState:
        if not self.state_path.exists():
            return DatasetState()
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return DatasetState(**payload)

    def save(self, state: DatasetState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    def reconcile(self, state: DatasetState, available_dataset_ids: list[str]) -> DatasetState:
        mounted = [dataset_id for dataset_id in state.mounted_dataset_ids if dataset_id in available_dataset_ids]
        current = state.current_dataset_id if state.current_dataset_id in mounted else (mounted[0] if mounted else None)
        return DatasetState(mounted_dataset_ids=mounted, current_dataset_id=current)
