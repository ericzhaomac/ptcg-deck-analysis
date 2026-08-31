import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ARCHETYPE_MODULE_IDS,
  archetypeModuleForPhase,
  buildExpandableFamilyModel,
  createReportRoute,
  formatObservedWinRate,
  moduleAvailability,
  reduceReportSelection,
  matchupAvailabilityMessage,
  nextTableSort,
  sortMatchupRows,
  sortOverviewRows,
  toggleExpandedFamily,
} from '../../app/static/tournament-reports-core.mjs';


const INITIAL_STATE = {
  datasetId: '2026-new-orleans-ma',
  selectedFamilyId: null,
  visibleFamilyIds: ['dragapult-ex', 'charizard-ex'],
  familyReportAction: null,
  selection: null,
  modulePhases: {matchups: 'overall', composition: 'phase1'},
  requestGeneration: 0,
  appliedGeneration: 0,
  report: null,
};

const FAMILY_STATE = {
  ...INITIAL_STATE,
  selectedFamilyId: 'dragapult-ex',
  selection: {grain: 'family', selectionId: 'dragapult-ex'},
  modulePhases: {matchups: 'phase2', composition: 'top_cut'},
};

const DISTRIBUTION_MODULE = {
  module_id: 'phase1_meta_share',
  phase: 'phase1',
  status: {state: 'ready', exportable: true, message: null},
  data: {
    rows: [
      {
        family_id: 'dragapult-ex',
        family_name: 'Dragapult',
        players: 20,
        share: 0.5,
        report_eligible: true,
        variants: [
          {variant_id: 'dragapult-ex', variant_name: 'Dragapult', players: 12, share: 0.3, report_eligible: true},
          {variant_id: 'dragapult-dusknoir', variant_name: 'Dragapult Dusknoir', players: 8, share: 0.2, observed_win_rate: 0.7, report_eligible: false},
        ],
      },
      {
        family_id: 'charizard-ex',
        family_name: 'Charizard',
        players: 10,
        share: 0.25,
        report_eligible: false,
        variants: [],
      },
    ],
  },
};


test('report routes encode every dynamic path segment', () => {
  assert.equal(createReportRoute('index', null), '/tournament-reports');
  assert.equal(
    createReportRoute('overview', '2026 new/orleans'),
    '/tournament-reports/2026%20new%2Forleans',
  );
  assert.equal(
    createReportRoute('family', 'event', 'family', 'dragapult ex'),
    '/tournament-reports/event/families/dragapult%20ex',
  );
  assert.equal(
    createReportRoute('variant', 'event', 'variant', 'pult/dusk'),
    '/tournament-reports/event/variants/pult%2Fdusk',
  );
});


test('selecting a family synchronizes overview highlights without filtering rows', () => {
  const next = reduceReportSelection(INITIAL_STATE, {
    type: 'select-family',
    familyId: 'dragapult-ex',
  });

  assert.equal(next.selectedFamilyId, 'dragapult-ex');
  assert.equal(next.visibleFamilyIds.length, INITIAL_STATE.visibleFamilyIds.length);
  assert.equal(
    next.familyReportAction,
    '/tournament-reports/2026-new-orleans-ma/families/dragapult-ex',
  );
});


test('grain change clears stale module phases and carries event context', () => {
  const next = reduceReportSelection(FAMILY_STATE, {
    type: 'select-variant',
    variantId: 'dragapult-dusknoir',
  });

  assert.deepEqual(next.selection, {
    grain: 'variant',
    selectionId: 'dragapult-dusknoir',
  });
  assert.deepEqual(next.modulePhases, {
    matchups: 'overall',
    composition: 'phase1',
  });
  assert.equal(next.datasetId, '2026-new-orleans-ma');
});


test('stale report responses cannot replace the latest generation', () => {
  const requested = reduceReportSelection(
    reduceReportSelection(INITIAL_STATE, {type: 'request-report'}),
    {type: 'request-report'},
  );
  const stale = reduceReportSelection(requested, {
    type: 'receive-report',
    generation: 1,
    report: {snapshot_version: 'old'},
  });
  const current = reduceReportSelection(stale, {
    type: 'receive-report',
    generation: 2,
    report: {snapshot_version: 'new'},
  });

  assert.equal(stale.report, null);
  assert.equal(current.report.snapshot_version, 'new');
  assert.equal(current.appliedGeneration, 2);
});


test('expandable family model reveals variants in place without changing family ranking', () => {
  const collapsed = buildExpandableFamilyModel(DISTRIBUTION_MODULE, null);
  const expanded = buildExpandableFamilyModel(DISTRIBUTION_MODULE, 'dragapult-ex');

  assert.equal(collapsed.rows.length, 2);
  assert.deepEqual(collapsed.rows.map((row) => row.familyId), ['dragapult-ex', 'charizard-ex']);
  assert.deepEqual(collapsed.rows.flatMap((row) => row.variants), []);
  assert.equal(expanded.rows.length, 2);
  assert.equal(expanded.rows[0].expanded, true);
  assert.equal(expanded.rows[0].reportEligible, true);
  assert.equal(expanded.rows[1].reportEligible, false);
  assert.deepEqual(
    expanded.rows[0].variants.map((row) => row.variantId),
    ['dragapult-ex', 'dragapult-dusknoir'],
  );
  assert.equal(
    expanded.rows[0].variants.reduce((total, row) => total + row.share, 0),
    expanded.rows[0].share,
  );
});


