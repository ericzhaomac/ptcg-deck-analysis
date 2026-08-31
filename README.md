# PTCG Deck Analysis

Standalone FastAPI service for multi-event PTCG deck-analysis datasets.

## What This Repo Does

- Discovers datasets from a mounted data directory
- Tracks mounted datasets and the current active dataset
- Serves generic metagame summary, compare, and explain APIs
- Supports OpenAI-compatible providers through env vars or a local config file
- Saves reusable deck lists by pasting, parsing, and validating a complete list in the local Deck Library
- Discovers available models from an OpenAI-compatible provider
- Ships with curated 2026 Limitless Labs MA datasets

## Included Datasets

- Prague: `2026-prague-ma` (`0062`)
- Los Angeles: `2026-los-angeles-ma` (`0063`)
- Utrecht: `2026-utrecht-ma` (`0064`)
- Campinas: `2026-campinas-ma` (`0065`)
- Melbourne: `2026-melbourne-ma` (`0066`)
- Lima: `2026-lima-ma` (`0067`)
- Indianapolis: `2026-indianapolis-ma` (`0068`)
- Turin: `2026-turin-ma` (`0069`)
- New Orleans: `2026-new-orleans-ma` (`0070`)

The current mounted/current dataset state lives in `data/config/dataset_state.json`.

## Project Layout

- `app/main.py`: FastAPI entrypoint
- `app/api/routes.py`: API routes and provider config page
- `app/config.py`: environment-backed app configuration
- `app/provider_config.py`: provider config file read/write and masking
- `app/deck_store.py`: validated local saved-deck persistence
- `app/services/dataset_analysis_service.py`: dataset loading and analysis logic
- `app/providers/openai_compatible.py`: OpenAI-compatible provider adapter
- `scripts/tools/limitless_tournament_analysis.py`: Limitless Labs dataset generator
- `scripts/tools/test_*.py`: script-level tests

## Dataset Layout

Datasets are discovered under `DATA_ROOT` using this structure:

```text
DATA_ROOT/
  <year>/
    <event>/
      <division>/
        analysis.json
        cache/
          tournament.json
          decks.json
          standings.json
          decklists/
            <tp_id>.json
          pairings/
            round-<nn>.json
          matchups/
            <variant_id>.json
          snapshots/
            <tournament_id>-<division>-<content_hash>/
              manifest.json
              ...verified source resources...
          verified-snapshot.json
```

Example:

```text
data/2026/Melbourne/MA/analysis.json
```

This is discovered as dataset id `2026-melbourne-ma`.

## Updating Tournament Data

Use the existing Limitless Labs pipeline with an event-specific cache directory. The flat cache layout matches the dataset structure above:

```bash
PYTHONPATH=. python3 scripts/tools/limitless_tournament_analysis.py \
  --tournament-id 0070 \
  --division MA \
  --cache-dir data/2026/New_Orleans/MA/cache \
  --flat-cache \
  --output-json data/2026/New_Orleans/MA/analysis.json
```

Successful responses are cached individually and written atomically. Re-running the same command reuses valid cache files and retries only missing, invalid, or unsuccessful responses. Keep each tournament in its own cache directory, verify its `analysis.json`, and then add its dataset id to `data/config/dataset_state.json` without changing a valid existing `current_dataset_id`.

Tournament Reports use a separate immutable snapshot promotion step. Refresh a completed event through the adapter, then verify the promoted snapshot entirely offline:

```bash
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py \
  --tournament-id 0070 \
  --division MA \
  --dataset-dir data/2026/New_Orleans/MA

PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py \
  --tournament-id 0070 \
  --division MA \
  --dataset-dir data/2026/New_Orleans/MA \
  --verify-only
```

The refresh promotes `cache/verified-snapshot.json` only after schema validation and exact local/source reconciliation pass. `--verify-only` performs no HTTP requests and reports the snapshot version, phase boundary, issue codes, and eligible family/variant counts.

### Season Update Convention

- Keep completed seasons immutable: do not overwrite or remove an existing tournament dataset when starting a new season.
- Store each tournament under `data/<year>/<Event_Name>/<division>/`, with `analysis.json` and its event-specific `cache/` kept together.
- Use dataset ids in the form `<year>-<event-slug>-<division-lowercase>` and record the Limitless tournament id beside the event in **Included Datasets**.
- For each new tournament, generate and verify `analysis.json`, add the dataset id to `mounted_dataset_ids`, and set `current_dataset_id` to the newest verified tournament only when intentionally advancing the default view.
- Treat New Orleans (`0070`) as the penultimate 2026 event. Complete and tag the 2026 season only after adding the 2026 World Championships (WCS); classify every tournament after WCS as part of the 2027 season.
- Start 2027 datasets under `data/2027/`; keep the 2026 datasets mounted for cross-event and cross-season access.
- Update **Included Datasets** and `data/config/dataset_state.json` in the same commit as the new tournament data.

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Useful env vars:

```bash
export DATA_ROOT=/data
export DATASET_STATE_PATH=/data/config/dataset_state.json
export PROVIDER_CONFIG_PATH=data/runtime/provider.json
export USER_DECKS_PATH=data/runtime/decks.json
export OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/
export OPENAI_COMPATIBLE_API_KEY=your_key
export OPENAI_COMPATIBLE_MODEL=kimi-code
```

Notes:

