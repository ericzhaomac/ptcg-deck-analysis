from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from uuid import uuid4

from .models import DeckWrite, SavedDeck


class DeckNotFoundError(KeyError):
    pass


class DeckStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def list_decks(self) -> list[SavedDeck]:
        with self._lock:
            return sorted(self._load(), key=lambda deck: deck.updated_at, reverse=True)

    def get(self, deck_id: str) -> SavedDeck:
        with self._lock:
            for deck in self._load():
                if deck.id == deck_id:
                    return deck
            raise DeckNotFoundError(deck_id)

    def create(self, payload: DeckWrite) -> SavedDeck:
        with self._lock:
            decks = self._load()
            now = datetime.now(UTC)
            deck = SavedDeck(
                id=str(uuid4()),
                created_at=now,
                updated_at=now,
                **payload.model_dump(),
            )
            decks.append(deck)
            self._save(decks)
            return deck

    def update(self, deck_id: str, payload: DeckWrite) -> SavedDeck:
        with self._lock:
            decks = self._load()
            for index, existing in enumerate(decks):
                if existing.id == deck_id:
                    updated = SavedDeck(
                        id=existing.id,
                        created_at=existing.created_at,
                        updated_at=datetime.now(UTC),
                        **payload.model_dump(),
                    )
                    decks[index] = updated
                    self._save(decks)
                    return updated
            raise DeckNotFoundError(deck_id)

    def duplicate(self, deck_id: str) -> SavedDeck:
        with self._lock:
            source = self.get(deck_id)
            return self.create(
                DeckWrite(
                    name=f"{source.name} (Copy)",
                    pokemon=source.pokemon,
                    trainer=source.trainer,
                    energy=source.energy,
                )
            )

    def delete(self, deck_id: str) -> None:
        with self._lock:
            decks = self._load()
            remaining = [deck for deck in decks if deck.id != deck_id]
            if len(remaining) == len(decks):
                raise DeckNotFoundError(deck_id)
            self._save(remaining)

    def _load(self) -> list[SavedDeck]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [SavedDeck.model_validate(row) for row in data.get("decks", [])]

    def _save(self, decks: list[SavedDeck]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                json.dump(
                    {"decks": [deck.model_dump(mode="json") for deck in decks]},
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary_path = Path(temporary_file.name)
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
