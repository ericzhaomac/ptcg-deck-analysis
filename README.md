# PTCG Deck Analysis

Standalone FastAPI service for multi-event PTCG deck-analysis datasets.

## What This Repo Does

- Discovers datasets from a mounted data directory
- Tracks mounted datasets and the current active dataset
- Serves generic metagame summary, compare, and explain APIs
- Supports OpenAI-compatible providers through env vars or a local config file
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
export PROVIDER_CONFIG_PATH=/data/config/provider.json
export OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/
export OPENAI_COMPATIBLE_API_KEY=your_key
export OPENAI_COMPATIBLE_MODEL=kimi-code
```

Notes:

- `DATA_ROOT` defaults to `data`
- `DATASET_STATE_PATH` defaults to `data/config/dataset_state.json`
- `PROVIDER_CONFIG_PATH` points to the persisted provider config file
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
  -e OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/ \
  -e OPENAI_COMPATIBLE_API_KEY=$OPENAI_COMPATIBLE_API_KEY \
  -e OPENAI_COMPATIBLE_MODEL=kimi-code \
  ptcg-deck-analysis
```

The browser config page is available at `http://localhost:8010/api/v1/provider/config`.

## Tests

```bash
PYTHONPATH=. pytest
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
- `GET /api/v1/provider`
- `GET /api/v1/provider/config`
- `POST /api/v1/provider/config`

## Provider Config Safety

`data/config/provider.json` is intentionally kept local and ignored by Git. Store API keys there if you want the browser config page to persist credentials across restarts.

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
