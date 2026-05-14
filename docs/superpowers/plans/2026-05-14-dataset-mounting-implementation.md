# Dataset Mounting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the standalone deck analysis service into a dataset-aware local service that discovers datasets from `data/`, supports multi-mount + single current dataset, and keeps existing single-dataset analysis working against the selected dataset.

**Architecture:** Add a small dataset layer beside the existing analysis/provider code: a discovery service scans `data/<year>/<event>/<division>/analysis.json`, a state store persists mounted/current dataset ids, and the existing Prague-specific analysis flow is generalized to load by dataset record. API routes split into dataset management and generic analysis endpoints, while keeping current-dataset fallback for the UI.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, unittest, FastAPI TestClient

---

## File map

### Create
- `app/services/dataset_registry_service.py` — scan `data/` and build normalized dataset records
- `app/services/dataset_state_store.py` — persist mounted/current dataset state under `data/config/dataset_state.json`
- `tests/test_dataset_registry_service.py` — discovery + normalization tests
- `tests/test_dataset_state_store.py` — state reconciliation tests
- `tests/test_dataset_api.py` — API tests for mount/current/summary behavior

### Modify
- `app/config.py` — replace Prague-only report path settings with dataset-root and state-path settings
- `app/models.py` — add dataset record, dataset state, and dataset request payload models
- `app/main.py` — wire registry, state store, and generic analysis service into the app
- `app/api/routes.py` — add dataset management routes and generic analysis routes
- `app/services/prague_analysis_service.py` — rename/generalize to dataset-driven analysis loader
- `README.md` — document new dataset directory convention and API usage

### Optional rename during implementation
- `app/services/prague_analysis_service.py` -> `app/services/dataset_analysis_service.py`

If the rename is done, update all imports in `app/main.py`, `app/api/routes.py`, and tests in the same task.

---

### Task 1: Add dataset models and config defaults

**Files:**
- Modify: `app/models.py`
- Modify: `app/config.py`
- Test: `tests/test_dataset_registry_service.py`

- [ ] **Step 1: Write the failing test for settings and dataset id shape**

```python
from app.config import Settings


def test_settings_default_data_root_and_state_path():
    settings = Settings.from_env()
    assert str(settings.data_root).endswith("data")
    assert str(settings.dataset_state_path).endswith("data/config/dataset_state.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_registry_service.py::test_settings_default_data_root_and_state_path -v`
Expected: FAIL with import error or missing `data_root` / `dataset_state_path`

- [ ] **Step 3: Add dataset models and config fields**

Add these model shapes in `app/models.py`:

```python
class DatasetRecord(BaseModel):
    dataset_id: str
    year: int
    event_slug: str
    event_name: str
    division: str
    display_name: str
    dataset_dir: str
    analysis_path: str
    cache_path: str | None = None
    tournament_id: str | None = None
    city: str | None = None
    source_provider: str | None = None


class DatasetState(BaseModel):
    mounted_dataset_ids: list[str] = Field(default_factory=list)
    current_dataset_id: str | None = None


class DatasetIdRequest(BaseModel):
    dataset_id: str
```

Update `app/config.py` to expose:

```python
DEFAULT_DATA_ROOT = Path("data")
DEFAULT_DATASET_STATE_PATH = Path("data/config/dataset_state.json")

@dataclass(frozen=True)
class Settings:
    app_name: str = "Ptcg Deck Analysis Service"
    data_root: Path = DEFAULT_DATA_ROOT
    dataset_state_path: Path = DEFAULT_DATASET_STATE_PATH
    provider_config_path: Path = DEFAULT_PROVIDER_CONFIG_PATH
```

And load env overrides:

```python
data_root=Path(os.getenv("DATA_ROOT", DEFAULT_DATA_ROOT)),
dataset_state_path=Path(os.getenv("DATASET_STATE_PATH", DEFAULT_DATASET_STATE_PATH)),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_dataset_registry_service.py::test_settings_default_data_root_and_state_path -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/config.py tests/test_dataset_registry_service.py
git commit -m "feat: add dataset models and config defaults"
```

