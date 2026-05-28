# PTCG Deck Analysis — Dataset Selector UI Design

## Goal

Add a left-side dataset selector UI to the existing deck analysis page so the user can:

1. see all locally discovered datasets
2. mount and unmount datasets from the browser
3. select exactly one current dataset from the mounted set
4. keep the existing deck-analysis workflow pointed at the current dataset
5. preserve the imported deck while switching dataset context

This phase only connects the selector UI to the already implemented dataset APIs. It does not add multi-dataset trend comparison UI yet.

---

## Scope

### In scope

- update the existing static web UI in `app/static/index.html`
- render available datasets and mounted datasets in the left column
- allow mount/unmount via checkbox controls
- allow current dataset selection via radio controls
- reload summary/archetypes when current dataset changes
- preserve the deck input and parsed deck when switching current dataset
- clear compare result and chat status when current dataset changes
- update provider links and page wording to dataset-aware wording

### Out of scope

- cross-dataset comparison UI
- dataset upload/import UI
- dataset editing UI
- automatic polling or file-watch refresh
- a framework migration or multi-page frontend refactor

---

## Why this shape

The backend now has three distinct concepts:

1. available datasets
2. mounted datasets
3. current dataset

The UI should reflect those concepts directly instead of inventing a different model. This reduces frontend logic and keeps the user mental model aligned with the API.

---

## Layout

Keep the existing three-column layout.

### Left column

Split the left column into two stacked sections:

1. **Dataset Selector**
2. **Current Dataset Meta Summary**

### Center column

Keep the current deck import / parse / compare flow.

### Right column

Keep the current AI chat panel.

This avoids a page-wide redesign while still making dataset selection a first-class workflow.

---

## Dataset Selector UI

The selector section contains two blocks.

### 1. Available Datasets

Purpose:
- show every dataset discovered by `GET /api/v1/datasets`
- let the user mount or unmount datasets

Presentation per row:
- checkbox
- dataset display name, e.g. `2026 Prague / MA`
- optional small metadata line if useful later (city, tournament id), but not required in the first pass

Behavior:
- checked = dataset is mounted
- unchecked = dataset is not mounted
- checking a row calls `POST /api/v1/datasets/mount`
- unchecking a row calls `POST /api/v1/datasets/unmount`

### 2. Mounted Datasets

Purpose:
- show only mounted datasets
- let the user select exactly one current dataset

Presentation per row:
- radio input
- dataset display name

Behavior:
- selected radio = current dataset
- selecting a radio calls `POST /api/v1/datasets/current`

### Why this split

This is clearer than a single mixed list because it shows:
- what exists
- what is active
- which mounted dataset is currently driving analysis

---

## Interaction model

### Initial page load

The page should first load dataset state:

- `GET /api/v1/datasets`

Then render:
- available dataset checkboxes
- mounted dataset radios

If `current_dataset_id` exists:
- load summary for that dataset
- populate archetype selector from that dataset
- update current-dataset label in the UI

If no current dataset exists:
- show an empty-state message in the meta panel
- keep deck/chat controls visible but clearly contextualize that no dataset is active

### Mount action

When a checkbox changes from unchecked to checked:

1. call `POST /api/v1/datasets/mount`
2. reload `GET /api/v1/datasets`
3. rerender both dataset blocks
4. if a current dataset now exists, refresh summary/archetypes

### Unmount action

When a checkbox changes from checked to unchecked:

1. call `POST /api/v1/datasets/unmount`
2. reload `GET /api/v1/datasets`
3. rerender both dataset blocks
4. if current dataset changed or disappeared, refresh summary/archetypes accordingly

### Current dataset change

When a mounted radio is selected:

1. call `POST /api/v1/datasets/current`
2. reload `GET /api/v1/datasets`
3. refresh current dataset summary
4. refresh archetype selector
5. clear compare result
6. clear chat status
7. keep deck input text and parsed deck intact

---

## Data fetching behavior

### Dataset state

Use `GET /api/v1/datasets` as the main frontend source of truth after every selector mutation.

Do not try to predict mounted/current state in the browser beyond immediate optimistic UI hints. After each mutation, reload the dataset state from the server.

### Summary

Use:

- `GET /api/v1/analysis/summary?dataset_id=<id>`

Even though the backend supports current-dataset fallback, the frontend should send explicit `dataset_id` after it knows the current dataset. That makes state easier to debug and reduces ambiguity.

### Compare

Use:

- `POST /api/v1/analysis/compare`

with explicit `dataset_id` in the JSON body.

### Explain

Use:

- `POST /api/v1/analysis/explain`

