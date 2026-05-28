from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_ANALYSIS_JSON = "data/2026/Prague/MA/analysis.json"
DEFAULT_SUMMARY_OUTPUT = "data/2026/Prague/MA/summary_zh.md"
SECTION_ORDER = ("pokemon", "trainer", "energy")
SECTION_LABELS = {
    "pokemon": "宝可梦",
    "trainer": "训练家",
    "energy": "能量",
}
BUCKET_LABELS = {
    "core": "核心",
    "common": "常见",
    "tech": "Tech",
}


def normalize_card_name(name: str) -> str:
    """Strip trailing set code and card number from decklist entries.

    PTCG decklists typically follow: `<count> <card name> <SET> <number>`.
    This keeps just the card name so multi-set versions match the same card.
    """
    stripped = name.strip()
    # Match trailing ` SET_CODE NUMBER` (e.g. "TWM 129", "MEE 5")
    m = re.search(r"\s+([A-Z]{2,6})\s+(\d+)\s*$", stripped)
    if m:
        return stripped[: m.start()].strip()
    # Fallback: just a trailing number
    m = re.search(r"\s+(\d+)\s*$", stripped)
    if m:
        return stripped[: m.start()].strip()
    return stripped


@dataclass(frozen=True)
class DeckEntry:
    name: str
    count: int


@dataclass(frozen=True)
class ComparedCard:
    name: str
    section: str
    bucket: str
    expected_count: float
    expected_when_present: float
    user_count: int
    delta_vs_expected: float
    delta_vs_floor: int
    note: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prague phase 1.5 summary + deck diff helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser("summary", help="Generate Chinese Prague meta summary")
    summary_parser.add_argument("--analysis-json", default=DEFAULT_ANALYSIS_JSON)
    summary_parser.add_argument("--output", default=DEFAULT_SUMMARY_OUTPUT)
    summary_parser.add_argument("--top-n", type=int, default=8)

    compare_parser = subparsers.add_parser("compare", help="Compare a user deck against one Prague archetype")
    compare_parser.add_argument("--analysis-json", default=DEFAULT_ANALYSIS_JSON)
    compare_parser.add_argument("--deck-json", required=True)
    compare_parser.add_argument("--archetype", required=True, help="Archetype name or id")
    compare_parser.add_argument("--output")

    template_parser = subparsers.add_parser("template", help="Write a sample user deck JSON schema")
    template_parser.add_argument("--output", default="tmp/limitless_reports/user_deck_schema.sample.json")

    return parser.parse_args(argv)


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_user_deck(payload: dict[str, Any]) -> dict[str, list[DeckEntry]]:
    normalized: dict[str, list[DeckEntry]] = {}
    for section in SECTION_ORDER:
        rows = payload.get(section, []) or []
        section_entries: list[DeckEntry] = []
        for row in rows:
            name = normalize_card_name(str(row.get("name", "")).strip())
            if not name:
                continue
            count = int(row.get("count", 0))
            if count <= 0:
                continue
            section_entries.append(DeckEntry(name=name, count=count))
        normalized[section] = section_entries
    return normalized


def find_archetype(analysis: dict[str, Any], archetype_query: str) -> dict[str, Any]:
    query = archetype_query.strip().lower()
    for row in analysis.get("archetypes", []):
        name = str(row.get("archetype_name", "")).strip().lower()
        archetype_id = str(row.get("archetype_id", "")).strip().lower()
        if query in {name, archetype_id}:
            return row
    raise ValueError(f"Archetype not found: {archetype_query}")


