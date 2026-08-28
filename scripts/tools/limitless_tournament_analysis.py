from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://mew.limitlesstcg.com/labs/data/tcg"
USER_AGENT = "Mozilla/5.0 (compatible; PtcgDeckAgent/limitless-analysis)"
DEFAULT_CACHE_DIR = "tmp/limitless_cache"
DEFAULT_OUTPUT_DIR = "tmp/limitless_reports"
DEFAULT_DIVISION = "MA"
DEFAULT_MIN_ARCHETYPE_PLAYERS = 10
DEFAULT_FETCH_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 1.0


@dataclass(frozen=True)
class TournamentRef:
    tournament_id: str
    division: str = DEFAULT_DIVISION


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Limitless Labs tournament data and build a structured deck trend report.",
    )
    parser.add_argument("--tournament-id", required=True)
    parser.add_argument("--division", default=DEFAULT_DIVISION)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-json")
    parser.add_argument("--min-archetype-players", type=int, default=DEFAULT_MIN_ARCHETYPE_PLAYERS)
    parser.add_argument("--pause-ms", type=int, default=0, help="Optional pause between player decklist fetches.")
    parser.add_argument("--workers", type=int, default=12, help="Concurrent decklist fetch worker count.")
    parser.add_argument(
        "--flat-cache",
        action="store_true",
        help="Store tournament/decks/standings/decklists directly under --cache-dir.",
    )
    return parser.parse_args(argv)


def build_archetype_card_summary(decklists: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "deck_count": len(decklists),
        "pokemon": _build_card_rows(decklists, section="pokemon"),
        "trainer": _build_card_rows(decklists, section="trainer"),
        "energy": _build_card_rows(decklists, section="energy"),
    }


def build_archetype_summary(
    archetype_row: dict[str, Any],
    standings_rows: list[dict[str, Any]],
    decklists: list[dict[str, Any]],
    total_players: int,
) -> dict[str, Any]:
    archetype_id = str(archetype_row.get("identifier", "")).strip()
    matching_rows = [
        row
        for row in standings_rows
        if str(row.get("deck_id", "")).strip() == archetype_id
    ]
    matching_rows.sort(key=lambda row: int(row.get("placement", 10**9)))

    players = int(archetype_row.get("players", 0))
    day2s = int(archetype_row.get("day2s", 0))
    wins = int(archetype_row.get("wins", 0))
    losses = int(archetype_row.get("losses", 0))
    ties = int(archetype_row.get("ties", 0))
    total_matches = wins + losses + ties

    return {
        "archetype_id": archetype_id,
        "archetype_name": str(archetype_row.get("name", "")).strip(),
        "meta": {
            "players": players,
            "share": round(players / float(total_players), 4) if total_players > 0 else 0.0,
            "day2s": day2s,
            "day2_conversion": round(day2s / float(players), 4) if players > 0 else 0.0,
        },
        "performance": {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "win_rate": round((wins + 0.5 * ties) / float(total_matches), 4) if total_matches > 0 else 0.0,
            "top8_count": sum(1 for row in matching_rows if int(row.get("placement", 10**9)) <= 8),
            "top16_count": sum(1 for row in matching_rows if int(row.get("placement", 10**9)) <= 16),
            "top64_count": sum(1 for row in matching_rows if int(row.get("placement", 10**9)) <= 64),
        },
        "top_finishers": [
            {
                "placement": int(row.get("placement", 0)),
                "name": str(row.get("name", "")).strip(),
                "points": int(row.get("points", 0)),
                "record": {
                    "wins": int(row.get("wins", 0)),
                    "losses": int(row.get("losses", 0)),
                    "ties": int(row.get("ties", 0)),
                },
                "country": str(row.get("country", "")).strip(),
                "player_id": str(row.get("tp_id", row.get("player_id", ""))).strip(),
            }
            for row in matching_rows[:8]
        ],
        "card_summary": build_archetype_card_summary(decklists),
    }


