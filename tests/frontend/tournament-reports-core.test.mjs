import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildOverviewChartModel,
  createReportRoute,
  formatObservedWinRate,
  moduleAvailability,
  reduceReportSelection,
} from '../../app/static/tournament-reports-core.mjs';


const INITIAL_STATE = {
  datasetId: '2026-new-orleans-ma',
  selectedFamilyId: null,
  visibleFamilyIds: ['dragapult-ex', 'charizard-ex'],
  familyReportAction: null,
  selection: null,
  modulePhases: {matchups: 'overall', composition: 'first_phase'},
  requestGeneration: 0,
  appliedGeneration: 0,
  report: null,
};

const FAMILY_STATE = {
  ...INITIAL_STATE,
  selectedFamilyId: 'dragapult-ex',
  selection: {grain: 'family', selectionId: 'dragapult-ex'},
  modulePhases: {matchups: 'day2', composition: 'top_cut'},
};

const DISTRIBUTION_MODULE = {
  module_id: 'phase_topcut_distribution',
  status: {state: 'ready', exportable: true, message: null},
  data: {
    first_phase: [
      {
        family_id: 'dragapult-ex',
        family_name: 'Dragapult',
        players: 20,
        share: 0.5,
        record: {wins: 30, losses: 10, ties: 2},
        observed_win_rate: 0.73,
      },
      {
        family_id: 'charizard-ex',
        family_name: 'Charizard',
        players: 10,
        share: 0.25,
        record: {wins: 10, losses: 10, ties: 0},
        observed_win_rate: 0.5,
      },
    ],
    top_cut: [
      {
        family_id: 'dragapult-ex',
        family_name: 'Dragapult',
        players: 4,
        share: 0.5,
        record: {wins: 8, losses: 2, ties: 0},
        observed_win_rate: 0.8,
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
    composition: 'first_phase',
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


test('overview chart model preserves rows and synchronizes selected marks', () => {
  const model = buildOverviewChartModel(DISTRIBUTION_MODULE, 'dragapult-ex');

  assert.deepEqual(model.series.map((series) => series.phase), ['first_phase', 'top_cut']);
  assert.equal(model.series[0].marks.length, 2);
  assert.equal(model.series[0].marks[0].selected, true);
  assert.equal(model.series[1].marks[0].selected, true);
  assert.match(model.series[0].marks[0].tooltip, /20 players/);
  assert.match(model.series[0].marks[0].tooltip, /50\.0%/);
  assert.match(model.series[0].marks[0].tooltip, /30-10-2/);
  assert.equal(model.series[0].marks[0].share, 0.5);
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
