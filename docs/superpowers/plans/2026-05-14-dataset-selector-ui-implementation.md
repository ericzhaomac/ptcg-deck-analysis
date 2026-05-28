# Dataset Selector UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a left-side dataset selector UI to the existing deck analysis page so users can mount/unmount datasets, choose a current dataset, and drive the existing summary/compare/explain workflow from that selection while preserving the imported deck.

**Architecture:** Keep the current single-file static frontend and extend it with a small dataset state layer. The browser will load dataset state from `/api/v1/datasets`, render `Available` and `Mounted` blocks, call mount/current APIs on interaction, and reload summary/archetype data for the current dataset using explicit `dataset_id` parameters. The backend APIs already exist, so this plan focuses on HTML/CSS/JS integration plus a small API test for selector-friendly behavior.

**Tech Stack:** Static HTML/CSS/JavaScript, FastAPI, pytest, FastAPI TestClient

---

## File map

### Modify
- `app/static/index.html` — add dataset selector markup, dataset-aware labels, and JS state/actions
- `tests/test_dataset_api.py` — add small backend-friendly tests for selector assumptions if needed
- `README.md` — update UI usage section if the implemented workflow differs from current docs

### No new runtime files expected
- keep this phase inside the existing static page

---

### Task 1: Add dataset selector markup and left-column structure

**Files:**
- Modify: `app/static/index.html`
- Test: manual browser smoke later in Task 4

- [ ] **Step 1: Add the failing UI expectation as a code comment checklist near the left column**

Insert a short implementation note above the left-column markup so the worker has an explicit target while editing:

```html
<!-- Dataset selector target:
1. Available datasets block with checkboxes
2. Mounted datasets block with radios
3. Selector status/error area
4. Current dataset meta summary below selector
-->
```

- [ ] **Step 2: Replace the current left-column header/markup with selector containers**

Update the left column so it has this shape:

```html
<div class="column" id="meta-column">
  <h2>🗂️ Dataset Selector</h2>
  <div class="selector-panel">
    <h3>Available datasets</h3>
    <div id="available-datasets" class="selector-list"></div>
  </div>
  <div class="selector-panel">
    <h3>Mounted datasets</h3>
    <div id="mounted-datasets" class="selector-list"></div>
  </div>
  <div id="selector-status" class="selector-status"></div>

  <h2 style="margin-top:20px;">📊 Current Dataset Meta</h2>
  <div id="meta-loading" class="loading">Loading current dataset summary...</div>
  <div id="meta-content" style="display:none;"></div>
</div>
```

- [ ] **Step 3: Add minimal CSS for selector blocks**

Add CSS rules near the existing left-column styles:

```css
.selector-panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}
.selector-panel h3 {
  font-size: 13px;
  color: #8b949e;
  margin-bottom: 10px;
}
.selector-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.selector-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
}
.selector-item label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
  font-size: 12px;
}
.selector-item .dataset-name {
  color: #c9d1d9;
}
.selector-item .dataset-meta {
  color: #8b949e;
  font-size: 11px;
}
.selector-empty,
.selector-status {
  font-size: 12px;
  color: #8b949e;
}
.selector-status.error {
  color: #f85149;
}
```

- [ ] **Step 4: Verify the page still loads as static HTML**

Run: `python -m http.server 8015` from the project root, then open `http://localhost:8015/app/static/index.html`
Expected: the page renders with the new left-column structure and no malformed HTML

- [ ] **Step 5: Commit**

```bash
git add app/static/index.html
git commit -m "feat: add dataset selector layout to static page"
```

---

### Task 2: Add frontend dataset state loading and selector rendering

**Files:**
- Modify: `app/static/index.html`
- Test: manual browser smoke later in Task 4

- [ ] **Step 1: Add a small explicit state object in the script**

Near the top of the `<script>` block, replace the current globals with:

```javascript
const state = {
  datasets: [],
  mountedDatasetIds: [],
  currentDatasetId: null,
  currentDatasetDisplayName: null,
  currentSummary: null,
  archetypes: [],
  parsedDeck: null,
};
```

