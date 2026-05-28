import unittest

from scripts.tools.prague_phase15_tools import build_summary_markdown, compare_user_deck, sample_deck_schema


class PraguePhase15ToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = {
            "source": {"tournament_id": "0062", "division": "MA"},
            "tournament": {"name": "Prague Special Event"},
            "field": {"total_players": 100, "qualified_archetype_count": 2, "min_archetype_players": 10},
            "archetypes": [
                {
                    "archetype_id": "dragapult-ex",
                    "archetype_name": "Dragapult",
                    "meta": {"players": 20, "share": 0.2, "day2s": 8, "day2_conversion": 0.4},
                    "performance": {"win_rate": 0.55, "top8_count": 1, "top16_count": 2, "top64_count": 5},
                    "top_finishers": [{"placement": 5, "name": "Player A"}],
                    "card_summary": {
                        "deck_count": 20,
                        "pokemon": [
                            {"name": "Dreepy", "bucket": "core", "frequency": 1.0, "avg_count": 4.0, "avg_when_present": 4.0, "min_count": 4, "max_count": 4},
                            {"name": "Drakloak", "bucket": "core", "frequency": 1.0, "avg_count": 4.0, "avg_when_present": 4.0, "min_count": 4, "max_count": 4},
                            {"name": "Munkidori", "bucket": "common", "frequency": 0.7, "avg_count": 1.4, "avg_when_present": 2.0, "min_count": 1, "max_count": 2},
                            {"name": "Cleffa", "bucket": "tech", "frequency": 0.15, "avg_count": 0.15, "avg_when_present": 1.0, "min_count": 1, "max_count": 1},
                        ],
                        "trainer": [
                            {"name": "Buddy-Buddy Poffin", "bucket": "core", "frequency": 1.0, "avg_count": 4.0, "avg_when_present": 4.0, "min_count": 4, "max_count": 4},
                            {"name": "Boss's Orders", "bucket": "common", "frequency": 0.75, "avg_count": 2.5, "avg_when_present": 3.0, "min_count": 2, "max_count": 3},
                        ],
                        "energy": [
                            {"name": "Psychic Energy", "bucket": "core", "frequency": 1.0, "avg_count": 3.0, "avg_when_present": 3.0, "min_count": 3, "max_count": 4},
                        ],
                    },
                },
                {
                    "archetype_id": "garchomp",
                    "archetype_name": "Garchomp",
                    "meta": {"players": 15, "share": 0.15, "day2s": 9, "day2_conversion": 0.6},
                    "performance": {"win_rate": 0.52, "top8_count": 1, "top16_count": 1, "top64_count": 4},
                    "top_finishers": [],
                    "card_summary": {"deck_count": 15, "pokemon": [], "trainer": [], "energy": []},
                },
            ],
        }

    def test_build_summary_markdown_contains_main_sections(self) -> None:
        markdown = build_summary_markdown(self.analysis, top_n=2)
        self.assertIn("Prague 0062 环境趋势摘要", markdown)
        self.assertIn("### 1. Dragapult", markdown)
        self.assertIn("核心骨架", markdown)
        self.assertIn("代表成绩：#5 Player A", markdown)

    def test_compare_user_deck_flags_missing_core_common_and_extra(self) -> None:
        deck = {
            "pokemon": [
                {"name": "Dreepy", "count": 4},
                {"name": "Munkidori", "count": 1},
                {"name": "Pikachu", "count": 1},
            ],
            "trainer": [{"name": "Buddy-Buddy Poffin", "count": 4}],
            "energy": [{"name": "Psychic Energy", "count": 2}],
        }
        result = compare_user_deck(self.analysis, "Dragapult", deck)

        missing_core_names = {row["name"] for row in result["missing_core"]}
        self.assertIn("Drakloak", missing_core_names)

        underplayed_names = {row["name"] for row in result["underplayed_core"]}
        self.assertIn("Psychic Energy", underplayed_names)

        missing_common_names = {row["name"] for row in result["missing_common"]}
        self.assertIn("Boss's Orders", missing_common_names)

        extra_names = {row["name"] for row in result["extra_cards"]}
        self.assertIn("Pikachu", extra_names)

    def test_sample_deck_schema_has_expected_shape(self) -> None:
        sample = sample_deck_schema()
        self.assertIn("pokemon", sample)
        self.assertIn("trainer", sample)
        self.assertIn("energy", sample)


if __name__ == "__main__":
    unittest.main()
