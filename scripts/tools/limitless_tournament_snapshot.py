from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.tournament_reports.contracts import (
    RawTournamentSnapshot,
    SnapshotManifest,
    SnapshotResource,
)
from app.tournament_reports.builders import build_event_overview
from app.tournament_reports.facts import FamilyOverrideSet, load_family_overrides, normalize_snapshot
from app.tournament_reports.reconciliation import reconcile_tournament, verify_candidate_snapshot
from app.tournament_reports.snapshots import SnapshotStore, SnapshotValidationError, atomic_write_json


API_ROOT = "https://mew.limitlesstcg.com/labs/data/tcg"
USER_AGENT = "Mozilla/5.0 (compatible; PtcgDeckAgent/tournament-snapshot)"
DEFAULT_DIVISION = "MA"


@dataclass(frozen=True)
class TournamentRef:
    tournament_id: str
    division: str = DEFAULT_DIVISION


@dataclass(frozen=True)
class StagedSnapshot:
    path: Path
    manifest: SnapshotManifest
    raw: RawTournamentSnapshot


class LimitlessClient:
    def __init__(
        self,
        *,
        attempts: int = 3,
        retry_delay_seconds: float = 1.0,
        opener: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be positive")
        self.attempts = attempts
        self.retry_delay_seconds = retry_delay_seconds
        self._opener = opener
        self._sleeper = sleeper

    def fetch(self, endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
        query = urlencode(params)
        request = Request(
            f"{API_ROOT}/{endpoint}?{query}",
            headers={"User-Agent": USER_AGENT},
        )
        for attempt in range(self.attempts):
            try:
                opener = self._opener or urlopen
                with opener(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                _require_successful_envelope(payload, endpoint)
                return payload
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                if attempt + 1 == self.attempts:
                    raise
                sleeper = self._sleeper or time.sleep
                sleeper(self.retry_delay_seconds * (2**attempt))
        raise RuntimeError("unreachable")

    def fetch_cached(
        self,
        endpoint: str,
        params: dict[str, str | int],
        cache_path: Path,
    ) -> dict[str, Any]:
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                _require_successful_envelope(cached, endpoint)
                if bool(cached.get("message")):
                    return cached
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                pass
        payload = self.fetch(endpoint, params)
        if not bool(payload.get("message")):
            raise ValueError(f"Limitless returned an empty payload for {endpoint}")
        atomic_write_json(cache_path, payload)
        return payload


class LimitlessSnapshotAdapter:
    def __init__(
        self,
        client: LimitlessClient,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))

    def collect(self, ref: TournamentRef, dataset_dir: Path) -> StagedSnapshot:
        cache_dir = dataset_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        staged_dir = Path(tempfile.mkdtemp(prefix="snapshot-candidate-", dir=cache_dir))
        try:
            tournament = self._fetch_resource(
                staged_dir,
                cache_dir,
                "tournament",
                "tournament",
                {"id": ref.tournament_id, "division": ref.division},
            )
            decks = self._fetch_resource(
                staged_dir,
                cache_dir,
                "decks",
                "decks",
                {"tournamentId": ref.tournament_id, "division": ref.division},
            )
            standings = self._fetch_resource(
                staged_dir,
                cache_dir,
                "standings",
                "standings",
                {"tournamentId": ref.tournament_id, "division": ref.division},
            )
            tournament_message = _message_of_type(tournament, "tournament", dict)
            deck_rows = _message_of_type(decks, "decks", list)
            standing_rows = _message_of_type(standings, "standings", list)
            declared_rounds = _positive_int(tournament_message.get("round"), "tournament round")

            for round_number in range(1, declared_rounds + 1):
                self._fetch_resource(
                    staged_dir,
                    cache_dir,
                    f"pairings/round-{round_number:02d}",
                    "pairings",
                    {
                        "tournamentId": ref.tournament_id,
                        "division": ref.division,
                        "round": round_number,
                    },
                )

            player_ids = sorted(
                {
                    str(row.get("tp_id", "")).strip()
                    for row in standing_rows
                    if isinstance(row, dict) and int(row.get("decklist", 0)) == 1
                    and str(row.get("tp_id", "")).strip()
                }
            )
            for player_id in player_ids:
                self._fetch_resource(
                    staged_dir,
                    cache_dir,
                    f"decklists/{player_id}",
                    "decklist",
                    {"tournamentId": ref.tournament_id, "playerId": player_id},
                )

            variant_ids = sorted(
                {
                    str(row.get("identifier", "")).strip()
                    for row in deck_rows
                    if isinstance(row, dict) and str(row.get("identifier", "")).strip()
                }
            )
            for variant_id in variant_ids:
                self._fetch_resource(
                    staged_dir,
                    cache_dir,
                    f"matchups/{variant_id}",
                    "matchups",
                    {
                        "tournamentId": ref.tournament_id,
                        "division": ref.division,
                        "deckId": variant_id,
                    },
                )

            manifest = _build_manifest(
                ref=ref,
                staged_dir=staged_dir,
                declared_rounds=declared_rounds,
                source_updated_at=_parse_source_datetime(tournament_message.get("updated_at")),
                fetched_at=self.clock(),
            )
            atomic_write_json(staged_dir / "manifest.json", manifest.model_dump(mode="json"))
            raw = SnapshotStore().load_candidate(staged_dir, manifest)
            return StagedSnapshot(path=staged_dir, manifest=manifest, raw=raw)
        except Exception:
            shutil.rmtree(staged_dir)
            raise

    def _fetch_resource(
        self,
        staged_dir: Path,
        raw_cache_dir: Path,
        key: str,
        endpoint: str,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        fetch_cached = getattr(self.client, "fetch_cached", None)
        if callable(fetch_cached):
            payload = fetch_cached(endpoint, params, raw_cache_dir / f"{key}.json")
        else:
            payload = self.client.fetch(endpoint, params)
        _require_successful_envelope(payload, endpoint)
        atomic_write_json(staged_dir / f"{key}.json", payload)
        return payload


class VerifiedSnapshotRefresher:
    def __init__(
        self,
        *,
        adapter: LimitlessSnapshotAdapter,
        store: SnapshotStore,
        family_overrides: FamilyOverrideSet,
    ) -> None:
        self.adapter = adapter
        self.store = store
        self.family_overrides = family_overrides

    def refresh(self, ref: TournamentRef, dataset_dir: Path) -> SnapshotManifest:
        staged = self.adapter.collect(ref, dataset_dir)
        try:
            verification = verify_candidate_snapshot(staged.raw, self.family_overrides)
            self.store.promote(
                dataset_dir,
                staged.path,
                staged.manifest,
                verification,
            )
            return staged.manifest
        except Exception:
            if staged.path.exists():
                shutil.rmtree(staged.path)
            raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh a verified Limitless tournament snapshot.")
    parser.add_argument("--tournament-id", required=True)
    parser.add_argument("--division", default=DEFAULT_DIVISION)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument(
        "--family-overrides",
        default="data/config/archetype_family_overrides.json",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify the current local snapshot without making HTTP requests.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verify_only:
        try:
            return verify_only(Path(args.dataset_dir), Path(args.family_overrides))
        except SnapshotValidationError as exc:
            print(json.dumps({"ok": False, "code": exc.code, "message": str(exc)}, sort_keys=True))
            return 1
    refresher = VerifiedSnapshotRefresher(
        adapter=LimitlessSnapshotAdapter(client=LimitlessClient()),
        store=SnapshotStore(),
        family_overrides=load_family_overrides(Path(args.family_overrides)),
    )
    try:
        manifest = refresher.refresh(
            TournamentRef(str(args.tournament_id), str(args.division)),
            Path(args.dataset_dir),
        )
    except SnapshotValidationError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_version": manifest.snapshot_version,
                "dataset_dir": str(Path(args.dataset_dir)),
            },
            sort_keys=True,
        )
    )
    return 0


def verify_only(dataset_dir: Path, overrides_path: Path) -> int:
    snapshot = SnapshotStore().load(dataset_dir)
    facts = normalize_snapshot(snapshot, load_family_overrides(overrides_path))
    result = reconcile_tournament(facts)
    overview = build_event_overview(facts, result, dataset_dir.name)
    eligible_family_ids = {
        option.selection_id for option in overview.families if option.eligible
    }
    variant_counts: dict[str, int] = {}
    for player in facts.players.values():
        if player.variant_id:
            variant_counts[player.variant_id] = variant_counts.get(player.variant_id, 0) + 1
    eligible_variant_count = sum(
        count >= 10
        and facts.variants[variant_id].family_id in eligible_family_ids
        for variant_id, count in variant_counts.items()
    )
    blocking_codes = list(
        dict.fromkeys(issue.code for issue in result.issues if issue.blocks_publication)
    )
    print(
        json.dumps(
            {
                "ok": not blocking_codes,
                "snapshot_version": snapshot.manifest.snapshot_version,
                "phase_boundary": result.phase_boundary,
                "issue_codes": list(dict.fromkeys(issue.code for issue in result.issues)),
                "blocking_issue_codes": blocking_codes,
                "eligible_family_count": len(eligible_family_ids),
                "eligible_variant_count": eligible_variant_count,
            },
            sort_keys=True,
        )
    )
    return 1 if blocking_codes else 0


def _require_successful_envelope(payload: Any, endpoint: str) -> None:
    if not isinstance(payload, dict) or payload.get("ok") is not True or "message" not in payload:
        raise ValueError(f"Limitless returned an unsuccessful payload for {endpoint}")


def _message_of_type(payload: dict[str, Any], endpoint: str, expected: type) -> Any:
    _require_successful_envelope(payload, endpoint)
    message = payload["message"]
    if not isinstance(message, expected):
        raise ValueError(f"Limitless returned an incompatible payload for {endpoint}")
    if expected is list and not all(isinstance(row, dict) for row in message):
        raise ValueError(f"Limitless returned incompatible rows for {endpoint}")
    return message


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _parse_source_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("tournament updated_at is not an ISO date-time") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _build_manifest(
    *,
    ref: TournamentRef,
    staged_dir: Path,
    declared_rounds: int,
    source_updated_at: datetime | None,
    fetched_at: datetime,
) -> SnapshotManifest:
    resources: dict[str, SnapshotResource] = {}
    for path in sorted(staged_dir.rglob("*.json")):
        if path.name == "manifest.json" or path.name.endswith(".tmp"):
            continue
        relative_path = path.relative_to(staged_dir).as_posix()
        key = relative_path.removesuffix(".json")
        resources[key] = SnapshotResource(
            path=relative_path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    canonical_index = {
        key: resource.model_dump(mode="json")
        for key, resource in sorted(resources.items())
    }
    content_hash = hashlib.sha256(
        json.dumps(canonical_index, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return SnapshotManifest(
        schema_version=1,
        snapshot_version=f"{ref.tournament_id}-{ref.division.lower()}-{content_hash}",
        tournament_id=ref.tournament_id,
        division=ref.division,
        source_provider="Limitless Labs",
        source_updated_at=source_updated_at,
        fetched_at=fetched_at,
        declared_rounds=declared_rounds,
        resources=resources,
    )


if __name__ == "__main__":
    raise SystemExit(main())