- [ ] **Step 2: Add dataset-loading and rendering helpers**

Add these functions before `loadMeta()` (which will be replaced later):

```javascript
async function loadDatasets() {
  const res = await fetch('/api/v1/datasets');
  if (!res.ok) {
    throw new Error(`Failed to load datasets: ${res.status}`);
  }
  const data = await res.json();
  state.datasets = data.datasets || [];
  state.mountedDatasetIds = data.mounted_dataset_ids || [];
  state.currentDatasetId = data.current_dataset_id || null;
  const current = state.datasets.find(d => d.dataset_id === state.currentDatasetId);
  state.currentDatasetDisplayName = current ? current.display_name : null;
  renderDatasetSelector();
}

function renderDatasetSelector() {
  renderAvailableDatasets();
  renderMountedDatasets();
}
```

Also add:

```javascript
function renderAvailableDatasets() {
  const container = document.getElementById('available-datasets');
  if (!state.datasets.length) {
    container.innerHTML = '<div class="selector-empty">No datasets found under data/</div>';
    return;
  }
  container.innerHTML = state.datasets.map(dataset => {
    const checked = state.mountedDatasetIds.includes(dataset.dataset_id) ? 'checked' : '';
    const meta = [dataset.city, dataset.tournament_id].filter(Boolean).join(' · ');
    return `
      <div class="selector-item">
        <input type="checkbox" ${checked} onchange="toggleDatasetMount('${dataset.dataset_id}', this.checked)">
        <label>
          <span class="dataset-name">${escapeHtml(dataset.display_name)}</span>
          <span class="dataset-meta">${escapeHtml(meta)}</span>
        </label>
      </div>
    `;
  }).join('');
}

function renderMountedDatasets() {
  const container = document.getElementById('mounted-datasets');
  const mounted = state.datasets.filter(dataset => state.mountedDatasetIds.includes(dataset.dataset_id));
  if (!mounted.length) {
    container.innerHTML = '<div class="selector-empty">No mounted datasets</div>';
    return;
  }
  container.innerHTML = mounted.map(dataset => {
    const checked = dataset.dataset_id === state.currentDatasetId ? 'checked' : '';
    return `
      <div class="selector-item">
        <input type="radio" name="current-dataset" ${checked} onchange="changeCurrentDataset('${dataset.dataset_id}')">
        <label>
          <span class="dataset-name">${escapeHtml(dataset.display_name)}</span>
        </label>
      </div>
    `;
  }).join('');
}
```

- [ ] **Step 3: Add selector status helpers**

Add:

```javascript
function setSelectorStatus(message = '', isError = false) {
  const el = document.getElementById('selector-status');
  el.textContent = message;
  el.className = isError ? 'selector-status error' : 'selector-status';
}
```

- [ ] **Step 4: Replace startup call**

Replace the old `loadMeta();` init line with:

```javascript
initializePage();
```

and add:

```javascript
async function initializePage() {
  try {
    await loadDatasets();
  } catch (e) {
    setSelectorStatus(e.message, true);
  }
}
```

- [ ] **Step 5: Verify the script parses cleanly**

Run: `node --check app/static/index.html`
Expected: this will FAIL because it is HTML, not JS

Then run the actual meaningful check:

```bash
python - <<'PY'
from pathlib import Path
html = Path('app/static/index.html').read_text(encoding='utf-8')
assert 'function renderDatasetSelector()' in html
assert 'function loadDatasets()' in html
assert 'initializePage();' in html
print('ok')
PY
```

Expected: prints `ok`

- [ ] **Step 6: Commit**

```bash
git add app/static/index.html
git commit -m "feat: render dataset selector from dataset APIs"
```

---

### Task 3: Wire dataset actions and dataset-aware analysis requests

**Files:**
- Modify: `app/static/index.html`
- Test: `tests/test_dataset_api.py` (only if a backend tweak becomes necessary)

- [ ] **Step 1: Add mount/unmount/current action helpers**

Add these functions:

