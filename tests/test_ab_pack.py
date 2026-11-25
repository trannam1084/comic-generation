import csv

import pytest

from src.image_generator import ab_experiment as ab
from src.image_generator import ab_pack as pack
from src.image_generator.ab_rubric import read_rating_sheet
from src.image_generator.image_generator import MockImageGenerator


def _story(chars, scene_chars):
    return {
        "summary": "s",
        "characters": [{"id": c, "visual": f"look of {c}"} for c in chars],
        "scenes": [{"index": i, "caption_vi": "x", "image_prompt_en": f"p{i}", "characters": sc}
                   for i, sc in enumerate(scene_chars, 1)],
    }


STORIES = {
    "story_013": _story(["a", "b"], [["a", "b"]] * 4),
    "story_020_v2": _story(["BÀ CON", "DU KHÁCH", "x"], [["BÀ CON"], ["DU KHÁCH", "BÀ CON"], ["DU KHÁCH"], []]),
    "story_027": _story(["solo"], [["solo"], [], [], []]),   # không nhân vật nào đủ điều kiện chấm
}
SPECS = [ab.StorySpec(k, v) for k, v in STORIES.items()]
SEEDS = (100, 200)


@pytest.fixture
def run(tmp_path):
    out = tmp_path / "run"
    ab.run_ab_generation_stories(MockImageGenerator(), stories=SPECS, base_seeds=SEEDS, out_dir=out)
    return ab.load_records(out)


def test_split_tiers(run):
    tiers = pack.split_tiers(run, SEEDS)
    assert set(tiers) == {"core", "extra"}
    assert {r.base_seed for r in tiers["core"]} == {100} and {r.base_seed for r in tiers["extra"]} == {200}
    assert set(pack.split_tiers([r for r in run if r.base_seed == 100], (100,))) == {"core"}
    with pytest.raises(ValueError, match="không nằm trong"):
        pack.split_tiers(run, (100,))
    with pytest.raises(ValueError, match="ít nhất"):
        pack.split_tiers(run, ())


def test_build_packs_layout_and_ids(run, tmp_path):
    out = tmp_path / "packs"
    keys = pack.build_blind_packs(run, STORIES, SEEDS, out, shuffle_seed=7)
    assert set(keys) == {"core", "extra"}
    assert len(keys["core"]) == len(keys["extra"]) == 6
    assert [r["comic_id"] for r in keys["core"]] == [f"C0{i}" for i in range(1, 7)]
    assert [r["comic_id"] for r in keys["extra"]] == [f"E0{i}" for i in range(1, 7)]
    for tier in ("core", "extra"):
        base = out / tier / "for_raters"
        assert (base / "rating_pack.pdf").is_file() and (base / "rating_sheet.csv").is_file()
        assert len(list((base / "comics").glob("*.png"))) == 6
        assert (out / tier / "private" / "KEY.csv").is_file()
    # mỗi truyện có đủ một A và một B trong mỗi tầng
    for tier in keys:
        for story in STORIES:
            arms = sorted(r["arm"] for r in keys[tier] if r["story_id"] == story)
            assert arms == ["A", "B"]


def test_rater_folder_does_not_leak_arm_story_or_seed(run, tmp_path):
    out = tmp_path / "packs"
    pack.build_blind_packs(run, STORIES, SEEDS, out, shuffle_seed=7)
    for tier in ("core", "extra"):
        for path in (out / tier / "for_raters").rglob("*"):
            text = path.name
            if path.suffix in (".md", ".csv"):
                text += path.read_text(encoding="utf-8-sig")
            for forbidden in ("story_013", "story_020", "story_027", "seed", "_A", "_B"):
                assert forbidden not in text, (path, forbidden)


def test_guide_lists_characters_of_each_comic_and_empty_case(run, tmp_path):
    out = tmp_path / "packs"
    keys = pack.build_blind_packs(run, STORIES, SEEDS, out, shuffle_seed=7)
    guide = (out / "core" / "for_raters" / "HUONG_DAN_CHAM.md").read_text(encoding="utf-8")
    solo = next(r["comic_id"] for r in keys["core"] if r["story_id"] == "story_027")
    section = guide.split(f"### {solo}")[1].split("###")[0]
    assert "Không có nhân vật nào cần chấm" in section
    ba = next(r["comic_id"] for r in keys["core"] if r["story_id"] == "story_020_v2")
    section = guide.split(f"### {ba}")[1].split("###")[0]
    assert "BÀ CON" in section and "DU KHÁCH" in section and "look of BÀ CON" in section
    assert "char_no 3" not in section   # nhân vật "x" không xuất hiện trong cảnh nào nên không được chấm


def test_expected_rows_and_filled_sheet_round_trip(run, tmp_path):
    out = tmp_path / "packs"
    pack.build_blind_packs(run, STORIES, SEEDS, out, shuffle_seed=7)
    expected = pack.read_expected_rows(out / "core")
    # story_013: 1+2, story_020_v2: 1+2, story_027: 1 (mỗi truyện 2 nhánh)
    assert len(expected) == 2 * (3 + 3 + 1)
    sheet = out / "core" / "for_raters" / "rating_sheet.csv"
    rows = list(csv.reader(sheet.open(encoding="utf-8-sig")))
    filled = [rows[0]]
    for r in rows[1:]:
        r = list(r)
        if r[1] == "0":
            r[4], r[5] = "0", "0"
        else:
            r[3] = "3"
        filled.append(r)
    mine = tmp_path / "rater.csv"
    with open(mine, "w", encoding="utf-8-sig", newline="") as h:
        csv.writer(h).writerows(filled)
    table = read_rating_sheet(mine, expected_rows=expected)
    assert len(table) == len(expected)


def test_deterministic_and_seed_changes_order(run, tmp_path):
    a = pack.build_blind_packs(run, STORIES, SEEDS, tmp_path / "a", shuffle_seed=7)
    b = pack.build_blind_packs(run, STORIES, SEEDS, tmp_path / "b", shuffle_seed=7)
    c = pack.build_blind_packs(run, STORIES, SEEDS, tmp_path / "c", shuffle_seed=8)
    seq = lambda keys: [(r["story_id"], r["arm"]) for r in keys["core"]]
    assert seq(a) == seq(b)
    assert seq(a) != seq(c)


def test_errors(run, tmp_path):
    (tmp_path / "busy").mkdir(); (tmp_path / "busy" / "x").write_text("1")
    with pytest.raises(FileExistsError):
        pack.build_blind_packs(run, STORIES, SEEDS, tmp_path / "busy", shuffle_seed=7)
    with pytest.raises(ValueError, match="Thiếu storyboard"):
        pack.build_blind_packs(run, {"story_013": STORIES["story_013"]}, SEEDS, tmp_path / "m", shuffle_seed=7)


def test_single_seed_makes_only_core(run, tmp_path):
    only = [r for r in run if r.base_seed == 100]
    keys = pack.build_blind_packs(only, STORIES, (100,), tmp_path / "one", shuffle_seed=7)
    assert set(keys) == {"core"} and not (tmp_path / "one" / "extra").exists()