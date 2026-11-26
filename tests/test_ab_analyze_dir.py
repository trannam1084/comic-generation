import csv

import pytest

from src.image_generator import ab_analysis as an
from src.image_generator import ab_experiment as ab
from src.image_generator import ab_pack as pack
from src.image_generator.ab_rubric import RatingFileError
from src.image_generator.image_generator import MockImageGenerator


def _story(chars, scene_chars):
    return {
        "summary": "s",
        "characters": [{"id": c, "visual": f"look of {c}"} for c in chars],
        "scenes": [{"index": i, "caption_vi": "x", "image_prompt_en": f"p{i}", "characters": sc}
                   for i, sc in enumerate(scene_chars, 1)],
    }


STORIES = {
    "story_a": _story(["a", "b"], [["a", "b"]] * 4),
    "story_b": _story(["BÀ CON", "DU KHÁCH"], [["BÀ CON"], ["DU KHÁCH", "BÀ CON"], ["DU KHÁCH"], []]),
    "story_c": _story(["solo"], [["solo"], [], [], []]),
}


@pytest.fixture
def packs(tmp_path):
    run = tmp_path / "run"
    ab.run_ab_generation_stories(MockImageGenerator(), stories=[ab.StorySpec(k, v) for k, v in STORIES.items()],
                                 base_seeds=(100, 200), out_dir=run)
    pack.build_blind_packs(ab.load_records(run), STORIES, (100, 200), tmp_path / "packs", shuffle_seed=7)
    return tmp_path / "packs" / "core"


def _fill(tier_dir, path, b_score, a_score, delta=0):
    """Điền phiếu: nhánh B điểm b_score, nhánh A điểm a_score (+delta để mô phỏng người chấm khác)."""
    arm_of = {r["comic_id"]: r["arm"] for r in pack.read_pack_key(tier_dir)}
    rows = list(csv.reader((tier_dir / "for_raters" / "rating_sheet.csv").open(encoding="utf-8-sig")))
    out = [rows[0]]
    for r in rows[1:]:
        r = list(r)
        if r[1] == "0":
            r[4], r[5] = "0", "0"
        else:
            r[3] = str((b_score if arm_of[r[0]] == "B" else a_score) + delta)
        out.append(r)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(out)


def test_end_to_end_two_raters(packs, tmp_path):
    _fill(packs, tmp_path / "nam.csv", 4, 2)
    _fill(packs, tmp_path / "tv3.csv", 4, 2, delta=-1)
    analysis = an.analyze_tier_dir(packs, {"Nam": tmp_path / "nam.csv", "TV3": tmp_path / "tv3.csv"}, tmp_path / "report")
    by_story = analysis["by_story"]["identity_consistency"]
    assert by_story["story_a"]["a"] == 1.5 and by_story["story_a"]["b"] == 3.5     # trung bình hai người chấm
    assert by_story["story_a"]["diff_b_minus_a"] == 2.0 and by_story["story_c"]["diff_b_minus_a"] is None
    assert analysis["summary"]["identity_consistency"]["b_better"] == 2
    assert {p.name for p in (tmp_path / "report").iterdir()} == {"summary.md", "analysis.json", "per_comic.csv"}
    assert "`core`" in (tmp_path / "report" / "summary.md").read_text(encoding="utf-8")


def test_single_rater_works(packs, tmp_path):
    _fill(packs, tmp_path / "nam.csv", 3, 3)
    analysis = an.analyze_tier_dir(packs, {"Nam": tmp_path / "nam.csv"}, tmp_path / "report")
    assert analysis["inter_rater"] == {} and analysis["summary"]["identity_consistency"]["ties"] == 2


def test_errors_of_all_raters_are_reported_together(packs, tmp_path):
    _fill(packs, tmp_path / "nam.csv", 4, 2)
    bad = tmp_path / "tv3.csv"
    bad.write_text("comic_id,char_no\nC01,0\n", encoding="utf-8")
    worse = tmp_path / "x.csv"
    worse.write_text("", encoding="utf-8")
    with pytest.raises(RatingFileError) as err:
        an.analyze_tier_dir(packs, {"Nam": tmp_path / "nam.csv", "TV3": bad, "X": worse}, tmp_path / "report")
    text = str(err.value)
    assert "[TV3]" in text and "[X]" in text and "[Nam]" not in text
    assert not (tmp_path / "report").exists()      # lỗi thì không ghi báo cáo dở dang


def test_refuses_to_overwrite_report_dir(packs, tmp_path):
    _fill(packs, tmp_path / "nam.csv", 4, 2)
    (tmp_path / "report").mkdir(); (tmp_path / "report" / "old.txt").write_text("1")
    with pytest.raises(FileExistsError):
        an.analyze_tier_dir(packs, {"Nam": tmp_path / "nam.csv"}, tmp_path / "report")
    with pytest.raises(ValueError, match="ít nhất"):
        an.analyze_tier_dir(packs, {}, tmp_path / "other")


def test_cli(packs, tmp_path, capsys):
    _fill(packs, tmp_path / "nam.csv", 4, 2)
    code = an.main(["--tier-dir", str(packs), "--rater", f"Nam={tmp_path / 'nam.csv'}", "--out", str(tmp_path / "rep")])
    assert code == 0 and (tmp_path / "rep" / "summary.md").is_file()
    assert "Đã ghi báo cáo" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        an.main(["--tier-dir", str(packs), "--rater", "khong-co-dau-bang", "--out", str(tmp_path / "r2")])
    with pytest.raises(SystemExit):
        an.main(["--tier-dir", str(packs), "--rater", f"Nam={tmp_path / 'nam.csv'}", "--rater", f"Nam={tmp_path / 'nam.csv'}",
                 "--out", str(tmp_path / "r3")])