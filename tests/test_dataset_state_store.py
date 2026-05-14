from app.models import DatasetState
from app.services.dataset_state_store import DatasetStateStore


def test_state_store_persists_and_loads(tmp_path):
    store = DatasetStateStore(tmp_path / "dataset_state.json")
    state = DatasetState(mounted_dataset_ids=["2026-prague-ma"], current_dataset_id="2026-prague-ma")
    store.save(state)

    loaded = store.load()
    assert loaded.mounted_dataset_ids == ["2026-prague-ma"]
    assert loaded.current_dataset_id == "2026-prague-ma"


def test_state_reconcile_drops_missing_current(tmp_path):
    store = DatasetStateStore(tmp_path / "dataset_state.json")
    state = DatasetState(mounted_dataset_ids=["missing"], current_dataset_id="missing")
    reconciled = store.reconcile(state, available_dataset_ids=["2026-prague-ma"])

    assert reconciled.mounted_dataset_ids == []
    assert reconciled.current_dataset_id is None
