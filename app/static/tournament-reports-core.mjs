/**
 * @typedef {Object} ReportUiState
 * @property {string|null} datasetId
 * @property {string|null} selectedFamilyId
 * @property {string[]} visibleFamilyIds
 * @property {string|null} familyReportAction
 * @property {{grain: 'family'|'variant', selectionId: string}|null} selection
 * @property {{matchups: string, composition: string}} modulePhases
 * @property {number} requestGeneration
 * @property {number} appliedGeneration
 * @property {Object|null} report
 */

export const ARCHETYPE_MODULE_IDS = Object.freeze([
  'headline_performance',
  'phase_performance',
  'top_finishers',
  'matchups_overall',
  'matchups_phase1',
  'matchups_phase2',
  'deck_composition_phase1',
  'deck_composition_phase2',
  'deck_composition_top_cut',
  'representative_lists',
]);

export const PNG_EXPORT_MODULE_IDS = Object.freeze([
  'phase1_meta_share',
  'phase2_meta_share',
  'family_ranking',
  'headline_performance',
  'phase_performance',
  'top_finishers',
  'matchups_overall',
  'matchups_phase1',
  'matchups_phase2',
  'deck_composition_phase1',
  'deck_composition_phase2',
  'deck_composition_top_cut',
  'representative_lists',
]);

/**
 * @typedef {{type: string, familyId?: string, variantId?: string, generation?: number, report?: Object}} ReportUiAction
 */

/**
 * @typedef {{series: Array<{phase: string, marks: Array<Object>}>}} OverviewChartModel
 */


export function createReportRoute(view, datasetId, grain = null, selectionId = null) {
  if (view === 'index') return '/tournament-reports';
  if (!datasetId) throw new TypeError('datasetId is required for report routes');
  const dataset = encodeURIComponent(datasetId);
  if (view === 'overview') return `/tournament-reports/${dataset}`;
  if (!selectionId) throw new TypeError('selectionId is required for archetype routes');
  const selection = encodeURIComponent(selectionId);
  if (view === 'family' && grain === 'family') {
    return `/tournament-reports/${dataset}/families/${selection}`;
  }
  if (view === 'variant' && grain === 'variant') {
    return `/tournament-reports/${dataset}/variants/${selection}`;
  }
  throw new TypeError(`unsupported report route: ${view}`);
}


/** @param {ReportUiState} state @param {ReportUiAction} action */
export function reduceReportSelection(state, action) {
  switch (action.type) {
    case 'select-family': {
      const familyId = action.familyId;
      return {
        ...state,
        selectedFamilyId: familyId,
        familyReportAction: createReportRoute(
          'family', state.datasetId, 'family', familyId,
        ),
      };
    }
    case 'select-variant':
      return {
        ...state,
        selection: {grain: 'variant', selectionId: action.variantId},
        modulePhases: {matchups: 'overall', composition: 'phase1'},
      };
    case 'set-matchup-phase':
      return {
        ...state,
        modulePhases: {...state.modulePhases, matchups: action.phase},
      };
    case 'set-composition-phase':
      return {
        ...state,
        modulePhases: {...state.modulePhases, composition: action.phase},
      };
    case 'request-report':
      return {...state, requestGeneration: state.requestGeneration + 1};
    case 'receive-report':
      return action.generation === state.requestGeneration
        ? {
            ...state,
            report: action.report,
            appliedGeneration: action.generation,
          }
        : state;
    default:
      return state;
  }
}


export function archetypeModuleForPhase(report, owner, phase) {
  const moduleId = owner === 'matchups'
    ? `matchups_${phase}`
    : `deck_composition_${phase}`;
  return report.modules.find((module) => module.module_id === moduleId) || null;
}


export function matchupAvailabilityMessage(module) {
  if (module.sample_size === 0) return 'No matches';
  if (module.sample_size < 30) return `Insufficient sample (n=${module.sample_size})`;
  return '';
}


export function toggleExpandedFamily(expandedFamilyId, familyId) {
  return expandedFamilyId === familyId ? null : familyId;
}


export function nextTableSort(current, key, defaultKey) {
  if (!current) return {key: defaultKey, direction: 'desc'};
  if (current.key !== key) return {key, direction: 'desc'};
  return {key, direction: current.direction === 'desc' ? 'asc' : 'desc'};
}


export function sortMatchupRows(rows, sort = {key: 'matches', direction: 'desc'}) {
  return [...(rows || [])].sort((left, right) => {
    const primary = sort.key === 'opponent_name'
      ? compareText(left.opponent_name, right.opponent_name) * (sort.direction === 'desc' ? -1 : 1)
      : compareNullableNumberDirected(left[sort.key], right[sort.key], sort.direction);
    if (primary) return primary;
    return compareNullableNumberDirected(left.matches, right.matches, 'desc')
      || compareNullableNumberDirected(left.observed_win_rate, right.observed_win_rate, 'desc')
      || compareText(left.opponent_name, right.opponent_name)
      || compareText(left.opponent_id, right.opponent_id);
  });
}