def _build_card_rows(decklists: list[dict[str, Any]], section: str) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    total_decks = len(decklists)
    for deck in decklists:
        seen_names: set[str] = set()
        for raw_entry in deck.get(section, []) or []:
            name = str(raw_entry.get("name", "")).strip()
            if not name:
                continue
            count = int(raw_entry.get("count", 0))
            row = stats.setdefault(
                name,
                {
                    "name": name,
                    "appearances": 0,
                    "count_total": 0,
                    "min_count": None,
                    "max_count": None,
                },
            )
            row["count_total"] += count
            row["min_count"] = count if row["min_count"] is None else min(int(row["min_count"]), count)
            row["max_count"] = count if row["max_count"] is None else max(int(row["max_count"]), count)
            if name not in seen_names:
                row["appearances"] += 1
                seen_names.add(name)

    rows: list[dict[str, Any]] = []
    for row in stats.values():
        appearances = int(row["appearances"])
        frequency = appearances / float(total_decks) if total_decks > 0 else 0.0
        rows.append(
            {
                "name": row["name"],
                "appearances": appearances,
                "frequency": round(frequency, 4),
                "avg_count": round(row["count_total"] / float(total_decks), 4) if total_decks > 0 else 0.0,
                "avg_when_present": round(row["count_total"] / float(appearances), 4) if appearances > 0 else 0.0,
                "min_count": int(row["min_count"] or 0),
                "max_count": int(row["max_count"] or 0),
                "bucket": _bucket_for_frequency(frequency),
            }
        )

    rows.sort(key=lambda item: (-item["frequency"], -item["avg_count"], item["name"]))
    return rows


