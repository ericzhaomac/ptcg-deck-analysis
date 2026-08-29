# Deck Editor and AI Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent saved-deck editing and AI backend model discovery behind an exactly three-tab frontend while preserving and correcting the existing Analysis experience.

**Architecture:** Add a focused JSON `DeckStore` and REST routes, extend the provider adapter/store without exposing secrets, and split the static frontend into presentation, orchestration, and pure testable behavior. Runtime data is configurable and ignored; tournament packages and dataset state remain immutable.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, httpx, pytest, framework-free HTML/CSS/JavaScript, Node 26 built-in test runner.

**Spec:** `docs/superpowers/specs/2026-08-29-deck-editor-ai-settings-design.md`

## Global Constraints

- Approved Companion option A is authoritative: `PTCG Deck Analysis` header, then a top tab bar with exactly `Analysis`, `Deck Library`, and `AI Backend`; never use a sidebar.
- Do not modify `data/2026`, regenerate tournament datasets, or alter `data/config/dataset_state.json`.
- Never commit secrets, saved decks, provider runtime files, or `.venv`.
- Do not commit or push before coordinator review.
- Every production behavior starts with a failing test and an observed expected failure.
- All commands that run Git, dependencies, tests, or the application use the visible Orca-hosted shell.

---

### Task 1: Runtime configuration and saved-deck store

**Files:**
- Create: `app/deck_store.py`
- Modify: `app/models.py`
- Modify: `app/config.py`
- Modify: `.gitignore`
- Test: `tests/test_deck_store.py`

**Interfaces:**
- Produces: `DeckCard`, `DeckWrite`, and `SavedDeck` Pydantic models.
- Produces: `DeckStore(path).list_decks/get/create/update/duplicate/delete`.
- Produces: `Settings.user_decks_path`, default `data/runtime/decks.json`.

- [ ] Write store tests that independently assert create timestamps/ID, persistence and sorted listing, editing while retaining `created_at`, duplicate naming/new identity, deletion, missing IDs, and invalid card/count/total/duplicate-card validation.
- [ ] Run `orca terminal send ... ".venv/bin/python -m pytest tests/test_deck_store.py -q"` and observe failure because the module/models do not exist.
- [ ] Implement the minimal models/store using UUID4, timezone-aware UTC ISO strings, and atomic same-directory replacement.
- [ ] Run the focused tests and observe all pass.
- [ ] Add `.venv/` and `data/runtime/` ignores, change the local provider default to `data/runtime/provider.json`, and verify Git status lists no runtime artifacts.

### Task 2: Saved-deck REST API

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Test: `tests/test_deck_api.py`

**Interfaces:**
- Consumes: `DeckStore` and saved-deck models from Task 1.
- Produces: `GET/POST /api/v1/decks`, `GET/PUT/DELETE /api/v1/decks/{deck_id}`, and `POST /api/v1/decks/{deck_id}/duplicate`.
- Produces: `create_app(..., user_decks_path=..., provider_config_path=...)` test seams.

- [ ] Write API tests covering empty/list/create/load/edit/rename/duplicate/delete, 404 behavior, and 422 validation.
- [ ] Run the focused API file and observe route failures.
- [ ] Inject `DeckStore` through app composition and add thin route handlers with 201/204 status codes and 404 translation.
- [ ] Run deck store and deck API tests and observe all pass.

### Task 3: Provider settings JSON API and model discovery

**Files:**
- Modify: `app/models.py`
- Modify: `app/providers/openai_compatible.py`
- Modify: `app/api/routes.py`
- Test: `tests/test_provider_config.py`
- Test: `tests/test_openai_compatible_provider.py`
- Test: `tests/test_provider_api.py`

**Interfaces:**
- Produces: `OpenAICompatibleProvider.models_url` and `list_models() -> list[str]`.
- Produces: `GET/PUT /api/v1/provider/settings` and `POST /api/v1/provider/models`.
- Preserves: `GET /api/v1/provider` masked output and legacy `/config` form.