---

### Task 2: Implement dataset discovery from the local data directory

**Files:**
- Create: `app/services/dataset_registry_service.py`
- Test: `tests/test_dataset_registry_service.py`

- [ ] **Step 1: Write failing discovery tests**

```python
import json
from pathlib import Path

from app.services.dataset_registry_service import DatasetRegistryService


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
```

```python
def test_discovery_skips_invalid_analysis_json(tmp_path: Path):
    dataset_dir = tmp_path / "2026" / "Broken" / "MA"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "analysis.json").write_text("not-json", encoding="utf-8")

    records = DatasetRegistryService(tmp_path).list_datasets()

    assert records == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dataset_registry_service.py -v`
Expected: FAIL because `DatasetRegistryService` does not exist

- [ ] **Step 3: Write minimal discovery implementation**

Create `app/services/dataset_registry_service.py` with a focused service:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dataset_registry_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/dataset_registry_service.py tests/test_dataset_registry_service.py
git commit -m "feat: add local dataset discovery service"
```

---

### Task 3: Implement mounted/current dataset state persistence

**Files:**
- Create: `app/services/dataset_state_store.py`
- Test: `tests/test_dataset_state_store.py`

- [ ] **Step 1: Write failing state-store tests**

```python
from app.models import DatasetState
from app.services.dataset_state_store import DatasetStateStore


def test_state_store_persists_and_loads(tmp_path):
    store = DatasetStateStore(tmp_path / "dataset_state.json")
    state = DatasetState(mounted_dataset_ids=["2026-prague-ma"], current_dataset_id="2026-prague-ma")
    store.save(state)

    loaded = store.load()
    assert loaded.mounted_dataset_ids == ["2026-prague-ma"]
    assert loaded.current_dataset_id == "2026-prague-ma"
```

```python
def test_state_reconcile_drops_missing_current(tmp_path):
    store = DatasetStateStore(tmp_path / "dataset_state.json")
    state = DatasetState(mounted_dataset_ids=["missing"], current_dataset_id="missing")
    reconciled = store.reconcile(state, available_dataset_ids=["2026-prague-ma"])

    assert reconciled.mounted_dataset_ids == []
    assert reconciled.current_dataset_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dataset_state_store.py -v`
Expected: FAIL because `DatasetStateStore` does not exist

- [ ] **Step 3: Implement the state store**

Create `app/services/dataset_state_store.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dataset_state_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/dataset_state_store.py tests/test_dataset_state_store.py
git commit -m "feat: persist mounted and current dataset state"
```

---

### Task 4: Generalize analysis loading from Prague-only to dataset-aware

**Files:**
- Modify: `app/services/prague_analysis_service.py` or rename to `app/services/dataset_analysis_service.py`
- Modify: `app/main.py`
- Test: `tests/test_dataset_api.py`

- [ ] **Step 1: Write the failing test for current-dataset summary**

```python
import json
from fastapi.testclient import TestClient

from app.main import create_app