def _bucket_for_frequency(frequency: float) -> str:
    if frequency >= 0.8:
        return "core"
    if frequency >= 0.5:
        return "common"
    return "tech"


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    ref = TournamentRef(tournament_id=str(args.tournament_id), division=str(args.division))
    cache_root = Path(args.cache_dir).resolve()
    output_json = Path(args.output_json).resolve() if args.output_json else _default_output_path(ref)
    flat_cache = bool(getattr(args, "flat_cache", False))

    tournament = _fetch_tournament(ref, cache_root, flat_cache=flat_cache)
    decks = _fetch_decks(ref, cache_root, flat_cache=flat_cache)
    standings = _fetch_standings(ref, cache_root, flat_cache=flat_cache)

    total_players = int(tournament.get("players_r1", tournament.get("players", 0)))
    decklists_by_archetype: dict[str, list[dict[str, Any]]] = defaultdict(list)
    qualifying_decks = [row for row in decks if int(row.get("players", 0)) >= int(args.min_archetype_players)]
    qualifying_ids = {str(row.get("identifier", "")).strip() for row in qualifying_decks}

    fetch_jobs: list[tuple[str, str]] = []
    for row in standings:
        if int(row.get("decklist", 0)) != 1:
            continue
        archetype_id = str(row.get("deck_id", "")).strip()
        tp_id = str(row.get("tp_id", "")).strip()
        if not archetype_id or not tp_id or archetype_id not in qualifying_ids:
            continue
        fetch_jobs.append((archetype_id, tp_id))

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
        future_map = {
            executor.submit(_fetch_player_decklist, ref, tp_id, cache_root, flat_cache=flat_cache): (
                archetype_id,
                tp_id,
            )
            for archetype_id, tp_id in fetch_jobs
        }
        for future in as_completed(future_map):
            archetype_id, _tp_id = future_map[future]
            decklist_payload = future.result()
            if decklist_payload:
                decklists_by_archetype[archetype_id].append(decklist_payload)
            if int(args.pause_ms) > 0:
                time.sleep(int(args.pause_ms) / 1000.0)

    qualifying_decks.sort(key=lambda row: int(row.get("players", 0)), reverse=True)

    archetype_reports = [
        build_archetype_summary(
            archetype_row=row,
            standings_rows=standings,
            decklists=decklists_by_archetype.get(str(row.get("identifier", "")).strip(), []),
            total_players=total_players,
        )
        for row in qualifying_decks
    ]

    result = {
        "source": {
            "provider": "Limitless Labs",
            "tournament_id": ref.tournament_id,
            "division": ref.division,
            "cache_dir": str(cache_root),
        },
        "tournament": tournament,
        "field": {
            "total_players": total_players,
            "qualified_archetype_count": len(archetype_reports),
            "min_archetype_players": int(args.min_archetype_players),
        },
        "archetypes": archetype_reports,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _default_output_path(ref: TournamentRef) -> Path:
    return Path(DEFAULT_OUTPUT_DIR).resolve() / f"limitless_{ref.tournament_id}_{ref.division}_analysis.json"


def _cache_base(ref: TournamentRef, cache_root: Path, *, flat_cache: bool) -> Path:
    return cache_root if flat_cache else cache_root / ref.tournament_id / ref.division


def _fetch_tournament(ref: TournamentRef, cache_root: Path, *, flat_cache: bool = False) -> dict[str, Any]:
    payload = _fetch_json(
        endpoint="tournament",
        params={"id": ref.tournament_id, "division": ref.division},
        cache_path=_cache_base(ref, cache_root, flat_cache=flat_cache) / "tournament.json",
    )
    return payload.get("message", {}) if payload.get("ok") else {}


def _fetch_decks(ref: TournamentRef, cache_root: Path, *, flat_cache: bool = False) -> list[dict[str, Any]]:
    payload = _fetch_json(
        endpoint="decks",
        params={"tournamentId": ref.tournament_id, "division": ref.division},
        cache_path=_cache_base(ref, cache_root, flat_cache=flat_cache) / "decks.json",
    )
    return payload.get("message", []) if payload.get("ok") else []


def _fetch_standings(ref: TournamentRef, cache_root: Path, *, flat_cache: bool = False) -> list[dict[str, Any]]:
    payload = _fetch_json(
        endpoint="standings",
        params={"tournamentId": ref.tournament_id, "division": ref.division},
        cache_path=_cache_base(ref, cache_root, flat_cache=flat_cache) / "standings.json",
    )
    return payload.get("message", []) if payload.get("ok") else []


def _fetch_player_decklist(
    ref: TournamentRef,
    player_id: str,
    cache_root: Path,
    *,
    flat_cache: bool = False,
) -> dict[str, Any]:
    payload = _fetch_json(
        endpoint="decklist",
        params={"tournamentId": ref.tournament_id, "playerId": player_id},
        cache_path=_cache_base(ref, cache_root, flat_cache=flat_cache) / "decklists" / f"{player_id}.json",
    )
    return payload.get("message", {}) if payload.get("ok") else {}


def _fetch_json(endpoint: str, params: dict[str, Any], cache_path: Path) -> dict[str, Any]:
    if cache_path.exists():
        try:
            cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if _is_successful_payload(cached_payload):
                return cached_payload
        except (OSError, json.JSONDecodeError):
            pass

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    query = urlencode(params)
    url = f"{API_ROOT}/{endpoint}?{query}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(DEFAULT_FETCH_ATTEMPTS):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not _is_successful_payload(payload):
                raise ValueError(f"Limitless returned an unsuccessful payload for {endpoint}")

            temporary_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
            temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary_path.replace(cache_path)
            return payload
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            if attempt + 1 == DEFAULT_FETCH_ATTEMPTS:
                raise
            time.sleep(DEFAULT_RETRY_DELAY_SECONDS * (2**attempt))

    raise RuntimeError("unreachable")


def _is_successful_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("ok") is True and bool(payload.get("message"))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_analysis(args)
    compact = {
        "output_json": args.output_json or str(_default_output_path(TournamentRef(str(args.tournament_id), str(args.division)))),
        "archetype_count": len(result.get("archetypes", [])),
        "top_archetypes": [
            {
                "name": row.get("archetype_name", ""),
                "players": row.get("meta", {}).get("players", 0),
                "win_rate": row.get("performance", {}).get("win_rate", 0.0),
            }
            for row in result.get("archetypes", [])[:8]
        ],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
