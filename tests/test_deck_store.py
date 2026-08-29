from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.deck_store import DeckNotFoundError, DeckStore
from app.models import DeckCard, DeckWrite


def deck_payload(name: str = "Dragapult") -> DeckWrite:
    return DeckWrite(
        name=name,
        pokemon=[DeckCard(name="Dreepy TWM 128", count=4)],
        trainer=[DeckCard(name="Buddy-Buddy Poffin TEF 144", count=4)],
        energy=[DeckCard(name="Psychic Energy MEE 5", count=3)],
    )


def test_create_persists_a_timestamped_deck_that_can_be_reloaded(tmp_path):
    path = tmp_path / "runtime" / "decks.json"
    store = DeckStore(path)

    created = store.create(deck_payload())
    reloaded = DeckStore(path).get(created.id)

    assert created.id
    assert created.name == "Dragapult"
    assert isinstance(created.created_at, datetime)
    assert created.updated_at == created.created_at
    assert reloaded == created


def test_list_returns_most_recently_updated_deck_first(tmp_path):
    store = DeckStore(tmp_path / "decks.json")
    first = store.create(deck_payload("First"))
    second = store.create(deck_payload("Second"))

    store.update(first.id, deck_payload("First renamed"))

    assert [deck.name for deck in store.list_decks()] == ["First renamed", "Second"]


def test_update_preserves_creation_identity_and_changes_content(tmp_path):
    store = DeckStore(tmp_path / "decks.json")
    created = store.create(deck_payload())

    updated = store.update(
        created.id,
        DeckWrite(
            name="Dragapult v2",
            pokemon=[DeckCard(name="Dreepy TWM 128", count=3)],
            trainer=[],
            energy=[],
        ),
    )

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert updated.name == "Dragapult v2"
    assert updated.pokemon[0].count == 3


def test_duplicate_creates_a_new_copy_without_mutating_original(tmp_path):
    store = DeckStore(tmp_path / "decks.json")
    original = store.create(deck_payload())

    duplicate = store.duplicate(original.id)

    assert duplicate.id != original.id
    assert duplicate.name == "Dragapult (Copy)"
    assert duplicate.pokemon == original.pokemon
    assert store.get(original.id).name == "Dragapult"


def test_delete_removes_deck_and_missing_ids_raise(tmp_path):
    store = DeckStore(tmp_path / "decks.json")
    created = store.create(deck_payload())

    store.delete(created.id)

    assert store.list_decks() == []
    with pytest.raises(DeckNotFoundError):
        store.get(created.id)
    with pytest.raises(DeckNotFoundError):
        store.update("missing", deck_payload())
    with pytest.raises(DeckNotFoundError):
        store.duplicate("missing")
    with pytest.raises(DeckNotFoundError):
        store.delete("missing")


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "pokemon": [], "trainer": [], "energy": []},
        {"name": "Bad", "pokemon": [{"name": "", "count": 1}], "trainer": [], "energy": []},
        {"name": "Bad", "pokemon": [{"name": "Dreepy", "count": 0}], "trainer": [], "energy": []},
        {"name": "Bad", "pokemon": [{"name": "Dreepy", "count": 61}], "trainer": [], "energy": []},
        {
            "name": "Duplicate",
            "pokemon": [{"name": "Dreepy", "count": 2}, {"name": " dreepy ", "count": 2}],
            "trainer": [],
            "energy": [],
        },
        {"name": "Too many", "pokemon": [{"name": "Dreepy", "count": 40}], "trainer": [{"name": "Poffin", "count": 21}], "energy": []},
    ],
)
def test_deck_validation_rejects_values_the_editor_cannot_safely_use(payload):
    with pytest.raises(ValidationError):
        DeckWrite.model_validate(payload)


def test_empty_deck_is_valid_so_it_can_be_built_incrementally():
    deck = DeckWrite(name="New Deck")

    assert deck.pokemon == []
    assert deck.trainer == []
    assert deck.energy == []


def test_concurrent_creates_do_not_lose_decks(tmp_path):
    store = DeckStore(tmp_path / "decks.json")

    with ThreadPoolExecutor(max_workers=8) as executor:
        created = list(executor.map(lambda index: store.create(deck_payload(f"Deck {index}")), range(40)))

    assert len({deck.id for deck in created}) == 40
    assert len(store.list_decks()) == 40