- `DATA_ROOT` defaults to `data`
- `DATASET_STATE_PATH` defaults to `data/config/dataset_state.json`
- `PROVIDER_CONFIG_PATH` points to the persisted provider config file and defaults locally to the ignored `data/runtime/provider.json`
- `USER_DECKS_PATH` points to the saved-deck library and defaults to the ignored `data/runtime/decks.json`
- `POST /api/v1/analysis/explain` reads `PROVIDER_CONFIG_PATH` first, then falls back to env vars

## Docker

Build:

```bash
docker build -t ptcg-deck-analysis .
```

Run:

```bash
docker run --rm -p 8010:8010 \
  -v $(pwd)/data:/data \
  -e DATA_ROOT=/data \
  -e DATASET_STATE_PATH=/data/config/dataset_state.json \
  -e PROVIDER_CONFIG_PATH=/data/config/provider.json \
  -e USER_DECKS_PATH=/data/runtime/decks.json \
  -e OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/ \
  -e OPENAI_COMPATIBLE_API_KEY=$OPENAI_COMPATIBLE_API_KEY \
  -e OPENAI_COMPATIBLE_MODEL=kimi-code \
  ptcg-deck-analysis
```

The application at `http://localhost:8010/` has four top tabs: Analysis, Deck Library, Tournament Reports, and AI Backend. Tournament Reports provides independent Phase 1 and Phase 2 family Top 10 meta-share modules, an expandable family ranking, inline family-to-variant drill-down, per-module phase controls, and portrait PNG export. The legacy provider config page remains available at `http://localhost:8010/api/v1/provider/config`.

Tournament matchup bars require at least 30 observed matches and support Overall, Phase 1, and Phase 2 views. The reconciled unique round boundary defines Phase 1/Phase 2; Top Cut pairings are removed only when explicit pairing-stage metadata exists, otherwise that limitation is disclosed. Phase 1 and Phase 2 deck-composition categories require at least 10 valid lists and 60% list coverage. Top Cut classifies any non-zero valid-list sample and labels fewer than 10 valid lists `Small sample — descriptive only`. Phase 2 composition compares with Phase 1, and Top Cut compares descriptively with Phase 2; `More common`/`Less common` requires a 15 percentage-point appearance-rate change. Source `topcut=1` is authoritative and may include play-in entrants, not only a final Top 8. Win rate uses `(wins + ties / 3) / (wins + losses + ties)`. Every exported module is a fixed 1080×1350 PNG, uses canonical server order rather than transient table sorting, and is blocked unless the exact module state and snapshot version are ready.

## Development Worktrees and UI Review

- `main` is the integration and formal Docker deployment checkout. Port `8010` belongs to the service built from merged `main`.
- `tournament-data-updates` is the persistent worktree for future tournament dataset updates. Generate and verify data there, then merge it into `main` through the normal non-force workflow.
- New application features use dedicated, temporary feature worktrees based on a clean `main`.
- Before acceptance, run feature previews on an unused non-`8010` port; do not replace the formal service.
- If the Orca pane cannot render or scroll the complete UI, use the `orca-companion-ui-preview` skill. Companion is a temporary authenticated wrapper, not part of the formal deployment.
- After acceptance, verify and push the feature, integrate it into `main`, rebuild and smoke-test `8010`, then stop preview/Companion processes and remove obsolete local worktrees only after their commits are preserved remotely.

## Tests

```bash
PYTHONPATH=. pytest
node --test tests/frontend/*.test.mjs
```

## API Surface

- `GET /health`
- `GET /api/v1/datasets`
- `GET /api/v1/datasets/mounted`
- `POST /api/v1/datasets/mount`
- `POST /api/v1/datasets/unmount`
- `POST /api/v1/datasets/current`
- `GET /api/v1/analysis/summary`
- `POST /api/v1/analysis/compare`
- `POST /api/v1/analysis/explain`
- `GET /api/v1/decks`
- `POST /api/v1/decks`
- `GET /api/v1/decks/{deck_id}`
- `PUT /api/v1/decks/{deck_id}`
- `POST /api/v1/decks/{deck_id}/duplicate`
- `DELETE /api/v1/decks/{deck_id}`
- `GET /api/v1/provider`
- `GET /api/v1/provider/settings`
- `PUT /api/v1/provider/settings`
- `POST /api/v1/provider/models`
- `GET /api/v1/provider/config`
- `POST /api/v1/provider/config`
- `GET /api/v1/tournament-reports`
- `GET /api/v1/tournament-reports/{dataset_id}`
- `GET /api/v1/tournament-reports/{dataset_id}/families/{family_id}`
- `GET /api/v1/tournament-reports/{dataset_id}/variants/{variant_id}`

## Provider Config Safety

`data/runtime/` and the legacy `data/config/provider.json` are intentionally ignored by Git. Provider API keys and user deck lists are plaintext local runtime state; keep them out of commits and secure the host filesystem appropriately. Docker uses explicit paths under its `/data` volume.

## Compare Request Example

```json
{
  "dataset_id": "2026-prague-ma",
  "archetype": "Dragapult",
  "deck": {
    "pokemon": [{"name": "Dreepy", "count": 4}],
    "trainer": [{"name": "Buddy-Buddy Poffin", "count": 4}],
    "energy": [{"name": "Psychic Energy", "count": 3}]
  }
}
```

`dataset_id` is optional when a current dataset is already mounted.
