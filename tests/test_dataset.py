"""Unit tests for the shared dataset validation logic."""

import json
from pathlib import Path

import pytest

from scripts.dataset_validation import validate_dataset_files, validate_record

ROOT_DIR = Path(__file__).resolve().parents[1]
DEV_FILE = ROOT_DIR / "data" / "dev_cases.jsonl"
TEST_FILE = ROOT_DIR / "data" / "test_cases.jsonl"


def valid_record(story_id="story_001", url="https://example.org/story"):
    return {
        "id": story_id,
        "title": "Tên truyện",
        "summary": "Tóm tắt truyện.",
        "characters": [
            {"id": "char_1", "name": "Nhân vật", "description": "Mô tả nhân vật."}
        ],
        "key_events": ["Sự kiện thứ nhất.", "Sự kiện thứ hai."],
        "source": "Nguồn truyện",
        "source_url": url,
        "difficulty": "easy",
        "selection_score": 8,
    }


def write_jsonl(path: Path, records):
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_repository_dataset_passes():
    errors, counts = validate_dataset_files(DEV_FILE, TEST_FILE)
    assert errors == []
    assert counts == {"dev_records": 20, "test_records": 10, "total_records": 30}


def test_json_record_must_be_dictionary():
    assert any("dictionary" in e for e in validate_record(["not", "object"], "test"))


@pytest.mark.parametrize("bad_id", [None, 123, [], {}])
def test_id_must_be_non_empty_string(bad_id):
    record = valid_record()
    record["id"] = bad_id
    assert any("id must be a non-empty string" in e for e in validate_record(record, "test"))


@pytest.mark.parametrize("bad_character", ["name", None, {}, {"id": "x", "name": "A"}])
def test_character_must_have_id_name_description(bad_character):
    record = valid_record()
    record["characters"] = [bad_character]
    assert any("character 1" in e for e in validate_record(record, "test"))


@pytest.mark.parametrize("bad_event", ["", "   ", None, 42, {}])
def test_each_key_event_must_be_non_empty_string(bad_event):
    record = valid_record()
    record["key_events"] = ["Sự kiện hợp lệ", bad_event]
    assert any("key_events[2]" in e for e in validate_record(record, "test"))


@pytest.mark.parametrize("bad_url", ["", "not-a-url", "ftp://example.org/story"])
def test_source_url_must_be_http_or_https(bad_url):
    record = valid_record(url=bad_url)
    assert any("source_url" in e for e in validate_record(record, "test"))


@pytest.mark.parametrize("bad_difficulty", ["", "unknown", 1, None])
def test_difficulty_must_be_supported_value(bad_difficulty):
    record = valid_record()
    record["difficulty"] = bad_difficulty
    assert any("difficulty" in e for e in validate_record(record, "test"))


@pytest.mark.parametrize("bad_score", [True, "8", -1, 9, float("nan")])
def test_selection_score_must_be_number_from_zero_to_eight(bad_score):
    record = valid_record()
    record["selection_score"] = bad_score
    assert any("selection_score" in e for e in validate_record(record, "test"))


def test_cross_split_duplicate_id_is_detected(tmp_path):
    dev = tmp_path / "dev.jsonl"
    test = tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record("same_id", "https://example.org/dev")])
    write_jsonl(test, [valid_record("same_id", "https://example.org/test")])
    errors, _ = validate_dataset_files(dev, test, expected_dev=1, expected_test=1)
    assert any("duplicate story id across splits" in e for e in errors)


def test_cross_split_duplicate_url_is_detected(tmp_path):
    dev = tmp_path / "dev.jsonl"
    test = tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record("story_a", "https://example.org/story/")])
    write_jsonl(test, [valid_record("story_b", "https://EXAMPLE.org/story")])
    errors, _ = validate_dataset_files(dev, test, expected_dev=1, expected_test=1)
    assert any("duplicate source_url across splits" in e for e in errors)


def test_wrong_record_counts_are_detected(tmp_path):
    dev = tmp_path / "dev.jsonl"
    test = tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record()])
    write_jsonl(test, [valid_record("story_002", "https://example.org/2")])
    errors, _ = validate_dataset_files(dev, test, expected_dev=20, expected_test=10)
    assert any("expected 20 records" in e for e in errors)
    assert any("expected 10 records" in e for e in errors)


def test_duplicate_character_ids_are_detected():
    record = valid_record()
    record["characters"].append(
        {"id": "char_1", "name": "Nhân vật khác", "description": "Mô tả."}
    )
    assert any("duplicate character id" in e for e in validate_record(record, "test"))
