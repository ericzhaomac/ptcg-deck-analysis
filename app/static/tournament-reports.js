import {
  buildOverviewChartModel,
  createReportRoute,
  moduleAvailability,
  reduceReportSelection,
} from './tournament-reports-core.mjs';


export function createTournamentReportsController({requestJson, root, navigate}) {
  const index = root.querySelector('#tournament-report-index');
  const overview = root.querySelector('#tournament-report-overview');
  const archetype = root.querySelector('#tournament-report-archetype');
  const breadcrumbs = root.querySelector('#tournament-report-breadcrumbs');
  const title = root.querySelector('#tournament-report-title');
  const status = root.querySelector('#tournament-report-status');
  const notification = root.querySelector('#tournament-report-notification');
  let disposed = false;
  let state = initialState(null);

  async function initialize() {
    return showLocation(window.location.pathname);
  }

  async function showLocation(pathname) {
    if (disposed) return;
    const parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
    if (parts[0] !== 'tournament-reports' || parts.length === 1) return showIndex();
    if (parts.length === 2) return showOverview(parts[1]);
    if (parts[2] === 'families' || parts[2] === 'variants') {
      return showArchetypeSkeleton(parts[1], parts[2], parts[3]);
    }
    return showIndex();
  }

  async function showIndex() {
    setView(index);
    title.textContent = 'Tournament Reports';
    status.textContent = 'Loading completed mounted events…';
    breadcrumbs.replaceChildren();
    const response = await requestJson('/api/v1/tournament-reports');
    if (disposed) return;
    index.replaceChildren();
    const list = document.createElement('div');
    list.className = 'tournament-report-event-list';
    for (const item of response.events) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'card tournament-report-event';
      button.append(
        textElement('strong', item.event.name),
        textElement('span', `${item.event.date} · ${item.event.division}`),
        textElement('small', `Snapshot ${item.snapshot_version}`),
      );
      button.addEventListener('click', () => go(createReportRoute('overview', item.dataset_id)));
      list.append(button);
    }
    if (!response.events.length) list.append(emptyState('No completed mounted tournament reports are available.'));
    index.append(list);
    status.textContent = `${response.events.length} completed event${response.events.length === 1 ? '' : 's'}`;
  }

  async function showOverview(datasetId) {
    setView(overview);
    title.textContent = 'Tournament overview';
    status.textContent = 'Loading verified report…';
    state = initialState(datasetId);
    const report = await requestJson(`/api/v1/tournament-reports/${encodeURIComponent(datasetId)}`);
    if (disposed || state.datasetId !== datasetId) return;
    title.textContent = report.event.name;
    status.textContent = `${report.event.date} · ${report.event.division} · Snapshot ${report.snapshot_version}`;
    renderBreadcrumbs(report);
    overview.replaceChildren();
    const renderers = {
      event_identity: renderEventIdentity,
      phase_topcut_distribution: renderDistributionComparison,
      day2_conversion: renderConversion,
      family_ranking: renderFamilyRanking,
    };
    for (const module of report.modules) {
      const renderer = renderers[module.module_id];
      if (renderer) overview.append(renderer(module));
    }
    overview.append(renderFamilyAction());
  }

  async function showArchetypeSkeleton(datasetId, collection, selectionId) {
    setView(archetype);
    status.textContent = 'Loading archetype report…';
    const grain = collection === 'families' ? 'family' : 'variant';
    state = {...initialState(datasetId), selection: {grain, selectionId}};
    const report = await requestJson(
      `/api/v1/tournament-reports/${encodeURIComponent(datasetId)}/${collection}/${encodeURIComponent(selectionId)}`,
    );
    if (disposed || state.datasetId !== datasetId) return;
    state = {...state, report};
    title.textContent = report.selection.selection_id;
    status.textContent = `Snapshot ${report.snapshot_version}`;
    renderBreadcrumbs(report);
    archetype.replaceChildren(emptyState('Archetype modules loaded.'));
  }

  function renderEventIdentity(module) {
    const section = moduleSection(module);
    section.append(textElement('p', `${module.data.date} · ${module.data.division}`));
    return section;
  }

  function renderDistributionComparison(module) {
    const section = moduleSection(module);
    const model = buildOverviewChartModel(module, state.selectedFamilyId);
    const comparison = document.createElement('div');
    comparison.className = 'tournament-report-comparison';
    model.series.forEach((series) => comparison.append(chartPanel(series, selectOverviewFamily)));
    section.append(comparison, distributionTable(module));
    return section;
  }

  function renderConversion(module) {
    const section = moduleSection(module);
    const model = buildOverviewChartModel(module, state.selectedFamilyId);
    section.append(chartPanel(model.series[0], selectOverviewFamily));
    section.append(rowsTable(module.data.rows, [
      ['Archetype', 'family_name'],
      ['First Phase', 'first_phase_players'],
      ['Day 2', 'day2_players'],
      ['Conversion', (row) => formatPercent(row.rate)],
    ]));
    return section;
  }

  function renderFamilyRanking(module) {
    const section = moduleSection(module);
    section.append(rowsTable(module.data.rows, [
      ['Archetype', 'family_name'],
      ['Players', 'players'],
      ['Share', (row) => formatPercent(row.share)],
      ['Official record', (row) => formatRecord(row.record)],
      ['Observed win rate', (row) => formatPercent(row.observed_win_rate)],
    ], selectOverviewFamily));
    return section;
  }

  function selectOverviewFamily(familyId) {
    state = reduceReportSelection(state, {type: 'select-family', familyId});
    root.querySelectorAll('[data-family-id]').forEach((node) => {
      const selected = node.dataset.familyId === familyId;
      node.classList.toggle('selected', selected);
      node.setAttribute('aria-pressed', String(selected));
    });
    const oldAction = root.querySelector('#tournament-report-family-action');
    if (oldAction) oldAction.replaceWith(renderFamilyAction());
    notification.textContent = `${familyId} selected across overview modules.`;
  }

  function renderFamilyAction() {
    const wrapper = document.createElement('div');
    wrapper.id = 'tournament-report-family-action';
    wrapper.className = 'tournament-report-action';
    if (!state.familyReportAction) {
      wrapper.append(textElement('p', 'Select an archetype to open its full report.'));
      return wrapper;
    }
    const button = textElement('button', 'View family report');
    button.type = 'button';
    button.className = 'button primary';
    button.addEventListener('click', () => go(state.familyReportAction));
    wrapper.append(button);
    return wrapper;
  }

  function chartPanel(series, onSelect) {
    const panel = document.createElement('div');
    panel.className = 'tournament-report-chart';
    panel.append(textElement('h4', phaseLabel(series.phase)));
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 100 ${Math.max(40, series.marks.length * 36)}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${phaseLabel(series.phase)} archetype distribution`);
    series.marks.forEach((mark) => {
      const group = document.createElementNS(svg.namespaceURI, 'g');
      group.dataset.familyId = mark.familyId;
      group.classList.add('tournament-report-mark');
      if (mark.selected) group.classList.add('selected');
      group.setAttribute('role', 'button');
      group.setAttribute('tabindex', '0');
      group.setAttribute('aria-label', mark.tooltip);
      group.setAttribute('aria-pressed', String(mark.selected));
      const rect = document.createElementNS(svg.namespaceURI, 'rect');
      rect.setAttribute('x', '0');
      rect.setAttribute('y', String(mark.y + 4));
      rect.setAttribute('width', String(Math.max(1, mark.width)));
      rect.setAttribute('height', '22');
      const label = document.createElementNS(svg.namespaceURI, 'text');
      label.setAttribute('x', '2');
      label.setAttribute('y', String(mark.y + 19));
      label.textContent = `${mark.label} ${mark.share === null ? '' : formatPercent(mark.share)}`;
      group.append(rect, label);
      group.addEventListener('click', () => onSelect(mark.familyId));
      group.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(mark.familyId);
        }
      });
      svg.append(group);
    });
    panel.append(svg);
    return panel;
  }

  function distributionTable(module) {
    const rows = [];
    for (const [phase, values] of [['First Phase', module.data.first_phase], ['Top Cut', module.data.top_cut]]) {
      values.forEach((row) => rows.push({...row, phase}));
    }
    return rowsTable(rows, [
      ['Phase', 'phase'],
      ['Archetype', 'family_name'],
      ['Players', 'players'],
      ['Share', (row) => formatPercent(row.share)],
      ['Official record', (row) => formatRecord(row.record)],
    ], selectOverviewFamily);
  }

  function rowsTable(rows, columns, onSelect = null) {
    const table = document.createElement('table');
    table.className = 'tournament-report-table';
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    columns.forEach(([label]) => headRow.append(textElement('th', label)));
    head.append(headRow);
    const body = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      if (row.family_id) tr.dataset.familyId = row.family_id;
      columns.forEach(([, accessor]) => {
        const value = typeof accessor === 'function' ? accessor(row) : row[accessor];
        tr.append(textElement('td', value ?? '—'));
      });
      if (onSelect && row.family_id) {
        tr.tabIndex = 0;
        tr.setAttribute('role', 'button');
        tr.setAttribute('aria-pressed', 'false');
        tr.addEventListener('click', () => onSelect(row.family_id));
        tr.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') onSelect(row.family_id);
        });
      }
      body.append(tr);
    });
    table.append(head, body);
    return table;
  }

  function moduleSection(module) {
    const section = document.createElement('section');
    const availability = moduleAvailability(module);
    section.className = 'card tournament-report-module tournament-report-state';
    section.dataset.state = availability.kind;
    section.append(textElement('h3', module.title));
    if (availability.message) section.append(textElement('p', availability.message));
    section.append(textElement('small', `n=${module.sample_size} · ${module.metric_notes.join(' ')}`));
    return section;
  }

  function renderBreadcrumbs(report) {
    breadcrumbs.replaceChildren();
    const all = textElement('button', 'Tournament Reports');
    all.type = 'button';
    all.addEventListener('click', () => go(createReportRoute('index', null)));
    breadcrumbs.append(all, textElement('span', '›'), textElement('span', report.event.name));
  }

  function go(path) {
    navigate(path);
    return showLocation(path);
  }

  function setView(active) {
    [index, overview, archetype].forEach((view) => { view.hidden = view !== active; });
  }

  function dispose() {
    disposed = true;
  }

  return {initialize, showIndex, showOverview, showLocation, dispose};
}


function initialState(datasetId) {
  return {
    datasetId,
    selectedFamilyId: null,
    visibleFamilyIds: [],
    familyReportAction: null,
    selection: null,
    modulePhases: {matchups: 'overall', composition: 'first_phase'},
    requestGeneration: 0,
    appliedGeneration: 0,
    report: null,
  };
}


function textElement(tag, text) {
  const node = document.createElement(tag);
  node.textContent = String(text ?? '');
  return node;
}


function emptyState(text) {
  const node = textElement('div', text);
  node.className = 'empty-state';
  return node;
}


function formatPercent(value) {
  return value === null || value === undefined ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
}


function formatRecord(record) {
  return record ? `${record.wins}-${record.losses}-${record.ties}` : '—';
}


function phaseLabel(phase) {
  return String(phase).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}
