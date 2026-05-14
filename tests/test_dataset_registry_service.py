from app.config import Settings


def test_settings_default_data_root_and_state_path():
    settings = Settings.from_env()
    assert str(settings.data_root).endswith("data")
    assert str(settings.dataset_state_path).endswith("data/config/dataset_state.json")
