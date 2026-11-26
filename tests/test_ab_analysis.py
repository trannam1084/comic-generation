import pytest

from src.image_generator import ab_analysis as an
from src.image_generator.ab_rubric import COMIC_ROW_LABEL, SheetRow

# 3 truyện x 2 nhánh; mỗi truyện 2 nhân vật, trừ s3 chỉ có 1 dòng toàn truyện (không nhân vật đủ điều kiện)
KEY = []
EXPECTED = []
n = 0
for story, n_chars in (("s1", 2), ("s2", 2), ("s3", 0)):
    for arm in ("A", "B"):
        n += 1
        cid = f"C{n:02d}"
        KEY.append({"comic_id": cid, "story_id": story, "arm": arm, "base_seed": 100})
        EXPECTED.append(SheetRow(cid, 0, COMIC_ROW_LABEL))
        EXPECTED += [SheetRow(cid, k, f"c{k}") for k in range(1, n_chars + 1)]
CID = {(r["story_id"], r["arm"]): r["comic_id"] for r in KEY}


def table(identity, dup=0, blend=0, na=()):
    """identity: dict (story, arm) -> điểm cho mọi nhân vật; na: các (story, arm, char_no) ghi NA."""
    t = {}
    for row in EXPECTED:
        key = (row.comic_id, row.char_no)
        story, arm = next((r["story_id"], r["arm"]) for r in KEY if r["comic_id"] == row.comic_id)
        if row.char_no == 0:
            t[key] = {"panels_duplicate_figure": dup, "panels_blended_figure": blend}
        else:
            t[key] = {"identity_consistency": None if (story, arm, row.char_no) in na else identity[(story, arm)]}
    return t


SCORES_1 = {("s1", "A"): 2, ("s1", "B"): 4, ("s2", "A"): 3, ("s2", "B"): 3, ("s3", "A"): 1, ("s3", "B"): 1}


def test_single_rater_summary_and_direction():
    res = an.analyze_tier(KEY, EXPECTED, {"r1": table(SCORES_1)})
    by_story = res["by_story"]["identity_consistency"]
    assert by_story["s1"]["diff_b_minus_a"] == 2 and by_story["s1"]["verdict"] == 1
    assert by_story["s2"]["verdict"] == 0
    assert by_story["s3"]["diff_b_minus_a"] is None          # không nhân vật nào để chấm
    s = res["summary"]["identity_consistency"]
    assert (s["n_stories_with_data"], s["b_better"], s["a_better"], s["ties"]) == (2, 1, 0, 1)
    assert s["mean_diff_b_minus_a"] == 1.0
    assert res["inter_rater"] == {}


def test_lower_is_better_direction_for_panel_counts():
    low_b = table(SCORES_1, dup=0)
    res_a = an.analyze_tier(KEY, EXPECTED, {"r1": low_b})
    assert res_a["summary"]["panels_duplicate_figure"]["ties"] == 3
    # B có nhiều khung dư hơn A -> A tốt hơn
    t = table(SCORES_1)
    for row in EXPECTED:
        if row.char_no == 0 and CID[("s1", "B")] == row.comic_id:
            t[(row.comic_id, 0)]["panels_duplicate_figure"] = 2
    res = an.analyze_tier(KEY, EXPECTED, {"r1": t})
    s1 = res["by_story"]["panels_duplicate_figure"]["s1"]
    assert s1["diff_b_minus_a"] == 2 and s1["verdict"] == -1


def test_na_is_excluded_from_mean_and_counted():
    na = {("s1", "B", 1)}   # nhân vật 1 của s1-B ghi NA; nhân vật 2 vẫn tính
    t = table(SCORES_1, na=na)
    res = an.analyze_tier(KEY, EXPECTED, {"r1": t})
    assert res["by_story"]["identity_consistency"]["s1"]["b"] == 4
    assert res["na_per_rater_by_arm"] == {"A": 0.0, "B": 1.0}
    all_na = {("s1", "B", 1), ("s1", "B", 2)}
    res = an.analyze_tier(KEY, EXPECTED, {"r1": table(SCORES_1, na=all_na)})
    assert res["by_story"]["identity_consistency"]["s1"]["b"] is None