export function sortOverviewRows(rows, sort = {key: 'share', direction: 'desc'}) {
  return [...(rows || [])].sort((left, right) => {
    const primary = compareNullableNumberDirected(left[sort.key], right[sort.key], sort.direction);
    if (primary) return primary;
    return compareNullableNumberDirected(left.share, right.share, 'desc')
      || compareNullableNumberDirected(left.observed_win_rate, right.observed_win_rate, 'desc')
      || compareText(left.family_name || left.variant_name, right.family_name || right.variant_name)
      || compareText(left.family_id || left.variant_id, right.family_id || right.variant_id);
  });
}


export function buildExpandableFamilyModel(
  module,
  expandedFamilyId,
  sort = {key: 'share', direction: 'desc'},
) {
  return {
    rows: sortOverviewRows(module.data.rows || [], sort).map((row) => {
      const expanded = row.family_id === expandedFamilyId;
      return {
        familyId: row.family_id,
        familyName: row.family_name,
        players: row.players,
        share: row.share,
        reportEligible: row.report_eligible === true,
        record: row.record || null,
        observedWinRate: row.observed_win_rate ?? null,
        expanded,
        variants: expanded
          ? sortOverviewRows(row.variants || [], sort).map((variant) => ({
              variantId: variant.variant_id,
              variantName: variant.variant_name,
              players: variant.players,
              share: variant.share,
              observedWinRate: variant.observed_win_rate ?? null,
              reportEligible: variant.report_eligible === true,
              record: variant.record || null,
            }))
          : [],
      };
    }),
  };
}


export function moduleAvailability(module) {
  return {
    kind: module.status.state,
    message: module.status.message || '',
    canExport: module.status.state === 'ready' && module.status.exportable === true,
  };
}


export function formatObservedWinRate(value) {
  return value === null || value === undefined ? '—' : formatPercent(value);
}


export function assertExportable(module, context) {
  if (module.status.state !== 'ready') {
    throw new Error('Module must be ready before export.');
  }
  if (module.status.exportable !== true) {
    throw new Error('Module export is disabled.');
  }
  if (module.provenance.snapshot_version !== context.snapshotVersion) {
    throw new Error('Module snapshot version does not match the displayed report.');
  }
}


export function exportFilename(module, context) {
  const parts = [
    context.datasetId,
    module.module_id,
    context.grain || module.grain || 'event',
    context.selectionId || module.selection_id || 'overview',
    module.phase || 'overall',
  ];
  return `${parts.map(asciiSlug).join('-')}.png`;
}


