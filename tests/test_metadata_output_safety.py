"""Regression tests that optional metadata scripts never clobber existing data by default."""
from pathlib import Path

import pytest

from data.output_safety import atomic_write_text, ensure_outputs_available


def test_existing_file_is_protected_by_default(tmp_path):
    target = tmp_path / "dataset_selection.csv"
    target.write_text("preserve this metadata", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        atomic_write_text(target, "new data", encoding="utf-8")

    assert target.read_text(encoding="utf-8") == "preserve this metadata"


def test_explicit_overwrite_replaces_file_atomically(tmp_path):
    target = tmp_path / "ai_evaluated_stories.csv"
    target.write_text("old metadata", encoding="utf-8")

    atomic_write_text(target, "new evaluation", encoding="utf-8", overwrite=True)

    assert target.read_text(encoding="utf-8") == "new evaluation"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_multi_output_preflight_fails_before_any_output_is_written(tmp_path):
    first = tmp_path / "new_full.csv"
    second = tmp_path / "existing_selected.csv"
    second.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        ensure_outputs_available([first, second], overwrite=False)

    assert not first.exists()
    assert second.read_text(encoding="utf-8") == "keep"


def test_new_file_can_be_created_without_overwrite_flag(tmp_path):
    target = tmp_path / "new_batch.txt"
    atomic_write_text(target, "prompt batch", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "prompt batch"


def test_helper_does_not_touch_an_existing_file_during_preflight(tmp_path):
    target = tmp_path / "curated.csv"
    target.write_text("curated rows", encoding="utf-8")

    with pytest.raises(FileExistsError):
        ensure_outputs_available([target], overwrite=False)

    assert target.read_text(encoding="utf-8") == "curated rows"


def test_evaluate_stories_main_refuses_existing_output_before_api_setup(tmp_path, monkeypatch):
    import data.evaluate_stories as module

    source = tmp_path / "candidate.csv"
    source.write_text("id,title,content\n1,Story,Text\n", encoding="utf-8")
    target = tmp_path / "ai_evaluated_stories.csv"
    target.write_text("curated metadata", encoding="utf-8")
    monkeypatch.setattr(module, "INPUT_PATH", source)
    monkeypatch.setattr(module, "OUTPUT_PATH", target)
    monkeypatch.setattr("sys.argv", ["evaluate_stories.py"])

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        module.main()

    assert target.read_text(encoding="utf-8") == "curated metadata"


def test_save_ai_review_main_refuses_existing_selected_output_before_reading_results(tmp_path, monkeypatch):
    import data.save_ai_review as module

    result_dir = tmp_path / "missing_results"
    full_output = tmp_path / "new_full.csv"
    selected_output = tmp_path / "selected_stories.csv"
    selected_output.write_text("human-curated selection", encoding="utf-8")
    monkeypatch.setattr(module, "RESULT_DIR", result_dir)
    monkeypatch.setattr(module, "OUTPUT_FILE", full_output)
    monkeypatch.setattr(module, "SELECTED_FILE", selected_output)
    monkeypatch.setattr("sys.argv", ["save_ai_review.py"])

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        module.main()

    assert not full_output.exists()
    assert selected_output.read_text(encoding="utf-8") == "human-curated selection"


def test_prepare_ai_review_preflights_all_batches_before_any_write(tmp_path, monkeypatch):
    import data.prepare_ai_review as module

    pd = pytest.importorskip("pandas")
    source = tmp_path / "candidate.csv"
    pd.DataFrame([
        {"id": str(i), "title": f"Story {i}", "url": f"https://example.org/{i}", "content": f"Text {i}"}
        for i in range(6)
    ]).to_csv(source, index=False)
    output_dir = tmp_path / "batches"
    output_dir.mkdir()
    existing = output_dir / "batch_002.txt"
    existing.write_text("keep this old batch", encoding="utf-8")
    monkeypatch.setattr(module, "INPUT_FILE", source)
    monkeypatch.setattr(module, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr("sys.argv", ["prepare_ai_review.py"])

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        module.main()

    assert not (output_dir / "batch_001.txt").exists()
    assert existing.read_text(encoding="utf-8") == "keep this old batch"



def _prepare_save_ai_review_run(tmp_path, monkeypatch, rows):
    import json
    import data.save_ai_review as module

    result_dir = tmp_path / "ai_review_results"
    result_dir.mkdir()
    (result_dir / "batch_001.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )
    full_output = tmp_path / "full_output.csv"
    selected_output = tmp_path / "selected_output.csv"
    monkeypatch.setattr(module, "RESULT_DIR", result_dir)
    monkeypatch.setattr(module, "OUTPUT_FILE", full_output)
    monkeypatch.setattr(module, "SELECTED_FILE", selected_output)
    monkeypatch.setattr("sys.argv", ["save_ai_review.py"])
    return module, full_output, selected_output


def _valid_review_row():
    return {
        "id": "story_001",
        "title": "Example story",
        "characters_clear": 2,
        "events_clear": 1,
        "scene_suitable": 2,
        "ending_clear": 1,
        "score": 6,
        "selected_candidate": True,
        "difficulty": "easy",
        "reason": "test fixture",
    }


def test_save_ai_review_rejects_fractional_component_scores(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    row = _valid_review_row()
    row["characters_clear"] = 1.5
    module, full_output, selected_output = _prepare_save_ai_review_run(
        tmp_path, monkeypatch, [row]
    )

    with pytest.raises(SystemExit, match="fractional values are not rounded or truncated"):
        module.main()

    assert not full_output.exists()
    assert not selected_output.exists()


def test_save_ai_review_rejects_identical_duplicate_ids(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    row = _valid_review_row()
    module, full_output, selected_output = _prepare_save_ai_review_run(
        tmp_path, monkeypatch, [row, row.copy()]
    )

    with pytest.raises(SystemExit, match="identical duplicate rows: story_001"):
        module.main()

    assert not full_output.exists()
    assert not selected_output.exists()


def test_save_ai_review_rejects_conflicting_duplicate_ids(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    first = _valid_review_row()
    second = _valid_review_row()
    second["reason"] = "different evaluation for the same ID"
    module, full_output, selected_output = _prepare_save_ai_review_run(
        tmp_path, monkeypatch, [first, second]
    )

    with pytest.raises(SystemExit, match="conflicting rows: story_001"):
        module.main()

    assert not full_output.exists()
    assert not selected_output.exists()


def test_evaluate_stories_uses_dedicated_three_case_smoke_test_output():
    import data.evaluate_stories as module

    assert module.TEST_LIMIT == 3
    assert module.OUTPUT_PATH.name == "ai_evaluated_stories_test3.csv"
    assert module.OUTPUT_PATH.name != "ai_evaluated_stories.csv"