test('family expansion toggles closed when the same row is clicked twice', () => {
  const expanded = toggleExpandedFamily(null, 'dragapult-ex');
  assert.equal(expanded, 'dragapult-ex');
  assert.equal(toggleExpandedFamily(expanded, 'dragapult-ex'), null);
  assert.equal(toggleExpandedFamily(expanded, 'charizard-ex'), 'charizard-ex');
});


test('module availability never exports degraded or blocked data', () => {
  assert.deepEqual(moduleAvailability(DISTRIBUTION_MODULE), {
    kind: 'ready',
    message: '',
    canExport: true,
  });
  assert.deepEqual(
    moduleAvailability({status: {state: 'degraded', exportable: true, message: 'Low sample'}}),
    {kind: 'degraded', message: 'Low sample', canExport: false},
  );
});


test('observed win rate formatter distinguishes missing values', () => {
  assert.equal(formatObservedWinRate(0.625), '62.5%');
  assert.equal(formatObservedWinRate(null), '—');
});


test('phase actions update only their owning module', () => {
  const matchup = reduceReportSelection(FAMILY_STATE, {
    type: 'set-matchup-phase',
    phase: 'phase2',
  });
  assert.equal(matchup.modulePhases.matchups, 'phase2');
  assert.equal(matchup.modulePhases.composition, 'top_cut');

  const composition = reduceReportSelection(matchup, {
    type: 'set-composition-phase',
    phase: 'phase1',
  });
  assert.equal(composition.modulePhases.matchups, 'phase2');
  assert.equal(composition.modulePhases.composition, 'phase1');
});


test('archetype module contract and phase lookup use exact server module ids', () => {
  assert.deepEqual(ARCHETYPE_MODULE_IDS, [
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
  const report = {
    modules: ARCHETYPE_MODULE_IDS.map((module_id) => ({module_id})),
  };
  assert.equal(
    archetypeModuleForPhase(report, 'matchups', 'phase2').module_id,
    'matchups_phase2',
  );
  assert.equal(
    archetypeModuleForPhase(report, 'composition', 'top_cut').module_id,
    'deck_composition_top_cut',
  );
});


test('matchup sorting is immutable with deterministic tie breakers', () => {
  const rows = [
    {opponent_id: 'z', opponent_name: 'Zoroark', matches: 10, observed_win_rate: 0.5},
    {opponent_id: 'a', opponent_name: 'Arceus', matches: 10, observed_win_rate: 0.5},
    {opponent_id: 'b', opponent_name: 'Baxcalibur', matches: 8, observed_win_rate: 0.7},
  ];
  const snapshot = structuredClone(rows);

  assert.deepEqual(
    sortMatchupRows(rows, {key: 'matches', direction: 'desc'}).map((row) => row.opponent_id),
    ['a', 'z', 'b'],
  );
  assert.deepEqual(
    sortMatchupRows(rows, {key: 'observed_win_rate', direction: 'asc'}).map((row) => row.opponent_id),
    ['a', 'z', 'b'],
  );
  assert.deepEqual(rows, snapshot);
});


test('overview sorting keeps membership and expansion while variants follow active sort', () => {
  const sorted = sortOverviewRows(DISTRIBUTION_MODULE.data.rows, {
    key: 'observed_win_rate', direction: 'desc',
  });
  const model = buildExpandableFamilyModel(
    {...DISTRIBUTION_MODULE, data: {rows: sorted}},
    'dragapult-ex',
    {key: 'observed_win_rate', direction: 'desc'},
  );

  assert.deepEqual(new Set(model.rows.map((row) => row.familyId)), new Set(['dragapult-ex', 'charizard-ex']));
  assert.equal(model.rows.find((row) => row.familyId === 'dragapult-ex').expanded, true);
  assert.deepEqual(
    model.rows.find((row) => row.familyId === 'dragapult-ex').variants.map((row) => row.variantId),
    ['dragapult-dusknoir', 'dragapult-ex'],
  );
});


test('sortable headers default descending and then toggle direction', () => {
  const share = nextTableSort(null, 'share', 'share');
  assert.deepEqual(share, {key: 'share', direction: 'desc'});
  assert.deepEqual(nextTableSort(share, 'share', 'share'), {key: 'share', direction: 'asc'});
  assert.deepEqual(nextTableSort(share, 'observed_win_rate', 'share'), {
    key: 'observed_win_rate', direction: 'desc',
  });
});


test('matchup availability distinguishes zero from a sub-threshold sample', () => {
  assert.equal(matchupAvailabilityMessage({sample_size: 0}), 'No matches');
  assert.equal(matchupAvailabilityMessage({sample_size: 12}), 'Insufficient sample (n=12)');
  assert.equal(matchupAvailabilityMessage({sample_size: 30}), '');
});