export function buildModuleSvg(module, context) {
  assertExportable(module, context);
  const titleLines = wrapWords(module.title, 48);
  const eventLines = wrapWords(context.eventName, 58);
  const body = renderExportBody(module);
  const notes = wrapWords(module.metric_notes.join(' '), 92).slice(0, 3);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350" viewBox="0 0 1080 1350">
  <rect width="1080" height="1350" fill="#f8fafc"/>
  <style>text{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#172033}.muted{fill:#64748b}.title{font-size:54px;font-weight:800}.event{font-size:28px;font-weight:700}.meta{font-size:24px}.body-head{font-size:25px;font-weight:750}.body{font-size:22px}.foot{font-size:18px}</style>
  ${svgLines(eventLines, 70, 82, 34, 'event')}
  <text x="70" y="150" class="meta muted">${escapeXml(context.eventDate)} · ${escapeXml(context.selectionLabel)} · ${escapeXml(context.phaseLabel)}</text>
  ${svgLines(titleLines, 70, 235, 62, 'title')}
  <text x="70" y="${235 + titleLines.length * 62 + 18}" class="meta muted">n=${module.sample_size} · ${escapeXml(module.grain || context.grain || 'event')} · ${escapeXml(module.phase)}</text>
  <line x1="70" y1="410" x2="1010" y2="410" stroke="#d7dce5" stroke-width="2"/>
  ${body}
  <line x1="70" y1="1115" x2="1010" y2="1115" stroke="#d7dce5" stroke-width="2"/>
  <text x="70" y="1155" class="body-head">Sample &amp; statistical definition</text>
  ${svgLines(notes, 70, 1190, 27, 'foot muted')}
  <text x="70" y="1284" class="foot muted">${escapeXml(context.sourceProvider)} · source updated ${escapeXml(context.sourceUpdatedAt || 'unknown')} · fetched ${escapeXml(context.fetchedAt)}</text>
  <text x="70" y="1318" class="foot muted">Snapshot ${escapeXml(context.snapshotVersion)} · ${escapeXml(context.projectAttribution)}</text>
</svg>`;
}


function renderExportBody(module) {
  if (module.module_id.startsWith('matchups_')) {
    return renderRows(
      module.data.rows,
      (row) => row.opponent_name,
      (row) => `n=${row.matches} · ${recordText(row.record)} · Observed win rate ${formatObservedWinRate(row.observed_win_rate)}`,
    );
  }
  if (module.module_id === 'phase1_meta_share' || module.module_id === 'phase2_meta_share') {
    return renderRows((module.data.rows || []).slice(0, 10), (row) => row.family_name, (row) => `${row.players} players · ${formatPercent(row.share)}`);
  }
  if (module.module_id === 'family_ranking') {
    return renderRows((module.data.rows || []).slice(0, 12), (row) => row.family_name, (row) => `${row.players} players · ${formatPercent(row.share)} · Observed win rate ${formatObservedWinRate(row.observed_win_rate)}`);
  }
  if (module.module_id.startsWith('deck_composition_')) {
    return renderRows((module.data.rows || []).slice(0, 13), (row) => row.display_name, (row) => `${bucketLabel(row.bucket)} · ${formatPercent(row.appearance_rate)} appearance · ${Number(row.average_when_present).toFixed(2)} copies${row.appearance_rate_delta_pp === null || row.appearance_rate_delta_pp === undefined ? '' : ` · ${formatSigned(row.appearance_rate_delta_pp)} pp`}`);
  }
  if (module.module_id === 'top_finishers') {
    return renderRows(module.data.rows || [], (row) => `#${row.placement ?? '—'} ${row.player_name}`, (row) => `${row.points} points · ${recordText(row.record)}`);
  }
  if (module.module_id === 'representative_lists') {
    return renderRows((module.data.rows || []).slice(0, 3), (row) => `#${row.placement ?? '—'} ${row.player_name}`, (row) => `${row.points} points · ${row.cards.length} distinct cards`);
  }
  if (module.module_id === 'phase_performance') {
    return renderRows([
      {label: 'Phase 1', ...module.data.phase1},
      {label: 'Phase 2', ...module.data.phase2},
    ], (row) => row.label, (row) => `${recordText(row.record)} · Observed win rate ${formatObservedWinRate(row.observed_win_rate)}`);
  }
  if (module.module_id === 'headline_performance') {
    return renderRows([module.data], () => `${module.data.players} players`, (row) => `${recordText(row.record)} · Observed win rate ${formatObservedWinRate(row.observed_win_rate)}`);
  }
  return '<text x="70" y="480" class="body muted">No visualization rows available.</text>';
}


function renderRows(rows, label, detail) {
  return (rows || []).slice(0, 14).map((row, index) => {
    const y = 470 + index * 44;
    return `<text x="70" y="${y}" class="body-head">${escapeXml(label(row))}</text><text x="500" y="${y}" class="body muted">${escapeXml(detail(row))}</text>`;
  }).join('\n  ');
}


function svgLines(lines, x, y, lineHeight, className) {
  return `<text x="${x}" y="${y}" class="${className}">${lines.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${escapeXml(line)}</tspan>`).join('')}</text>`;
}


function wrapWords(value, limit) {
  const words = String(value ?? '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [''];
  const lines = [];
  let line = '';
  for (const word of words) {
    if (line && `${line} ${word}`.length > limit) {
      lines.push(line);
      line = word;
    } else {
      line = line ? `${line} ${word}` : word;
    }
  }
  lines.push(line);
  return lines;
}


function escapeXml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}


function asciiSlug(value) {
  const slug = String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'unknown';
}


function recordText(record) {
  return record ? `${record.wins}-${record.losses}-${record.ties}` : '—';
}


function bucketLabel(bucket) {
  return {core: 'Core', common: 'Common', tech: 'Tech', rare: 'Rare / Other'}[bucket] || bucket;
}


function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}


function formatSigned(value) {
  const number = Number(value);
  return `${number > 0 ? '+' : ''}${number.toFixed(1)}`;
}


function compareNullableNumberDirected(left, right, direction) {
  const leftMissing = left === null || left === undefined || Number.isNaN(Number(left));
  const rightMissing = right === null || right === undefined || Number.isNaN(Number(right));
  if (leftMissing || rightMissing) {
    if (leftMissing && rightMissing) return 0;
    return leftMissing ? 1 : -1;
  }
  const compared = Number(left) - Number(right);
  return direction === 'desc' ? -compared : compared;
}


function compareText(left, right) {
  return String(left ?? '').localeCompare(String(right ?? ''), 'en', {sensitivity: 'base'});
}
