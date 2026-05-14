# PTCG Deck Analysis — Dataset Mounting Design

## Goal

Refactor the current Prague-specific deck analysis service into a dataset-aware local service that:

1. discovers local tournament datasets from a fixed directory convention
2. supports mounting multiple datasets at the same time
3. keeps one current dataset as the active analysis context
4. preserves single-dataset analysis as the default behavior
5. supports future cross-dataset meta comparison without merging datasets into one pool

This phase does **not** add Limitless downloading, dataset generation, or mutation of the raw local datasets.

---

## Scope

### In scope

- independent project under `~/Documents/projects/ptcg-deck-analysis/`
- local dataset discovery from existing files
- dataset registry built by scanning the local data directory
- mounted dataset state persistence
- current dataset state persistence
- dataset-aware summary / compare / explain flow
- future-ready API boundary for cross-dataset meta comparison

### Out of scope

- downloading from Limitless inside Docker
- editing or regenerating raw dataset contents
- automatic dataset normalization from arbitrary raw files
- merging multiple datasets into one shared summary baseline
- SR / JR support implementation beyond directory compatibility

---

## Dataset model

A dataset is defined as one tournament + one division.

Examples:

- `2026 Prague / MA`
- `2026 Prague / JR`
- `2026 Los Angeles / MA`

This is the user-facing unit shown in the left sidebar and used for mounting.

Internally, each dataset record should include at least:

- `dataset_id`
- `year`
- `event_slug`
- `event_name`
- `division`
- `display_name`
- `dataset_dir`
- `analysis_path`
- `cache_path`
- `tournament_id` (if available from analysis JSON)
- `city` (if available from analysis JSON)
- `source_provider` (if available)

### Dataset identity

`dataset_id` format:

- `<year>-<event-slug>-<division-lower>`

Examples:

- `2026-prague-ma`
- `2026-los-angeles-ma`

`event_slug` should be normalized from the directory name:

- `Prague` -> `prague`
- `Los_Angeles` -> `los-angeles`

`display_name` should be human-friendly:

- `2026 Prague / MA`
- `2026 Los Angeles / MA`

---

## Directory convention

The service discovers datasets by scanning this structure:

```text
data/<year>/<event>/<division>/analysis.json
data/<year>/<event>/<division>/cache/
```

Examples:

```text
data/2026/Prague/MA/analysis.json
data/2026/Prague/MA/cache/
data/2026/Los_Angeles/MA/analysis.json
data/2026/Los_Angeles/MA/cache/
```

### Rules

- a directory counts as a valid dataset only if `analysis.json` exists
- `cache/` is optional for discovery but expected for full local dataset packaging
- the service must not rewrite any files inside the dataset directories
- the service only reads from dataset directories

---

## Discovery strategy

Use directory scanning, not a manually maintained registry file.

### Why

- matches the desired hot-plug workflow
- avoids duplicating metadata by hand
- lets future datasets appear by simply adding folders
- keeps the service focused on consuming local datasets rather than managing imports

### Discovery algorithm

For each path matching:

```text
data/*/*/*/analysis.json
```

The service should:

1. parse `year`, `event`, and `division` from the path
2. load `analysis.json`
3. extract metadata where available
4. construct a normalized dataset record
5. include the dataset in the available registry

If `analysis.json` is invalid or unreadable, skip that dataset and surface the issue in diagnostics.

---

## State model

Separate three concepts clearly:

1. **available datasets** — discovered on disk
2. **mounted datasets** — selected for active use in the UI
3. **current dataset** — the single active context for summary / compare / explain

### State persistence

Persist mount state in:

```text
data/config/dataset_state.json
```

Example:

```json
{
  "mounted_dataset_ids": [
    "2026-prague-ma",
    "2026-los-angeles-ma"
  ],
  "current_dataset_id": "2026-prague-ma"
}
```

### State rules

- `mounted_dataset_ids` may contain multiple dataset ids
- `current_dataset_id` must be one of the mounted dataset ids
- if persisted `current_dataset_id` is missing from the mounted set, clear it or reset to the first mounted dataset
- if a mounted dataset no longer exists on disk, drop it from effective state
- if no datasets are mounted, current dataset is `null`

---

## Analysis behavior

### Single-dataset analysis remains primary

All existing core analysis flows remain scoped to one dataset:

- summary
- user deck compare
- explain

This avoids mixing tournament contexts and keeps the current Prague-first logic easy to generalize.