```javascript
async function toggleDatasetMount(datasetId, shouldMount) {
  setSelectorStatus(shouldMount ? 'Mounting dataset...' : 'Unmounting dataset...');
  try {
    const endpoint = shouldMount ? '/api/v1/datasets/mount' : '/api/v1/datasets/unmount';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    if (!res.ok) {
      throw new Error(`Dataset update failed: ${res.status}`);
    }
    await loadDatasets();
    await refreshCurrentDatasetUi();
    setSelectorStatus('');
  } catch (e) {
    setSelectorStatus(e.message, true);
    await loadDatasets();
  }
}

async function changeCurrentDataset(datasetId) {
  setSelectorStatus('Switching current dataset...');
  try {
    const res = await fetch('/api/v1/datasets/current', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    if (!res.ok) {
      throw new Error(`Failed to set current dataset: ${res.status}`);
    }
    await loadDatasets();
    resetDatasetDependentUi();
    await refreshCurrentDatasetUi();
    setSelectorStatus('');
  } catch (e) {
    setSelectorStatus(e.message, true);
    await loadDatasets();
  }
}
```

- [ ] **Step 2: Add current-dataset summary refresh helpers**

Replace `loadMeta()` with:

```javascript
async function refreshCurrentDatasetUi() {
  if (!state.currentDatasetId) {
    renderNoCurrentDataset();
    populateArchetypeSelect([]);
    return;
  }
  await loadSummary(state.currentDatasetId);
}

async function loadSummary(datasetId) {
  document.getElementById('meta-loading').style.display = 'block';
  document.getElementById('meta-content').style.display = 'none';
  document.getElementById('meta-loading').textContent = 'Loading current dataset summary...';
  document.getElementById('meta-loading').className = 'loading';

  const res = await fetch(`/api/v1/analysis/summary?dataset_id=${encodeURIComponent(datasetId)}`);
  if (!res.ok) {
    throw new Error(`Failed to load summary: ${res.status}`);
  }
  const data = await res.json();
  state.currentSummary = data;
  state.archetypes = data.archetypes || [];
  renderMeta(data);
  populateArchetypeSelect(state.archetypes);
}

function renderNoCurrentDataset() {
  document.getElementById('meta-loading').style.display = 'none';
  document.getElementById('meta-content').style.display = 'block';
  document.getElementById('meta-content').innerHTML = '<div class="selector-empty">Mount a dataset to start analysis.</div>';
}
```

- [ ] **Step 3: Make compare and explain requests send explicit dataset_id**

Update `compareWithMeta()` request body to:

```javascript
body: JSON.stringify({
  dataset_id: state.currentDatasetId,
  archetype,
  deck: state.parsedDeck
})
```

Update `sendMessage()` request body to:

```javascript
body: JSON.stringify({
  dataset_id: state.currentDatasetId,
  archetype,
  deck: state.parsedDeck,
  question: message
})
```

Also update the provider-config link in the 501 message to `/api/v1/provider/config`.

- [ ] **Step 4: Preserve deck but reset dataset-dependent UI**

Add:

```javascript
function resetDatasetDependentUi() {
  document.getElementById('compare-result').innerHTML = '';
  document.getElementById('chat-status').textContent = '';
  document.getElementById('archetype-select').value = '';
}
```

Keep `state.parsedDeck` and the textarea contents untouched.

- [ ] **Step 5: Verify the page logic references current dataset explicitly**

Run:

```bash
python - <<'PY'
from pathlib import Path
html = Path('app/static/index.html').read_text(encoding='utf-8')
assert '/api/v1/datasets/mount' in html
assert '/api/v1/datasets/current' in html
assert 'dataset_id: state.currentDatasetId' in html
assert '/api/v1/provider/config' in html
print('ok')
PY
```

Expected: prints `ok`

- [ ] **Step 6: Commit**

```bash
git add app/static/index.html
git commit -m "feat: wire dataset selector to analysis workflow"
```

---

### Task 4: Final polish for empty states, copy, and manual smoke verification

**Files:**
- Modify: `app/static/index.html`
- Modify: `README.md` (if UI usage wording needs sync)

- [ ] **Step 1: Make page copy dataset-aware**

Update the following hardcoded Prague-only strings in `app/static/index.html`:

