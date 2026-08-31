import {
  ARCHETYPE_MODULE_IDS,
  COMPOSITION_TABS,
  PNG_EXPORT_MODULE_IDS,
  archetypeModuleForPhase,
  assertExportable,
  buildCompositionProgressionModel,
  buildExpandableFamilyModel,
  buildModuleSvg,
  createReportRoute,
  moduleAvailability,
  reduceReportSelection,
  matchupAvailabilityMessage,
  nextTableSort,
  replaceSortedView,
  sortMatchupRows,
  tableHeaderPresentation,
  toggleExpandedFamily,
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
  const expandedFamilies = new Map();
  const tableSorts = new Map();

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
    expandedFamilies.clear();
    tableSorts.clear();
    const report = await requestJson(`/api/v1/tournament-reports/${encodeURIComponent(datasetId)}`);
    if (disposed || state.datasetId !== datasetId) return;
    title.textContent = report.event.name;
    state = {...state, report};
    status.textContent = `${report.event.date} · ${report.event.division} · Snapshot ${report.snapshot_version}`;
    renderBreadcrumbs(report);
    overview.replaceChildren();
    const renderers = {
      event_identity: renderEventIdentity,
      phase1_meta_share: renderExpandableFamilyModule,
      phase2_meta_share: renderExpandableFamilyModule,
      family_ranking: renderExpandableFamilyModule,
    };
    for (const module of report.modules) {
      const renderer = renderers[module.module_id];
      if (renderer) overview.append(renderer(module));
    }
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
      node.textContent = `${option.label} · ${option.phase1_players} players`;
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
      {phase: 'Phase 1', ...module.data.phase1},
      {phase: 'Phase 2', ...module.data.phase2},
    ];
    section.append(rowsTable(rows, [
      ['Phase', 'phase'],
      ['Official record', (row) => formatRecord(row.record)],
      ['Observed win rate', (row) => formatPercent(row.observed_win_rate)],
    ]));
    if (module.data.conversion) {
      section.append(textElement(
        'p',
        `Conversion: ${module.data.conversion.phase2_players}/${module.data.conversion.phase1_players} (${formatPercent(module.data.conversion.rate)})`,
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
      [['overall', 'Overall'], ['phase1', 'Phase 1'], ['phase2', 'Phase 2']],
      state.modulePhases.matchups,
      (phase) => {
        state = reduceReportSelection(state, {type: 'set-matchup-phase', phase});
        wrapper.replaceWith(renderMatchupGroup(report));
      },
    ));
    const module = archetypeModuleForPhase(report, 'matchups', state.modulePhases.matchups);
    const sort = tableSorts.get(module.module_id) || {key: 'matches', direction: 'desc'};
    wrapper.append(renderMatchups(module, report, sort, (key) => {
      tableSorts.set(module.module_id, nextTableSort(sort, key, 'matches'));
      replaceSortedView(wrapper, renderMatchupGroup(report), key);
    }));
    return wrapper;
  }

  function renderMatchups(module, report, sort, onSort) {
    const section = moduleSection(module, report);
    const unavailable = matchupAvailabilityMessage(module);
    if (unavailable) {
      const message = textElement('p', unavailable);
      message.className = 'tournament-report-insufficient';
      section.append(message);
    } else {
      section.append(sortableRowsTable(sortMatchupRows(module.data.rows, sort), [
        ['Opponent', 'opponent_name', 'opponent_name'],
        ['Matches', 'matches', 'matches'],
        ['Official record', (row) => formatRecord(row.record), null],
        ['Observed win rate', (row) => formatPercent(row.observed_win_rate), 'observed_win_rate'],
      ], sort, onSort));
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
      COMPOSITION_TABS,
      state.modulePhases.composition,
      (phase) => {
        state = reduceReportSelection(state, {type: 'set-composition-phase', phase});
        wrapper.replaceWith(renderCompositionGroup(report));
      },
    ));
    if (state.modulePhases.composition === 'progression') {
      wrapper.append(renderCompositionProgression(report));
      return wrapper;
    }
    const module = archetypeModuleForPhase(report, 'composition', state.modulePhases.composition);
    wrapper.append(renderDeckComposition(module, report));
    return wrapper;
  }

  function renderCompositionProgression(report) {
    const model = buildCompositionProgressionModel(report);
    const section = document.createElement('section');
    section.className = 'card tournament-report-module tournament-report-progression';
    section.append(
      textElement('h3', 'Deck Composition Progression: Phase 1 → Phase 2 → Top Cut'),
      textElement(
        'p',
        'This view follows card representation within the selected archetype across all three competition stages, highlighting where the list pool broadens, concentrates, or changes direction.',
      ),
    );
    if (model.smallSampleDescriptive) {
      const warning = textElement(
        'p',
        'Top Cut is a small sample — deviations are descriptive signals, not statistical-significance claims.',
      );
      warning.className = 'tournament-report-descriptive';
      section.append(warning);
    }
    if (!model.available) {
      section.append(emptyState(model.reason));
      return section;
    }

    const stageSummary = document.createElement('div');
    stageSummary.className = 'tournament-report-progression-stages';
    model.stages.forEach((stage) => {
      const card = document.createElement('article');
      card.className = 'tournament-report-progression-stage';
      card.append(
        textElement('h4', stage.label),
        textElement('strong', `${stage.validLists}/${stage.eligiblePlayers} valid lists`),
        textElement('span', `${formatPercent(stage.coverage)} coverage`),
        textElement('span', `${stage.representedCards} represented cards · ${stage.coreCards} core`),
        textElement('span', `${formatPercent(stage.coreSlotConcentration)} core-slot concentration`),
      );
      stageSummary.append(card);
    });
    section.append(
      textElement('h4', 'Diversity and concentration shift'),
      textElement(
        'p',
        'Represented cards measure composition breadth. Core-slot concentration estimates the share of expected deck slots supplied by cards appearing in at least 80% of valid lists.',
      ),
      stageSummary,
    );

    const callouts = document.createElement('div');
    callouts.className = 'tournament-report-progression-callouts';
    callouts.append(
      progressionCallout('Rising representation', model.risers, (row) => `${row.displayName} (+${formatCompactNumber(row.positiveMovement)} pp)`),
      progressionCallout('Falling representation', model.fallers, (row) => `${row.displayName} (−${formatCompactNumber(row.negativeMovement)} pp)`),
      progressionCallout('Disappeared by Top Cut', model.disappeared, (row) => row.displayName),
      progressionCallout('Noteworthy Top Cut deviations', model.topCutDeviations, (row) => `${row.displayName} (${formatPercentagePointDelta(row.phase2ToTopCutDeltaPp)})`),
    );
    section.append(textElement('h4', 'Material movement'), callouts);

    const flow = document.createElement('div');
    flow.className = 'tournament-report-progression-flow';
    flow.setAttribute('role', 'list');
    model.rows.slice(0, 12).forEach((row) => {
      const item = document.createElement('article');
      item.className = 'tournament-report-progression-row';
      item.setAttribute('role', 'listitem');
      item.setAttribute(
        'aria-label',
        `${row.displayName}: Phase 1 ${formatPercent(row.phase1Rate)}, Phase 2 ${formatPercent(row.phase2Rate)}, Top Cut ${formatPercent(row.topCutRate)}; ${progressionTrendLabel(row.trend)}`,
      );
      item.append(textElement('strong', row.displayName));
      [
        ['Phase 1', row.phase1Rate],
        ['Phase 2', row.phase2Rate],
        ['Top Cut', row.topCutRate],
      ].forEach(([label, rate]) => item.append(progressionRate(label, rate)));
      const trend = textElement('span', progressionTrendLabel(row.trend));
      trend.className = `tournament-report-progression-trend ${row.trend}`;
      item.append(trend);
      flow.append(item);
    });
    section.append(textElement('h4', 'Largest stage-to-stage shifts'), flow);
    return section;
  }

  function progressionCallout(titleText, rows, describe) {
    const article = document.createElement('article');
    article.append(textElement('h5', titleText));
    if (!rows.length) {
      article.append(textElement('p', 'No material 15-point shift.'));
      return article;
    }
    const list = document.createElement('ul');
    rows.slice(0, 4).forEach((row) => list.append(textElement('li', describe(row))));
    article.append(list);
    return article;
  }

  function progressionRate(label, rate) {
    const wrapper = document.createElement('span');
    wrapper.className = 'tournament-report-progression-rate';
    const heading = textElement('small', label);
    const meter = document.createElement('span');
    meter.className = 'tournament-report-progression-meter';
    meter.setAttribute('aria-hidden', 'true');
    const fill = document.createElement('span');
    fill.style.width = `${Math.max(0, Math.min(100, rate * 100))}%`;
    meter.append(fill);
    wrapper.append(heading, meter, textElement('b', formatPercent(rate)));
    return wrapper;
  }

  function renderDeckComposition(module, report) {
    const section = moduleSection(module, report);
    section.append(textElement(
      'p',
      `${module.data.valid_lists}/${module.data.eligible_players} valid lists · ${formatPercent(module.data.coverage)} coverage`,
    ));
    if (module.data.small_sample_descriptive) {
      const warning = textElement('p', 'Small sample — descriptive only');
      warning.className = 'tournament-report-descriptive';
      section.append(warning);
    }
    if (!module.data.eligible_for_classification) {
      section.append(emptyState('Not enough covered deck lists to classify Core, Common, or Tech cards.'));
      return section;
    }
    const labels = {core: 'Core', common: 'Common', tech: 'Tech', rare: 'Rare / Other'};
    for (const bucket of ['core', 'common', 'tech', 'rare']) {
      const rows = module.data.rows.filter((row) => row.bucket === bucket);
      if (!rows.length) continue;
      section.append(textElement('h4', labels[bucket]));
      const columns = [
        ['Card', 'display_name'],
        ['Appearance', (row) => formatPercent(row.appearance_rate)],
        ['Average copies when present', (row) => Number(row.average_when_present).toFixed(2)],
      ];
      if (module.data.comparison_available) {
        columns.push(
          ['Appearance Δ', (row) => formatPercentagePointDelta(row.appearance_rate_delta_pp)],
          ['Copies Δ', (row) => formatNumberDelta(row.average_when_present_delta)],
          ['Change', (row) => commonalityLabel(row.commonality_tag, module.phase)],
        );
      }
      section.append(rowsTable(rows, columns));
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

  function renderExpandableFamilyModule(module) {
    const section = moduleSection(module);
    const sort = tableSorts.get(module.module_id) || {key: 'share', direction: 'desc'};
    const model = buildExpandableFamilyModel(
      module,
      expandedFamilies.get(module.module_id) || null,
      sort,
    );
    const includePerformance = module.module_id === 'family_ranking';
    const table = document.createElement('table');
    table.className = 'tournament-report-table tournament-report-family-table';
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    ['', 'Archetype', 'Players'].forEach((label) => headRow.append(textElement('th', label)));
    headRow.append(sortableHeader('Share', 'share', sort, (key) => {
      tableSorts.set(module.module_id, nextTableSort(sort, key, 'share'));
      replaceSortedView(section, renderExpandableFamilyModule(module), key);
    }));
    if (includePerformance) {
      headRow.append(textElement('th', 'Official record'));
    }
    headRow.append(sortableHeader('Observed win rate', 'observed_win_rate', sort, (key) => {
      tableSorts.set(module.module_id, nextTableSort(sort, key, 'share'));
      replaceSortedView(section, renderExpandableFamilyModule(module), key);
    }));
    head.append(headRow);
    const body = document.createElement('tbody');
    model.rows.forEach((row) => {
      const familyRow = document.createElement('tr');
      familyRow.className = `tournament-report-family-row${row.expanded ? ' expanded' : ''}`;
      familyRow.dataset.familyId = row.familyId;
      const arrow = textElement('button', row.expanded ? '▾' : '▸');
      arrow.type = 'button';
      arrow.className = 'tournament-report-disclosure';
      arrow.setAttribute('aria-expanded', String(row.expanded));
      arrow.setAttribute('aria-label', `${row.expanded ? 'Collapse' : 'Expand'} ${row.familyName} variants`);
      const arrowCell = document.createElement('td');
      arrowCell.append(arrow);
      const nameCell = document.createElement('td');
      if (row.reportEligible) {
        const familyLink = textElement('button', row.familyName);
        familyLink.type = 'button';
        familyLink.className = 'tournament-report-inline-link';
        familyLink.addEventListener('click', (event) => {
          event.stopPropagation();
          go(createReportRoute('family', state.datasetId, 'family', row.familyId));
        });
        nameCell.append(familyLink);
      } else {
        const label = textElement('span', row.familyName);
        label.title = 'Family report is limited to the Phase 1 Top 10.';
        nameCell.append(label);
      }
      familyRow.append(
        arrowCell,
        nameCell,
        textElement('td', row.players),
        textElement('td', formatPercent(row.share)),
      );
      if (includePerformance) {
        familyRow.append(textElement('td', formatRecord(row.record)));
      }
      familyRow.append(textElement('td', formatPercent(row.observedWinRate)));
      const toggle = () => {
        expandedFamilies.set(
          module.module_id,
          toggleExpandedFamily(expandedFamilies.get(module.module_id) || null, row.familyId),
        );
        section.replaceWith(renderExpandableFamilyModule(module));
      };
      familyRow.addEventListener('click', toggle);
      arrow.addEventListener('click', (event) => {
        event.stopPropagation();
        toggle();
      });
      body.append(familyRow);
      row.variants.forEach((variant) => {
        const variantRow = document.createElement('tr');
        variantRow.className = 'tournament-report-variant-row';
        variantRow.append(document.createElement('td'));
        const variantName = document.createElement('td');
        if (variant.reportEligible) {
          const variantLink = textElement('button', variant.variantName);
          variantLink.type = 'button';
          variantLink.className = 'tournament-report-inline-link';
          variantLink.addEventListener('click', () => go(createReportRoute(
            'variant', state.datasetId, 'variant', variant.variantId,
          )));
          variantName.append(variantLink);
        } else {
          const label = textElement('span', variant.variantName);
          label.title = 'Variant report requires at least 10 Phase 1 players.';
          variantName.append(label);
        }
        variantRow.append(
          variantName,
          textElement('td', variant.players),
          textElement('td', formatPercent(variant.share)),
        );
        if (includePerformance) variantRow.append(textElement('td', formatRecord(variant.record)));
        variantRow.append(textElement('td', formatPercent(variant.observedWinRate)));
        body.append(variantRow);
      });
    });
    table.append(head, body);
    section.append(table);
    return section;
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

  function sortableRowsTable(rows, columns, sort, onSort) {
    const table = document.createElement('table');
    table.className = 'tournament-report-table';
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    columns.forEach(([label, , sortKey]) => {
      headRow.append(sortKey ? sortableHeader(label, sortKey, sort, onSort) : textElement('th', label));
    });
    head.append(headRow);
    const body = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      columns.forEach(([, accessor]) => {
        const value = typeof accessor === 'function' ? accessor(row) : row[accessor];
        tr.append(textElement('td', value ?? '—'));
      });
      body.append(tr);
    });
    table.append(head, body);
    return table;
  }

  function sortableHeader(label, key, sort, onSort) {
    const presentation = tableHeaderPresentation(label, key, sort);
    const header = document.createElement('th');
    header.className = 'tournament-report-sortable-header';
    header.dataset.sortActive = String(presentation.active);
    if (presentation.ariaSort) header.setAttribute('aria-sort', presentation.ariaSort);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tournament-report-sort';
    button.dataset.sortKey = key;
    button.setAttribute('aria-label', presentation.ariaLabel);
    button.append(textElement('span', presentation.label));
    const indicator = textElement('span', presentation.indicator);
    indicator.className = 'tournament-report-sort-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    button.append(indicator);
    button.addEventListener('click', () => onSort(key));
    header.append(button);
    return header;
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
    modulePhases: {matchups: 'overall', composition: 'phase1'},
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
  return {overall: 'Overall', phase1: 'Phase 1', phase2: 'Phase 2', top_cut: 'Top Cut'}[phase]
    || String(phase);
}


function formatPercentagePointDelta(value) {
  if (value === null || value === undefined) return '—';
  const number = Number(value);
  return `${number > 0 ? '+' : ''}${number.toFixed(1)} pp`;
}


function formatCompactNumber(value) {
  return Number(value).toFixed(1).replace(/\.0$/, '');
}


function progressionTrendLabel(trend) {
  return {
    rising: 'Rising',
    falling: 'Falling',
    volatile: 'Rose, then reversed',
    disappeared: 'Absent from Top Cut',
    stable: 'Broadly stable',
  }[trend] || 'Broadly stable';
}


function formatNumberDelta(value) {
  if (value === null || value === undefined) return '—';
  const number = Number(value);
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}`;
}


function commonalityLabel(tag, phase) {
  if (!tag) return '—';
  const label = tag === 'more_common' ? 'More common' : 'Less common';
  return phase === 'top_cut' ? `Descriptive: ${label}` : label;
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