- [ ] Write adapter tests using `httpx.MockTransport` for URL/header parsing, unique sorted IDs, HTTP failures, and malformed payloads.
- [ ] Observe focused adapter test failure, implement discovery, and observe pass.
- [ ] Write config-store tests for atomic persistence and unchanged masking.
- [ ] Observe expected failures, implement atomic save, and observe pass.
- [ ] Write API tests for masked GET, first save requiring a key, blank-key preservation, model discovery with saved settings, and clear 502 errors.
- [ ] Observe route failures, implement JSON routes/error mapping, and observe pass.

### Task 4: Pure frontend behavior and regression coverage

**Files:**
- Create: `app/static/core.mjs`
- Create: `tests/frontend/core.test.mjs`

**Interfaces:**
- Produces: `parseDeckText`, `serializeDeck`, `validateDeck`, `planDatasetMountRequests`, `comparisonCategories`, and `deckTotal`.
- The mount request planner returns `{endpoint, datasetId}` and uses `/unmount` for removals.
- Comparison descriptors cover all six meaningful backend arrays.

- [ ] Write Node tests for parser section/count behavior and errors, serialization round-trip, 60-card validation, mount/unmount endpoint plans, and all six comparison categories.
- [ ] Run `node --test tests/frontend/core.test.mjs` and observe missing-module failure.
- [ ] Implement the minimal pure module and run the focused test to green.
- [ ] Refactor only after green while preserving literal expected outputs.

### Task 5: Approved three-tab frontend, Deck Library, AI Backend, and complete diff UI

**Files:**
- Modify: `app/static/index.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Test: `tests/frontend/core.test.mjs`
- Test: `tests/test_static_app.py`

**Interfaces:**
- Consumes all Task 2/3 APIs and Task 4 pure helpers.
- Produces exactly three accessible top-tab buttons and panels matching the approved Companion visual direction and responsive behavior.
- Shares `state.parsedDeck` between saved-deck selection and Analysis.

- [ ] Write static integration tests asserting the root serves linked split assets, the `PTCG Deck Analysis` header, and exactly the required `Analysis`, `Deck Library`, and `AI Backend` top-tab labels/panels.
- [ ] Run focused Python/static and Node tests and observe failure against the current monolith.
- [ ] Move existing styles/behavior into split files, preserving Analysis selectors/import/chat.
- [ ] Wire `applyMounts` to `planDatasetMountRequests`, check non-OK comparison responses, and render every descriptor from `comparisonCategories` with escaped content.
- [ ] Add the saved-deck library/editor workflow, including search, a complete-list textarea using the shared parser/serializer, total/validation feedback, save/overwrite, rename, duplicate/delete, timestamps, and load-to-Analysis.
- [ ] Add provider settings load/save/discover behavior with blank-key preservation and explicit loading/success/error states.
- [ ] Run focused frontend/static/API tests and observe all pass.

### Task 6: Documentation, full verification, and review handoff

**Files:**
- Modify: `README.md`
- Modify: `docker-compose.yml`

**Interfaces:**
- Documents `USER_DECKS_PATH`, local runtime paths, deck/provider endpoints, and frontend test command.
- Docker sets `USER_DECKS_PATH=/data/runtime/decks.json` while retaining its explicit provider path.

- [ ] Update documentation and Docker environment without touching tournament data or committed dataset state.
- [ ] Run `.venv/bin/python -m pytest` in the Orca shell and confirm zero failures.
- [ ] Run `node --test tests/frontend/*.test.mjs` in the Orca shell and confirm zero failures.
- [ ] Start Uvicorn in a visible Orca terminal with temporary runtime paths, verify `/health`, `/`, deck CRUD, provider masked response, and static assets, then stop it.
- [ ] Inspect `git status --short`, `git diff --check`, `git diff --stat`, and `git diff -- data/2026 data/config/dataset_state.json` in the Orca shell.
- [ ] Confirm no secret-like values or runtime JSON are present in the diff and update the Orca comment to ready for review.
- [ ] Do not commit or push; hand the verified diff to the coordinator.
