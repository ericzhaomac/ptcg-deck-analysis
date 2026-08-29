export const DECK_SECTIONS = ['pokemon', 'trainer', 'energy'];

const SECTION_LABELS = {
  pokemon: 'Pokémon',
  trainer: 'Trainer',
  energy: 'Energy',
};


export function nextTabIndex(currentIndex, key, count) {
  if (!Number.isInteger(currentIndex) || count < 1) return null;
  if (key === 'ArrowRight') return (currentIndex + 1) % count;
  if (key === 'ArrowLeft') return (currentIndex - 1 + count) % count;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  return null;
}


export function deckTotal(deck) {
  return DECK_SECTIONS.reduce(
    (total, section) => total + (deck?.[section] || []).reduce((subtotal, card) => subtotal + Number(card.count || 0), 0),
    0,
  );
}


export function validateDeck(deck) {
  const errors = [];
  for (const section of DECK_SECTIONS) {
    const seen = new Set();
    for (const card of deck?.[section] || []) {
      const name = String(card.name || '').trim();
      const count = Number(card.count);
      if (!name) {
        errors.push(`Card name cannot be empty in ${SECTION_LABELS[section]}`);
      }
      if (!Number.isInteger(count) || count < 1 || count > 60) {
        errors.push(`Card count for ${name || 'unnamed card'} must be between 1 and 60`);
      }
      const key = name.toLocaleLowerCase();
      if (name && seen.has(key)) {
        errors.push(`Duplicate card in ${SECTION_LABELS[section]}: ${name}`);
      }
      seen.add(key);
    }
  }
  if (deckTotal(deck) > 60) {
    errors.push('Deck cannot contain more than 60 cards');
  }
  return errors;
}


export function parseDeckText(text) {
  if (!String(text || '').trim()) {
    throw new Error('Deck list is empty');
  }
  const deck = {pokemon: [], trainer: [], energy: []};
  let currentSection = null;
  const lines = String(text).split(/\r?\n/);

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;
    const header = line.match(/^(pok[eé]mon|trainer|energy)\s*:/i);
    if (header) {
      const key = header[1].toLocaleLowerCase();
      currentSection = key.startsWith('pok') ? 'pokemon' : key;
      return;
    }
    if (!currentSection) {
      throw new Error(`Line ${index + 1} must follow a category header`);
    }
    const cardLine = line.match(/^(\d+)\s+(.+)$/);
    if (!cardLine) {
      throw new Error(`Line ${index + 1}: expected count and card name`);
    }
    deck[currentSection].push({name: cardLine[2].trim(), count: Number(cardLine[1])});
  });

  const errors = validateDeck(deck);
  if (errors.length) {
    throw new Error(errors.join('; '));
  }
  return deck;
}


export function serializeDeck(deck) {
  return DECK_SECTIONS.map((section) => {
    const cards = deck?.[section] || [];
    const total = cards.reduce((sum, card) => sum + Number(card.count || 0), 0);
    const lines = cards.map((card) => `${card.count} ${String(card.name).trim()}`);
    return [`${SECTION_LABELS[section]}: ${total}`, ...lines].join('\n');
  }).join('\n\n');
}


export function parseDeckEditorDraft(text) {
  const deck = parseDeckText(text);
  return {deck, total: deckTotal(deck)};
}


export function prepareDeckEditorDraft(deck) {
  return {text: serializeDeck(deck), total: deckTotal(deck)};
}


export function planDatasetMountRequests(currentIds, desiredIds) {
  const current = new Set(currentIds);
  const desired = new Set(desiredIds);
  return [
    ...desiredIds
      .filter((datasetId) => !current.has(datasetId))
      .map((datasetId) => ({endpoint: '/api/v1/datasets/mount', datasetId})),
    ...currentIds
      .filter((datasetId) => !desired.has(datasetId))
      .map((datasetId) => ({endpoint: '/api/v1/datasets/unmount', datasetId})),
  ];
}


export function comparisonCategories(data) {
  return [
    {key: 'missing_core', summaryKey: 'missing_core_count', label: 'Missing core', className: 'missing-core'},
    {key: 'underplayed_core', summaryKey: 'underplayed_core_count', label: 'Underplayed core', className: 'underplayed-core'},
    {key: 'missing_common', summaryKey: 'missing_common_count', label: 'Missing common', className: 'missing-common'},
    {key: 'overplayed', summaryKey: 'overplayed_count', label: 'Overplayed', className: 'overplayed'},
    {key: 'tech_deviations', summaryKey: 'tech_deviation_count', label: 'Tech deviations', className: 'tech-deviation'},
    {key: 'extra_cards', summaryKey: 'extra_card_count', label: 'Extra cards', className: 'extra-card'},
  ].map((category) => ({...category, items: data?.[category.key] || []}));
}