def build_summary_markdown(analysis: dict[str, Any], top_n: int = 8) -> str:
    tournament = analysis.get("tournament", {})
    field = analysis.get("field", {})
    archetypes = analysis.get("archetypes", [])
    top_rows = archetypes[:top_n]

    tournament_name = str(tournament.get('name') or 'Prague Special Event').strip()
    lines = [
        f"# Prague 0062 环境趋势摘要（{analysis.get('source', {}).get('division', 'MA')}）",
        "",
        f"- 比赛：{tournament_name}（ID {analysis.get('source', {}).get('tournament_id', '0062')}）",
        f"- 总人数：{field.get('total_players', 0)}",
        f"- 纳入统计的 archetype：{field.get('qualified_archetype_count', 0)} 个（门槛 {field.get('min_archetype_players', 0)} 人）",
        "",
        "## 一句话结论",
    ]

    if top_rows:
        top_names = "、".join(f"{row['archetype_name']}（{row['meta']['players']}人）" for row in top_rows[:5])
        lines.append(f"- Prague 当前主流主要由 {top_names} 构成。")
        best_win = max(top_rows, key=lambda row: row.get("performance", {}).get("win_rate", 0.0))
        best_conv = max(top_rows, key=lambda row: row.get("meta", {}).get("day2_conversion", 0.0))
        lines.append(
            f"- 在前 {len(top_rows)} 个主流 archetype 里，胜率最高的是 {best_win['archetype_name']}（{_pct(best_win['performance']['win_rate'])}），Day 2 转化最高的是 {best_conv['archetype_name']}（{_pct(best_conv['meta']['day2_conversion'])}）。"
        )
    else:
        lines.append("- 当前没有可摘要的 archetype 数据。")

    lines.extend(["", "## 主流 archetype 概览"])
    for index, row in enumerate(top_rows, start=1):
        meta = row.get("meta", {})
        perf = row.get("performance", {})
        finishers = row.get("top_finishers", [])
        lines.extend(
            [
                "",
                f"### {index}. {row.get('archetype_name', '')}",
                f"- 人数 / 占比：{meta.get('players', 0)} / {_pct(meta.get('share', 0.0))}",
                f"- Day 2：{meta.get('day2s', 0)}，转化 {_pct(meta.get('day2_conversion', 0.0))}",
                f"- 胜率：{_pct(perf.get('win_rate', 0.0))}；Top8 / Top16 / Top64 = {perf.get('top8_count', 0)} / {perf.get('top16_count', 0)} / {perf.get('top64_count', 0)}",
                f"- 核心骨架：{_format_core_cards(row.get('card_summary', {}))}",
                f"- 常见弹性位：{_format_bucket_cards(row.get('card_summary', {}), bucket='common', limit=6)}",
                f"- 代表成绩：{_format_finishers(finishers[:3])}",
            ]
        )

    lines.extend(["", "## 使用建议", "- 如果用户想比较自己的 deck，下一步只需要提供：目标 archetype 名称 + 标准化 deck JSON。", "- 对比重点优先看：缺失 core、核心数量偏低、common/tech 偏移。", ""])
    return "\n".join(lines)


def compare_user_deck(analysis: dict[str, Any], archetype_query: str, deck_payload: dict[str, Any]) -> dict[str, Any]:
    archetype = find_archetype(analysis, archetype_query)
    normalized = normalize_user_deck(deck_payload)
    user_lookup = {
        section: {entry.name: entry.count for entry in entries}
        for section, entries in normalized.items()
    }

    missing_core: list[ComparedCard] = []
    underplayed: list[ComparedCard] = []
    overplayed: list[ComparedCard] = []
    missing_common: list[ComparedCard] = []
    tech_deviations: list[ComparedCard] = []
    extra_cards: list[dict[str, Any]] = []

    archetype_known_cards: dict[str, set[str]] = {section: set() for section in SECTION_ORDER}

    for section in SECTION_ORDER:
        for row in archetype.get("card_summary", {}).get(section, []):
            name = normalize_card_name(str(row.get("name", "")))
            archetype_known_cards[section].add(name)
            user_count = int(user_lookup.get(section, {}).get(name, 0))
            expected_count = float(row.get("avg_count", 0.0))
            expected_when_present = float(row.get("avg_when_present", 0.0))
            min_count = int(row.get("min_count", 0))
            bucket = str(row.get("bucket", "tech"))
            compared = ComparedCard(
                name=name,
                section=section,
                bucket=bucket,
                expected_count=expected_count,
                expected_when_present=expected_when_present,
                user_count=user_count,
                delta_vs_expected=round(user_count - expected_count, 4),
                delta_vs_floor=user_count - min_count,
                note="",
            )
            if bucket == "core" and user_count == 0:
                missing_core.append(_with_note(compared, f"主流核心通常带 {expected_when_present:.1f} 张，你当前未带。"))
            elif bucket == "core" and user_count < max(1, min_count):
                underplayed.append(_with_note(compared, f"低于 Prague 样本下限 {min_count}。"))
            elif bucket == "common" and user_count == 0:
                missing_common.append(_with_note(compared, f"这是常见配置，样本均值 {expected_count:.1f}。"))
            elif user_count > 0 and user_count > max(min_count, round(expected_when_present)) and bucket in {"core", "common"}:
                overplayed.append(_with_note(compared, f"高于常见区间，上限 {row.get('max_count', 0)}。"))
            elif bucket == "tech" and user_count > 0:
                tech_deviations.append(_with_note(compared, f"这是 Prague 中出现频率 {_pct(row.get('frequency', 0.0))} 的 tech 位。"))

    for section in SECTION_ORDER:
        for entry in normalized.get(section, []):
            if entry.name not in archetype_known_cards[section]:
                extra_cards.append(
                    {
                        "section": section,
                        "name": entry.name,
                        "count": entry.count,
                        "note": "该卡未出现在此 Prague archetype 统计里，可视为强偏离或个人 tech。",
                    }
                )

    return {
        "archetype": {
            "id": archetype.get("archetype_id", ""),
            "name": archetype.get("archetype_name", ""),
            "deck_count": archetype.get("card_summary", {}).get("deck_count", 0),
        },
        "summary": {
            "missing_core_count": len(missing_core),
            "underplayed_core_count": len(underplayed),
            "missing_common_count": len(missing_common),
            "overplayed_count": len(overplayed),
            "tech_deviation_count": len(tech_deviations),
            "extra_card_count": len(extra_cards),
        },
        "missing_core": [_compared_card_to_dict(item) for item in missing_core[:15]],
        "underplayed_core": [_compared_card_to_dict(item) for item in underplayed[:15]],
        "missing_common": [_compared_card_to_dict(item) for item in missing_common[:15]],
        "overplayed": [_compared_card_to_dict(item) for item in overplayed[:15]],
        "tech_deviations": [_compared_card_to_dict(item) for item in tech_deviations[:15]],
        "extra_cards": extra_cards[:20],
    }


