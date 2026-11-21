"""Dataset validator unit tests use synthetic temporary JSONL fixtures only."""
import json
from pathlib import Path
import pytest
from scripts.dataset_validation import validate_dataset_files, validate_record
from scripts.validate_dataset import main as validate_cli

def valid_record(record_id="sample-alpha", url="https://example.org/sample-alpha"):
    return {
        "id": record_id,
        "title": "Synthetic example",
        "summary": "A fictional summary made only for a unit test.",
        "characters": [{"id": "character-one", "name": "Character One", "description": "Synthetic fixture character."}],
        "key_events": ["A fictional event happens.", "A fictional result follows."],
        "source": "Synthetic test fixture",
        "source_url": url,
        "difficulty": "easy",
        "selection_score": 8,
    }

def write_jsonl(path: Path, records):
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")

def test_json_record_must_be_dictionary():
    assert any("dictionary" in error for error in validate_record(["not", "object"], "fixture"))

@pytest.mark.parametrize("bad_id", [None, 123, [], {}])
def test_id_must_be_non_empty_string(bad_id):
    record = valid_record()
    record["id"] = bad_id
    assert any("id must be a non-empty string" in error for error in validate_record(record, "fixture"))

@pytest.mark.parametrize("bad_character", ["name", None, {}, {"id": "character-one", "name": "Only a name"}])
def test_character_must_have_id_name_description(bad_character):
    record = valid_record()
    record["characters"] = [bad_character]
    assert any("character 1" in error for error in validate_record(record, "fixture"))

@pytest.mark.parametrize("bad_event", ["", "   ", None, 42, {}])
def test_each_key_event_must_be_non_empty_string(bad_event):
    record = valid_record()
    record["key_events"] = ["A valid synthetic event.", bad_event]
    assert any("key_events[2]" in error for error in validate_record(record, "fixture"))

@pytest.mark.parametrize("bad_url", ["", "not-a-url", "ftp://example.org/sample"])
def test_source_url_must_be_http_or_https(bad_url):
    record = valid_record(url=bad_url)
    assert any("source_url" in error for error in validate_record(record, "fixture"))

@pytest.mark.parametrize("bad_difficulty", ["", "unknown", 1, None])
def test_difficulty_must_be_supported_value(bad_difficulty):
    record = valid_record()
    record["difficulty"] = bad_difficulty
    assert any("difficulty" in error for error in validate_record(record, "fixture"))

@pytest.mark.parametrize("bad_score", [True, "8", -1, 9, float("nan")])
def test_selection_score_must_be_number_from_zero_to_eight(bad_score):
    record = valid_record()
    record["selection_score"] = bad_score
    assert any("selection_score" in error for error in validate_record(record, "fixture"))

def test_cross_split_duplicate_id_is_detected(tmp_path):
    dev, test = tmp_path / "dev.jsonl", tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record("same-fixture-id", "https://example.org/dev")])
    write_jsonl(test, [valid_record("same-fixture-id", "https://example.org/test")])
    errors, _ = validate_dataset_files(dev, test, expected_dev=1, expected_test=1)
    assert any("duplicate story id across splits" in error for error in errors)

def test_cross_split_duplicate_url_is_detected(tmp_path):
    dev, test = tmp_path / "dev.jsonl", tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record("fixture-dev", "https://example.org/sample/")])
    write_jsonl(test, [valid_record("fixture-test", "https://EXAMPLE.org/sample")])
    errors, _ = validate_dataset_files(dev, test, expected_dev=1, expected_test=1)
    assert any("duplicate source_url across splits" in error for error in errors)

def test_wrong_record_counts_are_detected(tmp_path):
    dev, test = tmp_path / "dev.jsonl", tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record()])
    write_jsonl(test, [valid_record("sample-beta", "https://example.org/sample-beta")])
    errors, _ = validate_dataset_files(dev, test, expected_dev=20, expected_test=10)
    assert any("expected 20 records" in error for error in errors)
    assert any("expected 10 records" in error for error in errors)

def test_duplicate_character_ids_are_detected():
    record = valid_record()
    record["characters"].append({"id": "character-one", "name": "Another", "description": "Conflicting ID fixture."})
    assert any("duplicate character id" in error for error in validate_record(record, "fixture"))

def test_empty_jsonl_files_can_be_validated_without_fixed_counts(tmp_path):
    dev, test = tmp_path / "empty-dev.jsonl", tmp_path / "empty-test.jsonl"
    dev.write_text("", encoding="utf-8")
    test.write_text("", encoding="utf-8")
    errors, counts = validate_dataset_files(dev, test)
    assert errors == []
    assert counts == {"dev_records": 0, "test_records": 0, "total_records": 0}

def test_missing_jsonl_file_is_reported(tmp_path):
    missing, present = tmp_path / "missing.jsonl", tmp_path / "present.jsonl"
    write_jsonl(present, [valid_record()])
    errors, _ = validate_dataset_files(missing, present, expected_test=1)
    assert any("file does not exist" in error for error in errors)

def test_malformed_url_does_not_crash_validator():
    errors = validate_record(valid_record(url="https://[invalid-host/sample"), "fixture")
    assert any("source_url must be a valid HTTP(S) URL" in error for error in errors)

def test_duplicate_url_inside_same_split_is_detected(tmp_path):
    dev, test = tmp_path / "dev.jsonl", tmp_path / "test.jsonl"
    write_jsonl(dev, [valid_record("fixture-one", "https://example.org/sample"), valid_record("fixture-two", "https://EXAMPLE.org/sample/")])
    write_jsonl(test, [])
    errors, _ = validate_dataset_files(dev, test, expected_dev=2, expected_test=0)
    assert any("Dev: duplicate source_url" in error for error in errors)

def test_cli_uses_only_explicit_synthetic_fixture_paths(tmp_path, capsys):
    dev, test = tmp_path / "synthetic-dev.jsonl", tmp_path / "synthetic-test.jsonl"
    write_jsonl(dev, [valid_record()])
    write_jsonl(test, [valid_record("sample-beta", "https://example.org/sample-beta")])
    exit_code = validate_cli(["--dev", str(dev), "--test", str(test), "--expected-dev", "1", "--expected-test", "1"])
    assert exit_code == 0
    assert "Dataset validation PASSED." in capsys.readouterr().out

def test_cli_returns_nonzero_for_invalid_synthetic_fixture(tmp_path, capsys):
    dev, test = tmp_path / "synthetic-dev.jsonl", tmp_path / "synthetic-test.jsonl"
    write_jsonl(dev, [valid_record()])
    test.write_text("{not valid json}\n", encoding="utf-8")
    exit_code = validate_cli(["--dev", str(dev), "--test", str(test)])
    assert exit_code == 1
    assert "Dataset validation FAILED:" in capsys.readouterr().out

def test_optional_utility_modules_import_without_running_jobs():
    import importlib
    for module in ("data.evaluate_stories", "data.inspect_dataset", "data.prepare_ai_review", "data.save_ai_review"):
        importlib.import_module(module)
