from __future__ import annotations

from pathlib import Path

import pytest

from app.provider_config import ProviderConfigStore


def test_provider_config_round_trip_masks_key_without_exposing_it(tmp_path):
    path = tmp_path / "runtime" / "provider.json"
    store = ProviderConfigStore(path)

    saved = store.save(base_url=" https://provider.test/v1 ", api_key=" 1234567890abcdef ", model=" model-a ")
    loaded = store.load()

    assert loaded == saved
    assert loaded.base_url == "https://provider.test/v1"
    assert loaded.model == "model-a"
    assert loaded.masked()["api_key"] == "1234********cdef"
    assert "1234567890abcdef" not in str(loaded.masked())


def test_provider_config_atomic_write_preserves_old_value_if_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "provider.json"
    store = ProviderConfigStore(path)
    store.save(base_url="https://old.test/v1", api_key="old-secret", model="old-model")

    def fail_replace(self: Path, target: Path):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.save(base_url="https://new.test/v1", api_key="new-secret", model="new-model")

    assert store.load().base_url == "https://old.test/v1"
    assert store.load().model == "old-model"