def test_summary_uses_current_dataset_from_state(tmp_path):
    prague_dir = tmp_path / "data" / "2026" / "Prague" / "MA"
    prague_dir.mkdir(parents=True)
    (prague_dir / "analysis.json").write_text(json.dumps({
        "source": {"tournament_id": "0062", "division": "MA"},
        "tournament": {"name": "Prague Special Event"},
        "field": {},
        "archetypes": []
    }), encoding="utf-8")
    state_path = tmp_path / "data" / "config" / "dataset_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "mounted_dataset_ids": ["2026-prague-ma"],
        "current_dataset_id": "2026-prague-ma"
    }), encoding="utf-8")

    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))
    response = client.get("/api/v1/analysis/summary")

    assert response.status_code == 200
    assert response.json()["tournament"]["name"] == "Prague Special Event"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_dataset_api.py::test_summary_uses_current_dataset_from_state -v`
Expected: FAIL because generic dataset-aware routes are not wired yet

- [ ] **Step 3: Refactor the analysis service to load by dataset record**

Use this shape for the service class:

```python
class DatasetAnalysisService:
    def load_analysis(self, analysis_path: str | Path) -> dict[str, Any]:
        ...

    def get_summary(self, analysis_path: str | Path) -> dict[str, Any]:
        ...

    def compare_deck(self, analysis_path: str | Path, archetype: str, deck_payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def build_explain_context(self, analysis_path: str | Path, archetype: str | None = None, deck_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ...
```

Update `app/main.py` so `create_app` can take optional overrides:

```python
def create_app(
    data_root: str | Path | None = None,
    dataset_state_path: str | Path | None = None,
) -> FastAPI:
```

And wire:

- `DatasetRegistryService(settings.data_root)`
- `DatasetStateStore(settings.dataset_state_path)`
- `DatasetAnalysisService()`

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_dataset_api.py::test_summary_uses_current_dataset_from_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/services/prague_analysis_service.py tests/test_dataset_api.py
git commit -m "refactor: make analysis service dataset-aware"
```

---

### Task 5: Add dataset management API routes

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/models.py`
- Test: `tests/test_dataset_api.py`

- [ ] **Step 1: Write failing mount/current API tests**

```python
def test_datasets_endpoint_lists_available_and_state(tmp_path):
    # arrange dataset files + empty state
    ...
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))

    response = client.get("/api/v1/datasets")

    assert response.status_code == 200
    assert response.json()["datasets"][0]["dataset_id"] == "2026-prague-ma"
```

```python
def test_mount_then_set_current(tmp_path):
    # arrange one dataset
    ...
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))

    mount_response = client.post("/api/v1/datasets/mount", json={"dataset_id": "2026-prague-ma"})
    current_response = client.post("/api/v1/datasets/current", json={"dataset_id": "2026-prague-ma"})

    assert mount_response.status_code == 200
    assert current_response.status_code == 200
    assert current_response.json()["current_dataset_id"] == "2026-prague-ma"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dataset_api.py -v`
Expected: FAIL because dataset management endpoints do not exist

- [ ] **Step 3: Implement dataset routes and state mutation**

Add route helpers in `app/api/routes.py` for:

```python
@router.get("/api/v1/datasets")
def list_datasets(): ...

@router.get("/api/v1/datasets/mounted")
def list_mounted(): ...

@router.post("/api/v1/datasets/mount")
def mount_dataset(request: DatasetIdRequest): ...

@router.post("/api/v1/datasets/unmount")
def unmount_dataset(request: DatasetIdRequest): ...

@router.post("/api/v1/datasets/current")
def set_current_dataset(request: DatasetIdRequest): ...
```

Implementation rules:

- only mount available datasets
- `set_current_dataset` rejects unmounted ids with 400
- unmounting the current dataset clears current or falls back to the first remaining mounted dataset
- every mutation saves reconciled state through `DatasetStateStore`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dataset_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py app/models.py tests/test_dataset_api.py
git commit -m "feat: add dataset mount and current selection APIs"
```

---

### Task 6: Switch summary/compare/explain routes to generic analysis endpoints

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/models.py`
- Test: `tests/test_dataset_api.py`

- [ ] **Step 1: Write failing tests for explicit dataset override**

```python
def test_summary_accepts_explicit_dataset_id(tmp_path):
    # arrange Prague + LA datasets and no current state
    ...
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=state_path))

    response = client.get("/api/v1/analysis/summary", params={"dataset_id": "2026-los-angeles-ma"})

    assert response.status_code == 200
    assert response.json()["tournament"]["name"] == "Los Angeles Regional"
```

```python
def test_summary_without_current_or_dataset_id_returns_400(tmp_path):
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=tmp_path / "data/config/dataset_state.json"))
    response = client.get("/api/v1/analysis/summary")
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dataset_api.py -v`
Expected: FAIL because routes still use Prague-only endpoint paths or require a fixed report path

- [ ] **Step 3: Implement generic analysis route resolution**

Add a request model or query parameter support so route handlers resolve the active dataset by:

1. explicit `dataset_id` if provided
2. otherwise reconciled `current_dataset_id`
3. otherwise return 400

Target route names:

```python
GET /api/v1/analysis/summary
POST /api/v1/analysis/compare
POST /api/v1/analysis/explain
```

For POST payloads, extend request models with optional `dataset_id`:

```python
class DeckCompareRequest(BaseModel):
    dataset_id: str | None = None
    archetype: str
    deck: dict[str, list[dict[str, Any]]]
