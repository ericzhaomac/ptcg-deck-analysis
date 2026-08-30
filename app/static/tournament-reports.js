import {
  ARCHETYPE_MODULE_IDS,
  PNG_EXPORT_MODULE_IDS,
  archetypeModuleForPhase,
  assertExportable,
  buildOverviewChartModel,
  buildModuleSvg,
  createReportRoute,
  moduleAvailability,
  reduceReportSelection,
  matchupAvailabilityMessage,
  exportFilename,
} from './tournament-reports-core.mjs';


export async function exportModulePng(moduleElement, module, context) {
  assertExportable(module, context);
  const svg = buildModuleSvg(module, context);
  const image = await loadSvgImage(svg);
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1350;
  canvas.getContext('2d').drawImage(image, 0, 0, 1080, 1350);
  const blob = await canvasBlob(canvas, 'image/png');
  downloadBlob(blob, exportFilename(module, context));
  moduleElement.dataset.lastExportedSnapshot = context.snapshotVersion;
}


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
  let requestSequence = 0;

  async function initialize() {
    return showLocation(window.location.pathname);
  }

  async function showLocation(pathname) {
    if (disposed) return;
    const parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
    if (parts[0] !== 'tournament-reports' || parts.length === 1) return showIndex();
    if (parts.length === 2) return showOverview(parts[1]);
    if (parts[2] === 'families' || parts[2] === 'variants') {
      return showArchetypeReport(parts[1], parts[2], parts[3]);
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
    state = {...state, report};
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

  async function showArchetypeReport(datasetId, collection, selectionId) {
    setView(archetype);
    status.textContent = 'Loading archetype report…';
    const grain = collection === 'families' ? 'family' : 'variant';
    state = {
      ...initialState(datasetId),
      selection: {grain, selectionId},
      requestGeneration: requestSequence,
    };
    state = reduceReportSelection(state, {type: 'request-report'});
    requestSequence = state.requestGeneration;
    const generation = state.requestGeneration;
    const report = await requestJson(
      `/api/v1/tournament-reports/${encodeURIComponent(datasetId)}/${collection}/${encodeURIComponent(selectionId)}`,
    );
    if (disposed) return;
    state = reduceReportSelection(state, {type: 'receive-report', generation, report});
    if (state.appliedGeneration !== generation) return;
    renderArchetypeReport(report);
  }

  function renderArchetypeReport(report) {
    title.textContent = report.selection.selection_id;
    status.textContent = `${report.event.date} · ${report.event.division} · Snapshot ${report.snapshot_version}`;
    renderBreadcrumbs(report);
    archetype.replaceChildren();
    const actualIds = report.modules.map((module) => module.module_id);
    if (actualIds.length !== ARCHETYPE_MODULE_IDS.length
      || actualIds.some((moduleId, index) => moduleId !== ARCHETYPE_MODULE_IDS[index])) {
      archetype.append(emptyState('This report uses an unsupported module contract.'));
      return;
    }
    archetype.append(renderVariantSelector(report));
    const modules = Object.fromEntries(report.modules.map((module) => [module.module_id, module]));
    archetype.append(
      renderHeadlinePerformance(modules.headline_performance, report),
      renderPhasePerformance(modules.phase_performance, report),
      renderTopFinishers(modules.top_finishers, report),
      renderMatchupGroup(report),
      renderCompositionGroup(report),
      renderRepresentativeLists(modules.representative_lists, report),
    );
  }

  function renderVariantSelector(report) {
    const wrapper = document.createElement('div');
    wrapper.className = 'card tournament-report-selector';
    const label = textElement('label', 'Report grain');
    label.htmlFor = 'tournament-report-variant-select';
    const select = document.createElement('select');
    select.id = 'tournament-report-variant-select';
    const summary = document.createElement('option');
    summary.value = '';
    summary.textContent = report.selection.grain === 'family'
      ? `Family · ${report.selection.selection_id}`
      : 'Return to family report to view the family summary';
    select.append(summary);
    report.variants.filter((option) => option.eligible).forEach((option) => {
      const node = document.createElement('option');
      node.value = option.selection_id;
      node.textContent = `${option.label} · ${option.first_phase_players} players`;
      node.selected = report.selection.grain === 'variant'
        && report.selection.selection_id === option.selection_id;
      select.append(node);
    });
    select.addEventListener('change', () => {
      if (select.value) selectVariant(select.value);
    });
    wrapper.append(label, select);
    return wrapper;
  }

  async function selectVariant(variantId) {
    state = reduceReportSelection(state, {type: 'select-variant', variantId});
    const path = createReportRoute('variant', state.datasetId, 'variant', variantId);
    navigate(path);
    return showArchetypeReport(state.datasetId, 'variants', variantId);
  }

  function renderHeadlinePerformance(module, report) {
    const section = moduleSection(module, report);
    section.append(rowsTable([module.data], [
      ['Players', 'players'],
      ['Official record', (row) => formatRecord(row.record)],
      ['Observed win rate', (row) => formatPercent(row.observed_win_rate)],
    ]));
    return section;
  }

  function renderPhasePerformance(module, report) {
    const section = moduleSection(module, report);
    const rows = [
      {phase: 'Day 1', ...module.data.day1},
      {phase: 'Day 2', ...module.data.day2},
    ];
    section.append(rowsTable(rows, [
      ['Phase', 'phase'],
      ['Official record', (row) => formatRecord(row.record)],
      ['Observed win rate', (row) => formatPercent(row.observed_win_rate)],
    ]));
    if (module.data.conversion) {
      section.append(textElement(
        'p',
        `Conversion: ${module.data.conversion.day2_players}/${module.data.conversion.first_phase_players} (${formatPercent(module.data.conversion.rate)})`,
      ));
    }
    return section;
  }

  function renderTopFinishers(module, report) {
    const section = moduleSection(module, report);
    section.append(rowsTable(module.data.rows, [
      ['Place', 'placement'],
      ['Player', 'player_name'],
      ['Points', 'points'],
      ['Official record', (row) => formatRecord(row.record)],
    ]));
    return section;
  }

  function renderMatchupGroup(report) {
    const wrapper = document.createElement('div');
    wrapper.className = 'tournament-report-phase-group';
    wrapper.append(phaseControls(
      'Matchup phase',
      [['overall', 'Overall'], ['day2', 'Day 2']],
      state.modulePhases.matchups,
      (phase) => {
        state = reduceReportSelection(state, {type: 'set-matchup-phase', phase});
        wrapper.replaceWith(renderMatchupGroup(report));
      },
    ));
    const module = archetypeModuleForPhase(report, 'matchups', state.modulePhases.matchups);
    wrapper.append(renderMatchups(module, report));
    return wrapper;
  }

  function renderMatchups(module, report) {
    const section = moduleSection(module, report);
    const unavailable = matchupAvailabilityMessage(module);
    if (unavailable) {
      const message = textElement('p', unavailable);
      message.className = 'tournament-report-insufficient';
      section.append(message);
    } else {
      section.append(rowsTable(module.data.rows, [
        ['Opponent', 'opponent_name'],
        ['Matches', 'matches'],
        ['Official record', (row) => formatRecord(row.record)],
        ['Observed win rate', (row) => formatPercent(row.observed_win_rate)],
      ]));
    }
    section.append(textElement(
      'p',
      `Excluded: ${module.data.unknown_count} unknown opponent · ${module.data.procedural_count} procedural result`,
    ));
    return section;
  }

  function renderCompositionGroup(report) {
    const wrapper = document.createElement('div');
    wrapper.className = 'tournament-report-phase-group';
    wrapper.append(phaseControls(
      'Deck-list phase',
      [['first_phase', 'First Phase'], ['day2', 'Day 2'], ['top_cut', 'Top Cut']],
      state.modulePhases.composition,
      (phase) => {
        state = reduceReportSelection(state, {type: 'set-composition-phase', phase});
        wrapper.replaceWith(renderCompositionGroup(report));
      },
    ));
    const module = archetypeModuleForPhase(report, 'composition', state.modulePhases.composition);
    wrapper.append(renderDeckComposition(module, report));
    return wrapper;
  }

  function renderDeckComposition(module, report) {
    const section = moduleSection(module, report);
    section.append(textElement(
      'p',
      `${module.data.valid_lists}/${module.data.eligible_players} valid lists · ${formatPercent(module.data.coverage)} coverage`,
    ));
    if (!module.data.eligible_for_classification) {
      section.append(emptyState('Not enough covered deck lists to classify Core, Common, or Tech cards.'));
      return section;
    }
    const labels = {core: 'Core', common: 'Common', tech: 'Tech', rare: 'Rare / Other'};
    for (const bucket of ['core', 'common', 'tech', 'rare']) {
      const rows = module.data.rows.filter((row) => row.bucket === bucket);
      if (!rows.length) continue;
      section.append(textElement('h4', labels[bucket]));
      section.append(rowsTable(rows, [
        ['Card', 'display_name'],
        ['Appearance', (row) => formatPercent(row.appearance_rate)],
        ['Average copies when present', (row) => Number(row.average_when_present).toFixed(2)],
      ]));
    }
    return section;
  }

  function renderRepresentativeLists(module, report) {
    const section = moduleSection(module, report);
    module.data.rows.slice(0, 3).forEach((row) => {
      const article = document.createElement('article');
      article.className = 'tournament-report-list';
      article.append(textElement(
        'h4',
        `${row.player_name} · #${row.placement ?? '—'} · ${row.points} points`,
      ));
      article.append(rowsTable(row.cards, [
        ['Count', 'count'],
        ['Card', 'display_name'],
        ['Set', 'set_code'],
        ['Collector no.', 'collector_number'],
      ]));
      section.append(article);
    });
    if (!module.data.rows.length) section.append(emptyState('No valid representative lists.'));
    return section;
  }

  function phaseControls(label, options, selected, onSelect) {
    const group = document.createElement('div');
    group.className = 'tournament-report-phase-controls';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    options.forEach(([value, text]) => {
      const button = textElement('button', text);
      button.type = 'button';
      button.className = `button small${value === selected ? ' primary' : ''}`;
      button.setAttribute('aria-pressed', String(value === selected));
      button.addEventListener('click', () => onSelect(value));
      group.append(button);
    });
    return group;
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

  function moduleSection(module, report = null) {
    const section = document.createElement('section');
    const availability = moduleAvailability(module);
    section.className = 'card tournament-report-module tournament-report-state';
    section.dataset.state = availability.kind;
    section.append(textElement('h3', module.title));
    if (availability.message) section.append(textElement('p', availability.message));
    section.append(textElement('small', `n=${module.sample_size} · ${module.metric_notes.join(' ')}`));
    if (report) {
      section.append(textElement(
        'small',
        `${report.event.name} · ${report.selection.grain} ${report.selection.selection_id} · ${phaseLabel(module.phase)} · ${module.provenance.source_provider} · source updated ${formatTimestamp(module.provenance.source_updated_at)} · fetched ${formatTimestamp(module.provenance.fetched_at)}`,
      ));
    }
    const activeReport = report || state.report;
    if (activeReport && PNG_EXPORT_MODULE_IDS.includes(module.module_id) && availability.canExport) {
      const actions = document.createElement('div');
      actions.className = 'tournament-report-module-actions';
      const button = textElement('button', 'Export PNG');
      button.type = 'button';
      button.className = 'button small';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          await exportModulePng(section, module, exportContext(activeReport, module));
          notification.textContent = `${module.title} exported as PNG.`;
        } catch (error) {
          notification.textContent = `PNG export failed: ${error.message}`;
        } finally {
          button.disabled = false;
        }
      });
      actions.append(button);
      section.append(actions);
    }
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


function formatTimestamp(value) {
  return value ? new Date(value).toLocaleString() : 'unknown';
}


function exportContext(report, module) {
  return {
    datasetId: report.dataset_id,
    eventName: report.event.name,
    eventDate: report.event.date,
    grain: module.grain || report.selection?.grain || 'event',
    selectionId: module.selection_id || report.selection?.selection_id || 'overview',
    selectionLabel: report.selection?.selection_id || 'Event overview',
    phaseLabel: phaseLabel(module.phase),
    snapshotVersion: report.snapshot_version,
    sourceProvider: module.provenance.source_provider,
    sourceUpdatedAt: module.provenance.source_updated_at,
    fetchedAt: module.provenance.fetched_at,
    projectAttribution: 'PTCG Deck Analysis',
  };
}


function loadSvgImage(svg) {
  return new Promise((resolve, reject) => {
    const blob = new Blob([svg], {type: 'image/svg+xml;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Could not render the export document.'));
    };
    image.src = url;
  });
}


function canvasBlob(canvas, type) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error('Could not encode the PNG.'));
    }, type);
  });
}


function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
