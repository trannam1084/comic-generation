"""Phân tích kết quả chấm Task 6 cho một tầng (core hoặc extra), nhiều truyện.

Quy ước: (1) mỗi người chấm -> mỗi truyện tranh (trung bình các nhân vật không NA); (2) trung bình các người chấm;
(3) trung bình các seed trong cùng truyện và cùng nhánh; (4) so B với A theo TỪNG TRUYỆN. Không dùng p-value:
với 5 truyện, kiểm định dấu hai phía có p nhỏ nhất 0.0625 nên không bao giờ đạt mức 0.05.
"""

from __future__ import annotations

import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.image_generator.ab_rubric import (
    COMIC_ROW_NO,
    RATING_FIELDS,
    RatingTable,
    SheetRow,
)

METRICS = tuple(f.name for f in RATING_FIELDS)
FIELD = {f.name: f for f in RATING_FIELDS}
ARMS = ("A", "B")


def _mean(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _verdict(metric: str, diff: float, eps: float = 1e-9) -> int:
    """+1 nếu B tốt hơn A, -1 nếu A tốt hơn B, 0 nếu hòa (xét theo chiều tốt của chỉ số)."""
    if abs(diff) <= eps:
        return 0
    improves = diff > 0 if FIELD[metric].better == "higher" else diff < 0
    return 1 if improves else -1


def _rater_comic_metrics(table: RatingTable, comic_id: str, char_nos: Sequence[int]) -> dict[str, float | None]:
    values = [table[(comic_id, n)]["identity_consistency"] for n in char_nos]
    seen = [v for v in values if v is not None]
    comic_row = table[(comic_id, COMIC_ROW_NO)]
    return {
        "identity_consistency": _mean(seen),
        "identity_na": len(values) - len(seen),
        "panels_duplicate_figure": comic_row["panels_duplicate_figure"],
        "panels_blended_figure": comic_row["panels_blended_figure"],
    }


def _inter_rater(raters: Sequence[str], ratings: Mapping[str, RatingTable]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    keys = sorted(next(iter(ratings.values())))
    for field in RATING_FIELDS:
        gaps: list[float] = []
        for first, second in itertools.combinations(raters, 2):
            for key in keys:
                x = ratings[first][key].get(field.name)
                y = ratings[second][key].get(field.name)
                if key in ratings[first] and field.name in ratings[first][key] and x is not None and y is not None:
                    gaps.append(abs(x - y))
        if gaps:
            result[field.name] = {
                "n_cells": len(gaps),
                "mean_abs_diff": sum(gaps) / len(gaps),
                "exact_agreement": sum(g == 0 for g in gaps) / len(gaps),
                "within_one": sum(g <= 1 for g in gaps) / len(gaps),
            }
    return result


def analyze_tier(
    key_rows: Sequence[Mapping[str, Any]],
    expected_rows: Sequence[SheetRow],
    ratings_by_rater: Mapping[str, RatingTable],
) -> dict[str, Any]:
    if not ratings_by_rater:
        raise ValueError("Cần ít nhất một file điểm")
    key = {row["comic_id"]: row for row in key_rows}
    char_nos: dict[str, list[int]] = defaultdict(list)
    for row in expected_rows:
        if row.comic_id not in key:
            raise ValueError(f"Phiếu có mã truyện không có trong khóa: {row.comic_id}")
        if row.char_no != COMIC_ROW_NO:
            char_nos[row.comic_id].append(row.char_no)
    expected_keys = {(r.comic_id, r.char_no) for r in expected_rows}
    for rater, table in ratings_by_rater.items():
        if set(table) != expected_keys:
            raise ValueError(f"Người chấm {rater} không chấm đủ các dòng của phiếu")

    raters = list(ratings_by_rater)
    stories = sorted({row["story_id"] for row in key_rows})
    for story in stories:
        for arm in ARMS:
            if not any(r["story_id"] == story and r["arm"] == arm for r in key_rows):
                raise ValueError(f"Truyện {story} thiếu nhánh {arm}")

    per_rater = {
        rater: {cid: _rater_comic_metrics(table, cid, char_nos[cid]) for cid in key}
        for rater, table in ratings_by_rater.items()
    }
    comic_mean = {
        cid: {m: _mean([per_rater[r][cid][m] for r in raters]) for m in METRICS} for cid in key
    }

    def story_value(source: Mapping[str, Mapping[str, Any]], story: str, arm: str, metric: str) -> float | None:
        cids = [cid for cid, row in key.items() if row["story_id"] == story and row["arm"] == arm]
        return _mean([source[cid][metric] for cid in cids])

    def compare(source: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        table: dict[str, dict[str, Any]] = {}
        for metric in METRICS:
            rows = {}
            for story in stories:
                a, b = story_value(source, story, "A", metric), story_value(source, story, "B", metric)
                diff = None if a is None or b is None else b - a
                rows[story] = {"a": a, "b": b, "diff_b_minus_a": diff,
                               "verdict": None if diff is None else _verdict(metric, diff)}
            table[metric] = rows
        return table

    by_story = compare(comic_mean)
    summary: dict[str, Any] = {}
    for metric, rows in by_story.items():
        usable = [r for r in rows.values() if r["diff_b_minus_a"] is not None]
        verdicts = [r["verdict"] for r in usable]
        summary[metric] = {
            "better": FIELD[metric].better,
            "primary": FIELD[metric].primary,
            "n_stories_with_data": len(usable),
            "mean_a": _mean([r["a"] for r in usable]),
            "mean_b": _mean([r["b"] for r in usable]),
            "mean_diff_b_minus_a": _mean([r["diff_b_minus_a"] for r in usable]),
            "b_better": verdicts.count(1),
            "a_better": verdicts.count(-1),
            "ties": verdicts.count(0),
        }

    rater_direction: dict[str, Any] = {}
    for rater in raters:
        cmp_r = compare(per_rater[rater])
        rater_direction[rater] = {}
        for metric, rows in cmp_r.items():
            usable = [r for r in rows.values() if r["diff_b_minus_a"] is not None]
            verdicts = [r["verdict"] for r in usable]
            rater_direction[rater][metric] = {
                "mean_diff_b_minus_a": _mean([r["diff_b_minus_a"] for r in usable]),
                "b_better": verdicts.count(1), "a_better": verdicts.count(-1), "ties": verdicts.count(0),
            }

    na_per_rater = {
        arm: _mean([
            sum(per_rater[r][cid]["identity_na"] for cid, row in key.items() if row["arm"] == arm)
            for r in raters
        ])
        for arm in ARMS
    }
    rated_cells = {arm: sum(len(char_nos[cid]) for cid, row in key.items() if row["arm"] == arm) for arm in ARMS}

    return {
        "n_stories": len(stories),
        "stories": stories,
        "raters": raters,
        "by_story": by_story,
        "summary": summary,
        "per_rater_direction": rater_direction,
        "na_per_rater_by_arm": na_per_rater,
        "rated_character_cells_by_arm": rated_cells,
        "inter_rater": _inter_rater(raters, ratings_by_rater) if len(raters) >= 2 else {},
        "comic_means": comic_mean,
    }


def _fmt(value: float | None, spec: str = "{:.2f}") -> str:
    return "–" if value is None else spec.format(value)


def format_report(analysis: Mapping[str, Any], tier: str) -> str:
    n = analysis["n_stories"]
    raters = analysis["raters"]
    lines = [
        f"# Kết quả so sánh A và B, tầng `{tier}` (Task 6)",
        "",
        f"- Số truyện: {n}. Người chấm ({len(raters)}): {', '.join(raters)}. Điểm của một truyện là trung bình các người chấm.",
        "- A: prompt độc lập từng cảnh. B: có mô tả nhân vật dùng chung. Cùng seed, cùng thông số cho A và B.",
        "",
        "> Thống kê mô tả trên mẫu rất nhỏ, do người chấm theo cảm nhận. Không dùng p-value (với vài truyện, "
        "kiểm định dấu không thể đạt mức ý nghĩa). Đọc bảng theo từng truyện, không kết luận phương án nào tốt hơn "
        "chỉ từ giá trị trung bình.",
        "",
    ]
    if len(raters) == 1:
        lines += ["> Chỉ có MỘT người chấm: không đo được độ đồng thuận giữa người chấm.", ""]

    lines += ["## Tóm tắt theo chỉ số", "",
              "| Chỉ số | Số truyện có dữ liệu | Trung bình A | Trung bình B | B trừ A | B tốt hơn | A tốt hơn | Hòa |",
              "|---|---|---|---|---|---|---|---|"]
    for metric, row in analysis["summary"].items():
        arrow = "cao hơn là tốt" if row["better"] == "higher" else "thấp hơn là tốt"
        role = "chính" if row["primary"] else "phụ"
        lines.append(
            f"| `{metric}` ({role}; {arrow}) | {row['n_stories_with_data']} | {_fmt(row['mean_a'])} | {_fmt(row['mean_b'])} | "
            f"{_fmt(row['mean_diff_b_minus_a'], '{:+.2f}')} | {row['b_better']} | {row['a_better']} | {row['ties']} |"
        )
    lines.append("")

    for metric, rows in analysis["by_story"].items():
        lines += [f"## Từng truyện: `{metric}`", "", "| Truyện | A | B | B trừ A | Hướng |", "|---|---|---|---|---|"]
        for story, r in rows.items():
            hint = {1: "B tốt hơn", -1: "A tốt hơn", 0: "hòa", None: "không có dữ liệu"}[r["verdict"]]
            lines.append(f"| {story} | {_fmt(r['a'])} | {_fmt(r['b'])} | {_fmt(r['diff_b_minus_a'], '{:+.2f}')} | {hint} |")
        lines.append("")

    na = analysis["na_per_rater_by_arm"]
    cells = analysis["rated_character_cells_by_arm"]
    lines += [
        "## Ô `NA` (nhân vật thấy ở dưới 2 khung)", "",
        f"Trung bình mỗi người chấm: nhánh A {_fmt(na['A'], '{:.1f}')} / {cells['A']} ô nhân vật; "
        f"nhánh B {_fmt(na['B'], '{:.1f}')} / {cells['B']} ô nhân vật. "
        "NA không tính vào điểm nhất quán, nhưng chênh lệch NA giữa hai nhánh bản thân là thông tin (nhân vật không xuất hiện).",
        "",
        "## B trừ A theo từng người chấm", "",
        "| Người chấm | " + " | ".join(f"`{m}`" for m in METRICS) + " |",
        "|---|" + "---|" * len(METRICS),
    ]
    for rater, values in analysis["per_rater_direction"].items():
        cells_txt = [
            f"{_fmt(values[m]['mean_diff_b_minus_a'], '{:+.2f}')} (B {values[m]['b_better']}/A {values[m]['a_better']})"
            for m in METRICS
        ]
        lines.append(f"| {rater} | " + " | ".join(cells_txt) + " |")
    lines += ["", "Nếu các người chấm cho hướng chênh lệch ngược nhau, kết quả không đáng tin dù trung bình trông rõ ràng.", ""]

    if analysis["inter_rater"]:
        lines += ["## Độ đồng thuận giữa người chấm", "",
                  "| Chỉ số | Số ô so sánh | Sai khác tuyệt đối TB | Chấm trùng nhau | Lệch không quá 1 |", "|---|---|---|---|---|"]
        for metric, row in analysis["inter_rater"].items():
            lines.append(f"| `{metric}` | {row['n_cells']} | {row['mean_abs_diff']:.2f} | "
                         f"{row['exact_agreement']:.0%} | {row['within_one']:.0%} |")
        lines.append("")
    return "\n".join(lines)


def write_analysis(analysis: Mapping[str, Any], key_rows: Sequence[Mapping[str, Any]], tier: str, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(format_report(analysis, tier), encoding="utf-8")
    (out / "analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(out / "per_comic.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["comic_id", "story_id", "arm", "base_seed"] + list(METRICS))
        for row in sorted(key_rows, key=lambda r: (r["story_id"], int(r["base_seed"]), r["arm"])):
            means = analysis["comic_means"][row["comic_id"]]
            writer.writerow([row["comic_id"], row["story_id"], row["arm"], row["base_seed"]]
                            + ["" if means[m] is None else f"{means[m]:.2f}" for m in METRICS])