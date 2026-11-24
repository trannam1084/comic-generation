import json
from pathlib import Path

import pytest

from src.image_generator.image_generator import MockImageGenerator
from src.image_generator.story_runs import run_stories, run_story

SAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples" / "storyboard.json").read_text(encoding="utf-8")
)


class FailOnCall(MockImageGenerator):
    """Mock chỉ để kiểm tra đường lỗi: raise ở lần gọi thứ N."""

    def __init__(self, fail_on: int) -> None:
        super().__init__()
        self.calls = 0
        self.fail_on = fail_on

    def generate(self, prompt, *args, **kwargs):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("boom")
        return super().generate(prompt, *args, **kwargs)


def test_success_writes_artifacts_and_metadata(tmp_path):
    record = run_story("s1", SAMPLE, image_backend=MockImageGenerator(), out_root=tmp_path, base_seed=42)
    assert record["status"] == "success"
    story_dir = tmp_path / "s1"
    assert sorted(p.name for p in (story_dir / "raw").iterdir()) == [f"scene_{i}.png" for i in range(1, 5)]
    assert (story_dir / record["comic_path"]).is_file()
    assert (story_dir / "storyboard.json").is_file() and (story_dir / "SHA256SUMS").is_file()
    saved = json.loads((story_dir / "metadata.json").read_text(encoding="utf-8"))
    assert [s["scene_index"] for s in saved["scenes"]] == [1, 2, 3, 4]
    assert len({s["seed"] for s in saved["scenes"]}) == 4
    assert saved["quality_notes"] is None


def test_same_base_seed_gives_same_seeds_across_stories(tmp_path):
    a = run_story("a", SAMPLE, image_backend=MockImageGenerator(), out_root=tmp_path, base_seed=42)
    b = run_story("b", SAMPLE, image_backend=MockImageGenerator(), out_root=tmp_path, base_seed=42)
    assert [s["seed"] for s in a["scenes"]] == [s["seed"] for s in b["scenes"]]


def test_backend_failure_is_recorded_without_fake_images(tmp_path):
    record = run_story("bad", SAMPLE, image_backend=FailOnCall(3), out_root=tmp_path, base_seed=42)
    assert record["status"] == "error" and record["stage"] == "pipeline"
    assert record["error_type"] == "RuntimeError" and "boom" in record["traceback"]
    assert "comic_path" not in record and "scenes" not in record
    assert list((tmp_path / "bad" / "raw").iterdir()) == []
    assert not (tmp_path / "bad" / "comic").exists() or not any((tmp_path / "bad" / "comic").iterdir())


def test_invalid_storyboard_never_reaches_backend(tmp_path):
    broken = dict(SAMPLE, scenes=SAMPLE["scenes"][:3])
    backend = FailOnCall(fail_on=0)
    record = run_story("broken", broken, image_backend=backend, out_root=tmp_path, base_seed=42)
    assert record["status"] == "error" and record["stage"] == "storyboard"
    assert backend.calls == 0


def test_run_stories_continues_after_failure(tmp_path):
    backend = FailOnCall(fail_on=1)
    results = run_stories({"first": SAMPLE, "second": SAMPLE}, out_root=tmp_path, image_backend=backend, base_seed=42)
    assert [r["status"] for r in results] == ["error", "success"]
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert [row["story_id"] for row in summary] == ["first", "second"]


def test_existing_directory_is_never_overwritten(tmp_path):
    (tmp_path / "s1").mkdir()
    with pytest.raises(FileExistsError):
        run_story("s1", SAMPLE, image_backend=MockImageGenerator(), out_root=tmp_path, base_seed=42)


@pytest.mark.parametrize("bad_id", ["", "a/b", "..", "a b"])
def test_story_id_is_restricted(tmp_path, bad_id):
    with pytest.raises(ValueError):
        run_story(bad_id, SAMPLE, image_backend=MockImageGenerator(), out_root=tmp_path, base_seed=42)