```

```python
class ExplainRequest(BaseModel):
    dataset_id: str | None = None
    question: str
    archetype: str | None = None
    deck: dict[str, list[dict[str, Any]]] | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dataset_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py app/models.py tests/test_dataset_api.py
git commit -m "feat: add generic dataset-aware analysis endpoints"
```

---

### Task 7: Preserve provider config page behavior while removing Prague-only hardcoding

**Files:**
- Modify: `app/api/routes.py`
- Modify: `README.md`
- Test: `tests/test_dataset_api.py`

- [ ] **Step 1: Write failing provider route tests**

```python
def test_provider_page_redirect_still_works(tmp_path):
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=tmp_path / "data/config/dataset_state.json"))
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {200, 307}
```
```

def test_provider_config_endpoint_exists(tmp_path):
    client = TestClient(create_app(data_root=tmp_path / "data", dataset_state_path=tmp_path / "data/config/dataset_state.json"))
    response = client.get("/api/v1/provider/config")
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dataset_api.py -v`
Expected: FAIL because provider routes still live under Prague-only paths

- [ ] **Step 3: Move provider config routes to neutral paths and update docs**

Use neutral provider paths:

```python
GET /api/v1/provider
GET /api/v1/provider/config
POST /api/v1/provider/config
```

Update app root redirect to `/api/v1/provider/config`.

Update `README.md` examples so they use:

- dataset directory convention
- `DATA_ROOT`
- `DATASET_STATE_PATH`
- generic analysis endpoints
- neutral provider config endpoint

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dataset_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py app/main.py README.md tests/test_dataset_api.py
git commit -m "refactor: move provider config to neutral API paths"
```

---

### Task 8: Final verification sweep

**Files:**
- Modify: any touched files from previous tasks if fixes are needed
- Test: `tests/test_dataset_registry_service.py`
- Test: `tests/test_dataset_state_store.py`
- Test: `tests/test_dataset_api.py`

- [ ] **Step 1: Run focused unit tests**

Run: `python -m pytest tests/test_dataset_registry_service.py tests/test_dataset_state_store.py tests/test_dataset_api.py -v`
Expected: all PASS

- [ ] **Step 2: Run full service tests if legacy tests remain**

Run: `python -m pytest -v`
Expected: PASS, or document any legacy test path updates needed after the service rename

- [ ] **Step 3: Smoke-test app creation against the real local data directory**

Run:

```bash
python - <<'PY'
from app.main import create_app
app = create_app()
print(app.title)
PY
```

Expected output:

```text
Ptcg Deck Analysis Service
```

- [ ] **Step 4: Commit final cleanup if any test-driven fixes were needed**

```bash
git add app tests README.md
git commit -m "test: verify dataset mounting service end to end"
```

---

## Self-review

### Spec coverage

Covered:
- directory-based dataset discovery — Task 2
- mounted/current state persistence — Task 3
- single current dataset behavior — Tasks 4 and 6
- multi-mount dataset management API — Task 5
- future-neutral provider/config API surface — Task 7
- test and reconciliation behavior — Tasks 2, 3, 6, 8

Not implemented yet by design:
- cross-dataset comparison endpoint
- dataset download/generation pipeline
- SR/JR-specific functionality beyond compatible directory structure

### Placeholder scan

Removed vague “add validation later” language. Each task contains exact file paths, commands, and code targets.

### Type consistency

Planned shared names:
- `DatasetRecord`
- `DatasetState`
- `DatasetIdRequest`
- `DatasetRegistryService`
- `DatasetStateStore`
- `DatasetAnalysisService`

Use these names consistently during implementation, especially if `prague_analysis_service.py` is renamed.