- title: `PTCG Deck Analysis`
- header: `🎴 PTCG Deck Analysis`
- loading text: `Loading current dataset summary...`
- intro AI message: mention the current dataset generically rather than Prague specifically
- compare success/AI helper text: replace `Prague` wording with `current dataset`

Use exact strings like:

```html
<title>PTCG Deck Analysis</title>
<h1>🎴 PTCG Deck Analysis</h1>
```

And AI intro seed:

```javascript
<div class="content">你好！我可以帮你分析当前 dataset 环境下的卡组构筑。请先挂载并选择一个 dataset，然后导入你的卡组。</div>
```

- [ ] **Step 2: Make `renderMeta()` show current dataset identity**

Change the meta header block to use `state.currentDatasetDisplayName`:

```javascript
let html = `<div style="font-size:12px;color:#8b949e;margin-bottom:12px;">
  Current dataset: ${escapeHtml(state.currentDatasetDisplayName || 'Unknown')} | 总人数: ${field.total_players || '-'} | 主流 archetype: ${field.qualified_archetype_count || '-'} 个
</div>`;
```

- [ ] **Step 3: Do a real manual smoke test against the app**

Run the app from the project root:

```bash
PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --port 8010
```

Manual verification checklist in the browser at `http://localhost:8010/`:
- Available datasets show Prague and Los Angeles
- Mounting a dataset updates Mounted datasets
- Selecting a mounted radio loads current meta summary
- Switching current dataset keeps deck textarea contents
- Switching current dataset clears compare result
- Provider nav links open `/api/v1/provider/config` and `/api/v1/provider`

If any item fails, fix `app/static/index.html` and repeat the manual smoke test.

- [ ] **Step 4: Sync README usage notes if needed**

If the current README still describes Prague-only UI behavior, update the UI usage section to say:
- datasets are discovered from `data/<year>/<event>/<division>/analysis.json`
- users mount datasets in the browser
- mounted datasets can be switched with a current selector
- compare/explain operate on the current dataset unless a caller passes explicit `dataset_id`

- [ ] **Step 5: Commit**

```bash
git add app/static/index.html README.md
git commit -m "refactor: polish dataset selector UI copy and behavior"
```

---

### Task 5: Final verification sweep

**Files:**
- Modify: any touched files if smoke-test fixes are needed
- Test: `tests/test_dataset_api.py`

- [ ] **Step 1: Run backend regression tests**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_dataset_api.py -q
```

Expected: PASS

- [ ] **Step 2: Run a targeted app smoke creation check**

Run:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from app.main import create_app
app = create_app()
print(app.title)
PY
```

Expected output:

```text
Ptcg Deck Analysis Service
```

- [ ] **Step 3: Re-run manual browser verification if Task 4 made fixes**

Checklist:
- selector renders
- mount/unmount works
- radio current works
- current summary switches
- deck input persists
- compare result clears on dataset switch

- [ ] **Step 4: Commit final cleanup if needed**

```bash
git add app/static/index.html README.md tests/test_dataset_api.py
git commit -m "test: verify dataset selector UI workflow"
```

---

## Self-review

### Spec coverage

Covered:
- available datasets checkbox block — Tasks 1 and 2
- mounted datasets radio block — Tasks 1 and 2
- current dataset summary refresh — Task 3
- explicit `dataset_id` usage from frontend — Task 3
- deck preservation + compare/chat reset — Task 3
- dataset-aware copy and empty states — Task 4
- manual smoke verification — Tasks 4 and 5

Intentionally out of scope:
- cross-dataset comparison UI
- upload/import flow
- frontend framework migration

### Placeholder scan

No `TODO`, `TBD`, or vague "handle errors later" placeholders remain. Each task names exact files, code targets, and concrete verification steps.

### Type consistency

Shared identifiers used consistently across the plan:
- `state.currentDatasetId`
- `state.mountedDatasetIds`
- `state.datasets`
- `loadDatasets()`
- `refreshCurrentDatasetUi()`
- `resetDatasetDependentUi()`
- `/api/v1/datasets/*`
- `/api/v1/analysis/*`
- `/api/v1/provider/*`
