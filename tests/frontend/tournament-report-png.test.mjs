import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertExportable,
  buildModuleSvg,
  exportFilename,
} from '../../app/static/tournament-reports-core.mjs';


const READY_MATCHUP_MODULE = {
  module_id: 'matchups_overall',
  title: 'Observed matchups & conversion',
  status: {state: 'ready', exportable: true, message: null},
  grain: 'family',
  phase: 'overall',
  selection_id: 'dragapult-ex',
  sample_size: 705,
  metric_notes: [
    'Observed win rate weights each tie as one-third of a win.',
    'Unknown opponents and procedural results are excluded.',
  ],
  provenance: {
    source_provider: 'Limitless Labs',
    source_updated_at: '2026-06-14T19:37:59Z',
    fetched_at: '2026-06-14T20:00:00Z',
    snapshot_version: '0070-ma-deadbeef1234',
  },
  data: {
    rows: [
      {
        opponent_name: 'Charizard & Pidgeot',
        matches: 120,
        record: {wins: 70, losses: 40, ties: 10},
        observed_win_rate: 0.6111,
      },
      {
        opponent_name: 'Gardevoir',
        matches: 95,
        record: {wins: 45, losses: 42, ties: 8},
        observed_win_rate: 0.5018,
      },
    ],
    unknown_count: 7,
    procedural_count: 3,
  },
};

const EXPORT_CONTEXT = {
  datasetId: '2026-new-orleans-ma',
  eventName: 'International Championship New Orleans',
  eventDate: 'June 12–14, 2026',
  grain: 'family',
  selectionId: 'dragapult-ex',
  selectionLabel: 'Dragapult',
  phaseLabel: 'Overall',
  snapshotVersion: '0070-ma-deadbeef1234',
  sourceProvider: 'Limitless Labs',
  sourceUpdatedAt: '2026-06-14T19:37:59Z',
  fetchedAt: '2026-06-14T20:00:00Z',
  projectAttribution: 'PTCG Deck Analysis',
};


test('export document contains fixed dimensions and publication context', () => {
  const svg = buildModuleSvg(READY_MATCHUP_MODULE, EXPORT_CONTEXT);

  assert.match(svg, /width="1080" height="1350"/);
  assert.match(svg, /viewBox="0 0 1080 1350"/);
  assert.match(svg, /International Championship New Orleans/);
  assert.match(svg, /Dragapult/);
  assert.match(svg, /Observed win rate/);
  assert.match(svg, /n=705/);
  assert.match(svg, /Limitless Labs/);
  assert.match(svg, /PTCG Deck Analysis/);
});


test('export document escapes source text and wraps long titles', () => {
  const svg = buildModuleSvg(
    {
      ...READY_MATCHUP_MODULE,
      title: 'A very long tournament module title that must wrap safely without clipping & overlap',
    },
    {...EXPORT_CONTEXT, selectionLabel: '<Dragapult & Friends>'},
  );

  assert.doesNotMatch(svg, /<Dragapult & Friends>/);
  assert.match(svg, /&lt;Dragapult &amp; Friends&gt;/);
  assert.ok((svg.match(/<tspan/g) || []).length >= 2);
});


test('stale and non-ready modules cannot export', () => {
  assert.throws(
    () => assertExportable(READY_MATCHUP_MODULE, {...EXPORT_CONTEXT, snapshotVersion: 'stale'}),
    /snapshot version/i,
  );
  assert.throws(
    () => assertExportable({...READY_MATCHUP_MODULE, status: {state: 'degraded', exportable: false}}, EXPORT_CONTEXT),
    /ready/i,
  );
  assert.throws(
    () => assertExportable({...READY_MATCHUP_MODULE, status: {state: 'ready', exportable: false}}, EXPORT_CONTEXT),
    /disabled/i,
  );
});


test('export filename is deterministic and ASCII safe', () => {
  assert.equal(
    exportFilename(READY_MATCHUP_MODULE, EXPORT_CONTEXT),
    '2026-new-orleans-ma-matchups-overall-family-dragapult-ex-overall.png',
  );
  assert.equal(
    exportFilename(READY_MATCHUP_MODULE, {...EXPORT_CONTEXT, selectionId: 'Púlt / Dusk'}),
    '2026-new-orleans-ma-matchups-overall-family-pult-dusk-overall.png',
  );
});