### Multiple mounts do not imply merged analysis

Mounting multiple datasets means:

- they are available side by side
- the user can switch quickly between them
- future comparisons may reference them together

It does **not** mean:

- auto-merging them into one meta
- combining archetype shares by default
- building one explain context from several tournaments unless an explicit compare feature does so

---

## API design

### Dataset management

#### `GET /api/v1/datasets`
Returns all discovered datasets plus effective mounted/current state.

#### `GET /api/v1/datasets/mounted`
Returns mounted datasets only.

#### `POST /api/v1/datasets/mount`
Input:

```json
{ "dataset_id": "2026-prague-ma" }
```

Behavior:
- add to mounted set if available
- idempotent if already mounted

#### `POST /api/v1/datasets/unmount`
Input:

```json
{ "dataset_id": "2026-prague-ma" }
```

Behavior:
- remove from mounted set
- if it was current, clear current or fall back to another mounted dataset

#### `POST /api/v1/datasets/current`
Input:

```json
{ "dataset_id": "2026-los-angeles-ma" }
```

Behavior:
- set current dataset
- reject if dataset is not mounted

### Single-dataset analysis endpoints

Current Prague-specific endpoints should be generalized to dataset-aware routes.

Recommended shape:

- `GET /api/v1/analysis/summary`
- `POST /api/v1/analysis/compare`
- `POST /api/v1/analysis/explain`

Each should support either:

- explicit `dataset_id`, or
- fallback to persisted current dataset

Recommendation:
- support explicit `dataset_id` in backend logic
- UI defaults to current dataset

This keeps server behavior precise and easier to test.

### Future cross-dataset comparison

Reserve a separate endpoint family, for example:

- `POST /api/v1/datasets/compare-meta`

This feature should compare datasets side by side rather than merging them.

Expected future outputs:

- archetype share changes
- rank shifts
- day-2 conversion changes
- changes in top-finishing archetypes
- optional card trend changes for a selected archetype

---

## UI design

### Left sidebar

The sidebar should show available datasets and allow:

- mount / unmount
- current dataset selection

Each item shows:

- display name, e.g. `2026 Prague / MA`
- mounted state
- current state

### Main analysis area

The main area always reflects the current dataset:

- summary
- archetype analysis
- user deck comparison
- explain output

### Future compare area

A separate compare panel can later let the user select 2+ mounted datasets and request side-by-side trend/meta comparisons.

This compare area should be conceptually separate from the primary single-dataset workflow.

---

## Service refactor plan

The current code is Prague-specific:

- Prague-specific route prefix
- Prague-specific service naming
- Prague-specific config page paths

This should be refactored toward neutral naming.

### Suggested internal refactor

- `PragueAnalysisService` -> `DatasetAnalysisService`
- replace Prague-only path assumptions with a dataset loader abstraction
- introduce:
  - dataset discovery service
  - dataset state store
  - dataset registry model

### Minimal architecture

- `app/services/dataset_registry_service.py`
- `app/services/dataset_state_store.py`
- `app/services/dataset_analysis_service.py`
- `app/models.py` expanded for dataset records and state payloads
- existing provider config pieces reused with minimal change

---

## Error handling

### Discovery errors

If a dataset directory is malformed:

- skip it from available datasets
- include a warning in diagnostics/logs
- do not crash the whole app

### State errors

If persisted mounted/current ids reference missing datasets:

- reconcile state automatically on load
- remove invalid mounted ids
- clear invalid current id

### Analysis errors

If no current dataset exists and no `dataset_id` is provided:

- return a clear 400-level error explaining that no active dataset is selected

If a requested `dataset_id` is unknown:

- return 404

---

## Testing strategy

Minimum validation for this phase:

1. discovery finds Prague and Los Angeles datasets from the new directory structure
2. dataset ids and display names normalize correctly
3. mount/unmount/current state persists correctly
4. current dataset fallback works when state becomes invalid
5. summary/compare/explain read from the requested or current dataset
6. malformed dataset directories are skipped safely

---

## Why this design

This design keeps the system aligned with the real workflow:

- datasets are prepared outside the service
- the service consumes stable local analysis packages
- users can mount several datasets without forcing merged analysis
- current analysis remains simple and precise
- cross-dataset comparison has a clean future extension path

In short:

- **display unit** = tournament + division
- **storage unit** = local dataset directory
- **active analysis unit** = one current dataset
- **future comparison unit** = explicit side-by-side comparison, not hidden merging
