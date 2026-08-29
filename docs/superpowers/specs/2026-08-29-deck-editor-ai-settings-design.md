# Deck Editor and AI Settings Design

## Goal

Extend the existing FastAPI and framework-free frontend with exactly three top-level tabs: Analysis, Deck Library, and AI Backend. Preserve the Analysis workflow while adding persistent saved decks, OpenAI-compatible model discovery, the dataset unmount correction, and complete Deck Diff rendering.

The approved Companion brainstorming artifacts are the frontend source of truth:

- `/Users/ttest/.openclaw/workspace/user_created/temp/docs/deck-library-wireframe/.superpowers/brainstorm/27249-1787981704/content/navigation-layout.html`
- `/Users/ttest/.openclaw/workspace/user_created/temp/docs/deck-library-wireframe/.superpowers/brainstorm/29634-1787981836/content/navigation-layout-orca.html`

Use approved option A: a `PTCG Deck Analysis` header, immediately followed by the top tab bar. Preserve the wireframe's compact horizontal tabs, bordered content surface, blue active state, light neutral visual direction, and mobile-friendly wrapping. Do not introduce sidebar navigation.

## Constraints

- Do not modify `data/2026`, regenerate tournament data, or change committed dataset state.
- Do not commit provider credentials, saved decks, virtual environments, or other runtime state.
- Do not commit or push this feature before coordinator review.
- Keep the existing Analysis API and user workflow compatible.
- Use test-driven development for every behavior change.

## Backend Design

Saved decks are stored as one JSON document at `USER_DECKS_PATH`, defaulting to `data/runtime/decks.json`. The store owns atomic persistence, UUID identifiers, UTC timestamps, and create/list/get/update/duplicate/delete operations. A saved deck has `id`, `name`, `created_at`, `updated_at`, and the three parser-compatible sections `pokemon`, `trainer`, and `energy`. Counts must be positive integers no greater than 60, names must be non-empty, section/card combinations must be unique, and the whole list cannot exceed 60 cards. Empty decks are allowed so a user can create and then build a list incrementally.

The deck API lives at `/api/v1/decks`. It exposes collection GET/POST and item GET/PUT/DELETE plus `POST /{deck_id}/duplicate`. Missing IDs return 404 and invalid payloads return FastAPI's structured 422 response.

Provider settings continue to use `ProviderConfigStore` and masked responses. JSON settings are exposed separately from the legacy HTML form so existing behavior remains compatible. Saving a blank key preserves an existing saved key; first-time configuration still requires a key. Model discovery calls `<normalized-base-url>/models` with bearer authentication, returns sorted unique IDs, and maps provider/network/malformed-response failures to a clear 502 API error.

## Frontend Design

The document has a `PTCG Deck Analysis` header with a separate tab bar immediately below it containing exactly three buttons. Each button selects one tab panel without navigating away. The Analysis panel retains dataset selection, saved-deck selection or transient deck import, comparison, and AI explain/chat. Selecting a saved deck in Deck Library loads it into the shared in-memory parsed deck and serialized Analysis textarea, so comparison/chat work without another paste.

Deck Library provides search plus a library list and editor with deck name, timestamps, and the same complete-decklist textarea interaction as Analysis import. Users paste or edit one parser-compatible list, explicitly parse and validate it, see total-card feedback, then save or overwrite it. Loading a saved deck populates that textarea through the shared serializer. Load-to-Analysis, rename, duplicate, and delete remain available. API errors are shown in the tab rather than alerts where practical.

AI Backend provides provider status, Base URL, masked API-key behavior, manual model input, discovered-model selection/connection check, save, and explicit loading/success/error states. The API key field is never populated from a masked response.

The previous monolithic static document is split into `index.html`, `styles.css`, `core.mjs`, and `app.js`. Pure frontend behavior in `core.mjs` is exercised with Node's built-in test runner. Dataset mount operations are planned by a pure function that sends removals to `/api/v1/datasets/unmount`. Deck Diff rendering is driven by a six-category descriptor covering missing core, underplayed core, missing common, overplayed, tech deviations, and extra cards.

## Runtime Paths

- Saved decks: `data/runtime/decks.json` by default, configurable with `USER_DECKS_PATH`.
- Provider settings: `data/runtime/provider.json` by default, configurable with `PROVIDER_CONFIG_PATH`; Docker continues to set an explicit `/data/config/provider.json` path.
- `data/runtime/`, legacy `data/config/provider.json`, and `.venv/` are ignored.

## Verification

- Python service/store/API/provider tests via `.venv/bin/python -m pytest`.
- Frontend unit tests via `node --test tests/frontend/*.test.mjs`.
- Application smoke run through the Orca-hosted shell and browser/API checks against a temporary runtime path.
- Final Git diff/status inspection through the Orca-hosted shell, including confirmation that `data/2026` and `data/config/dataset_state.json` are untouched.
