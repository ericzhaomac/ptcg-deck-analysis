from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.tournament_reports.contracts import (
    RawTournamentSnapshot,
    SnapshotManifest,
    SnapshotVerification,
)


class SnapshotValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


class SnapshotStore:
    def load(self, dataset_dir: Path) -> RawTournamentSnapshot:
        pointer_path = dataset_dir / "cache" / "verified-snapshot.json"
        if not pointer_path.is_file():
            raise SnapshotValidationError("missing_verified_pointer", "verified snapshot pointer is missing")
        pointer = self._read_json(pointer_path)
        if not isinstance(pointer, dict) or not isinstance(pointer.get("snapshot_version"), str):
            raise SnapshotValidationError("invalid_verified_pointer", "verified snapshot pointer is invalid")
        snapshot_dir = dataset_dir / "cache" / "snapshots" / pointer["snapshot_version"]
        if not snapshot_dir.is_dir():
            raise SnapshotValidationError("missing_snapshot", "verified snapshot directory is missing")
        manifest_path = snapshot_dir / "manifest.json"
        if not manifest_path.is_file():
            raise SnapshotValidationError("missing_manifest", "snapshot manifest is missing")
        try:
            manifest = SnapshotManifest.model_validate(self._read_json(manifest_path))
        except ValidationError as exc:
            raise SnapshotValidationError("invalid_manifest", "snapshot manifest is invalid") from exc
        if manifest.snapshot_version != pointer["snapshot_version"]:
            raise SnapshotValidationError("snapshot_version_mismatch", "pointer and manifest versions differ")
        return self.load_candidate(snapshot_dir, manifest)

    def load_candidate(self, staged_dir: Path, manifest: SnapshotManifest) -> RawTournamentSnapshot:
        self._validate_staged(staged_dir, manifest)
        tournament = self._message(staged_dir, manifest, "tournament", dict)
        decks = self._message(staged_dir, manifest, "decks", list)
        standings = self._message(staged_dir, manifest, "standings", list)
        pairings = {
            round_number: tuple(
                self._message(staged_dir, manifest, f"pairings/round-{round_number:02d}", list)
            )
            for round_number in range(1, manifest.declared_rounds + 1)
        }
        decklists = {
            key.removeprefix("decklists/"): self._message(staged_dir, manifest, key, dict)
            for key in sorted(manifest.resources)
            if key.startswith("decklists/")
        }
        matchup_references = {
            key.removeprefix("matchups/"): self._message(staged_dir, manifest, key, (dict, list))
            for key in sorted(manifest.resources)
            if key.startswith("matchups/")
        }
        try:
            return RawTournamentSnapshot(
                manifest=manifest,
                tournament=tournament,
                decks=tuple(decks),
                standings=tuple(standings),
                pairings=pairings,
                decklists=decklists,
                matchup_references=matchup_references,
            )
        except ValidationError as exc:
            raise SnapshotValidationError("source_schema_incompatible", "raw snapshot schema is incompatible") from exc

    def promote(
        self,
        dataset_dir: Path,
        staged_dir: Path,
        manifest: SnapshotManifest,
        verification: SnapshotVerification,
    ) -> Path:
        if verification.blocking_issue_codes:
            raise SnapshotValidationError(
                "verification_blocked",
                ",".join(verification.blocking_issue_codes),
            )
        self.load_candidate(staged_dir, manifest)
        target = dataset_dir / "cache" / "snapshots" / manifest.snapshot_version
        self._install_idempotently(staged_dir, target, manifest)
        atomic_write_json(
            dataset_dir / "cache" / "verified-snapshot.json",
            {"snapshot_version": manifest.snapshot_version},
        )
        return target

    def _validate_staged(self, staged_dir: Path, manifest: SnapshotManifest) -> None:
        if manifest.schema_version != 1:
            raise SnapshotValidationError("unsupported_schema_version", "snapshot schema version must be 1")
        required = {"tournament", "decks", "standings"}
        missing_singletons = sorted(required - manifest.resources.keys())
        if missing_singletons:
            raise SnapshotValidationError("missing_resource", f"missing resource: {missing_singletons[0]}")
        for round_number in range(1, manifest.declared_rounds + 1):
            key = f"pairings/round-{round_number:02d}"
            if key not in manifest.resources:
                raise SnapshotValidationError("missing_round", f"missing round: {round_number}")
        for key, resource in manifest.resources.items():
            path = staged_dir / resource.path
            try:
                path.relative_to(staged_dir)
            except ValueError as exc:
                raise SnapshotValidationError("invalid_resource_path", f"resource escapes snapshot: {key}") from exc
            if not path.is_file():
                raise SnapshotValidationError("missing_resource", f"missing resource: {key}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != resource.sha256:
                raise SnapshotValidationError("hash_mismatch", f"resource hash mismatch: {key}")
        tournament = self._message(staged_dir, manifest, "tournament", dict)
        if tournament.get("round") != manifest.declared_rounds:
            raise SnapshotValidationError("source_schema_incompatible", "declared round count differs from tournament")
        self._message(staged_dir, manifest, "decks", list)
        self._message(staged_dir, manifest, "standings", list)
        for round_number in range(1, manifest.declared_rounds + 1):
            self._message(staged_dir, manifest, f"pairings/round-{round_number:02d}", list)
        for key in manifest.resources:
            if key.startswith("decklists/"):
                self._message(staged_dir, manifest, key, dict)
            elif key.startswith("matchups/"):
                self._message(staged_dir, manifest, key, (dict, list))

    def _message(
        self,
        root: Path,
        manifest: SnapshotManifest,
        key: str,
        expected_type: type | tuple[type, ...],
    ) -> Any:
        resource = manifest.resources[key]
        payload = self._read_json(root / resource.path)
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise SnapshotValidationError("source_schema_incompatible", f"unsuccessful source envelope: {key}")
        message = payload.get("message")
        if not isinstance(message, expected_type):
            raise SnapshotValidationError("source_schema_incompatible", f"invalid source message: {key}")
        if isinstance(message, list) and not all(isinstance(row, dict) for row in message):
            raise SnapshotValidationError("source_schema_incompatible", f"invalid source rows: {key}")
        return message

    def _read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotValidationError("malformed_json", f"malformed JSON: {path.name}") from exc

    def _install_idempotently(
        self,
        staged_dir: Path,
        target: Path,
        manifest: SnapshotManifest,
    ) -> None:
        if target.exists():
            installed_manifest_path = target / "manifest.json"
            if not installed_manifest_path.is_file():
                raise SnapshotValidationError("immutable_version_collision", "existing snapshot has no manifest")
            try:
                installed = SnapshotManifest.model_validate(self._read_json(installed_manifest_path))
            except ValidationError as exc:
                raise SnapshotValidationError("immutable_version_collision", "existing snapshot manifest is invalid") from exc
            if installed != manifest:
                raise SnapshotValidationError("immutable_version_collision", "snapshot version already has different content")
            shutil.rmtree(staged_dir)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        staged_dir.replace(target)
