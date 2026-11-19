"""Shared validation logic for the Comic Generation story dataset."""

from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
REQUIRED_FIELDS = {
    "id",
    "title",
    "summary",
    "characters",
    "key_events",
    "source",
    "source_url",
    "difficulty",
    "selection_score",
}


def normalize_url(value: str) -> str:
    """Normalize a URL for duplicate comparison."""
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return f"{scheme}://{netloc}{path}"


def validate_record(record, location: str) -> list[str]:
    errors: list[str] = []

    if not isinstance(record, dict):
        return [f"{location}: JSON record must be an object/dictionary"]

    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        errors.append(f"{location}: missing fields: {', '.join(sorted(missing))}")

    for field in ("id", "title", "summary", "source", "source_url"):
        value = record.get(field)
        if not isinstance(value, str):
            errors.append(f"{location}: {field} must be a string")
        elif not value.strip():
            errors.append(f"{location}: {field} must not be empty")

    story_id = record.get("id")
    if isinstance(story_id, str) and story_id.strip():
        pass
    elif "id" in record:
        # Explicitly catches lists, dicts, numbers, booleans and null.
        errors.append(f"{location}: id must be a non-empty string")

    source_url = record.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        parsed = urlsplit(source_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{location}: source_url must be a valid HTTP(S) URL")

    characters = record.get("characters")
    if not isinstance(characters, list):
        errors.append(f"{location}: characters must be a list")
    else:
        character_ids: set[str] = set()
        for index, character in enumerate(characters, start=1):
            where = f"{location}: character {index}"
            if not isinstance(character, dict):
                errors.append(f"{where} must be an object/dictionary")
                continue

            for field in ("id", "name", "description"):
                value = character.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{where}: {field} must be a non-empty string")

            char_id = character.get("id")
            if isinstance(char_id, str) and char_id.strip():
                if char_id in character_ids:
                    errors.append(f"{where}: duplicate character id {char_id}")
                character_ids.add(char_id)

    key_events = record.get("key_events")
    if not isinstance(key_events, list):
        errors.append(f"{location}: key_events must be a list")
    else:
        if len(key_events) < 2:
            errors.append(f"{location}: key_events must contain at least 2 events")
        for index, event in enumerate(key_events, start=1):
            if not isinstance(event, str) or not event.strip():
                errors.append(
                    f"{location}: key_events[{index}] must be a non-empty string"
                )

    difficulty = record.get("difficulty")
    if not isinstance(difficulty, str) or difficulty not in ALLOWED_DIFFICULTIES:
        errors.append(
            f"{location}: difficulty must be one of "
            f"{', '.join(sorted(ALLOWED_DIFFICULTIES))}"
        )

    score = record.get("selection_score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 8
    ):
        errors.append(f"{location}: selection_score must be a number from 0 to 8")

    return errors


def load_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    errors: list[str] = []

    if not path.is_file():
        return records, [f"{path}: file does not exist"]

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            for line_number, line in enumerate(file, start=1):
                location = f"{path.name}, line {line_number}"
                if not line.strip():
                    errors.append(f"{location}: empty line")
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{location}: invalid JSON: {exc}")
                    continue

                errors.extend(validate_record(record, location))
                if isinstance(record, dict):
                    records.append(record)
    except OSError as exc:
        return records, [f"{path}: cannot read file: {exc}"]

    return records, errors


def validate_dataset_files(
    dev_path: Path,
    test_path: Path,
    expected_dev: int = 20,
    expected_test: int = 10,
) -> tuple[list[str], dict[str, int]]:
    dev_records, dev_errors = load_jsonl(Path(dev_path))
    test_records, test_errors = load_jsonl(Path(test_path))
    errors = [f"Dev: {error}" for error in dev_errors]
    errors.extend(f"Test: {error}" for error in test_errors)

    if len(dev_records) != expected_dev:
        errors.append(
            f"Dev: expected {expected_dev} records, found {len(dev_records)}"
        )
    if len(test_records) != expected_test:
        errors.append(
            f"Test: expected {expected_test} records, found {len(test_records)}"
        )

    def check_unique(records: list[dict], label: str) -> set[str]:
        seen: set[str] = set()
        for index, record in enumerate(records, start=1):
            value = record.get("id")
            if isinstance(value, str) and value.strip():
                if value in seen:
                    errors.append(f"{label}: duplicate story id {value}")
                seen.add(value)
        return seen

    dev_ids = check_unique(dev_records, "Dev")
    test_ids = check_unique(test_records, "Test")
    for duplicate in sorted(dev_ids & test_ids):
        errors.append(f"Dev/Test: duplicate story id across splits: {duplicate}")

    def collect_urls(records: list[dict]) -> set[str]:
        values: set[str] = set()
        for record in records:
            value = record.get("source_url")
            if isinstance(value, str) and value.strip():
                try:
                    values.add(normalize_url(value))
                except ValueError:
                    # Invalid ports/URLs are already reported by validate_record.
                    continue
        return values

    dev_urls = collect_urls(dev_records)
    test_urls = collect_urls(test_records)
    for duplicate in sorted(dev_urls & test_urls):
        errors.append(f"Dev/Test: duplicate source_url across splits: {duplicate}")

    counts = {
        "dev_records": len(dev_records),
        "test_records": len(test_records),
        "total_records": len(dev_records) + len(test_records),
    }
    return errors, counts
