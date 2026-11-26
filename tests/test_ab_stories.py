import json
from pathlib import Path

import pytest
from PIL import Image

from src.image_generator import ab_experiment as ab
from src.image_generator.image_generator import MockImageGenerator

def _story(n_chars=2):
    return {
        "summary": "tóm tắt",
        "characters": [{"id": f"c{i}", "visual": "v"} for i in range(n_chars)],
        "scenes": [{"index": i, "caption_vi": "x", "image_prompt_en": f"scene {i}",
                    "characters": [f"c{j}" for j in range(n_chars)]} for i in range(1, 5)],
    }


SPECS = [ab.StorySpec("story_013", _story()), ab.StorySpec("story_020_v2", _story(3))]


def test_validate_stories_rejects_bad_input():
    with pytest.raises(ValueError, match="ít nhất một"):
        ab.validate_stories([])
    with pytest.raises(ValueError, match="trùng"):
        ab.validate_stories([SPECS[0], SPECS[0]])
    for bad in ("", "a/b", "../x", " story", "tập 1"):
        with pytest.raises(ValueError, match="story_id không hợp lệ"):
            ab.validate_stories([ab.StorySpec(bad, _story())])


def test_validate_stories_rejects_invalid_storyboard():
    broken = _story(); broken["scenes"] = broken["scenes"][:3]
    with pytest.raises(Exception):
        ab.validate_stories([ab.StorySpec("s1", broken)])


def test_digest_is_stable_and_changes_with_content():
    first = ab.validate_stories([SPECS[0]])[0][2]
    assert first == ab.validate_stories([ab.StorySpec("other", _story())])[0][2]
    changed = _story(); changed["summary"] = "khác"
    assert first != ab.validate_stories([ab.StorySpec("s", changed)])[0][2]


@pytest.fixture
def backend():
    return MockImageGenerator()


def test_generation_layout_manifest_and_order(tmp_path, backend):
    out = tmp_path / "run"
    records = ab.run_ab_generation_stories(backend, stories=SPECS, base_seeds=(100, 200), out_dir=out)
    assert len(records) == 2 * 2 * 2
    assert [(r.story_id, r.base_seed, r.arm) for r in records[:4]] == [
        ("story_013", 100, "A"), ("story_013", 100, "B"), ("story_013", 200, "A"), ("story_013", 200, "B")]
    for r in records:
        assert (out / r.comic_path).is_file()
    assert (out / "story_020_v2" / "B_seed200" / "raw" / "scene_4.png").is_file()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["base_seeds"] == [100, 200]
    assert [s["story_id"] for s in manifest["stories"]] == ["story_013", "story_020_v2"]
    assert all(len(s["storyboard_sha256"]) == 64 for s in manifest["stories"])
    a = next(r for r in manifest["runs"] if (r["story_id"], r["arm"], r["base_seed"]) == ("story_013", "A", 100))
    b = next(r for r in manifest["runs"] if (r["story_id"], r["arm"], r["base_seed"]) == ("story_013", "B", 100))
    assert [s["seed"] for s in a["scenes"]] == [s["seed"] for s in b["scenes"]]
    assert a["scenes"][0]["prompt"] != b["scenes"][0]["prompt"]


def test_generation_refuses_non_empty_dir_and_close_seeds(tmp_path):
    (tmp_path / "x").write_text("1")
    with pytest.raises(FileExistsError):
        ab.run_ab_generation_stories(object(), stories=SPECS, base_seeds=(100,), out_dir=tmp_path)
    with pytest.raises(ValueError, match="chồng lấn"):
        ab.run_ab_generation_stories(object(), stories=SPECS, base_seeds=(100, 102), out_dir=tmp_path / "n")


def test_load_records_roundtrip_keeps_story_id(tmp_path, backend):
    out = tmp_path / "run"
    ab.run_ab_generation_stories(backend, stories=SPECS, base_seeds=(100,), out_dir=out)
    loaded = ab.load_records(out)
    assert {r.story_id for r in loaded} == {"story_013", "story_020_v2"}
    ab._validate_records(loaded)


def _rec(tmp_path, story, arm, seed):
    path = tmp_path / f"{story}_{arm}_{seed}.png"
    Image.new("RGB", (4, 4)).save(path)
    return ab.RunRecord(arm, seed, path, story)


def test_validate_records_pairs_per_story(tmp_path):
    ok = [_rec(tmp_path, s, a, 100) for s in ("s1", "s2") for a in "AB"]
    ab._validate_records(ok)
    # cùng base_seed ở truyện khác nhau không được bù cho nhau
    bad = [_rec(tmp_path, "s1", "A", 100), _rec(tmp_path, "s2", "B", 100)]
    with pytest.raises(ValueError, match="đủ một truyện A và một truyện B"):
        ab._validate_records(bad)
    with pytest.raises(ValueError, match="Trùng"):
        ab._validate_records(ok + [_rec(tmp_path, "s1", "A", 100)])


def test_legacy_record_without_story_id_still_works(tmp_path):
    path = tmp_path / "c.png"; Image.new("RGB", (4, 4)).save(path)
    ab._validate_records([ab.RunRecord("A", 100, path), ab.RunRecord("B", 100, path)])