with explicit `dataset_id` in the JSON body.

---

## Frontend state

Keep a small explicit state object in the page script.

Recommended fields:

- `datasets`
- `mountedDatasetIds`
- `currentDatasetId`
- `currentDatasetDisplayName`
- `currentSummary`
- `archetypes`
- `parsedDeck`

Optional convenience fields:
- `datasetMap`
- `loadingFlags`

### State principle

The backend is the source of truth for:
- available datasets
- mounted datasets
- current dataset

The browser is only the source of truth for:
- draft deck text
- parsed deck result
- temporary loading/error state

---

## Deck preservation rule

When current dataset changes:

### Preserve

- deck textarea contents
- parsed deck object

### Reset

- compare result panel
- archetype dropdown selection
- chat status text
- chat welcome/context message if the UI uses one

### Why

The user wants to compare the same deck across different tournament environments. Preserving deck input makes that workflow smooth. Clearing compare/chat output prevents stale results from looking like they belong to the newly selected dataset.

---

## Empty and error states

### No datasets discovered

Available datasets block:
- show `No datasets found under data/`

Mounted datasets block:
- empty message such as `No mounted datasets`

Meta panel:
- `No dataset available. Add a dataset under data/<year>/<event>/<division>/analysis.json.`

### Datasets discovered but none mounted

Available datasets:
- normal checkbox list

Mounted datasets:
- `No mounted datasets`

Meta panel:
- `Mount a dataset to start analysis.`

### Mounted exists but no current

Mounted datasets block:
- radios shown, none selected

Meta panel:
- `Select a current dataset.`

### Current dataset summary request fails

Meta panel:
- show a bounded error card
- do not break the rest of the page

### Dataset mutation fails

Selector section:
- show inline error text near the selector
- then reload dataset state to prevent UI drift

---

## Meta summary behavior

The current meta summary panel should stop hardcoding Prague language.

It should instead render:
- current dataset display name
- total players
- archetype count
- top archetypes for the selected dataset

Header examples:
- `Current Dataset: 2026 Prague / MA`
- `Current Dataset: 2026 Los Angeles / MA`

Any loading copy should also be dataset-neutral.

---

## Archetype selector behavior

The archetype dropdown in the center column should be repopulated whenever the current dataset changes.

If the selected archetype is not present in the new dataset:
- clear the selection

This prevents cross-dataset stale archetype ids from leaking into compare/explain requests.

---

## Chat behavior

The chat panel remains single-dataset.

When current dataset changes:
- preserve prior message history only if it is clearly still valid, or
- better for first pass: keep visible history, but append/update a lightweight notice such as `Switched current dataset to 2026 Los Angeles / MA`

However, the minimum acceptable first version is:
- keep messages as-is
- clear the chat status line
- use the current dataset for all future explain requests

If a stronger reset is desired later, that can be a follow-up feature.

---

## Implementation strategy

Keep the UI implementation inside the existing single-file static page.

### Minimal frontend refactor

Add small dedicated JS helpers:
- `loadDatasets()`
- `renderDatasetSelector()`
- `mountDataset(datasetId)`
- `unmountDataset(datasetId)`
- `setCurrentDataset(datasetId)`
- `loadCurrentSummary(datasetId)`
- `resetDatasetDependentUi()`

This is enough structure for clarity without introducing a frontend framework.

### Minimal HTML additions

Add selector containers in the left column above the meta summary container.

Suggested structure:

```html
<div class="selector-panel">
  <h3>Available datasets</h3>
  <div id="available-datasets"></div>
</div>
<div class="selector-panel">
  <h3>Mounted datasets</h3>
  <div id="mounted-datasets"></div>
</div>
<div id="selector-status"></div>
```

Then keep or rename the existing meta area below it.

---

## Testing approach

For this phase, the smallest meaningful verification is:

1. load the page successfully
2. confirm dataset selector renders from `/api/v1/datasets`
3. mount/unmount/current actions hit the expected endpoints
4. current summary switches between Prague and Los Angeles
5. deck text stays in place while current dataset changes
6. compare result clears on dataset switch

Automated browser tests are optional in this phase. A manual smoke test is acceptable if it is clearly documented.

---

## Why this design

This design matches the backend model exactly:

- **available** is visible in the Available block
- **mounted** is visible in the Mounted block
- **current** is visible in the radio selection

It also supports the main intended workflow:

- mount several tournament datasets
- keep one deck loaded
- switch current dataset to compare how the same deck fits different tournament environments

That gives immediate value now without overbuilding the eventual cross-dataset comparison interface.
