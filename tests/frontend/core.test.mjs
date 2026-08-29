import test from 'node:test';
import assert from 'node:assert/strict';

import {
  comparisonCategories,
  deckTotal,
  nextTabIndex,
  parseDeckText,
  parseDeckEditorDraft,
  planDatasetMountRequests,
  prepareDeckEditorDraft,
  serializeDeck,
  validateDeck,
} from '../../app/static/core.mjs';

const ACCEPTED_DECK_LIST = `Pokémon: 18
4 Dreepy ASC 158
4 Drakloak ASC 159
3 Dragapult ex ASC 160
2 Munkidori ASC 99
1 Dunsparce JTG 120
1 Dudunsparce TEF 129
1 Budew ASC 16
1 Fezandipiti ex ASC 142
1 Meowth ex POR 62

Trainer: 33
4 Lillie's Determination MEG 119
3 Boss's Orders MEG 114
2 Crispin SCR 133
1 Rosa's Encouragement POR 84
4 Buddy-Buddy Poffin ASC 184
4 Poké Pad POR 81
4 Ultra Ball MEG 131
4 Crushing Hammer POR 71
3 Night Stretcher ASC 196
1 Special Red Card CRI 82
1 Unfair Stamp TWM 165
2 Risky Ruins MEG 127

Energy: 9
4 Psychic Energy MEE 5
3 Fire Energy MEE 2
2 Darkness Energy MEE 7`;


test('deck parser accepts the existing three-section export format', () => {
  const deck = parseDeckText(`Pokémon: 4
4 Dreepy TWM 128

Trainer: 4
4 Buddy-Buddy Poffin TEF 144

Energy: 3
3 Psychic Energy MEE 5`);

  assert.deepEqual(deck, {
    pokemon: [{name: 'Dreepy TWM 128', count: 4}],
    trainer: [{name: 'Buddy-Buddy Poffin TEF 144', count: 4}],
    energy: [{name: 'Psychic Energy MEE 5', count: 3}],
  });
  assert.equal(deckTotal(deck), 11);
});


test('deck parser rejects lines outside categories and invalid counts', () => {
  assert.throws(() => parseDeckText('4 Dreepy TWM 128'), /category header/i);
  assert.throws(() => parseDeckText('Pokemon: 1\n0 Dreepy'), /between 1 and 60/i);
  assert.throws(() => parseDeckText('Pokemon: 1\nDreepy'), /expected count and card name/i);
});


test('serialization round trips parser-compatible deck content', () => {
  const deck = {
    pokemon: [{name: 'Dreepy TWM 128', count: 4}],
    trainer: [],
    energy: [{name: 'Psychic Energy MEE 5', count: 3}],
  };

  const text = serializeDeck(deck);

  assert.equal(text, 'Pokémon: 4\n4 Dreepy TWM 128\n\nTrainer: 0\n\nEnergy: 3\n3 Psychic Energy MEE 5');
  assert.deepEqual(parseDeckText(text), deck);
});


test('deck validation reports duplicate cards and totals over 60', () => {
  assert.deepEqual(
    validateDeck({
      pokemon: [{name: 'Dreepy', count: 40}, {name: ' dreepy ', count: 1}],
      trainer: [{name: 'Poffin', count: 21}],
      energy: [],
    }),
    ['Duplicate card in Pokémon: dreepy', 'Deck cannot contain more than 60 cards'],
  );
});


test('mount planning uses the dedicated unmount contract for removals', () => {
  assert.deepEqual(
    planDatasetMountRequests(['prague', 'utrecht'], ['utrecht', 'new-orleans']),
    [
      {endpoint: '/api/v1/datasets/mount', datasetId: 'new-orleans'},
      {endpoint: '/api/v1/datasets/unmount', datasetId: 'prague'},
    ],
  );
});


test('comparison categories expose every meaningful backend diff array', () => {
  const data = {
    missing_core: [{name: 'A'}],
    underplayed_core: [{name: 'B'}],
    missing_common: [{name: 'C'}],
    overplayed: [{name: 'D'}],
    tech_deviations: [{name: 'E'}],
    extra_cards: [{name: 'F'}],
  };

  assert.deepEqual(
    comparisonCategories(data).map(({key, summaryKey, label, items}) => ({key, summaryKey, label, names: items.map(item => item.name)})),
    [
      {key: 'missing_core', summaryKey: 'missing_core_count', label: 'Missing core', names: ['A']},
      {key: 'underplayed_core', summaryKey: 'underplayed_core_count', label: 'Underplayed core', names: ['B']},
      {key: 'missing_common', summaryKey: 'missing_common_count', label: 'Missing common', names: ['C']},
      {key: 'overplayed', summaryKey: 'overplayed_count', label: 'Overplayed', names: ['D']},
      {key: 'tech_deviations', summaryKey: 'tech_deviation_count', label: 'Tech deviations', names: ['E']},
      {key: 'extra_cards', summaryKey: 'extra_card_count', label: 'Extra cards', names: ['F']},
    ],
  );
});


test('tab keyboard navigation wraps and supports Home and End', () => {
  assert.equal(nextTabIndex(0, 'ArrowRight', 3), 1);
  assert.equal(nextTabIndex(2, 'ArrowRight', 3), 0);
  assert.equal(nextTabIndex(0, 'ArrowLeft', 3), 2);
  assert.equal(nextTabIndex(1, 'Home', 3), 0);
  assert.equal(nextTabIndex(1, 'End', 3), 2);
  assert.equal(nextTabIndex(1, 'Enter', 3), null);
});


test('Deck Library draft parsing validates the accepted complete 60-card list', () => {
  const result = parseDeckEditorDraft(ACCEPTED_DECK_LIST);

  assert.equal(result.total, 60);
  assert.equal(result.deck.pokemon.length, 9);
  assert.equal(result.deck.trainer.length, 12);
  assert.equal(result.deck.energy.length, 3);
});


test('loading a saved deck prepares the exact canonical full-list textarea value', () => {
  const savedDeck = parseDeckText(ACCEPTED_DECK_LIST);

  assert.deepEqual(prepareDeckEditorDraft(savedDeck), {
    text: ACCEPTED_DECK_LIST,
    total: 60,
  });
});
