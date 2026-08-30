import {DECK_SECTIONS, comparisonCategories, deckTotal, nextTabIndex, parseDeckEditorDraft, parseDeckText, planDatasetMountRequests, prepareDeckEditorDraft, serializeDeck} from './core.mjs';
import {createTournamentReportsController} from './tournament-reports.js';

const state = {
  datasets: [], mountedDatasetIds: [], currentDatasetId: null, currentDatasetDisplayName: null,
  archetypes: [], parsedDeck: null, savedDecks: [], selectedSavedDeckId: null, editingDeck: null,
  editorParsedDeck: null, editorParsedText: null,
};
const sectionLabels = {pokemon: 'Pokémon', trainer: 'Trainer', energy: 'Energy'};
const element = (id) => document.getElementById(id);

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = String(value ?? '');
  return div.innerHTML;
}

function setStatus(id, message = '', kind = '') {
  const target = element(id);
  target.textContent = message;
  target.className = `status${kind ? ` ${kind}` : ''}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join('; ') : body.detail;
    const error = new Error(detail || `Request failed (HTTP ${response.status})`);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

const tournamentReports = createTournamentReportsController({
  requestJson,
  root: element('tournament-reports-panel'),
  navigate: (path) => history.pushState({path}, '', path),
});
let tournamentReportsInitialized = false;

function switchTab(tabName) {
  document.querySelectorAll('[role="tab"]').forEach((tab) => {
    const selected = tab.dataset.tab === tabName;
    tab.classList.toggle('active', selected);
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll('[role="tabpanel"]').forEach((panel) => { panel.hidden = panel.id !== `${tabName}-panel`; });
  if (tabName === 'tournament-reports' && !tournamentReportsInitialized) {
    tournamentReportsInitialized = true;
    tournamentReports.initialize().catch((error) => console.error(error));
  }
}

function handleTabKeydown(event) {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const targetIndex = nextTabIndex(tabs.indexOf(event.currentTarget), event.key, tabs.length);
  if (targetIndex === null) return;
  event.preventDefault();
  const target = tabs[targetIndex];
  switchTab(target.dataset.tab);
  target.focus();
}

function emptyMessage(text) {
  const message = document.createElement('div');
  message.className = 'empty-state';
  message.textContent = text;
  return message;
}

async function loadDatasets() {
  const data = await requestJson('/api/v1/datasets');
  state.datasets = data.datasets || [];
  state.mountedDatasetIds = data.mounted_dataset_ids || [];
  state.currentDatasetId = data.current_dataset_id || null;
  state.currentDatasetDisplayName = state.datasets.find((dataset) => dataset.dataset_id === state.currentDatasetId)?.display_name || null;
  renderDatasetSelector();
  if (state.currentDatasetId) await loadSummary(state.currentDatasetId);
  else renderNoCurrentDataset();
}

function datasetLabel(dataset) {
  const wrapper = document.createElement('span');
  const name = document.createElement('span');
  name.className = 'dataset-name';
  name.textContent = dataset.display_name || dataset.dataset_id;
  const meta = document.createElement('span');
  meta.className = 'dataset-meta';
  meta.textContent = [dataset.year, dataset.event_name, dataset.division, dataset.city, dataset.source_provider].filter(Boolean).join(' · ') || dataset.dataset_id;
  wrapper.append(name, meta);
  return wrapper;
}

function renderDatasetSelector() {
  const available = element('available-datasets');
  available.replaceChildren();
  if (!state.datasets.length) available.append(emptyMessage('No available datasets found.'));
  state.datasets.forEach((dataset) => {
    const item = document.createElement('label');
    item.className = 'selector-item';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = dataset.dataset_id;
    checkbox.checked = state.mountedDatasetIds.includes(dataset.dataset_id);
    checkbox.className = 'dataset-checkbox';
    item.append(checkbox, datasetLabel(dataset));
    available.append(item);
  });

  const mounted = state.datasets.filter((dataset) => state.mountedDatasetIds.includes(dataset.dataset_id));
  const mountedPanel = element('mounted-panel');
  const mountedContainer = element('mounted-datasets');
  mountedPanel.hidden = !mounted.length;
  mountedContainer.replaceChildren();
  mounted.forEach((dataset) => {
    const item = document.createElement('label');
    item.className = 'selector-item';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'current-dataset';
    radio.checked = dataset.dataset_id === state.currentDatasetId;
    radio.addEventListener('change', () => changeCurrentDataset(dataset.dataset_id));
    item.append(radio, datasetLabel(dataset));
    mountedContainer.append(item);
  });
}

async function applyMounts() {
  const desired = [...document.querySelectorAll('.dataset-checkbox:checked')].map((checkbox) => checkbox.value);
  const operations = planDatasetMountRequests(state.mountedDatasetIds, desired);
  if (!operations.length) return setStatus('selector-status', 'No changes to apply.');
  const button = element('apply-mounts-btn');
  button.disabled = true;
  setStatus('selector-status', 'Applying dataset changes…');
  try {
    for (const operation of operations) {
      await requestJson(operation.endpoint, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({dataset_id: operation.datasetId}),
      });
    }
    await loadDatasets();
    setStatus('selector-status', 'Dataset mounts updated.', 'success');
  } catch (error) {
    setStatus('selector-status', error.message, 'error');
    await loadDatasets().catch(() => {});
  } finally { button.disabled = false; }
}

async function changeCurrentDataset(datasetId) {
  setStatus('selector-status', 'Switching current dataset…');
  try {
    const data = await requestJson('/api/v1/datasets/current', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({dataset_id: datasetId}),
    });
    state.currentDatasetId = data.current_dataset_id;
    state.currentDatasetDisplayName = state.datasets.find((dataset) => dataset.dataset_id === state.currentDatasetId)?.display_name || null;
    renderDatasetSelector();
    await loadSummary(state.currentDatasetId);
    setStatus('selector-status', 'Current dataset switched.', 'success');
  } catch (error) {
    setStatus('selector-status', error.message, 'error');
    renderDatasetSelector();
  }
}

async function loadSummary(datasetId) {
  setStatus('meta-loading', 'Loading dataset summary…');
  try {
    const data = await requestJson(`/api/v1/analysis/summary?dataset_id=${encodeURIComponent(datasetId)}`);
    state.archetypes = data.archetypes || [];
    renderMeta(data);
    populateArchetypes();
    setStatus('meta-loading');
  } catch (error) { setStatus('meta-loading', error.message, 'error'); }
}

function renderNoCurrentDataset() {
  state.archetypes = [];
  populateArchetypes();
  element('meta-content').replaceChildren(emptyMessage('Mount and select a current dataset to view its meta.'));
  setStatus('meta-loading');
}

function renderMeta(data) {
  const field = data.field || {};
  let html = `<div class="helper">${escapeHtml(state.currentDatasetDisplayName || 'Current dataset')} · ${escapeHtml(field.total_players || '—')} players · ${escapeHtml(field.qualified_archetype_count || '—')} archetypes</div>`;
  (data.archetypes || []).slice(0, 8).forEach((archetype, index) => {
    const meta = archetype.meta || {};
    const performance = archetype.performance || {};
    const coreCards = [];
    DECK_SECTIONS.forEach((section) => {
      (archetype.card_summary?.[section] || []).filter((card) => card.bucket === 'core').slice(0, 3).forEach((card) => coreCards.push(`${card.name} ×${Number(card.avg_when_present || 0).toFixed(1)}`));
    });
    html += `<article class="card"><h3>${index + 1}. ${escapeHtml(archetype.archetype_name)}</h3><div class="helper">${meta.players || 0} players · ${(Number(meta.share || 0) * 100).toFixed(1)}% share · ${(Number(performance.win_rate || 0) * 100).toFixed(1)}% win rate</div><div class="helper">Core: ${escapeHtml(coreCards.join(', ') || 'No core-card data')}</div></article>`;
  });
  element('meta-content').innerHTML = html;
}

function populateArchetypes() {
  const select = element('archetype-select');
  select.innerHTML = '<option value="">Select an archetype</option>';
  state.archetypes.forEach((archetype) => {
    const option = document.createElement('option');
    option.value = archetype.archetype_id;
    option.textContent = archetype.archetype_name;
    select.append(option);
  });
}

function parseAnalysisDeck() {
  try {
    state.parsedDeck = parseDeckText(element('deck-input').value);
    state.selectedSavedDeckId = null;
    element('analysis-saved-deck').value = '';
    renderDeckPreview();
    setStatus('analysis-deck-status', `${deckTotal(state.parsedDeck)} cards parsed.`, 'success');
  } catch (error) { setStatus('analysis-deck-status', error.message, 'error'); }
}

function renderDeckPreview() {
  const target = element('deck-preview');
  if (!state.parsedDeck) return target.replaceChildren();
  let html = `<div class="deck-preview"><h3>Parsed deck · ${deckTotal(state.parsedDeck)} cards</h3>`;
  DECK_SECTIONS.forEach((section) => {
    const cards = state.parsedDeck[section] || [];
    if (!cards.length) return;
    html += `<div class="deck-section"><div class="deck-section-title">${sectionLabels[section]}</div>`;
    cards.forEach((card) => { html += `<span class="deck-card"><span class="count">${card.count}</span>${escapeHtml(card.name)}</span>`; });
    html += '</div>';
  });
  target.innerHTML = `${html}</div>`;
}

function deckContent(deck) {
  return Object.fromEntries(DECK_SECTIONS.map((section) => [section, (deck?.[section] || []).map((card) => ({name: card.name, count: card.count}))]));
}

async function loadSavedDeckToAnalysis(deckId, switchToAnalysis = false) {
  if (!deckId) return;
  try {
    const deck = await requestJson(`/api/v1/decks/${encodeURIComponent(deckId)}`);
    state.selectedSavedDeckId = deck.id;
    state.parsedDeck = deckContent(deck);
    element('analysis-saved-deck').value = deck.id;
    element('deck-input').value = serializeDeck(state.parsedDeck);
    renderDeckPreview();
    setStatus('analysis-deck-status', `${deck.name} loaded from Deck Library.`, 'success');
    if (switchToAnalysis) switchTab('analysis');
  } catch (error) { setStatus('analysis-deck-status', error.message, 'error'); }
}

async function compareWithMeta() {
  if (!state.parsedDeck) return setStatus('analysis-deck-status', 'Parse or load a deck first.', 'error');
  const archetype = element('archetype-select').value;
  if (!archetype) return setStatus('analysis-deck-status', 'Select an archetype first.', 'error');
  element('compare-result').innerHTML = '<div class="status">Comparing…</div>';
  try {
    const payload = {archetype, deck: state.parsedDeck};
    if (state.currentDatasetId) payload.dataset_id = state.currentDatasetId;
    const data = await requestJson('/api/v1/analysis/compare', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    renderComparison(data);
  } catch (error) { element('compare-result').innerHTML = `<div class="status error">${escapeHtml(error.message)}</div>`; }
}

function renderComparison(data) {
  const summary = data.summary || {};
  const categories = comparisonCategories(data);
  let html = `<div class="compare-result"><h3>Deck Diff · ${escapeHtml(data.archetype?.name || 'Meta')}</h3><div class="diff-summary">`;
  categories.forEach((category) => { html += `<span class="diff-chip">${category.label}: ${summary[category.summaryKey] || 0}</span>`; });
  html += '</div>';
  categories.forEach((category) => {
    if (!category.items.length) return;
    html += `<section class="diff-group"><h5 class="${category.className}">${category.label}</h5>`;
    category.items.forEach((card) => {
      const section = card.section_label || sectionLabels[card.section] || card.section || 'Card';
      html += `<div class="diff-row ${category.className}">• ${escapeHtml(card.name)}${card.count ? ` ×${card.count}` : ''} (${escapeHtml(section)}) — ${escapeHtml(card.note || '')}</div>`;
    });
    html += '</section>';
  });
  element('compare-result').innerHTML = `${html}</div>`;
}

async function sendMessage() {
  const input = element('chat-input');
  const question = input.value.trim();
  if (!question) return;
  if (!state.parsedDeck) return addChatMessage('ai', 'Parse or load a deck first.');
  addChatMessage('user', question);
  input.value = '';
  setStatus('chat-status', 'Waiting for the configured model…');
  try {
    const payload = {question, deck: state.parsedDeck, archetype: element('archetype-select').value || null};
    if (state.currentDatasetId) payload.dataset_id = state.currentDatasetId;
    const data = await requestJson('/api/v1/analysis/explain', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    addChatMessage('ai', data.answer || 'The provider returned no answer.');
    setStatus('chat-status', `Model: ${data.model || 'unknown'}`);
  } catch (error) {
    addChatMessage('ai', error.status === 501 ? 'AI Backend is not configured. Open the AI Backend tab to add a provider.' : `Request failed: ${error.message}`);
    setStatus('chat-status');
  }
}

function addChatMessage(role, content) {
  const message = document.createElement('div');
  message.className = `chat-message ${role}`;
  message.textContent = content;
  element('chat-messages').append(message);
  message.scrollIntoView({block: 'end'});
}

async function loadSavedDecks(preferredId = null) {
  state.savedDecks = await requestJson('/api/v1/decks');
  renderDeckList();
  renderAnalysisDeckOptions();
  const nextId = preferredId || state.editingDeck?.id;
  const selected = state.savedDecks.find((deck) => deck.id === nextId);
  if (selected) editDeck(selected);
}

function renderAnalysisDeckOptions() {
  const select = element('analysis-saved-deck');
  select.innerHTML = '<option value="">Temporary import</option>';
  state.savedDecks.forEach((deck) => {
    const option = document.createElement('option');
    option.value = deck.id;
    option.textContent = deck.name;
    select.append(option);
  });
  select.value = state.selectedSavedDeckId || '';
}

function renderDeckList() {
  const query = element('deck-search').value.trim().toLocaleLowerCase();
  const filtered = state.savedDecks.filter((deck) => deck.name.toLocaleLowerCase().includes(query));
  const list = element('deck-list');
  list.replaceChildren();
  if (!filtered.length) return list.append(emptyMessage(query ? 'No decks match this search.' : 'No saved decks yet.'));
  filtered.forEach((deck) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `deck-list-item${state.editingDeck?.id === deck.id ? ' active' : ''}`;
    button.innerHTML = `<span class="deck-list-name">${escapeHtml(deck.name)}</span><span class="deck-list-meta">${deckTotal(deck)} cards · updated ${escapeHtml(formatDate(deck.updated_at))}</span>`;
    button.addEventListener('click', () => editDeck(deck));
    list.append(button);
  });
}

function newDeck() {
  editDeck({id: null, name: 'Untitled Deck', pokemon: [], trainer: [], energy: [], created_at: null, updated_at: null});
}

function editDeck(deck) {
  state.editingDeck = {...deck, ...deckContent(deck)};
  element('editor-empty').hidden = true;
  element('deck-editor').hidden = false;
  element('deck-name').value = state.editingDeck.name;
  element('deck-timestamps').textContent = deck.id ? `Created ${formatDate(deck.created_at)} · Updated ${formatDate(deck.updated_at)}` : 'Not saved yet';
  element('duplicate-deck-btn').hidden = !deck.id;
  element('delete-deck-btn').hidden = !deck.id;
  if (deck.id) {
    const draft = prepareDeckEditorDraft(state.editingDeck);
    element('deck-library-input').value = draft.text;
    state.editorParsedDeck = deckContent(state.editingDeck);
    state.editorParsedText = draft.text;
    element('deck-total').textContent = `${draft.total} / 60 cards`;
    setStatus('deck-editor-status', `${draft.total} cards loaded and valid.`, 'success');
  } else {
    element('deck-library-input').value = '';
    state.editorParsedDeck = null;
    state.editorParsedText = null;
    element('deck-total').textContent = 'Not validated';
    setStatus('deck-editor-status', 'Paste a complete deck list, then parse and validate it before saving.');
  }
  renderDeckList();
}

function parseEditingDeck() {
  const text = element('deck-library-input').value;
  try {
    const result = parseDeckEditorDraft(text);
    state.editorParsedDeck = result.deck;
    state.editorParsedText = text;
    element('deck-total').textContent = `${result.total} / 60 cards`;
    setStatus('deck-editor-status', `${result.total} cards parsed and valid.`, 'success');
  } catch (error) {
    state.editorParsedDeck = null;
    state.editorParsedText = null;
    element('deck-total').textContent = 'Not validated';
    setStatus('deck-editor-status', error.message, 'error');
  }
}

function invalidateEditorDraft() {
  state.editorParsedDeck = null;
  state.editorParsedText = null;
  element('deck-total').textContent = 'Not validated';
  setStatus('deck-editor-status', 'Deck list changed. Parse and validate it before saving.');
}

async function saveEditingDeck(event) {
  event.preventDefault();
  const wasExisting = Boolean(state.editingDeck.id);
  const name = element('deck-name').value.trim();
  if (!name) return setStatus('deck-editor-status', 'Deck name cannot be empty.', 'error');
  if (!state.editorParsedDeck || state.editorParsedText !== element('deck-library-input').value) {
    return setStatus('deck-editor-status', 'Parse and validate the current deck list before saving.', 'error');
  }
  const payload = {name, ...deckContent(state.editorParsedDeck)};
  try {
    const saved = await requestJson(wasExisting ? `/api/v1/decks/${state.editingDeck.id}` : '/api/v1/decks', {
      method: wasExisting ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    await loadSavedDecks(saved.id);
    setStatus('deck-editor-status', wasExisting ? 'Deck overwritten.' : 'Deck saved.', 'success');
  } catch (error) { setStatus('deck-editor-status', error.message, 'error'); }
}

async function duplicateEditingDeck() {
  if (!state.editingDeck?.id) return;
  try {
    const copy = await requestJson(`/api/v1/decks/${state.editingDeck.id}/duplicate`, {method: 'POST'});
    await loadSavedDecks(copy.id);
    setStatus('deck-editor-status', 'Deck duplicated.', 'success');
  } catch (error) { setStatus('deck-editor-status', error.message, 'error'); }
}

async function deleteEditingDeck() {
  if (!state.editingDeck?.id || !window.confirm(`Delete “${state.editingDeck.name}”?`)) return;
  try {
    await requestJson(`/api/v1/decks/${state.editingDeck.id}`, {method: 'DELETE'});
    if (state.selectedSavedDeckId === state.editingDeck.id) state.selectedSavedDeckId = null;
    state.editingDeck = null;
    state.editorParsedDeck = null;
    state.editorParsedText = null;
    element('deck-editor').hidden = true;
    element('editor-empty').hidden = false;
    await loadSavedDecks();
  } catch (error) { setStatus('deck-editor-status', error.message, 'error'); }
}

function formatDate(value) {
  return value ? new Intl.DateTimeFormat(undefined, {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value)) : '—';
}

async function loadProviderSettings() {
  try {
    const data = await requestJson('/api/v1/provider/settings');
    const preferred = data.file || data.active || data.env;
    element('provider-base-url').value = preferred?.base_url || '';
    element('provider-model').value = preferred?.model || '';
    element('provider-api-key').value = '';
    element('provider-api-key').placeholder = data.file?.api_key ? `Saved: ${data.file.api_key}` : 'Enter API key';
    renderProviderSummary(data);
  } catch (error) { setStatus('provider-form-status', error.message, 'error'); }
}

function renderProviderSummary(data) {
  const active = data.active;
  element('provider-summary').innerHTML = active
    ? `<dt>Status</dt><dd>Configured</dd><dt>Source</dt><dd>${escapeHtml(active.source)}</dd><dt>Base URL</dt><dd>${escapeHtml(active.base_url)}</dd><dt>Model</dt><dd>${escapeHtml(active.model)}</dd><dt>API key</dt><dd>${escapeHtml(active.api_key)}</dd>`
    : '<dt>Status</dt><dd>Not configured</dd>';
}

async function saveProvider(event) {
  event.preventDefault();
  const button = element('save-provider-btn');
  button.disabled = true;
  setStatus('provider-form-status', 'Saving provider settings…');
  try {
    await requestJson('/api/v1/provider/settings', {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        base_url: element('provider-base-url').value, api_key: element('provider-api-key').value, model: element('provider-model').value,
      }),
    });
    await loadProviderSettings();
    setStatus('provider-form-status', 'Provider settings saved.', 'success');
  } catch (error) { setStatus('provider-form-status', error.message, 'error'); }
  finally { button.disabled = false; }
}

async function fetchModels() {
  const button = element('fetch-models-btn');
  button.disabled = true;
  setStatus('provider-form-status', 'Fetching available models…');
  try {
    const data = await requestJson('/api/v1/provider/models', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        base_url: element('provider-base-url').value, api_key: element('provider-api-key').value,
      }),
    });
    const select = element('discovered-models');
    select.innerHTML = '<option value="">Choose a discovered model</option>';
    data.models.forEach((model) => {
      const option = document.createElement('option');
      option.value = model;
      option.textContent = model;
      select.append(option);
    });
    setStatus('provider-form-status', data.models.length ? `${data.models.length} models found.` : 'Connection succeeded; the provider returned no models.', 'success');
  } catch (error) { setStatus('provider-form-status', error.message, 'error'); }
  finally { button.disabled = false; }
}

function bindEvents() {
  document.querySelectorAll('[role="tab"]').forEach((tab) => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    tab.addEventListener('keydown', handleTabKeydown);
  });
  element('apply-mounts-btn').addEventListener('click', applyMounts);
  element('parse-deck-btn').addEventListener('click', parseAnalysisDeck);
  element('compare-btn').addEventListener('click', compareWithMeta);
  element('analysis-saved-deck').addEventListener('change', (event) => loadSavedDeckToAnalysis(event.target.value));
  element('send-chat-btn').addEventListener('click', sendMessage);
  element('chat-input').addEventListener('keydown', (event) => { if (event.key === 'Enter') sendMessage(); });
  element('new-deck-btn').addEventListener('click', newDeck);
  element('deck-search').addEventListener('input', renderDeckList);
  element('deck-editor').addEventListener('submit', saveEditingDeck);
  element('parse-library-deck-btn').addEventListener('click', parseEditingDeck);
  element('deck-library-input').addEventListener('input', invalidateEditorDraft);
  element('duplicate-deck-btn').addEventListener('click', duplicateEditingDeck);
  element('delete-deck-btn').addEventListener('click', deleteEditingDeck);
  element('load-analysis-btn').addEventListener('click', () => state.editingDeck?.id ? loadSavedDeckToAnalysis(state.editingDeck.id, true) : setStatus('deck-editor-status', 'Save this deck before loading it in Analysis.', 'error'));
  element('provider-form').addEventListener('submit', saveProvider);
  element('fetch-models-btn').addEventListener('click', fetchModels);
  element('discovered-models').addEventListener('change', (event) => { if (event.target.value) element('provider-model').value = event.target.value; });
  window.addEventListener('popstate', () => {
    if (window.location.pathname.startsWith('/tournament-reports')) {
      switchTab('tournament-reports');
      tournamentReports.showLocation(window.location.pathname);
    }
  });
}

async function initialize() {
  bindEvents();
  if (window.location.pathname.startsWith('/tournament-reports')) switchTab('tournament-reports');
  const results = await Promise.allSettled([loadDatasets(), loadSavedDecks(), loadProviderSettings()]);
  results.forEach((result) => { if (result.status === 'rejected') console.error(result.reason); });
}

initialize();