def sample_deck_schema() -> dict[str, Any]:
    return {
        "deck_name": "My Prague Test Deck",
        "archetype_hint": "Dragapult",
        "pokemon": [
            {"name": "Dreepy", "count": 4},
            {"name": "Drakloak", "count": 4},
            {"name": "Dragapult ex", "count": 3},
        ],
        "trainer": [
            {"name": "Buddy-Buddy Poffin", "count": 4},
            {"name": "Boss's Orders", "count": 3},
        ],
        "energy": [
            {"name": "Psychic Energy", "count": 3},
            {"name": "Fire Energy", "count": 3},
        ],
    }


def _with_note(item: ComparedCard, note: str) -> ComparedCard:
    return ComparedCard(**{**item.__dict__, "note": note})


def _compared_card_to_dict(item: ComparedCard) -> dict[str, Any]:
    return {
        "section": item.section,
        "section_label": SECTION_LABELS[item.section],
        "name": item.name,
        "bucket": item.bucket,
        "bucket_label": BUCKET_LABELS.get(item.bucket, item.bucket),
        "expected_count": item.expected_count,
        "expected_when_present": item.expected_when_present,
        "user_count": item.user_count,
        "delta_vs_expected": item.delta_vs_expected,
        "delta_vs_floor": item.delta_vs_floor,
        "note": item.note,
    }


def _pct(value: float) -> str:
    return f"{float(value) * 100:.1f}%"


def _format_core_cards(card_summary: dict[str, Any]) -> str:
    parts: list[str] = []
    for section in SECTION_ORDER:
        rows = [row for row in card_summary.get(section, []) if row.get("bucket") == "core"][:4]
        for row in rows:
            parts.append(f"{row['name']}×{row['avg_when_present']:.1f}")
    return "、".join(parts[:8]) if parts else "无"


def _format_bucket_cards(card_summary: dict[str, Any], bucket: str, limit: int) -> str:
    rows: list[str] = []
    for section in SECTION_ORDER:
        for row in card_summary.get(section, []):
            if row.get("bucket") != bucket:
                continue
            rows.append(f"{row['name']}（{_pct(row['frequency'])} / {row['avg_when_present']:.1f}）")
    return "、".join(rows[:limit]) if rows else "无"


def _format_finishers(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "无公开 decklist 成绩代表"
    return "；".join(f"#{row.get('placement', '?')} {row.get('name', '')}" for row in rows)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "summary":
        analysis = load_json(args.analysis_json)
        markdown = build_summary_markdown(analysis, top_n=int(args.top_n))
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(output_path)
        return 0

    if args.command == "compare":
        analysis = load_json(args.analysis_json)
        deck_payload = load_json(args.deck_json)
        result = compare_user_deck(analysis, args.archetype, deck_payload)
        rendered = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            print(output_path)
        else:
            print(rendered)
        return 0

    if args.command == "template":
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(sample_deck_schema(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(output_path)
        return 0

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
