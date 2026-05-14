import json
from pathlib import Path

from app.config import Settings
from app.services.dataset_registry_service import DatasetRegistryService


def test_settings_default_data_root_and_state_path():
    settings = Settings.from_env()
    assert str(settings.data_root).endswith("data")
    assert str(settings.dataset_state_path).endswith("data/config/dataset_state.json")


def test_discovery_builds_dataset_records(tmp_path: Path):
    dataset_dir = tmp_path / "2026" / "Los_Angeles" / "MA"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "analysis.json").write_text(json.dumps({
        "source": {"provider": "Limitless Labs", "tournament_id": "0063", "division": "MA"},
        "tournament": {"city": "Los Angeles"}
    }), encoding="utf-8")

    records = DatasetRegistryService(tmp_path).list_datasets()

    assert len(records) == 1
    assert records[0].dataset_id == "2026-los-angeles-ma"
    assert records[0].display_name == "2026 Los Angeles / MA"


def test_discovery_skips_invalid_analysis_json(tmp_path: Path):
    dataset_dir = tmp_path / "2026" / "Broken" / "MA"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "analysis.json").write_text("not-json", encoding="utf-8")

    records = DatasetRegistryService(tmp_path).list_datasets()

    assert records == []