def test_two_raters_average_and_inter_rater():
    second = dict(SCORES_1)
    second[("s1", "B")] = 3
    res = an.analyze_tier(KEY, EXPECTED, {"r1": table(SCORES_1), "r2": table(second)})
    assert res["by_story"]["identity_consistency"]["s1"]["b"] == 3.5     # (4 + 3) / 2
    ir = res["inter_rater"]["identity_consistency"]
    assert ir["n_cells"] == 8 and ir["exact_agreement"] == 6 / 8 and ir["within_one"] == 1.0
    assert res["per_rater_direction"]["r2"]["identity_consistency"]["mean_diff_b_minus_a"] == 0.5


def test_raters_disagreeing_in_direction_is_visible():
    flipped = dict(SCORES_1); flipped[("s1", "A")], flipped[("s1", "B")] = 4, 2
    res = an.analyze_tier(KEY, EXPECTED, {"r1": table(SCORES_1), "r2": table(flipped)})
    d = res["per_rater_direction"]
    assert d["r1"]["identity_consistency"]["b_better"] == 1 and d["r2"]["identity_consistency"]["a_better"] == 1
    assert res["by_story"]["identity_consistency"]["s1"]["verdict"] == 0   # trung bình triệt tiêu: phải đọc theo từng người


def test_multi_seed_stories_are_averaged_per_arm():
    key = list(KEY) + [{"comic_id": "C90", "story_id": "s1", "arm": "A", "base_seed": 200},
                       {"comic_id": "C91", "story_id": "s1", "arm": "B", "base_seed": 200}]
    expected = list(EXPECTED) + [SheetRow(c, k, "x") for c in ("C90", "C91") for k in (0, 1)]
    t = table(SCORES_1)
    t.update({("C90", 0): {"panels_duplicate_figure": 0, "panels_blended_figure": 0}, ("C90", 1): {"identity_consistency": 4},
              ("C91", 0): {"panels_duplicate_figure": 0, "panels_blended_figure": 0}, ("C91", 1): {"identity_consistency": 4}})
    res = an.analyze_tier(key, expected, {"r1": t})
    assert res["by_story"]["identity_consistency"]["s1"]["a"] == 3     # (2 + 4) / 2


def test_errors():
    with pytest.raises(ValueError, match="ít nhất"):
        an.analyze_tier(KEY, EXPECTED, {})
    incomplete = table(SCORES_1); incomplete.pop(next(iter(incomplete)))
    with pytest.raises(ValueError, match="không chấm đủ"):
        an.analyze_tier(KEY, EXPECTED, {"r1": incomplete})
    with pytest.raises(ValueError, match="thiếu nhánh"):
        an.analyze_tier([r for r in KEY if not (r["story_id"] == "s2" and r["arm"] == "B")],
                        [e for e in EXPECTED if e.comic_id != CID[("s2", "B")]], {"r1": {
                            k: v for k, v in table(SCORES_1).items() if k[0] != CID[("s2", "B")]}})


def test_report_and_files(tmp_path):
    res = an.analyze_tier(KEY, EXPECTED, {"r1": table(SCORES_1), "r2": table(SCORES_1)})
    text = an.format_report(res, "core")
    assert "p-value" in text and "Độ đồng thuận" in text and "`core`" in text and "không có dữ liệu" in text
    an.write_analysis(res, KEY, "core", tmp_path / "out")
    assert {p.name for p in (tmp_path / "out").iterdir()} == {"summary.md", "analysis.json", "per_comic.csv"}
    one = an.format_report(an.analyze_tier(KEY, EXPECTED, {"r1": table(SCORES_1)}), "core")
    assert "MỘT người chấm" in one