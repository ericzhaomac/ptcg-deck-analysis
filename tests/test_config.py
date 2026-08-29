from pathlib import Path

from app.config import Settings


def test_local_runtime_files_default_to_explicit_ignored_paths(monkeypatch):
    monkeypatch.delenv("PROVIDER_CONFIG_PATH", raising=False)
    monkeypatch.delenv("USER_DECKS_PATH", raising=False)

    settings = Settings.from_env()

    assert settings.provider_config_path == Path("data/runtime/provider.json")
    assert settings.user_decks_path == Path("data/runtime/decks.json")


def test_runtime_paths_can_be_overridden(monkeypatch, tmp_path):
    provider_path = tmp_path / "provider.json"
    decks_path = tmp_path / "decks.json"
    monkeypatch.setenv("PROVIDER_CONFIG_PATH", str(provider_path))
    monkeypatch.setenv("USER_DECKS_PATH", str(decks_path))

    settings = Settings.from_env()

    assert settings.provider_config_path == provider_path
    assert settings.user_decks_path == decks_path
