import unittest
from pathlib import Path

from scripts.tools.limitless_tournament_analysis import (
    TournamentRef,
    _cache_base,
    build_archetype_card_summary,
    build_archetype_summary,
)


class LimitlessTournamentAnalysisTests(unittest.TestCase):
    def test_cache_base_supports_nested_and_flat_layouts(self) -> None:
        ref = TournamentRef(tournament_id="0066", division="MA")
        cache_root = Path("/repo/data/2026/Melbourne/MA/cache")

        self.assertEqual(_cache_base(ref, cache_root, flat_cache=True), cache_root)
        self.assertEqual(_cache_base(ref, cache_root, flat_cache=False), cache_root / "0066" / "MA")

    def test_build_archetype_card_summary_groups_cards_by_frequency_and_count(self) -> None:
        decklists = [
            {
                "pokemon": [
                    {"name": "Dreepy", "count": 4},
                    {"name": "Drakloak", "count": 4},
                    {"name": "Dragapult ex", "count": 3},
                    {"name": "Munkidori", "count": 2},
                ],
                "trainer": [
                    {"name": "Boss's Orders", "count": 4},
                    {"name": "Night Stretcher", "count": 2},
                ],
                "energy": [{"name": "Psychic Energy", "count": 4}],
            },
            {
                "pokemon": [
                    {"name": "Dreepy", "count": 4},
                    {"name": "Drakloak", "count": 4},
                    {"name": "Dragapult ex", "count": 3},
                    {"name": "Munkidori", "count": 1},
                ],
                "trainer": [
                    {"name": "Boss's Orders", "count": 3},
                    {"name": "Night Stretcher", "count": 1},
                ],
                "energy": [{"name": "Psychic Energy", "count": 4}],
            },
            {
                "pokemon": [
                    {"name": "Dreepy", "count": 4},
                    {"name": "Drakloak", "count": 4},
                    {"name": "Dragapult ex", "count": 2},
                ],
                "trainer": [
                    {"name": "Boss's Orders", "count": 2},
                ],
                "energy": [{"name": "Psychic Energy", "count": 3}],
            },
        ]

        summary = build_archetype_card_summary(decklists)

        self.assertEqual(summary["deck_count"], 3)
        pokemon_rows = summary["pokemon"]
        trainer_rows = summary["trainer"]
        energy_rows = summary["energy"]

        dreepy_row = next(row for row in pokemon_rows if row["name"] == "Dreepy")
        self.assertEqual(dreepy_row["bucket"], "core")
        self.assertEqual(dreepy_row["frequency"], 1.0)
        self.assertEqual(dreepy_row["avg_count"], 4.0)

        dragapult_row = next(row for row in pokemon_rows if row["name"] == "Dragapult ex")
        self.assertEqual(dragapult_row["bucket"], "core")
        self.assertEqual(dragapult_row["min_count"], 2)
        self.assertEqual(dragapult_row["max_count"], 3)

        munkidori_row = next(row for row in pokemon_rows if row["name"] == "Munkidori")
        self.assertEqual(munkidori_row["bucket"], "common")
        self.assertAlmostEqual(munkidori_row["frequency"], 2.0 / 3.0, places=4)

        boss_row = next(row for row in trainer_rows if row["name"] == "Boss's Orders")
        self.assertEqual(boss_row["bucket"], "core")
        self.assertEqual(boss_row["avg_count"], 3.0)

        self.assertEqual(energy_rows[0]["name"], "Psychic Energy")
        self.assertEqual(energy_rows[0]["bucket"], "core")
        self.assertAlmostEqual(energy_rows[0]["avg_count"], 3.6667, places=3)

    def test_build_archetype_summary_combines_meta_and_finishers(self) -> None:
        archetype_row = {
            "identifier": "dragapult-ex",
            "name": "Dragapult",
            "players": 188,
            "day2s": 51,
            "wins": 751,
            "losses": 634,
            "ties": 248,
        }
        standings_rows = [
            {"placement": 5, "name": "Tord Reklev", "deck_name": "Dragapult", "deck_id": "dragapult-ex", "points": 37},
            {"placement": 18, "name": "Yoann Barszezak", "deck_name": "Dragapult", "deck_id": "dragapult-ex", "points": 30},
            {"placement": 64, "name": "riccardo corino", "deck_name": "Dragapult", "deck_id": "dragapult-ex", "points": 27},
            {"placement": 2, "name": "Elmar Tresp", "deck_name": "Crustle", "deck_id": "crustle-dri", "points": 40},
        ]

        summary = build_archetype_summary(archetype_row, standings_rows, decklists=[], total_players=1362)

        self.assertEqual(summary["archetype_id"], "dragapult-ex")
        self.assertEqual(summary["meta"]["players"], 188)
        self.assertAlmostEqual(summary["meta"]["share"], 188 / 1362.0, places=4)
        self.assertEqual(summary["performance"]["top8_count"], 1)
        self.assertEqual(summary["performance"]["top16_count"], 1)
        self.assertEqual(summary["performance"]["top64_count"], 3)
        self.assertEqual(summary["top_finishers"][0]["name"], "Tord Reklev")


if __name__ == "__main__":
    unittest.main()
