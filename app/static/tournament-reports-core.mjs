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
  'matchups_day2',
  'deck_composition_first_phase',
  'deck_composition_day2',
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
        modulePhases: {matchups: 'overall', composition: 'first_phase'},
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


export function buildOverviewChartModel(module, selectedFamilyId) {
  const groups = module.module_id === 'phase_topcut_distribution'
    ? [
        ['first_phase', module.data.first_phase || []],
        ['top_cut', module.data.top_cut || []],
      ]
    : [[module.phase || 'overall', module.data.rows || []]];
  return {
    series: groups.map(([phase, rows]) => ({
      phase,
      marks: rows.map((row, index) => overviewMark(row, index, selectedFamilyId)),
    })),
  };
}


function overviewMark(row, index, selectedFamilyId) {
  const familyId = row.family_id;
  const record = row.record || {wins: 0, losses: 0, ties: 0};
  const share = row.share ?? row.rate ?? null;
  const label = row.family_name || row.label || familyId;
  const players = row.players ?? row.first_phase_players ?? 0;
  const tooltipParts = [
    label,
    `${players} players`,
    share === null ? null : formatPercent(share),
    row.record ? `${record.wins}-${record.losses}-${record.ties}` : null,
    row.observed_win_rate === null || row.observed_win_rate === undefined
      ? null
      : `${formatObservedWinRate(row.observed_win_rate)} observed win rate`,
  ].filter(Boolean);
  return {
    familyId,
    label,
    players,
    share,
    x: 0,
    y: index * 36,
    width: share === null ? 0 : share * 100,
    colorIndex: index,
    selected: familyId === selectedFamilyId,
    tooltip: tooltipParts.join(' · '),
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


function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}
